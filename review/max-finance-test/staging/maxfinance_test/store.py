"""Хранилище тестового режима.

Отдельная SQLite-база, отдельная папка фотографий, отдельная база примеров.
Рабочая база и рабочая Google-таблица не используются. Проверка изоляции
выполняется при открытии хранилища.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import zipfile
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any

from .aliases import DEFAULT_ALIASES, REQUIRED_STAFF, AliasBook, normalize_alias
from .model import Report, classify_errors

TEST_DB_NAME = "test_finance.db"
SCHEMA_VERSION = 1


class IsolationError(RuntimeError):
    """Попытка тестового режима обратиться к рабочим данным."""


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ModeStore:
    def __init__(self, root: Path | str, prod_db: Path | str | None = None,
                 prod_sheet_id: str | None = None, test_sheet_id: str | None = None):
        self.root = Path(root).resolve()
        self.db_path = self.root / TEST_DB_NAME
        self.photos_dir = self.root / "confirmed"
        self.input_dir = self.root / "input"
        self.prod_db = Path(prod_db).resolve() if prod_db else None
        self.prod_sheet_id = prod_sheet_id
        self.test_sheet_id = test_sheet_id
        if self.prod_db and self.db_path == self.prod_db:
            raise IsolationError("Тестовая база не может совпадать с рабочей")
        if self.prod_db and self.prod_db.parent == self.root:
            raise IsolationError("Тестовое хранилище не может лежать в папке рабочего проекта")
        if self.prod_db and self.db_path.exists() and self.prod_db.exists():
            try:
                if os.path.samefile(self.db_path, self.prod_db):
                    raise IsolationError("Тестовая база является ссылкой на рабочую")
            except OSError:
                pass
        if prod_sheet_id and test_sheet_id and prod_sheet_id == test_sheet_id:
            raise IsolationError("Тестовая Google-таблица не может совпадать с рабочей")
        self.root.mkdir(parents=True, exist_ok=True)
        self.photos_dir.mkdir(parents=True, exist_ok=True)
        self.input_dir.mkdir(parents=True, exist_ok=True)

    # ---------- соединение и схема ----------

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with closing(self.connect()) as db, db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS staff(
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    active INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS staff_alias(
                    alias TEXT PRIMARY KEY COLLATE NOCASE,
                    staff_id INTEGER NOT NULL REFERENCES staff(id));
                CREATE TABLE IF NOT EXISTS seed_conflicts(
                    alias TEXT PRIMARY KEY COLLATE NOCASE, wanted TEXT NOT NULL,
                    existing TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS drafts(
                    user_id INTEGER PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS line_settings(
                    photo_sha TEXT PRIMARY KEY, left_edge REAL NOT NULL, right_edge REAL NOT NULL,
                    updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS examples(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    photo_sha TEXT NOT NULL, photo_path TEXT NOT NULL, source_file TEXT,
                    report_date TEXT NOT NULL, original_json TEXT NOT NULL,
                    confirmed_json TEXT NOT NULL, error_types TEXT NOT NULL,
                    engine_version TEXT NOT NULL, split TEXT NOT NULL DEFAULT 'train',
                    confirmed_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS audit(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
                    action TEXT NOT NULL, detail TEXT, created_at TEXT NOT NULL);
                """
            )
            db.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
            db.execute("INSERT OR IGNORE INTO meta VALUES ('engine_version', 'test-ocr-1.0')")
            db.execute("INSERT OR IGNORE INTO meta VALUES ('created_at', ?)", (_now(),))
            db.execute("INSERT OR IGNORE INTO settings VALUES ('mode', 'WORK')")
            try:
                db.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_examples_photo ON examples(photo_sha)")
            except sqlite3.IntegrityError:
                pass
            try:
                db.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_examples_photo_date ON examples(photo_sha, report_date)")
            except sqlite3.IntegrityError:
                pass
        seed_done = self.setting("seed_done")
        if self.prod_db and self.prod_db.is_file() and seed_done != "1":
            self.seed_from_production(self.prod_db)
            self.set_setting("seed_done", "1")
        elif not self.prod_db and self.setting("defaults_initialized") != "1":
            self._ensure_defaults()

    # ---------- сотрудники и словарь ----------

    def staff(self, active_only: bool = True) -> list[dict[str, Any]]:
        with closing(self.connect()) as db:
            query = "SELECT id,name,active FROM staff"
            if active_only:
                query += " WHERE active=1"
            query += " ORDER BY id"
            return [dict(row) for row in db.execute(query)]

    def aliases(self) -> dict[str, int]:
        with closing(self.connect()) as db:
            return {row["alias"]: row["staff_id"] for row in db.execute("SELECT alias,staff_id FROM staff_alias")}

    def alias_book(self, active_only: bool = True) -> AliasBook:
        return AliasBook(self.staff(active_only=active_only), self.aliases())

    def seed_from_production(self, prod_db: Path) -> None:
        """Скопировать действующих сотрудников и их историю обозначений.

        Идентификаторы TEST не переиспользуются: сотрудник сопоставляется по
        имени, а не по числовому id. При конфликте обозначение остаётся за
        прежним сотрудником TEST, конфликт записывается для владельца.
        """
        prod_db = Path(prod_db).resolve()
        if prod_db == self.db_path:
            raise IsolationError("Нельзя читать рабочую базу как тестовую")
        with closing(sqlite3.connect(f"file:{prod_db}?mode=ro", uri=True)) as source:
            source.row_factory = sqlite3.Row
            staff = [dict(row) for row in source.execute("SELECT id,name,active FROM staff_v3 ORDER BY id")]
            aliases = [dict(row) for row in source.execute("SELECT alias,staff_id FROM staff_alias_v3")]
        if not staff:
            self._ensure_defaults()
            return
        with closing(self.connect()) as db, db:
            by_name = {row["name"]: row["id"] for row in db.execute("SELECT id,name FROM staff")}
            mapping: dict[int, int] = {}
            for person in staff:
                name = str(person["name"]).strip().upper()
                if name in by_name:
                    mapping[int(person["id"])] = int(by_name[name])
                    continue
                cursor = db.execute(
                    "INSERT INTO staff(name,active) VALUES (?,?)",
                    (name, int(person.get("active", 1))),
                )
                mapping[int(person["id"])] = int(cursor.lastrowid)
                by_name[name] = int(cursor.lastrowid)
            existing = {row["alias"]: row["staff_id"] for row in db.execute("SELECT alias,staff_id FROM staff_alias")}
            for alias in aliases:
                target = mapping.get(int(alias["staff_id"]))
                if target is None:
                    continue
                key = str(alias["alias"])
                current = existing.get(key)
                if current is None:
                    db.execute("INSERT OR IGNORE INTO staff_alias(alias,staff_id) VALUES (?,?)", (key, target))
                    existing[key] = target
                elif int(current) != int(target):
                    db.execute(
                        "INSERT OR IGNORE INTO seed_conflicts(alias,wanted,existing,created_at) VALUES (?,?,?,?)",
                        (key, str(target), str(current), _now()),
                    )
        self._ensure_defaults()

    def _ensure_defaults(self) -> None:
        with closing(self.connect()) as db, db:
            by_name = {row["name"]: row["id"] for row in db.execute("SELECT id,name FROM staff")}
            for name in REQUIRED_STAFF:
                if name not in by_name:
                    cursor = db.execute("INSERT INTO staff(name,active) VALUES (?,1)", (name,))
                    by_name[name] = cursor.lastrowid
            existing = {row["alias"]: row["staff_id"] for row in db.execute("SELECT alias,staff_id FROM staff_alias")}
            for alias, name in DEFAULT_ALIASES.items():
                staff_id = by_name.get(name)
                if staff_id is None:
                    continue
                current = existing.get(alias)
                if current is None:
                    db.execute("INSERT OR IGNORE INTO staff_alias(alias,staff_id) VALUES (?,?)", (alias, staff_id))
                    existing[alias] = staff_id
                elif current != staff_id:
                    db.execute(
                        "INSERT OR IGNORE INTO seed_conflicts(alias,wanted,existing,created_at) VALUES (?,?,?,?)",
                        (alias, name, str(current), _now()),
                    )
            # Полное имя — тоже обозначение, если оно ещё не занято.
            for name, staff_id in by_name.items():
                db.execute("INSERT OR IGNORE INTO staff_alias(alias,staff_id) VALUES (?,?)", (name, staff_id))
            db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES ('defaults_initialized','1')")

    def add_employee(self, name: str) -> int:
        # Новый id считается по ВСЕМ сотрудникам, включая деактивированных:
        # иначе INSERT упирается в UNIQUE(id) после удаления последнего.
        book = self.alias_book(active_only=False)
        new_id = book.add_employee(name)
        with closing(self.connect()) as db, db:
            db.execute("INSERT INTO staff(id,name,active) VALUES (?,?,1)", (new_id, book.staff[new_id]))
            db.execute("INSERT OR IGNORE INTO staff_alias(alias,staff_id) VALUES (?,?)", (book.staff[new_id], new_id))
        return new_id

    def rename_employee(self, employee_id: int, name: str) -> None:
        book = self.alias_book()
        key = " ".join(str(name).strip().upper().split())
        if not key or len(key) > 40:
            raise ValueError("Некорректное имя")
        if book.employee_id_by_name(key) not in (None, int(employee_id)):
            raise ValueError("Имя принадлежит другому сотруднику")
        with closing(self.connect()) as db, db:
            db.execute("UPDATE staff SET name=? WHERE id=? AND active=1", (key, int(employee_id)))
            db.execute("INSERT OR IGNORE INTO staff_alias(alias,staff_id) VALUES (?,?)", (key, int(employee_id)))

    def remove_employee(self, employee_id: int) -> None:
        with closing(self.connect()) as db, db:
            cursor = db.execute("UPDATE staff SET active=0 WHERE id=? AND active=1", (int(employee_id),))
            if not cursor.rowcount:
                raise ValueError("Сотрудник не найден")

    def add_alias(self, alias: str, employee_id: int, allow_reassign: bool = False) -> None:
        book = self.alias_book()
        book.add_alias(alias, employee_id, allow_reassign=allow_reassign)
        key = normalize_alias(alias)
        with closing(self.connect()) as db, db:
            db.execute(
                "INSERT INTO staff_alias(alias,staff_id) VALUES (?,?) "
                "ON CONFLICT(alias) DO UPDATE SET staff_id=excluded.staff_id",
                (key, int(employee_id)),
            )

    def remove_alias(self, alias: str) -> None:
        key = normalize_alias(alias)
        with closing(self.connect()) as db, db:
            if not db.execute("DELETE FROM staff_alias WHERE alias=?", (key,)).rowcount:
                raise ValueError("Обозначение не найдено")

    def seed_conflicts(self) -> list[dict[str, Any]]:
        with closing(self.connect()) as db:
            return [dict(row) for row in db.execute("SELECT * FROM seed_conflicts")]

    # ---------- настройки, линия, черновики ----------

    def setting(self, key: str, default: str | None = None) -> str | None:
        with closing(self.connect()) as db:
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with closing(self.connect()) as db, db:
            db.execute(
                "INSERT INTO settings(key,value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)),
            )
        # Режим пользователя дублируется вне SQLite. Если база тестового
        # режима исчезнет/пересоздастся, маркер не даст молча вернуть
        # пользователя в рабочий режим.
        if key.startswith("mode:") and key.split(":", 1)[1].isdigit():
            self._write_mode_marker(int(key.split(":", 1)[1]), str(value))

    def _write_mode_marker(self, user_id: int, mode: str) -> None:
        folder = self.root / "active"
        path = folder / str(int(user_id))
        if mode == "TEST":
            folder.mkdir(parents=True, exist_ok=True)
            path.write_text("TEST", encoding="utf-8")
        elif path.exists():
            path.unlink()

    def is_test_marked(self, user_id: int) -> bool:
        return (self.root / "active" / str(int(user_id))).is_file()

    def save_line(self, photo_sha: str, boundary: tuple[float, float]) -> None:
        if not photo_sha:
            raise ValueError("Нет отпечатка фотографии")
        with closing(self.connect()) as db, db:
            db.execute(
                "INSERT INTO line_settings(photo_sha,left_edge,right_edge,updated_at) VALUES (?,?,?,?) "
                "ON CONFLICT(photo_sha) DO UPDATE SET left_edge=excluded.left_edge,"
                "right_edge=excluded.right_edge,updated_at=excluded.updated_at",
                (photo_sha, float(boundary[0]), float(boundary[1]), _now()),
            )

    def get_line(self, photo_sha: str) -> tuple[float, float] | None:
        if not photo_sha:
            return None
        with closing(self.connect()) as db:
            row = db.execute(
                "SELECT left_edge,right_edge FROM line_settings WHERE photo_sha=?", (photo_sha,)
            ).fetchone()
            return (row["left_edge"], row["right_edge"]) if row else None

    def save_draft(self, user_id: int, report: Report) -> None:
        with closing(self.connect()) as db, db:
            db.execute(
                "INSERT INTO drafts(user_id,payload,updated_at) VALUES (?,?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at",
                (int(user_id), json.dumps(report.to_json(), ensure_ascii=False), _now()),
            )

    def load_draft(self, user_id: int) -> Report | None:
        with closing(self.connect()) as db:
            row = db.execute("SELECT payload FROM drafts WHERE user_id=?", (int(user_id),)).fetchone()
            if not row:
                return None
            return Report.from_json(json.loads(row["payload"]))

    def delete_draft(self, user_id: int) -> None:
        with closing(self.connect()) as db, db:
            db.execute("DELETE FROM drafts WHERE user_id=?", (int(user_id),))

    def audit(self, user_id: int | None, action: str, detail: str = "") -> None:
        with closing(self.connect()) as db, db:
            db.execute(
                "INSERT INTO audit(user_id,action,detail,created_at) VALUES (?,?,?,?)",
                (user_id, action[:80], detail[:2000], _now()),
            )

    # ---------- примеры ----------

    def record_confirmed(self, report: Report, original: Report | None, photo_bytes: bytes,
                         user_id: int, split: str = "train") -> int:
        """Сохранить подтверждённый пример. Только после validate()."""
        report.validate({p["id"] for p in self.staff()})
        if split not in ("train", "holdout"):
            raise ValueError("Неизвестная часть выборки")
        if not photo_bytes:
            raise ValueError("Нет фотографии для базы примеров")
        photo_sha = _sha256_bytes(photo_bytes)
        if report.photo_sha and report.photo_sha != photo_sha:
            raise ValueError("Фотография не совпадает с черновиком")
        with closing(self.connect()) as db:
            if db.execute(
                "SELECT 1 FROM examples WHERE photo_sha=? AND report_date=?",
                (photo_sha, report.report_date),
            ).fetchone():
                raise ValueError("Этот тестовый отчёт уже подтверждён — дубль не создаётся")
        path = self.photos_dir / (photo_sha + ".jpg")
        if not path.exists():
            path.write_bytes(photo_bytes)
        error_types = classify_errors(original, report) if original else []
        original_json = json.dumps(original.to_json() if original else {}, ensure_ascii=False)
        confirmed_json = json.dumps(report.to_json(), ensure_ascii=False)
        with closing(self.connect()) as db, db:
            try:
                cursor = db.execute(
                    "INSERT INTO examples(photo_sha,photo_path,source_file,report_date,original_json,"
                    "confirmed_json,error_types,engine_version,split,confirmed_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (photo_sha, path.name, report.photo_path, report.report_date, original_json,
                     confirmed_json, json.dumps(error_types), report.engine_version, split, _now()),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("Этот тестовый отчёт уже подтверждён — дубль не создаётся") from exc
            example_id = cursor.lastrowid
            db.execute(
                "INSERT INTO audit(user_id,action,detail,created_at) VALUES (?,?,?,?)",
                (user_id, "example_confirmed", f"id={example_id} date={report.report_date} errors={','.join(error_types)}", _now()),
            )
        return example_id

    def examples(self, split: str | None = None) -> list[dict[str, Any]]:
        with closing(self.connect()) as db:
            query = "SELECT * FROM examples"
            args: tuple = ()
            if split:
                query += " WHERE split=?"
                args = (split,)
            query += " ORDER BY id"
            result = []
            for row in db.execute(query, args):
                item = dict(row)
                item["error_types"] = json.loads(item["error_types"])
                result.append(item)
            return result

    def few_shot(self, limit: int = 3) -> list[dict[str, Any]]:
        """Только подтверждённые обучающие примеры; holdout исключён."""
        return self.examples("train")[-limit:]

    def stats(self) -> dict[str, Any]:
        with closing(self.connect()) as db:
            total = db.execute("SELECT COUNT(*) FROM examples").fetchone()[0]
            train = db.execute("SELECT COUNT(*) FROM examples WHERE split='train'").fetchone()[0]
            holdout = db.execute("SELECT COUNT(*) FROM examples WHERE split='holdout'").fetchone()[0]
            dates = db.execute("SELECT MIN(report_date),MAX(report_date) FROM examples").fetchone()
        return {"total": total, "train": train, "holdout": holdout,
                "first": dates[0], "last": dates[1]}

    # ---------- резервные копии ----------

    def backup(self, destination: Path | str) -> Path:
        dest = Path(destination).resolve()
        if dest == self.root or self.root in dest.parents or dest.exists():
            raise ValueError("Нужна новая папка резервной копии вне тестового хранилища")
        dest.mkdir(parents=True, mode=0o700)
        db_copy = dest / TEST_DB_NAME
        with closing(self.connect()) as source, closing(sqlite3.connect(db_copy)) as target:
            source.backup(target)
            if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Проверка резервной базы не пройдена")
        photos = dest / "confirmed"
        if self.photos_dir.is_dir():
            shutil.copytree(self.photos_dir, photos)
        if self.input_dir.is_dir():
            shutil.copytree(self.input_dir, dest / "input")
        # Маркеры режима переживают потерю SQLite и должны попадать в копию.
        if (self.root / "active").is_dir():
            shutil.copytree(self.root / "active", dest / "active")
        manifest = {
            "created_at": _now(),
            "schema_version": SCHEMA_VERSION,
            "files": {},
        }
        for path in sorted(dest.rglob("*")):
            if path.is_file() and path != dest / "manifest.json":
                manifest["files"][str(path.relative_to(dest))] = _sha256_file(path)
        (dest / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return dest

    @staticmethod
    def verify_backup(source: Path | str) -> dict[str, Any]:
        source = Path(source).resolve()
        manifest_path = source / "manifest.json"
        if not manifest_path.is_file():
            raise ValueError("Нет manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not (source / TEST_DB_NAME).is_file():
            raise ValueError("В резервной копии нет тестовой базы")
        for name, expected in manifest.get("files", {}).items():
            path = source / name
            if not path.is_file() or _sha256_file(path) != expected:
                raise ValueError("Резервная копия повреждена: " + name)
        # Все фото подтверждённых примеров должны быть в копии и в манифесте.
        try:
            with closing(sqlite3.connect(f"file:{source / TEST_DB_NAME}?mode=ro", uri=True)) as db:
                for (photo_name,) in db.execute("SELECT photo_path FROM examples"):
                    photo = source / "confirmed" / str(photo_name)
                    if not photo.is_file() or str(photo.relative_to(source)) not in manifest.get("files", {}):
                        raise ValueError("В резервной копии нет фото примера: " + str(photo_name))
        except sqlite3.Error as exc:
            raise ValueError("Не удалось проверить фото примеров") from exc
        return manifest

    @classmethod
    def restore(cls, source: Path | str, destination: Path | str) -> "ModeStore":
        source = Path(source).resolve()
        dest = Path(destination).resolve()
        cls.verify_backup(source)
        if dest.exists():
            raise ValueError("Папка восстановления уже существует")
        dest.mkdir(parents=True)
        shutil.copy2(source / TEST_DB_NAME, dest / TEST_DB_NAME)
        if (source / "confirmed").is_dir():
            shutil.copytree(source / "confirmed", dest / "confirmed")
        if (source / "input").is_dir():
            shutil.copytree(source / "input", dest / "input")
        if (source / "active").is_dir():
            shutil.copytree(source / "active", dest / "active")
        with closing(sqlite3.connect(dest / TEST_DB_NAME)) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Восстановленная база повреждена")
            # Абсолютные пути к исходным фото старых черновиков заменяются на
            # новую директорию; имена файлов сохраняются.
            for (user_id, payload) in db.execute("SELECT user_id,payload FROM drafts").fetchall():
                data = json.loads(payload)
                old_path = data.get("photo_path")
                if old_path:
                    data["photo_path"] = str(dest / "input" / Path(old_path).name)
                # Undo-снимки тоже содержат абсолютный путь к фото.
                history = []
                for snapshot in data.get("history", []):
                    try:
                        entry = json.loads(snapshot)
                    except (TypeError, ValueError):
                        history.append(snapshot)
                        continue
                    old = entry.get("photo_path")
                    if old:
                        entry["photo_path"] = str(dest / "input" / Path(old).name)
                    history.append(json.dumps(entry, ensure_ascii=False))
                data["history"] = history
                db.execute("UPDATE drafts SET payload=? WHERE user_id=?", (json.dumps(data, ensure_ascii=False), user_id))
            db.commit()
        store = cls(dest)
        store.initialize()
        return store

    def export_examples(self, destination: Path | str) -> Path:
        dest = Path(destination).resolve()
        if dest.exists():
            raise ValueError("Файл уже существует")
        dest.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for item in self.examples():
                archive.writestr(f"examples/{item['id']}.json", json.dumps(item, ensure_ascii=False, indent=2))
                photo = self.photos_dir / item["photo_path"]
                if photo.is_file():
                    archive.write(photo, f"photos/{photo.name}")
        return dest


__all__ = ["IsolationError", "SCHEMA_VERSION", "TEST_DB_NAME", "ModeStore"]

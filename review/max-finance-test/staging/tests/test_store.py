import json
import os
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from maxfinance_test.model import Item, Report
from maxfinance_test.store import IsolationError, ModeStore


def make_prod(path: Path):
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE staff_v3(id INTEGER PRIMARY KEY, name TEXT, active INTEGER DEFAULT 1);
        CREATE TABLE staff_alias_v3(alias TEXT PRIMARY KEY, staff_id INTEGER);
        """
    )
    staff = [(1, "ПЕТ", 1), (2, "РОС", 1), (3, "ДИМ", 1), (4, "ОЛИ", 1),
             (5, "ТОЛ", 1), (6, "ДАН", 1), (7, "ВЛА", 1), (8, "ВАН", 0), (9, "СЕР", 0)]
    connection.executemany("INSERT INTO staff_v3 VALUES (?,?,?)", staff)
    connection.executemany("INSERT INTO staff_alias_v3 VALUES (?,?)", [(n, i) for i, n, _ in staff])
    connection.commit()
    connection.close()


@pytest.fixture
def env(tmp_path):
    prod = tmp_path / "prod" / "finance.db"
    prod.parent.mkdir()
    make_prod(prod)
    root = tmp_path / "test"
    store = ModeStore(root, prod_db=prod, prod_sheet_id="PROD_SHEET", test_sheet_id="TEST_SHEET")
    store.initialize()
    return store, prod


def test_isolation_rejects_prod_paths(tmp_path):
    prod = tmp_path / "finance.db"
    make_prod(prod)
    with pytest.raises(IsolationError):
        ModeStore(tmp_path, prod_db=prod, prod_sheet_id="S", test_sheet_id="S")


def test_seed_preserves_all_staff_and_adds_missing(env):
    store, _ = env
    names = {p["name"]: p["active"] for p in store.staff(active_only=False)}
    assert names["ПЕТ"] == 1 and names["ОЛИ"] == 1
    assert names["ВАН"] == 0 and names["СЕР"] == 0
    assert names["ЛЕХ"] == 1
    book = store.alias_book()
    for label, name in [("П", "ПЕТ"), ("Р", "РОС"), ("R", "РОС"), ("В", "ВЛА"),
                        ("V", "ВЛА"), ("Т", "ТОЛ"), ("Д", "ДАН"), ("Л", "ЛЕХ")]:
        assert book.resolve(label).employee_name == name
    # Повторная инициализация не создаёт дублей.
    store.initialize()
    assert len(store.staff(active_only=False)) == len(names)


def test_conflicting_alias_is_not_silently_merged(tmp_path):
    prod = tmp_path / "prod" / "finance.db"
    prod.parent.mkdir()
    make_prod(prod)
    root = tmp_path / "test"
    store = ModeStore(root, prod_db=prod)
    store.initialize()
    with store.connect() as db, db:
        db.execute("UPDATE staff_alias SET staff_id=3 WHERE alias='П'")
    store.seed_from_production(prod)
    assert store.alias_book().resolve("П").employee_id == 3
    assert store.seed_conflicts()


def test_draft_and_line_survive_reopen(env, tmp_path):
    store, _ = env
    report = Report("2026-11-27", photo_reviewed=True, items=[Item([Decimal("1000")], category="nal")])
    store.save_draft(42, report)
    store.save_line("abc", (0.5, 0.52))
    again = ModeStore(store.root)
    again.initialize()
    loaded = again.load_draft(42)
    assert loaded is not None and loaded.items[0].amount == Decimal("1000")
    assert again.get_line("abc") == (0.5, 0.52)


def test_confirmed_example_requires_valid_report(env):
    store, _ = env
    report = Report("2026-11-27", photo_reviewed=True, items=[Item([Decimal("1000")], category="employee")])
    with pytest.raises(Exception):
        store.record_confirmed(report, None, b"photo", 1)
    report.set_employee(0, 1)
    report.set_source(0, "nal")
    example_id = store.record_confirmed(report, report, b"photo-bytes", 1)
    assert example_id == 1
    examples = store.examples("train")
    assert examples[0]["error_types"] == []
    assert (store.photos_dir / examples[0]["photo_path"]).is_file()


def test_duplicate_confirmation_is_rejected(env):
    store, _ = env
    report = Report("2026-11-27", photo_reviewed=True, items=[Item([Decimal("1000")], category="nal")])
    store.record_confirmed(report, None, b"same-photo", 1)
    with pytest.raises(ValueError):
        store.record_confirmed(report, None, b"same-photo", 1)
    assert len(store.examples()) == 1


def test_seed_does_not_reuse_id_of_another_person(tmp_path):
    prod = tmp_path / "prod" / "finance.db"
    prod.parent.mkdir()
    make_prod(prod)
    root = tmp_path / "test"
    store = ModeStore(root, prod_db=prod)
    store.initialize()
    # Подменяем id=1 на другого человека и сбрасываем флаг импорта.
    with store.connect() as db, db:
        db.execute("UPDATE staff SET name='ЧУЖОЙ' WHERE id=1")
        db.execute("DELETE FROM settings WHERE key='seed_done'")
    store.initialize()
    names = {p["name"] for p in store.staff(active_only=False)}
    assert "ПЕТ" in names
    assert store.seed_conflicts()
    assert store.alias_book().employee_name(1) != "ПЕТ"


def test_test_db_hardlink_to_prod_is_rejected(tmp_path):
    prod = tmp_path / "prod" / "finance.db"
    prod.parent.mkdir()
    make_prod(prod)
    root = tmp_path / "test"
    root.mkdir()
    try:
        os.link(prod, root / "test_finance.db")
    except (OSError, NotImplementedError):
        pytest.skip("hardlink not supported")
    with pytest.raises(Exception):
        ModeStore(root, prod_db=prod)


def test_backup_includes_input_photos(env, tmp_path):
    store, _ = env
    image = store.input_dir / "photo.img"
    image.write_bytes(b"photo")
    backup = store.backup(tmp_path / "backup-input")
    assert (backup / "input" / "photo.img").is_file()


def test_removed_alias_is_not_restored_on_restart(env, tmp_path):
    store, _ = env
    store.remove_alias("П")
    again = ModeStore(store.root)
    again.initialize()
    assert again.alias_book().resolve("П").status != "resolved"


def test_holdout_never_used_for_few_shot(env):
    store, _ = env
    report = Report("2026-11-27", photo_reviewed=True, items=[Item([Decimal("1000")], category="nal")])
    store.record_confirmed(report, None, b"photo-a", 1, split="train")
    store.record_confirmed(report, None, b"photo-b", 1, split="holdout")
    shots = store.few_shot(10)
    assert len(shots) == 1
    assert shots[0]["split"] == "train"


def test_error_types_recorded(env):
    store, _ = env
    original = Report("2026-11-27", photo_reviewed=True, items=[Item([Decimal("1000")], category="nal")])
    corrected = Report.from_json(original.to_json())
    corrected.set_term(0, 0, "1200")
    store.record_confirmed(corrected, original, b"photo", 1)
    assert "amount_changed" in store.examples()[0]["error_types"]


def test_backup_restore_and_tamper_detection(env, tmp_path):
    store, _ = env
    report = Report("2026-11-27", photo_reviewed=True, items=[Item([Decimal("1000")], category="nal")])
    store.record_confirmed(report, None, b"photo", 1)
    backup = store.backup(tmp_path / "backup")
    assert ModeStore.verify_backup(backup)["files"]
    restored = ModeStore.restore(backup, tmp_path / "restored")
    assert len(restored.examples()) == 1
    with open(backup / "confirmed" / "manifest.json", "w", encoding="utf-8") as handle:
        handle.write("broken")
    # Порча постороннего файла не влияет на манифест, а порча базы — влияет.
    db_path = backup / "test_finance.db"
    db_path.write_bytes(b"broken")
    with pytest.raises(Exception):
        ModeStore.verify_backup(backup)


def test_export_examples(env, tmp_path):
    store, _ = env
    report = Report("2026-11-27", photo_reviewed=True, items=[Item([Decimal("1000")], category="nal")])
    store.record_confirmed(report, None, b"photo", 1)
    archive = store.export_examples(tmp_path / "export.zip")
    assert archive.is_file() and archive.stat().st_size > 0

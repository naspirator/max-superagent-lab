"""Проверка полной резервной копии и механизма восстановления."""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
import tarfile
import tempfile
from pathlib import Path

ARCHIVE = Path(r"E:\MAX-FINANCE-TEST\backups\max-finance-prod-20261127-182625.tar.gz")
PROD = Path(r"E:\MAX-FINANCE-TEST\prod-src\max-finance-stage")
REPORT = Path(r"E:\MAX-FINANCE-TEST\reports\backup-verification.json")
REQUIRED = ("bot.py", "finance_v3.py", "ocr_v3.py", "reports.py", "sheets_v3.py",
            "finance.db", ".env", "google_credentials.json")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    result = {"archive": str(ARCHIVE), "archive_sha256": sha(ARCHIVE), "checks": {}}
    with tarfile.open(ARCHIVE, "r:gz") as archive:
        names = archive.getnames()
        extracted = Path(tempfile.mkdtemp(prefix="maxfinance-rollback-"))
        # .venv содержит абсолютные символические ссылки Termux; для проверки
        # кода и базы он не нужен.
        members = [m for m in archive.getmembers() if "/.venv/" not in m.name and not m.name.endswith("/.venv")]
        archive.extractall(extracted, members=members, filter="data")
    root = extracted / "max-finance-stage"
    result["checks"]["archive_contains_project"] = root.is_dir()
    missing = [name for name in REQUIRED if not (root / name).is_file()]
    result["checks"]["required_files_missing"] = missing
    hashes = {}
    for name in REQUIRED:
        if not (root / name).is_file():
            continue
        source = PROD / name
        same = source.is_file() and sha(root / name) == sha(source)
        hashes[name] = {"sha256": sha(root / name), "matches_live_copy": same}
    result["checks"]["file_hashes"] = hashes
    with sqlite3.connect(root / "finance.db") as db:
        result["checks"]["database_integrity"] = db.execute("PRAGMA integrity_check").fetchone()[0]
        result["checks"]["report_count"] = db.execute("SELECT COUNT(*) FROM daily_reports").fetchone()[0]
        result["checks"]["staff_count"] = db.execute("SELECT COUNT(*) FROM staff_v3").fetchone()[0]
    # Проверяем восстановление кода: портим копию и возвращаем файл из архива.
    target = root / "bot.py"
    original = target.read_bytes()
    target.write_bytes(b"BROKEN")
    with tarfile.open(ARCHIVE, "r:gz") as archive:
        member = archive.getmember("max-finance-stage/bot.py")
        source = archive.extractfile(member)
        assert source is not None
        target.write_bytes(source.read())
    result["checks"]["rollback_code_restored"] = sha(target) == sha(PROD / "bot.py")
    result["checks"]["rollback_db_untouched"] = sha(root / "finance.db") == sha(PROD / "finance.db")
    result["checks"]["temporary_dir"] = str(extracted)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["checks"], ensure_ascii=False, indent=2)[:4000])
    ok = (result["checks"]["archive_contains_project"] and not missing
          and result["checks"]["database_integrity"] == "ok"
          and result["checks"]["rollback_code_restored"])
    print("BACKUP_VERIFICATION", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

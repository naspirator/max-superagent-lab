"""Построить манифест фотобазы: 13 train / 5 holdout, статус pending."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(r"E:\MAX-FINANCE-TEST\testdata")
LABELS = json.loads((ROOT / "MAX_FINANCE_TEST.json").read_text(encoding="utf-8"))
by_name = {record["image"]: record for record in LABELS["records"]}
names = sorted(by_name)
holdout = set(names[-5:])
manifest = {
    "project": "MAX FINANCE TEST",
    "status": "draft_unverified_not_for_production",
    "confirmed_examples": 0,
    "verified_amounts": 0,
    "holdout_policy": "5 последних фотографий исключены из настройки и few-shot",
    "records": [],
}
for name in names:
    path = ROOT / name
    date_part = name.split("_")[0]
    report_date = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}"
    manifest["records"].append({
        "image": name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
        "split": "holdout" if name in holdout else "train",
        "verification": "pending",
        "usable_for_training": False,
        "reason": "разметка MAX_FINANCE_TEST.json предварительная и не подтверждена владельцем",
        "draft_report_date": report_date,
        "draft_cashless": by_name[name].get("cashless_header_amount"),
        "draft_cash": by_name[name].get("cash_header_amount"),
        "draft_employee_rows": len(by_name[name].get("cash_employee_candidates", []))
        + len(by_name[name].get("cashless_employee_candidates", [])),
    })
(ROOT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
print("records", len(manifest["records"]), "holdout", len(holdout), "train", len(names) - len(holdout))
print("holdout", sorted(holdout))

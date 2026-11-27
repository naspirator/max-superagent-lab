"""Сравнение старого ocr_v3 и нового тестового распознавания на 5 holdout."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

STAGING = Path(r"E:\MAX-FINANCE-TEST\staging")
PROD = Path(r"E:\MAX-FINANCE-TEST\prod-src\max-finance-stage")
sys.path.insert(0, str(STAGING))
sys.path.insert(0, str(PROD))

from maxfinance_test.ocr import recognize  # noqa: E402
from maxfinance_test.store import ModeStore  # noqa: E402
import ocr_v3  # noqa: E402

BOUNDARIES = {
    "20261121_205236.jpg": 0.585,
    "20261122_211228.jpg": 0.565,
    "20261123_211146.jpg": 0.785,
    "20261125_214435.jpg": 0.730,
    "20261126_210217.jpg": 0.600,
}

EXPECTED = {
    "20261121_205236.jpg": {
        "headers": {"beznal": 36800, "nal": 17200},
        "employees": [("П", "beznal", 4500), ("Т", "nal", 4000), ("В", "nal", 4000), ("П", "nal", 9200)],
    },
    "20261122_211228.jpg": {
        "headers": {"beznal": 50200, "nal": 34700},
        "employees": [("П", "beznal", 700), ("Т", "nal", 5000), ("Р", "nal", 6000),
                      ("Д", "nal", 4000), ("П", "nal", 19700)],
    },
    "20261123_211146.jpg": {
        "headers": {"beznal": 53350, "nal": 15300},
        # Т~7000 зачёркнуто/не подтверждено — не включаем в эталон.
        "employees": [("Р", "beznal", 12200), ("Д", "nal", 4000), ("Р", "nal", 4300)],
    },
    "20261125_214435.jpg": {
        "headers": {"beznal": 30100, "nal": 15600},
        "employees": [("П", "beznal", 3700), ("Т", "nal", 4200), ("В", "nal", 4200), ("П", "nal", 7200)],
    },
    "20261126_210217.jpg": {
        "headers": {"beznal": 16100, "nal": 10000},
        "employees": [("Р", "beznal", 600), ("В", "nal", 1500), ("Р", "nal", 8500)],
    },
}


def expected_amounts(spec):
    values = list(spec["headers"].values()) + [x[2] for x in spec["employees"]]
    return Counter(int(v) for v in values)


def match_counts(expected: Counter, actual: Counter) -> tuple[int, int, int]:
    matched = sum((expected & actual).values())
    return matched, sum(expected.values()), sum(actual.values())


async def main():
    load_dotenv(PROD / ".env")
    store = ModeStore(r"E:\MAX-FINANCE-TEST\runtime-test-mode")
    store.initialize()
    book = store.alias_book()
    client = AsyncOpenAI(api_key=os.getenv("VSEGPT_API_KEY"), base_url="https://api.vsegpt.ru/v1",
                         timeout=180, max_retries=0)
    rows = []
    for name, spec in EXPECTED.items():
        data = (Path(r"E:\MAX-FINANCE-TEST\testdata") / name).read_bytes()
        boundary = (BOUNDARIES[name], BOUNDARIES[name])
        expected = expected_amounts(spec)

        started = time.time()
        for attempt in range(3):
            try:
                old = await ocr_v3.recognize(client, data, boundary)
                break
            except Exception:
                if attempt == 2:
                    raise
                await asyncio.sleep(3)
        old_time = time.time() - started
        old_amounts = Counter(int(p.amount) for p in old.positions if p.amount is not None)

        started = time.time()
        for attempt in range(3):
            try:
                new = await recognize(client, data, boundary, book)
                break
            except Exception:
                if attempt == 2:
                    raise
                await asyncio.sleep(3)
        new_time = time.time() - started
        from maxfinance_test.ensemble import merge_amounts
        new, replaced = merge_amounts(new, old.positions)
        new_items = [x for x in new.items if x.category != "ignore"]
        new_amounts = Counter(int(x.amount) for x in new_items)
        new_confirmed = Counter(int(x.amount) for x in new_items if not x.uncertain)

        old_match, total, old_actual = match_counts(expected, old_amounts)
        new_match, _, new_actual = match_counts(expected, new_amounts)
        confirmed_match, _, _ = match_counts(expected, new_confirmed)

        expected_emp = Counter(spec["employees"])
        actual_emp = Counter(
            (item.alias or "", item.source or "unknown", int(item.amount))
            for item in new.items
            if item.category == "employee" and item.employee_id is not None and not item.uncertain
        )
        emp_match = sum((expected_emp & actual_emp).values())

        expected_cat = Counter(
            [("beznal", "-", int(v)) for k, v in spec["headers"].items() if k == "beznal"]
            + [("nal", "-", int(v)) for k, v in spec["headers"].items() if k == "nal"]
            + [("employee", src, int(amount)) for _, src, amount in spec["employees"]]
        )
        actual_cat = Counter(
            (item.category or "unknown", item.source or "-", int(item.amount))
            for item in new.items
        )
        cat_match = sum((expected_cat & actual_cat).values())
        cat_total = sum(expected_cat.values())

        exact_old = expected == old_amounts
        exact_new = expected == new_amounts and not any(x.uncertain for x in new_items)

        rows.append({
            "image": name,
            "expected": dict(expected),
            "old_amounts": sorted(old_amounts.elements()),
            "new_amounts": sorted(new_amounts.elements()),
            "old_match": old_match,
            "new_match": new_match,
            "confirmed_match": confirmed_match,
            "expected_total": total,
            "old_actual": old_actual,
            "new_actual": new_actual,
            "employee_match": emp_match,
            "employee_total": len(spec["employees"]),
            "category_match": cat_match,
            "category_total": cat_total,
            "exact_old": exact_old,
            "exact_new": exact_new,
            "old_time": round(old_time, 1),
            "new_time": round(new_time, 1),
            "new_warnings": new.warnings,
            "old_warnings": old.warnings,
        })

    await client.close()
    report = {
        "holdout": len(rows),
        "old_amount_recall": round(sum(r["old_match"] for r in rows) / sum(r["expected_total"] for r in rows), 3),
        "new_amount_recall": round(sum(r["new_match"] for r in rows) / sum(r["expected_total"] for r in rows), 3),
        "new_confirmed_amount_recall": round(sum(r["confirmed_match"] for r in rows) / sum(r["expected_total"] for r in rows), 3),
        "employee_accuracy": round(sum(r["employee_match"] for r in rows) / sum(r["employee_total"] for r in rows), 3),
        "category_accuracy": round(sum(r["category_match"] for r in rows) / sum(r["category_total"] for r in rows), 3),
        "exact_reports_old": sum(r["exact_old"] for r in rows),
        "exact_reports_new": sum(r["exact_new"] for r in rows),
        "rows": rows,
    }
    out = Path(r"E:\MAX-FINANCE-TEST\reports\evaluation.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, ensure_ascii=False, indent=2))
    for row in rows:
        print(row["image"], "old", row["old_match"], "/", row["expected_total"],
              "new", row["new_match"], "/", row["expected_total"],
              "emp", row["employee_match"], "/", row["employee_total"],
              "exact", row["exact_old"], row["exact_new"])
    print("saved", out)


asyncio.run(main())

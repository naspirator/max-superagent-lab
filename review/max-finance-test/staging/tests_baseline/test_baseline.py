import json
import sqlite3
from decimal import Decimal

import pytest

import finance_v3 as f
import sheets_v3
from finance_v3 import Draft, Position, Store, amount_text, parse_amount, parse_ocr


def test_amount_parsing_and_format():
    assert parse_amount("1 500,50") == Decimal("1500.50")
    assert amount_text(Decimal("1500.00")) == "1 500"
    assert amount_text(Decimal("1500.50")) == "1 500,50"


def test_expression_arithmetic_is_programmatic():
    position = Position.from_text("6000+1450")
    assert position.amount == Decimal("7450")
    assert position.terms == ("6000", "1450")
    with pytest.raises(ValueError):
        Position.from_text("6000+1450=7000")


def test_ocr_parser_rejects_duplicate_result_line():
    payload = {
        "complete": True,
        "items": [
            {"id": "r1", "expression": "6000+1450", "bbox": [0.1, 0.2, 0.4, 0.25], "uncertain": False},
            {"id": "r2", "expression": "7450", "bbox": [0.5, 0.2, 0.7, 0.25], "uncertain": False,
             "result_of": "r1", "relation_text": "6000+1450=7450"},
        ],
    }
    geometry = {"left": 0.1, "right": 0.1, "top": 0.1, "width": 1000, "height": 1000}
    result = parse_ocr(json.dumps(payload), geometry)
    assert len(result.positions) == 1
    assert result.positions[0].amount == Decimal("7450")


def test_store_saves_report_and_detects_duplicate(tmp_path):
    db = tmp_path / "finance.db"
    store = Store(db)
    store.initialize()
    report = Draft("2026-11-01", "file-1", "nonce-1", positions=[
        Position(["1000"], "1000", category="beznal"),
        Position(["200"], "200", category="employee", employee_id=1, source="nal"),
    ], ready=True, confirmed=True, photo_unique_id="unique-1", photo_hash="hash-1")
    assert store.save(report, 1) == "saved"
    assert store.save(report, 1) == "already_saved"
    row = store.get_report("2026-11-01")
    assert row is not None and row[1] == 1000
    assert store.all_payouts()[0][3] == Decimal("200")


def test_employee_alias_history_preserved(tmp_path):
    store = Store(tmp_path / "finance.db")
    store.initialize()
    names = {x["name"] for x in store.employees()}
    with sqlite3.connect(tmp_path / "finance.db") as db:
        all_names = {row[0] for row in db.execute("SELECT name FROM staff_v3")}
    assert {"ПЕТ", "РОС", "ДИМ", "ОЛИ", "ТОЛ", "ДАН", "ВЛА"}.issubset(names)
    store.add_employee("ЛЕХ")
    assert "ЛЕХ" in {x["name"] for x in store.employees()}


def test_sheets_guard_rejects_unrecognized_edit():
    current = [["2026-11-01", "1000", "", "", "", "", "", ""]]
    desired = [["2026-11-01", "900", "", "", "", "", "", ""]]
    with pytest.raises(ValueError):
        sheets_v3.guard_table(current, desired, None, 8, set(range(1, 8)), "Все записи")


def test_sheets_employee_totals():
    rows = [("2026-11-01", "ПЕТ", "nal", Decimal("100")),
            ("2026-11-01", "ПЕТ", "beznal", Decimal("200"))]
    result = sheets_v3.employee_totals(rows)
    assert result == [["2026-11-01", "ПЕТ", 200, 100, 0, 300]]

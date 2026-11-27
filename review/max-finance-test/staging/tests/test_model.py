from decimal import Decimal

import pytest

from maxfinance_test.model import Item, Report, ReportError, classify_errors
from maxfinance_test.money import MoneyError, parse_amount, parse_expression, signed_total


def item(terms, signs=None, **kwargs):
    return Item(terms=[Decimal(str(x)) for x in terms], signs=signs or [], **kwargs)


def test_parse_amount_accepts_russian_format():
    assert parse_amount("1 500,50") == Decimal("1500.50")
    assert parse_amount("1500.5") == Decimal("1500.5")
    assert parse_amount(1500) == Decimal("1500")


@pytest.mark.parametrize("bad", ["", "abc", "1,2,3", "-", "1e5", None, True])
def test_parse_amount_rejects_bad(bad):
    with pytest.raises(MoneyError):
        parse_amount(bad)


def test_parse_expression_with_minus_and_unicode_dash():
    terms, signs = parse_expression("7150 − 500 + 100")
    assert terms == [Decimal("7150"), Decimal("500"), Decimal("100")]
    assert signs == ["+", "-", "+"]
    assert signed_total(terms, signs) == Decimal("6750")


def test_signed_total_programmatic():
    assert signed_total([Decimal("6000"), Decimal("1450")], ["+", "+"]) == Decimal("7450")
    assert signed_total([Decimal("10050"), Decimal("500")], ["+", "-"]) == Decimal("9550")


def test_report_totals_and_employee_payouts():
    report = Report("2026-11-27", items=[
        item([12000], category="beznal"),
        item([10050], category="nal"),
        item([7150], category="employee", employee_id=1, source="nal"),
        item([4000, 2000], ["+", "-"], category="employee", employee_id=2, source="beznal"),
        item([500], category="expense"),
        item([1000], category="debt"),
    ])
    totals = report.totals()
    assert totals["categories"]["beznal"] == Decimal("12000")
    assert totals["categories"]["nal"] == Decimal("10050")
    assert totals["employee_total"] == Decimal("9150")
    assert totals["expenses"] == Decimal("500")
    assert totals["debts"] == Decimal("1000")


def test_manual_category_total_does_not_change_employee_amounts():
    report = Report("2026-11-27", items=[
        item([10000], category="beznal"),
        item([3000], category="employee", employee_id=1, source="beznal"),
    ])
    report.set_category_total("beznal", 11000)
    assert report.category_total("beznal") == Decimal("11000")
    assert report.category_sum("beznal") == Decimal("10000")
    assert report.category_discrepancy("beznal") == Decimal("1000")
    assert report.employee_total_for(1) == Decimal("3000")


def test_every_item_is_editable_and_signs_change():
    report = Report("2026-11-27", items=[item([1000, 200])])
    report.set_sign(0, 1, "-")
    assert report.items[0].amount == Decimal("800")
    report.set_term(0, 0, "1500")
    assert report.items[0].amount == Decimal("1300")
    report.add_term(0, "300", "+")
    assert report.items[0].amount == Decimal("1600")
    report.remove_term(0, 2)
    assert report.items[0].amount == Decimal("1300")


def test_split_and_merge():
    report = Report("2026-11-27", items=[item([1000, 2000, 300], category="nal")])
    a, b = report.split_item(0, 2)
    assert len(report.items) == 2
    assert report.items[a].amount == Decimal("3000")
    assert report.items[b].amount == Decimal("300")
    merged = report.merge_items(a, b)
    assert report.items[merged].amount == Decimal("3300")


def test_delete_add_move_undo():
    report = Report("2026-11-27", items=[item([1000]), item([2000])])
    report.add_item(item([3000]))
    assert len(report.items) == 3
    report.move_item(2, -1)
    assert report.items[1].amount == Decimal("3000")
    report.delete_item(0)
    assert len(report.items) == 2
    report.undo()
    assert len(report.items) == 3
    report.undo()
    assert [x.amount for x in report.items] == [Decimal("1000"), Decimal("2000"), Decimal("3000")]


def test_validation_requires_employee_and_source():
    report = Report("2026-11-27", items=[item([1000], category="employee")])
    with pytest.raises(ReportError):
        report.validate()
    report.set_employee(0, 1)
    report.set_source(0, "nal")
    assert report.validate()


def test_uncertain_item_blocks_confirmation_until_edited():
    report = Report("2026-11-27", items=[item([1000], category="nal", uncertain=True)])
    with pytest.raises(ReportError):
        report.validate()
    report.set_term(0, 0, "1000")
    assert report.validate()


def test_struck_item_must_be_ignored():
    report = Report("2026-11-27", items=[
        item([1000], category="nal"),
        item([500], category="ignore", struck=True),
    ])
    assert report.validate()
    report.set_category(1, "expense")
    with pytest.raises(ReportError):
        report.validate()


def test_itog_not_required_and_not_auto_zero():
    report = Report("2026-11-27", items=[item([1000], category="beznal")])
    assert report.validate()
    assert "itog" not in report.totals()["categories"]


def test_classify_errors():
    original = Report("2026-11-27", items=[item([1000], category="nal")])
    corrected = Report.from_json(original.to_json())
    corrected.set_term(0, 0, "1200")
    corrected.set_category(0, "beznal")
    errors = classify_errors(original, corrected)
    assert "amount_changed" in errors
    assert "category_changed" in errors

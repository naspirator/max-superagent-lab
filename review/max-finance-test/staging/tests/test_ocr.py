import json
from decimal import Decimal

import pytest

from maxfinance_test.aliases import AliasBook, DEFAULT_ALIASES
from maxfinance_test.ocr import OcrError, parse_response


def book():
    staff = [
        {"id": 1, "name": "ПЕТ"}, {"id": 2, "name": "РОС"}, {"id": 3, "name": "ДИМ"},
        {"id": 4, "name": "ОЛИ"}, {"id": 5, "name": "ТОЛ"}, {"id": 6, "name": "ДАН"},
        {"id": 7, "name": "ВЛА"}, {"id": 8, "name": "ЛЕХ"},
    ]
    return AliasBook(staff, {a: next(p["id"] for p in staff if p["name"] == n) for a, n in DEFAULT_ALIASES.items()})


def payload(items, complete=True):
    return json.dumps({"complete": complete, "items": items}, ensure_ascii=False)


def row(**kwargs):
    base = {
        "id": "r1", "kind": "payout", "column": "nal", "label": "П",
        "terms": ["7150"], "signs": ["+"], "calc": "", "raw": "П - 7150 = 2800 = 1450",
        "struck": False, "corrected": False, "uncertain": False, "bbox": [0.1, 0.5, 0.3, 0.6],
    }
    base.update(kwargs)
    return base


def test_payout_sum_is_programmatic_not_from_calc():
    report = parse_response(payload([row(terms=["6000", "1450"], signs=["+", "+"], calc="7450")]), book())
    assert report.items[0].amount == Decimal("7450")
    assert "не прибавлены" in " ".join(report.warnings)


def test_minus_sign_is_applied():
    report = parse_response(payload([row(terms=["7150", "500"], signs=["+", "-"])]), book())
    assert report.items[0].amount == Decimal("6650")
    assert report.items[0].category == "employee"
    assert report.items[0].source == "nal"


def test_single_dash_after_label_is_separator_not_minus():
    report = parse_response(payload([
        row(id="h", kind="header_beznal", column="beznal", label="Б/Н", terms=["16100"], signs=["-"]),
        row(id="p", terms=["600"], signs=["-"]),
    ]), book())
    assert report.items[0].amount == Decimal("16100")
    assert report.items[1].amount == Decimal("600")


def test_header_and_total():
    report = parse_response(payload([
        row(id="h1", kind="header_beznal", column="beznal", label="Б/Н", terms=["12000"], signs=["+"]),
        row(id="h2", kind="header_nal", column="nal", label="Нал", terms=["10050"], signs=["+"]),
        row(id="t1", kind="total", column="unknown", label="Итог", terms=["22050"], signs=["+"]),
    ]), book())
    assert [x.category for x in report.items] == ["beznal", "nal", "itog"]
    assert report.items[0].amount == Decimal("12000")


def test_struck_line_is_kept_but_requires_confirmation():
    report = parse_response(payload([row(struck=True, terms=["10050"], signs=["+"])]), book())
    assert report.items[0].struck is True
    assert report.items[0].uncertain is True
    # Данные не теряются: владелец сам решит, исключить строку или восстановить.
    assert report.items[0].category == "employee"


def test_unknown_alias_is_not_guessed():
    report = parse_response(payload([row(label="Х", uncertain=False)]), book())
    assert report.items[0].employee_id is None
    assert report.items[0].uncertain is True
    assert "не найдено в словаре" in " ".join(report.warnings)


def test_no_invented_itog():
    report = parse_response(payload([row(kind="header_nal", column="nal", terms=["100"], signs=["+"])]), book())
    assert all(x.category != "itog" for x in report.items)


def test_missing_terms_is_warning_not_invented():
    report = parse_response(payload([row(terms=[], signs=[])]), book())
    assert not report.items
    assert "неясные числа" in " ".join(report.warnings)


def test_incomplete_flag():
    report = parse_response(payload([row()], complete=False), book())
    assert "Полнота" in " ".join(report.warnings)


def test_bad_json():
    with pytest.raises(OcrError):
        parse_response("not json", book())


def test_bbox_normalized_and_out_of_range_dropped():
    report = parse_response(payload([row(bbox=[0.1, 0.5, 0.3, 0.6]), row(id="r2", bbox=[1.2, 0, 0.3, 0.6])]), book())
    assert report.items[0].bbox == [0.1, 0.5, 0.3, 0.6]
    assert report.items[1].bbox is None


def test_source_inferred_from_block_order():
    report = parse_response(payload([
        row(id="b", kind="header_beznal", column="beznal", label="Б/Н", terms=["30100"], signs=["+"],
            bbox=[0.1, 0.40, 0.3, 0.44]),
        row(id="p1", terms=["3700"], signs=["+"], column="unknown", bbox=[0.1, 0.45, 0.3, 0.49]),
        row(id="n", kind="header_nal", column="nal", label="Нал", terms=["15600"], signs=["+"],
            bbox=[0.1, 0.55, 0.3, 0.59]),
        row(id="p2", terms=["4200"], signs=["+"], column="unknown", bbox=[0.1, 0.60, 0.3, 0.64]),
    ]), book())
    assert report.items[1].source == "beznal"
    assert report.items[3].source == "nal"


def test_uncertain_defaults_to_true_when_omitted():
    data = row()
    del data["uncertain"]
    report = parse_response(payload([data]), book())
    assert report.items[0].uncertain is True

from maxfinance_test.aliases import AliasBook, DEFAULT_ALIASES, normalize_alias


def book():
    staff = [
        {"id": 1, "name": "ПЕТ"},
        {"id": 2, "name": "РОС"},
        {"id": 3, "name": "ДИМ"},
        {"id": 4, "name": "ОЛИ"},
        {"id": 5, "name": "ТОЛ"},
        {"id": 6, "name": "ДАН"},
        {"id": 7, "name": "ВЛА"},
        {"id": 8, "name": "ЛЕХ"},
    ]
    return AliasBook(staff, {a: next(p["id"] for p in staff if p["name"] == n) for a, n in DEFAULT_ALIASES.items()})


def test_confirmed_dictionary():
    b = book()
    for label, name in [("П", "ПЕТ"), ("Р", "РОС"), ("R", "РОС"), ("В", "ВЛА"), ("V", "ВЛА"),
                        ("Т", "ТОЛ"), ("Д", "ДАН"), ("Л", "ЛЕХ"), ("ДИМ", "ДИМ")]:
        result = b.resolve(label)
        assert result.status == "resolved", label
        assert result.employee_name == name


def test_full_names_and_partial_handwriting():
    b = book()
    assert b.resolve("Пет").employee_name == "ПЕТ"
    assert b.resolve("Рос").employee_name == "РОС"
    assert b.resolve("Вл").employee_name == "ВЛА"
    assert b.resolve("Дим").employee_name == "ДИМ"
    assert b.resolve("П?").employee_name == "ПЕТ"


def test_unknown_is_not_guessed():
    b = book()
    assert b.resolve("Х").status == "unknown"
    assert b.resolve("").status == "unknown"


def test_ambiguous_prefix_not_merged():
    staff = [{"id": 1, "name": "ДАН"}, {"id": 2, "name": "ДАР"}]
    b = AliasBook(staff, {})
    result = b.resolve("ДА")
    assert result.status == "ambiguous"
    assert result.employee_id is None


def test_reassign_requires_confirmation():
    b = book()
    try:
        b.add_alias("П", 2)
    except ValueError as exc:
        assert "подтверждения" in str(exc)
    else:
        raise AssertionError("переназначение должно требовать подтверждения")
    b.add_alias("П", 2, allow_reassign=True)
    assert b.resolve("П").employee_id == 2


def test_add_employee_preserves_history():
    b = book()
    new_id = b.add_employee("СЕР")
    assert b.resolve("СЕР").employee_id == new_id
    assert len(b.staff_options()) == 9


def test_latin_homoglyph_is_normalized_not_merged():
    b = book()
    # «P» латиницей — визуальная копия кириллической «Р».
    assert b.resolve("P").employee_name == "РОС"
    # Но если такое обозначение уже занято другим сотрудником — оно главнее.
    b.add_alias("P", 1, allow_reassign=True)
    assert b.resolve("P").employee_name == "ПЕТ"


def test_normalize_alias():
    assert normalize_alias(" п ") == "П"
    assert normalize_alias("Дим.") == "ДИМ"
    assert normalize_alias("П?") == "П"

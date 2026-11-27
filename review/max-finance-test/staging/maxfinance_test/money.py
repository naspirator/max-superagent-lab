"""Денежные значения и выражения для MAX FINANCE TEST.

Сложение и вычитание выполняются только здесь, программно. Никакая модель
не должна возвращать готовый итог: модель возвращает слагаемые и знаки.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

MAX_AMOUNT = Decimal("100000000")
MIN_AMOUNT = Decimal("-100000000")
SIGNS = ("+", "-")

_SPACES = re.compile(r"[\s\u00a0\u202f]+")
_DASHES = str.maketrans({"−": "-", "–": "-", "—": "-", "﹣": "-", "－": "-", "＋": "+", "﹢": "+"})


class MoneyError(ValueError):
    """Некорректная денежная запись."""


def parse_amount(value: object) -> Decimal:
    """Разобрать одно число: '1 500,50', '1500.5', 1500."""
    if isinstance(value, bool) or value is None:
        raise MoneyError("Введите сумму цифрами")
    if isinstance(value, Decimal):
        number = value
    elif isinstance(value, (int, float)):
        number = Decimal(str(value))
    elif isinstance(value, str):
        text = _SPACES.sub("", value).replace(",", ".")
        if not text or not re.fullmatch(r"[+-]?\d{1,9}(?:\.\d{1,2})?", text):
            raise MoneyError("Введите сумму цифрами, например 1500 или 1500,50")
        number = Decimal(text)
    else:
        raise MoneyError("Введите сумму цифрами")
    if not number.is_finite():
        raise MoneyError("Недопустимое число")
    if number > MAX_AMOUNT or number < MIN_AMOUNT:
        raise MoneyError("Сумма слишком большая")
    return number


def parse_expression(text: object) -> tuple[list[Decimal], list[str]]:
    """Разобрать '1500+2000-500' в слагаемые и знаки.

    Возвращает (terms, signs), где signs[i] — знак перед terms[i] (для первого
    обычно '+'). Знак '-' означает вычитание.
    """
    if not isinstance(text, str):
        raise MoneyError("Введите выражение цифрами")
    value = _SPACES.sub("", text).translate(_DASHES)
    if not value:
        raise MoneyError("Пустое выражение")
    if value[0] in "+-":
        value = value[0] + value[1:]
    parts = re.split(r"([+-])", value)
    if parts and parts[0] == "":
        parts = parts[1:]
    if not parts:
        raise MoneyError("Пустое выражение")
    terms: list[Decimal] = []
    signs: list[str] = []
    current_sign = "+"
    for piece in parts:
        if piece in ("+", "-"):
            current_sign = piece
            continue
        terms.append(parse_amount(piece))
        signs.append(current_sign)
        current_sign = "+"
    if not terms or len(terms) > 30:
        raise MoneyError("Неверное число слагаемых")
    return terms, signs


def signed_total(terms: list[Decimal] | tuple[Decimal, ...], signs: list[str] | tuple[str, ...]) -> Decimal:
    """Программно сложить слагаемые с учётом знаков."""
    if len(terms) != len(signs):
        raise MoneyError("Количество слагаемых и знаков не совпадает")
    total = Decimal("0")
    for term, sign in zip(terms, signs):
        if sign not in SIGNS:
            raise MoneyError("Недопустимый знак")
        total += Decimal(term) if sign == "+" else -Decimal(term)
    if total > MAX_AMOUNT or total < MIN_AMOUNT:
        raise MoneyError("Сумма слишком большая")
    return total


def normalize_terms(terms: list[object], signs: list[object] | None = None) -> tuple[list[Decimal], list[str]]:
    """Проверить массивы terms/signs из ответа модели и привести к Decimal."""
    if not isinstance(terms, list) or not 1 <= len(terms) <= 30:
        raise MoneyError("Неверное число слагаемых")
    if signs is None:
        signs = ["+"] * len(terms)
    if not isinstance(signs, list) or len(signs) != len(terms):
        raise MoneyError("Количество слагаемых и знаков не совпадает")
    result_terms: list[Decimal] = []
    result_signs: list[str] = []
    for term, sign in zip(terms, signs):
        if sign not in SIGNS:
            raise MoneyError("Недопустимый знак")
        result_terms.append(parse_amount(term))
        result_signs.append(sign)
    return result_terms, result_signs


def format_amount(value: Decimal | int | str) -> str:
    """1 500,50; целые без копеек."""
    number = Decimal(value)
    text = f"{number:,.2f}".replace(",", " ")
    return text[:-3] if text.endswith(".00") else text.replace(".", ",")


def amount_cents(value: Decimal) -> int:
    return int((Decimal(value) * 100).to_integral_value())


def decimal_text(value: Decimal) -> str:
    """Стабильное строковое представление для JSON."""
    text = format(Decimal(value), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


__all__ = [
    "MAX_AMOUNT", "MoneyError", "amount_cents", "decimal_text", "format_amount",
    "normalize_terms", "parse_amount", "parse_expression", "signed_total",
]

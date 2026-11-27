"""Словарь обозначений сотрудников.

Подтверждённые владельцем обозначения не меняются автоматически. Любое
переназначение буквы на другого сотрудника требует явного решения владельца.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

DEFAULT_ALIASES: dict[str, str] = {
    "П": "ПЕТ",
    "ПЕТ": "ПЕТ",
    "Р": "РОС",
    "R": "РОС",
    "РОС": "РОС",
    "В": "ВЛА",
    "V": "ВЛА",
    "ВЛА": "ВЛА",
    "Т": "ТОЛ",
    "ТОЛ": "ТОЛ",
    "Д": "ДАН",
    "ДАН": "ДАН",
    "Л": "ЛЕХ",
    "ЛЕХ": "ЛЕХ",
    "ДИМ": "ДИМ",
}

# Полные имена, которые должны существовать в тестовой базе.
REQUIRED_STAFF = ("ПЕТ", "РОС", "ВЛА", "ТОЛ", "ДАН", "ЛЕХ", "ДИМ")

_TRAILING = re.compile(r"[^0-9A-ZА-ЯЁ]+$")

# Визуально одинаковые латинские буквы в рукописи. Применяются только если
# такого обозначения нет в словаре; это нормализация OCR, а не объединение
# сотрудников.
HOMOGLYPHS = {
    "P": "Р", "C": "С", "A": "А", "B": "В", "E": "Е", "H": "Н",
    "K": "К", "M": "М", "O": "О", "T": "Т", "X": "Х", "Y": "У",
}


def normalize_alias(value: object) -> str:
    text = str(value or "").strip().upper().replace("Ё", "Е")
    text = re.sub(r"\s+", "", text)
    text = text.replace("?", "").replace(".", "").replace(",", "")
    text = text.replace("R", "R").replace("V", "V")
    return text[:40]


@dataclass(frozen=True)
class Resolution:
    status: str  # resolved | unknown | ambiguous
    employee_id: int | None
    employee_name: str | None
    normalized: str
    candidates: tuple[int, ...] = ()


class AliasBook:
    """Словарь поверх списка сотрудников тестовой базы."""

    def __init__(self, staff: list[dict] | None = None, aliases: dict[str, int] | None = None):
        self.staff: dict[int, str] = {}
        self.aliases: dict[str, int] = {}
        for person in staff or []:
            self.staff[int(person["id"])] = str(person["name"])
        for alias, staff_id in (aliases or {}).items():
            key = normalize_alias(alias)
            if key and int(staff_id) in self.staff:
                self.aliases[key] = int(staff_id)

    # ---------- сотрудники ----------

    def employee_name(self, employee_id: int | None) -> str | None:
        return self.staff.get(int(employee_id)) if employee_id is not None else None

    def employee_id_by_name(self, name: str) -> int | None:
        key = normalize_alias(name)
        for ident, value in self.staff.items():
            if normalize_alias(value) == key:
                return ident
        return None

    def add_employee(self, name: str) -> int:
        key = normalize_alias(name)
        if not re.fullmatch(r"[А-ЯЁA-Z][А-ЯЁA-Z .-]{0,39}", key):
            raise ValueError("Имя: до 40 букв, пробел или дефис")
        existing = self.employee_id_by_name(key)
        if existing is not None:
            raise ValueError("Сотрудник уже существует")
        new_id = max(self.staff) + 1 if self.staff else 1
        self.staff[new_id] = key
        self.aliases[key] = new_id
        return new_id

    # ---------- буквенные обозначения ----------

    def add_alias(self, alias: str, employee_id: int, allow_reassign: bool = False) -> None:
        key = normalize_alias(alias)
        if not key:
            raise ValueError("Пустое обозначение")
        if int(employee_id) not in self.staff:
            raise ValueError("Сотрудник не найден")
        current = self.aliases.get(key)
        if current is not None and current != int(employee_id) and not allow_reassign:
            raise ValueError(
                "Обозначение «" + key + "» уже принадлежит сотруднику "
                + str(self.staff.get(current)) + ". Переназначение требует подтверждения владельца."
            )
        self.aliases[key] = int(employee_id)

    def remove_alias(self, alias: str) -> None:
        key = normalize_alias(alias)
        if key not in self.aliases:
            raise ValueError("Обозначение не найдено")
        del self.aliases[key]

    def aliases_for(self, employee_id: int) -> list[str]:
        return sorted(alias for alias, ident in self.aliases.items() if ident == int(employee_id))

    # ---------- распознавание ----------

    def resolve(self, label: object) -> Resolution:
        key = normalize_alias(label)
        if not key:
            return Resolution("unknown", None, None, key)
        if key in self.aliases:
            ident = self.aliases[key]
            return Resolution("resolved", ident, self.staff.get(ident), key)
        if len(key) == 1 and key in HOMOGLYPHS:
            mapped = HOMOGLYPHS[key]
            if mapped in self.aliases:
                ident = self.aliases[mapped]
                return Resolution("resolved", ident, self.staff.get(ident), mapped)
        exact = [ident for ident, name in self.staff.items() if normalize_alias(name) == key]
        if len(exact) == 1:
            return Resolution("resolved", exact[0], self.staff[exact[0]], key)
        if len(exact) > 1:
            return Resolution("ambiguous", None, None, key, tuple(sorted(exact)))
        # Частичное написание: «Вл» → ВЛА, «Пет» → ПЕТ.
        prefix = [
            ident for ident, name in self.staff.items()
            if len(key) >= 2 and normalize_alias(name).startswith(key)
        ]
        if len(prefix) == 1:
            return Resolution("resolved", prefix[0], self.staff[prefix[0]], key)
        if len(prefix) > 1:
            return Resolution("ambiguous", None, None, key, tuple(sorted(prefix)))
        return Resolution("unknown", None, None, key)

    def staff_options(self) -> list[tuple[int, str]]:
        return sorted(self.staff.items(), key=lambda x: x[1])


__all__ = ["AliasBook", "DEFAULT_ALIASES", "REQUIRED_STAFF", "Resolution", "normalize_alias"]

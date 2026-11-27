"""Модель тестового отчёта: позиции, правки, итоги, отмена.

Все финансовые итоги пересчитываются программно из слагаемых и знаков.
"""
from __future__ import annotations

import copy
import json
import secrets
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from .money import (
    MoneyError, decimal_text, format_amount, normalize_terms, parse_amount, signed_total,
)

CATEGORIES = ("beznal", "nal", "itog", "employee", "debt", "expense", "ignore")
SOURCES = ("beznal", "nal", "unknown")
HEADER_CATEGORIES = ("beznal", "nal", "itog")
CATEGORY_LABELS = {
    "beznal": "Безнал", "nal": "Наличные", "itog": "Итог", "employee": "Сотрудник",
    "debt": "Долг", "expense": "Расход", "ignore": "Не учитывать", None: "Не назначено",
}
SOURCE_LABELS = {"beznal": "Безнал", "nal": "Наличные", "unknown": "Не указан"}


class ReportError(ValueError):
    """Нарушение правил отчёта."""


def new_id() -> str:
    return secrets.token_hex(6)


@dataclass
class Item:
    terms: list[Decimal]
    signs: list[str] = field(default_factory=list)
    raw: str = ""
    category: str | None = None
    employee_id: int | None = None
    alias: str = ""
    source: str | None = None
    uncertain: bool = False
    struck: bool = False
    origin: str = "ocr"
    bbox: list[float] | None = None
    note: str = ""
    item_id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        self.terms, self.signs = normalize_terms(list(self.terms), list(self.signs) or None)

    @property
    def amount(self) -> Decimal:
        return signed_total(self.terms, self.signs)

    @property
    def editable(self) -> bool:
        return True

    def display(self) -> str:
        text = format_amount(self.amount) + " ₽"
        if len(self.terms) > 1:
            parts = []
            for index, (term, sign) in enumerate(zip(self.terms, self.signs)):
                if index == 0:
                    parts.append(("-" if sign == "-" else "") + format_amount(term))
                else:
                    parts.append(("+" if sign == "+" else "−") + " " + format_amount(term))
            text += " (" + " ".join(parts) + ")"
        if self.alias:
            text += " · " + self.alias
        if self.struck:
            text += " [зачёркнуто]"
        if self.uncertain:
            text += " [проверить]"
        return text

    def to_json(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "terms": [decimal_text(t) for t in self.terms],
            "signs": list(self.signs),
            "raw": self.raw,
            "category": self.category,
            "employee_id": self.employee_id,
            "alias": self.alias,
            "source": self.source,
            "uncertain": self.uncertain,
            "struck": self.struck,
            "origin": self.origin,
            "bbox": self.bbox,
            "note": self.note,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Item":
        return cls(
            terms=[Decimal(str(x)) for x in data.get("terms", [])],
            signs=list(data.get("signs", [])),
            raw=str(data.get("raw", "")),
            category=data.get("category"),
            employee_id=data.get("employee_id"),
            alias=str(data.get("alias", "")),
            source=data.get("source"),
            uncertain=bool(data.get("uncertain", False)),
            struck=bool(data.get("struck", False)),
            origin=str(data.get("origin", "ocr")),
            bbox=data.get("bbox"),
            note=str(data.get("note", "")),
            item_id=str(data.get("item_id") or new_id()),
        )


@dataclass
class Report:
    report_date: str
    photo_sha: str = ""
    photo_path: str = ""
    boundary: tuple[float, float] | None = None
    items: list[Item] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    version: int = 0
    engine_version: str = ""
    manual_totals: dict[str, str] = field(default_factory=dict)
    history: list[str] = field(default_factory=list)
    message_id: int | None = None
    created_at: str = ""
    nonce: str = field(default_factory=new_id)
    ocr_snapshot: dict[str, Any] | None = None
    ocr_complete: bool = True
    ocr_stale: bool = False
    debt_policy: str = "separate"

    # ---------- служебное ----------

    def touch(self) -> None:
        self.version += 1

    def _push_history(self) -> None:
        if self.version:
            snapshot = self.to_json(include_history=False, include_message=False)
            self.history.append(json.dumps(snapshot, ensure_ascii=False))
            if len(self.history) > 30:
                self.history = self.history[-30:]
        self.touch()

    def can_undo(self) -> bool:
        return bool(self.history)

    def push_undo(self) -> None:
        """Сохранить снимок перед внешней правкой."""
        self._push_history()

    def undo(self) -> None:
        if not self.history:
            raise ReportError("Отменять больше нечего")
        version = self.version
        menu_id = self.message_id
        data = json.loads(self.history.pop())
        current_history = list(self.history)
        restored = Report.from_json(data)
        self.__dict__.update(restored.__dict__)
        self.history = current_history
        # Ревизия только растёт; идентификатор меню не должен откатываться.
        self.version = version + 1
        self.message_id = menu_id

    # ---------- сериализация ----------

    def to_json(self, include_history: bool = True, include_message: bool = True) -> dict[str, Any]:
        data = {
            "report_date": self.report_date,
            "photo_sha": self.photo_sha,
            "photo_path": self.photo_path,
            "boundary": list(self.boundary) if self.boundary else None,
            "items": [item.to_json() for item in self.items],
            "warnings": list(self.warnings),
            "version": self.version,
            "engine_version": self.engine_version,
            "manual_totals": dict(self.manual_totals),
            "created_at": self.created_at,
            "nonce": self.nonce,
            "ocr_snapshot": self.ocr_snapshot,
            "ocr_complete": self.ocr_complete,
            "ocr_stale": self.ocr_stale,
            "debt_policy": self.debt_policy,
        }
        if include_history:
            data["history"] = list(self.history)
        if include_message:
            data["message_id"] = self.message_id
        return data

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Report":
        report = cls(
            report_date=str(data["report_date"]),
            photo_sha=str(data.get("photo_sha", "")),
            photo_path=str(data.get("photo_path", "")),
            boundary=tuple(data["boundary"]) if data.get("boundary") else None,
            items=[Item.from_json(x) for x in data.get("items", [])],
            warnings=[str(x) for x in data.get("warnings", [])],
            version=int(data.get("version", 0)),
            engine_version=str(data.get("engine_version", "")),
            manual_totals={str(k): str(v) for k, v in data.get("manual_totals", {}).items()},
            history=[str(x) for x in data.get("history", [])],
            message_id=data.get("message_id"),
            created_at=str(data.get("created_at", "")),
            nonce=str(data.get("nonce") or new_id()),
            ocr_snapshot=data.get("ocr_snapshot"),
            ocr_complete=bool(data.get("ocr_complete", True)),
            ocr_stale=bool(data.get("ocr_stale", False)),
            debt_policy=str(data.get("debt_policy", "separate")),
        )
        return report

    # ---------- итоги ----------

    def category_sum(self, category: str) -> Decimal:
        total = Decimal("0")
        for item in self.items:
            if item.category == category:
                total += item.amount
        return total

    def category_total(self, category: str) -> Decimal:
        """Итог категории: ручной, если владелец его задал, иначе вычисленный."""
        if category in self.manual_totals:
            try:
                return Decimal(self.manual_totals[category])
            except Exception:
                return self.category_sum(category)
        return self.category_sum(category)

    def category_discrepancy(self, category: str) -> Decimal | None:
        if category not in self.manual_totals:
            return None
        return self.category_total(category) - self.category_sum(category)

    def employee_totals(self) -> list[dict[str, Any]]:
        groups: dict[tuple[int, str], Decimal] = {}
        for item in self.items:
            if item.category != "employee" or item.employee_id is None:
                continue
            key = (item.employee_id, item.source or "unknown")
            groups[key] = groups.get(key, Decimal("0")) + item.amount
        result = []
        for (employee_id, source), amount in sorted(groups.items(), key=lambda x: (x[0][0], x[0][1])):
            result.append({"employee_id": employee_id, "source": source, "amount": amount})
        return result

    def employee_total_for(self, employee_id: int, source: str | None = None) -> Decimal:
        total = Decimal("0")
        for item in self.items:
            if item.category == "employee" and item.employee_id == employee_id:
                if source is None or (item.source or "unknown") == source:
                    total += item.amount
        return total

    def totals(self) -> dict[str, Any]:
        categories = {}
        for category in HEADER_CATEGORIES:
            # «Итог» не создаётся автоматически: только если он есть в отчёте
            # или владелец явно задал его вручную.
            if category == "itog" and category not in self.manual_totals and not any(
                item.category == "itog" for item in self.items
            ):
                continue
            categories[category] = self.category_total(category)
        employees = self.employee_totals()
        return {
            "categories": categories,
            "computed": {c: self.category_sum(c) for c in HEADER_CATEGORIES},
            "discrepancies": {c: self.category_discrepancy(c) for c in HEADER_CATEGORIES if self.category_discrepancy(c) is not None},
            "employees": employees,
            "employee_total": sum((x["amount"] for x in employees), Decimal("0")),
            "expenses": self.category_sum("expense"),
            "debts": self.category_sum("debt"),
            "debt_policy": self.debt_policy,
            "debt_note": (
                "Долги учитываются отдельной строкой, как в действующем v3; "
                "автоматически из безнала не вычитаются"
                if self.debt_policy == "separate" else
                "Долги вычитаются из безнала согласно выбранному правилу"
            ),
        }

    def employee_remaining(self) -> Decimal:
        """Насколько заголовочный безнал/нал больше выплат сотрудникам (справочно)."""
        header = self.category_sum("beznal") + self.category_sum("nal")
        return header - sum((x["amount"] for x in self.employee_totals()), Decimal("0"))

    # ---------- проверка ----------

    def validate(self, employee_ids: set[int] | None = None) -> bool:
        try:
            selected = date.fromisoformat(self.report_date)
        except (TypeError, ValueError) as exc:
            raise ReportError("Неверная дата отчёта") from exc
        if selected > date.today():
            raise ReportError("Дата в будущем")
        if not self.ocr_complete:
            raise ReportError("Сверьте фотографию и подтвердите полноту отчёта")
        if self.ocr_stale:
            raise ReportError("Линия изменена после распознавания — распознайте заново или подтвердите результат")
        if not self.items:
            raise ReportError("Добавьте хотя бы одну позицию")
        if len(self.items) > 200:
            raise ReportError("Слишком много позиций")
        active = [item for item in self.items if item.category != "ignore"]
        if not active:
            raise ReportError("Нет учитываемых позиций")
        for number, item in enumerate(self.items, 1):
            if item.category not in CATEGORIES:
                raise ReportError(f"Позиция {number}: назначьте категорию")
            if item.category == "ignore":
                continue
            if item.uncertain:
                raise ReportError(f"Позиция {number}: подтвердите или исправьте неясное значение")
            if item.struck:
                raise ReportError(f"Позиция {number}: зачёркнутая позиция должна быть исключена")
            if item.amount is None:
                raise ReportError(f"Позиция {number}: неясная сумма")
            if item.category == "employee":
                if item.employee_id is None:
                    raise ReportError(f"Позиция {number}: выберите сотрудника")
                if employee_ids is not None and item.employee_id not in employee_ids:
                    raise ReportError(f"Позиция {number}: сотрудник не найден среди активных")
                if item.source not in ("beznal", "nal"):
                    raise ReportError(f"Позиция {number}: выберите безнал или наличные")
                if item.amount < 0:
                    raise ReportError(f"Позиция {number}: отрицательная выплата сотруднику")
        for category in HEADER_CATEGORIES:
            if category in self.manual_totals:
                parse_amount(self.manual_totals[category])
        return True

    # ---------- правки ----------

    def set_date(self, value: str) -> None:
        selected = date.fromisoformat(value)
        if selected > date.today() or selected.year < 2000:
            raise ReportError("Дата вне допустимого диапазона")
        self._push_history()
        self.report_date = selected.isoformat()

    def set_terms(self, index: int, terms: list[object], signs: list[object] | None = None) -> None:
        item = self._item(index)
        new_terms, new_signs = normalize_terms(list(terms), list(signs) if signs is not None else None)
        self._push_history()
        item.terms, item.signs = new_terms, new_signs
        item.raw = " ".join(f"{s if i else ('-' if s == '-' else '')}{decimal_text(t)}" for i, (t, s) in enumerate(zip(new_terms, new_signs)))
        item.uncertain = False
        item.struck = False
        item.origin = "manual"

    def set_term(self, index: int, term_index: int, value: object) -> None:
        item = self._item(index)
        if not 0 <= term_index < len(item.terms):
            raise ReportError("Слагаемое не найдено")
        new_terms = list(item.terms)
        new_terms[term_index] = parse_amount(value)
        self._push_history()
        item.terms = new_terms
        item.raw = " ".join(
            (("−" if s == "-" else "+") if i else ("−" if s == "-" else "")) + decimal_text(t)
            for i, (t, s) in enumerate(zip(new_terms, item.signs))
        )
        item.uncertain = False
        item.origin = "manual"

    def set_sign(self, index: int, term_index: int, sign: str) -> None:
        item = self._item(index)
        if sign not in ("+", "-"):
            raise ReportError("Знак может быть только + или −")
        if not 0 <= term_index < len(item.signs):
            raise ReportError("Слагаемое не найдено")
        self._push_history()
        signs = list(item.signs)
        signs[term_index] = sign
        item.signs = signs
        item.uncertain = False
        item.origin = "manual"

    def add_term(self, index: int, value: object, sign: str = "+") -> None:
        item = self._item(index)
        if sign not in ("+", "-"):
            raise ReportError("Неверный знак")
        number = parse_amount(value)
        self._push_history()
        item.terms.append(number)
        item.signs.append(sign)
        item.uncertain = False
        item.origin = "manual"

    def remove_term(self, index: int, term_index: int) -> None:
        item = self._item(index)
        if len(item.terms) <= 1:
            raise ReportError("Нельзя удалить единственное слагаемое; удалите всю позицию")
        if not 0 <= term_index < len(item.terms):
            raise ReportError("Слагаемое не найдено")
        self._push_history()
        del item.terms[term_index]
        del item.signs[term_index]
        item.uncertain = False
        item.origin = "manual"

    def set_category(self, index: int, category: str | None) -> None:
        if category is not None and category not in CATEGORIES:
            raise ReportError("Неизвестная категория")
        item = self._item(index)
        self._push_history()
        item.category = category
        if category != "employee":
            item.employee_id = None
            item.source = None
        item.origin = "manual"

    def set_employee(self, index: int, employee_id: int | None) -> None:
        item = self._item(index)
        self._push_history()
        item.category = "employee"
        item.employee_id = employee_id
        if item.source is None:
            item.source = "unknown"
        item.origin = "manual"

    def set_alias(self, index: int, alias: str) -> None:
        item = self._item(index)
        self._push_history()
        item.alias = str(alias).strip()[:40]
        item.origin = "manual"

    def set_source(self, index: int, source: str) -> None:
        if source not in SOURCES:
            raise ReportError("Неизвестный источник")
        item = self._item(index)
        self._push_history()
        item.source = source
        item.category = "employee"
        item.origin = "manual"

    def add_item(self, item: Item, at: int | None = None) -> int:
        if len(self.items) >= 200:
            raise ReportError("Слишком много позиций")
        self._push_history()
        if at is None:
            self.items.append(item)
            return len(self.items) - 1
        at = max(0, min(int(at), len(self.items)))
        self.items.insert(at, item)
        return at

    def delete_item(self, index: int) -> None:
        self._item(index)
        if len(self.items) <= 1:
            raise ReportError("Нельзя удалить последнюю позицию; отмените отчёт целиком")
        self._push_history()
        del self.items[index]

    def split_item(self, index: int, at_term: int) -> tuple[int, int]:
        item = self._item(index)
        if not 0 < at_term < len(item.terms):
            raise ReportError("Укажите, после какого слагаемого разделить")
        self._push_history()
        left = Item(terms=list(item.terms[:at_term]), signs=list(item.signs[:at_term]), raw=item.raw,
                    category=item.category, employee_id=item.employee_id, alias=item.alias,
                    source=item.source, uncertain=item.uncertain, struck=item.struck, origin="manual")
        right = Item(terms=list(item.terms[at_term:]), signs=list(item.signs[at_term:]), raw=item.raw,
                     category=item.category, employee_id=item.employee_id, alias=item.alias,
                     source=item.source, uncertain=item.uncertain, struck=item.struck, origin="manual")
        self.items[index:index + 1] = [left, right]
        return index, index + 1

    def merge_items(self, index: int, other: int) -> int:
        if index == other:
            raise ReportError("Нельзя объединить позицию с самой собой")
        first = self._item(index)
        second = self._item(other)
        self._push_history()
        category = first.category if first.category == second.category else None
        employee_id = first.employee_id if first.employee_id == second.employee_id else None
        source = first.source if first.source == second.source else None
        merged = Item(
            terms=list(first.terms) + list(second.terms),
            signs=list(first.signs) + list(second.signs),
            raw=(first.raw + " + " + second.raw)[:300],
            category=category,
            employee_id=employee_id,
            alias=first.alias if first.alias == second.alias else "",
            source=source,
            uncertain=first.uncertain or second.uncertain or category is None,
            struck=first.struck or second.struck,
            origin="manual",
            note=(first.note + " " + second.note).strip()[:300],
        )
        target = min(index, other)
        for position in sorted({index, other}, reverse=True):
            del self.items[position]
        self.items.insert(target, merged)
        return target

    def move_item(self, index: int, delta: int) -> int:
        item = self._item(index)
        target = index + int(delta)
        if target < 0 or target >= len(self.items):
            raise ReportError("Дальше двигать некуда")
        self._push_history()
        del self.items[index]
        self.items.insert(target, item)
        return target

    def set_category_total(self, category: str, value: object | None) -> None:
        if category not in HEADER_CATEGORIES:
            raise ReportError("Итог можно задать только для Безнала, Наличных или Итога")
        if value is None:
            if category in self.manual_totals:
                self._push_history()
                del self.manual_totals[category]
            return
        number = parse_amount(value)
        self._push_history()
        self.manual_totals[category] = decimal_text(number)
        if category == "itog":
            return
        # Суммы сотрудников не меняются: расхождение показывается отдельно.

    def _item(self, index: int) -> Item:
        if not isinstance(index, int) or not 0 <= index < len(self.items):
            raise ReportError("Позиция не найдена")
        return self.items[index]

    def index_of(self, item_id: str) -> int:
        for index, item in enumerate(self.items):
            if item.item_id == item_id:
                return index
        raise ReportError("Позиция больше не существует — обнови список")


def _item_signature(item: Item) -> tuple[str, str, str, str]:
    return (
        decimal_text(item.amount),
        str(item.category),
        str(item.employee_id),
        str(item.source),
    )


def classify_errors(original: Report, corrected: Report) -> list[str]:
    """Типы исправлений между первоначальным и подтверждённым отчётом."""
    errors: list[str] = []
    if original.report_date != corrected.report_date:
        errors.append("date_changed")
    if original.boundary != corrected.boundary:
        errors.append("line_changed")
    old_by_id = {item.item_id: item for item in original.items}
    new_by_id = {item.item_id: item for item in corrected.items}
    only_new = set(new_by_id) - set(old_by_id)
    only_old = set(old_by_id) - set(new_by_id)
    split = len(corrected.items) > len(original.items) and bool(only_old)
    merged = len(corrected.items) < len(original.items) and bool(only_new)
    if only_new and not split and not merged:
        errors.append("item_added")
    if only_old and not split and not merged:
        errors.append("item_deleted")
    if split:
        errors.append("item_split")
    if merged:
        errors.append("item_merged")
    for item_id in set(old_by_id) & set(new_by_id):
        old, new = old_by_id[item_id], new_by_id[item_id]
        if [decimal_text(t) for t in old.terms] != [decimal_text(t) for t in new.terms]:
            errors.append("amount_changed")
        if old.signs != new.signs:
            errors.append("sign_changed")
        if old.category != new.category:
            errors.append("category_changed")
        if old.employee_id != new.employee_id:
            errors.append("employee_changed")
        if (old.source or "unknown") != (new.source or "unknown"):
            errors.append("source_changed")
        if old.alias != new.alias:
            errors.append("alias_changed")
    if len(corrected.items) > len(original.items) and "item_added" not in errors:
        errors.append("item_split")
    if len(corrected.items) < len(original.items) and "item_deleted" not in errors:
        errors.append("item_merged")
    if original.manual_totals != corrected.manual_totals:
        errors.append("total_overridden")
    ordered_old = [item.item_id for item in original.items if item.item_id in new_by_id]
    ordered_new = [item.item_id for item in corrected.items if item.item_id in old_by_id]
    if ordered_old != ordered_new:
        errors.append("order_changed")
    return sorted(set(errors))


__all__ = [
    "CATEGORIES", "CATEGORY_LABELS", "HEADER_CATEGORIES", "SOURCES", "SOURCE_LABELS",
    "Item", "Report", "ReportError", "classify_errors", "new_id",
]

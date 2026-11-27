"""Тексты и клавиатуры тестового режима (без Telegram-вызовов)."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .aliases import AliasBook
from .model import (
    CATEGORIES, CATEGORY_LABELS, HEADER_CATEGORIES, SOURCES, SOURCE_LABELS, Item, Report,
)
from .money import format_amount
from .training import error_summary_text

PAGE_SIZE = 5
EMPLOYEE_PAGE = 8


def button(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def keyboard(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cbd(nonce: str, action: str) -> str:
    return f"tt:{nonce}:{action}"


def category_text(item: Item, book: AliasBook) -> str:
    label = CATEGORY_LABELS.get(item.category, "?")
    if item.category == "employee":
        name = book.employee_name(item.employee_id) or "сотрудник не выбран"
        label += f": {name} / {SOURCE_LABELS.get(item.source or 'unknown', '?')}"
    return label


def main_text(store) -> str:
    draft = store.setting("has_draft", "0")
    lines = [
        "🧪 MAX FINANCE TEST",
        "",
        "Тестовый режим внутри действующего бота.",
        "Фотографии, распознавание и исправления хранятся отдельно.",
        "Рабочая Google-таблица не изменяется.",
        "",
        "Отправь фотографию отчёта или открой базу примеров.",
    ]
    if draft == "1":
        lines.append("Есть незавершённый тестовый черновик — нажми «Продолжить».")
    return "\n".join(lines)


def main_keyboard(nonce: str, has_draft: bool = False) -> InlineKeyboardMarkup:
    rows = []
    if has_draft:
        rows.append([button("▶️ Продолжить черновик", cbd(nonce, "resume"))])
    rows.extend([
        [button("📷 Новый отчёт: отправь фото", cbd(nonce, "newphoto"))],
        [button("📚 База примеров", cbd(nonce, "examples")), button("👥 Словарь", cbd(nonce, "staff"))],
        [button("⚙️ Линия распознавания", cbd(nonce, "linehelp"))],
        [button("↩️ В рабочий режим", cbd(nonce, "work"))],
    ])
    return keyboard(rows)


def items_text(report: Report, page: int, book: AliasBook, store=None) -> str:
    start = page * PAGE_SIZE
    end = min(len(report.items), start + PAGE_SIZE)
    lines = [
        "🧪 MAX FINANCE TEST · " + report.report_date,
        f"Позиции {start + 1}–{end} из {len(report.items)}" if report.items else "Позиций пока нет",
        "",
    ]
    for index in range(start, end):
        item = report.items[index]
        mark = "⚠️ " if item.uncertain else ""
        lines.append(f"{index + 1}. {mark}{item.display()}")
        lines.append("    " + category_text(item, book))
    totals = report.totals()
    lines.append("")
    for category in HEADER_CATEGORIES:
        if category not in totals["categories"]:
            continue
        value = totals["categories"][category]
        manual = report.category_discrepancy(category)
        suffix = ""
        if manual is not None:
            suffix = f" (введено вручную; расхождение {format_amount(manual)} ₽)"
        lines.append(f"{CATEGORY_LABELS[category]}: {format_amount(value)} ₽{suffix}")
    if totals["employees"]:
        lines.append(f"Выплаты сотрудникам: {format_amount(totals['employee_total'])} ₽")
    if totals["expenses"]:
        lines.append(f"Расходы: {format_amount(totals['expenses'])} ₽")
    if totals["debts"]:
        lines.append(f"Долги: {format_amount(totals['debts'])} ₽ — {totals['debt_note']}")
    if report.warnings:
        lines.extend(["", "⚠️ " + " | ".join(report.warnings)[:600]])
    if not report.photo_reviewed:
        lines.append("⚠️ Сверь все строки с фотографией и нажми «Я сверил фото».")
    if report.ocr_stale:
        lines.append("⚠️ Линия изменена после распознавания. Распознай заново.")
    lines.extend(["", "Нажми позицию, чтобы изменить любые данные."])
    return "\n".join(lines)[:3900]


def items_keyboard(report: Report, page: int, nonce: str) -> InlineKeyboardMarkup:
    start = page * PAGE_SIZE
    end = min(len(report.items), start + PAGE_SIZE)
    rows = []
    for index in range(start, end):
        item = report.items[index]
        prefix = "⚠️ " if item.uncertain else ""
        rows.append([button(f"{prefix}{index + 1}. {item.display()[:52]}", cbd(nonce, f"item:{item.item_id}"))])
    nav = []
    if page > 0:
        nav.append(button("◀️", cbd(nonce, f"page:{page - 1}")))
    if end < len(report.items):
        nav.append(button("▶️", cbd(nonce, f"page:{page + 1}")))
    if nav:
        rows.append(nav)
    if not report.photo_reviewed:
        rows.append([button("📷 Я сверил фото", cbd(nonce, "ackphoto"))])
    rows.extend([
        [button("➕ Добавить позицию", cbd(nonce, "add")), button("Σ Итоги", cbd(nonce, "totals"))],
        [button("📅 Дата", cbd(nonce, "date")), button("✂️ Линия", cbd(nonce, "lineedit"))],
        [button("🔁 Распознать заново", cbd(nonce, "rerun"))],
        [button("↩️ Отменить действие", cbd(nonce, "undo")), button("✅ Проверить", cbd(nonce, "review"))],
        [button("❌ Отменить отчёт", cbd(nonce, "cancel")), button("🏠 Меню", cbd(nonce, "menu"))],
    ])
    return keyboard(rows)


def item_text(report: Report, index: int, book: AliasBook) -> str:
    item = report.items[index]
    lines = [
        f"Позиция {index + 1}",
        f"Сумма: {format_amount(item.amount)} ₽",
        "Слагаемые: " + " ".join(
            (("−" if sign == "-" else "+") if number else ("−" if sign == "-" else "")) + format_amount(term)
            for number, (term, sign) in enumerate(zip(item.terms, item.signs))
        ),
        "Категория: " + category_text(item, book),
        "Буквенное обозначение: " + (item.alias or "—"),
        "Источник: " + SOURCE_LABELS.get(item.source or "unknown", "—"),
        "Исходная запись: " + (item.raw or "—"),
    ]
    if item.note:
        lines.append("Пояснение с фото: " + item.note)
    if item.bbox:
        lines.append("Координаты: " + ", ".join(f"{x:.3f}" for x in item.bbox))
    if item.uncertain:
        lines.append("⚠️ Требует подтверждения")
    if item.struck:
        lines.append("⚠️ Зачёркнуто, исключено")
    lines.append("")
    lines.append("Доступно любое изменение.")
    return "\n".join(lines)[:3500]


def item_keyboard(report: Report, index: int, nonce: str) -> InlineKeyboardMarkup:
    item = report.items[index]
    key = item.item_id
    rows = [
        [button("💰 Сумма/выражение", cbd(nonce, f"amount:{key}"))],
        [button("🔢 Слагаемые и знаки", cbd(nonce, f"terms:{key}"))],
        [button("👤 Сотрудник", cbd(nonce, f"employee:{key}")), button("🔤 Буква", cbd(nonce, f"alias:{key}"))],
        [button("🏷 Категория", cbd(nonce, f"category:{key}")), button("💳 Источник", cbd(nonce, f"source:{key}"))],
        [button("✂️ Разделить", cbd(nonce, f"split:{key}")), button("🔗 Объединить", cbd(nonce, f"merge:{key}"))],
        [button("⬆️ Выше", cbd(nonce, f"up:{key}")), button("⬇️ Ниже", cbd(nonce, f"down:{key}"))],
        [button("🗑 Удалить", cbd(nonce, f"delete:{key}"))],
        [button("↩️ К списку", cbd(nonce, f"page:{index // PAGE_SIZE}"))],
    ]
    return keyboard(rows)


def terms_text(report: Report, index: int) -> str:
    item = report.items[index]
    lines = [f"Слагаемые позиции {index + 1}", ""]
    for number, (term, sign) in enumerate(zip(item.terms, item.signs)):
        lines.append(f"{number + 1}. {sign} {format_amount(term)} ₽")
    lines.extend(["", "Можно изменить число, знак, добавить или удалить слагаемое."])
    return "\n".join(lines)


def terms_keyboard(report: Report, index: int, nonce: str) -> InlineKeyboardMarkup:
    item = report.items[index]
    key = item.item_id
    rows = [[button(f"{n + 1}. {s} {format_amount(t)}", cbd(nonce, f"term:{key}:{n}"))]
            for n, (t, s) in enumerate(zip(item.terms, item.signs))]
    rows.append([button("➕ Добавить слагаемое", cbd(nonce, f"addterm:{key}"))])
    rows.append([button("↩️ Назад", cbd(nonce, f"item:{key}"))])
    return keyboard(rows)


def term_keyboard(item_id: str, term: int, nonce: str) -> InlineKeyboardMarkup:
    return keyboard([
        [button("✏️ Изменить число", cbd(nonce, f"termvalue:{item_id}:{term}"))],
        [button("➕ Сделать плюсом", cbd(nonce, f"signplus:{item_id}:{term}")),
         button("➖ Сделать минусом", cbd(nonce, f"signminus:{item_id}:{term}"))],
        [button("🗑 Удалить слагаемое", cbd(nonce, f"termdel:{item_id}:{term}"))],
        [button("↩️ Назад", cbd(nonce, f"terms:{item_id}"))],
    ])


def employees_keyboard(book: AliasBook, item_id: str, nonce: str, page: int = 0) -> InlineKeyboardMarkup:
    people = book.staff_options()
    start = page * EMPLOYEE_PAGE
    rows = []
    for employee_id, name in people[start:start + EMPLOYEE_PAGE]:
        aliases = ", ".join(book.aliases_for(employee_id)[:6])
        label = name + (f" ({aliases})" if aliases else "")
        rows.append([button(label, cbd(nonce, f"setemp:{item_id}:{employee_id}"))])
    nav = []
    if page > 0:
        nav.append(button("◀️", cbd(nonce, f"emppage:{item_id}:{page - 1}")))
    if start + EMPLOYEE_PAGE < len(people):
        nav.append(button("▶️", cbd(nonce, f"emppage:{item_id}:{page + 1}")))
    if nav:
        rows.append(nav)
    rows.append([button("🚫 Без сотрудника", cbd(nonce, f"setemp:{item_id}:0"))])
    rows.append([button("↩️ Назад", cbd(nonce, f"item:{item_id}"))])
    return keyboard(rows)


def categories_keyboard(item_id: str, nonce: str) -> InlineKeyboardMarkup:
    rows = [[button(CATEGORY_LABELS[c], cbd(nonce, f"setcat:{item_id}:{c}"))] for c in CATEGORIES]
    rows.append([button("↩️ Назад", cbd(nonce, f"item:{item_id}"))])
    return keyboard(rows)


def sources_keyboard(item_id: str, nonce: str) -> InlineKeyboardMarkup:
    rows = [[button(SOURCE_LABELS[s], cbd(nonce, f"setsrc:{item_id}:{s}"))] for s in SOURCES]
    rows.append([button("↩️ Назад", cbd(nonce, f"item:{item_id}"))])
    return keyboard(rows)


def split_keyboard(report: Report, index: int, nonce: str) -> InlineKeyboardMarkup:
    item = report.items[index]
    key = item.item_id
    rows = [[button(f"После слагаемого {n + 1} ({format_amount(item.terms[n])})",
                    cbd(nonce, f"splitat:{key}:{n + 1}"))] for n in range(len(item.terms) - 1)]
    if len(item.terms) == 1:
        rows.append([button("Разделить на две суммы", cbd(nonce, f"splitamount:{key}"))])
    rows.append([button("↩️ Назад", cbd(nonce, f"item:{key}"))])
    return keyboard(rows)


def merge_keyboard(report: Report, index: int, nonce: str, book: AliasBook) -> InlineKeyboardMarkup:
    item = report.items[index]
    rows = []
    for other, candidate in enumerate(report.items):
        if other == index:
            continue
        rows.append([button(f"{other + 1}. {candidate.display()[:40]}",
                            cbd(nonce, f"mergeat:{item.item_id}:{candidate.item_id}"))])
        if len(rows) >= 10:
            break
    rows.append([button("↩️ Назад", cbd(nonce, f"item:{item.item_id}"))])
    return keyboard(rows)


def totals_text(report: Report) -> str:
    lines = ["Σ Итоги категорий", ""]
    for category in HEADER_CATEGORIES:
        computed = report.category_sum(category)
        manual = report.category_discrepancy(category)
        if not computed and category not in report.manual_totals and category == "itog":
            lines.append(f"{CATEGORY_LABELS[category]}: нет на фото (не создаём)")
            continue
        if manual is None:
            lines.append(f"{CATEGORY_LABELS[category]}: {format_amount(computed)} ₽ (вычислено)")
        else:
            lines.append(
                f"{CATEGORY_LABELS[category]}: {format_amount(report.category_total(category))} ₽ введено вручную, "
                f"вычислено {format_amount(computed)} ₽, расхождение {format_amount(manual)} ₽"
            )
    lines.append("")
    employees = report.employee_totals()
    if employees:
        lines.append("Выплаты сотрудникам (не меняются при правке итога категории):")
        for row in employees:
            lines.append(f"• #{row['employee_id']} · {SOURCE_LABELS.get(row['source'], '?')}: {format_amount(row['amount'])} ₽")
        lines.append(f"Всего выплат: {format_amount(report.totals()['employee_total'])} ₽")
    else:
        lines.append("Выплат сотрудникам нет.")
    if report.manual_totals:
        lines.extend(["", "Ручной итог не распределяет деньги по сотрудникам. Расхождение нужно подтвердить или исправить."])
    return "\n".join(lines)


def totals_keyboard(nonce: str) -> InlineKeyboardMarkup:
    return keyboard([
        [button("Безнал", cbd(nonce, "total:beznal")), button("Наличные", cbd(nonce, "total:nal"))],
        [button("Итог", cbd(nonce, "total:itog"))],
        [button("↩️ К позициям", cbd(nonce, "page:0"))],
    ])


def summary_text(report: Report, book: AliasBook) -> str:
    lines = [
        "✅ ПРОВЕРКА ТЕСТОВОГО ОТЧЁТА",
        f"📅 {report.report_date}",
        "",
    ]
    for index, item in enumerate(report.items, 1):
        lines.append(f"{index}. {item.display()} · {category_text(item, book)}")
    totals = report.totals()
    lines.append("")
    for category, value in totals["categories"].items():
        lines.append(f"{CATEGORY_LABELS[category]}: {format_amount(value)} ₽")
    if totals["employees"]:
        lines.append(f"Выплаты сотрудникам: {format_amount(totals['employee_total'])} ₽")
    lines.extend([
        "",
        "Подтверждение сохранит пример в тестовую базу.",
        "В рабочую Google-таблицу ничего не будет отправлено.",
    ])
    return "\n".join(lines)[:3900]


def confirm_keyboard(nonce: str, version: int) -> InlineKeyboardMarkup:
    return keyboard([
        [button("✅ Подтвердить и сохранить в тест", cbd(nonce, f"confirm:{version}"))],
        [button("↩️ Вернуться к правке", cbd(nonce, "page:0"))],
        [button("❌ Отменить отчёт", cbd(nonce, "cancel"))],
    ])


def examples_text(store) -> str:
    stats = store.stats()
    return (
        "📚 База подтверждённых примеров\n\n"
        f"Всего: {stats['total']}\n"
        f"Обучающих: {stats['train']}\n"
        f"Отложенных (holdout): {stats['holdout']}\n"
        f"Период: {stats['first'] or '—'} … {stats['last'] or '—'}\n\n"
        + error_summary_text(store)
        + "\n\nВ базу попадают только подтверждённые отчёты. Неподтверждённые суммы не используются."
    )


def staff_text(store) -> str:
    book = store.alias_book()
    lines = ["👥 Словарь сотрудников", ""]
    for employee_id, name in book.staff_options():
        aliases = ", ".join(book.aliases_for(employee_id)) or "—"
        lines.append(f"{name}: {aliases}")
    conflicts = store.seed_conflicts()
    if conflicts:
        lines.extend(["", "⚠️ Конфликты обозначений (не объединены автоматически):"])
        for conflict in conflicts:
            lines.append(f"• {conflict['alias']} → {conflict['wanted']} (занято #{conflict['existing']})")
    lines.extend(["", "Выбери сотрудника, чтобы изменить имя или буквы."])
    return "\n".join(lines)[:3500]


def staff_keyboard(store, nonce: str) -> InlineKeyboardMarkup:
    book = store.alias_book()
    rows = [[button(name, cbd(nonce, f"staff:{employee_id}"))]
            for employee_id, name in book.staff_options()]
    rows.append([button("➕ Добавить сотрудника", cbd(nonce, "staffadd"))])
    rows.append([button("🏠 Меню", cbd(nonce, "menu"))])
    return keyboard(rows)


def staff_card_text(store, employee_id: int) -> str:
    book = store.alias_book()
    name = book.employee_name(employee_id) or "?"
    aliases = ", ".join(book.aliases_for(employee_id)) or "—"
    return (
        f"👤 {name}\n\n"
        f"Обозначения: {aliases}\n\n"
        "Можно переименовать сотрудника, добавить или удалить буквенное обозначение. "
        "История выплат при этом сохраняется."
    )


def staff_card_keyboard(employee_id: int, nonce: str) -> InlineKeyboardMarkup:
    return keyboard([
        [button("✏️ Переименовать", cbd(nonce, f"staffrename:{employee_id}"))],
        [button("➕ Добавить букву", cbd(nonce, f"aliasadd:{employee_id}"))],
        [button("🗑 Убрать букву", cbd(nonce, f"aliasdel:{employee_id}"))],
        [button("🚫 Убрать сотрудника", cbd(nonce, f"staffremove:{employee_id}"))],
        [button("↩️ К словарю", cbd(nonce, "staff"))],
    ])


__all__ = [
    "button", "categories_keyboard", "cbd", "confirm_keyboard", "employees_keyboard",
    "examples_text", "item_keyboard", "item_text", "items_keyboard", "items_text",
    "keyboard", "main_keyboard", "main_text", "merge_keyboard", "sources_keyboard",
    "split_keyboard", "staff_card_keyboard", "staff_card_text", "staff_keyboard",
    "staff_text", "summary_text", "term_keyboard", "terms_keyboard", "terms_text",
    "totals_keyboard", "totals_text",
]

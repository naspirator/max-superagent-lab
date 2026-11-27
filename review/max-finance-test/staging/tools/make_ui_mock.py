"""Сгенерировать HTML-макет тестового интерфейса для отчёта.

Это именно макет по реальным текстам и клавиатурам aiogram, а не снимок
живого Telegram: запуск второго polling на том же токене запрещён.
"""
from __future__ import annotations

import html
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, r"E:\MAX-FINANCE-TEST\staging")

from maxfinance_test import ui
from maxfinance_test.aliases import AliasBook, DEFAULT_ALIASES
from maxfinance_test.model import Item, Report
from maxfinance_test.money import format_amount

OUT = Path(r"E:\MAX-FINANCE-TEST\reports\ui-mock.html")

staff = [
    {"id": 1, "name": "ПЕТ"}, {"id": 2, "name": "РОС"}, {"id": 4, "name": "ОЛИ"},
    {"id": 5, "name": "ТОЛ"}, {"id": 6, "name": "ДАН"}, {"id": 7, "name": "ВЛА"},
    {"id": 10, "name": "ЛЕХ"},
]
book = AliasBook(staff, {a: next(p["id"] for p in staff if p["name"] == n)
                         for a, n in DEFAULT_ALIASES.items() if n in {p["name"] for p in staff}})
report = Report("2026-11-21", items=[
    Item([Decimal("36800")], category="beznal", alias="Б/Н"),
    Item([Decimal("4500")], category="employee", employee_id=1, source="beznal", alias="П"),
    Item([Decimal("17200")], category="nal", alias="Нал"),
    Item([Decimal("4000")], category="employee", employee_id=5, source="nal", alias="Т"),
    Item([Decimal("4000")], category="employee", employee_id=7, source="nal", alias="В"),
    Item([Decimal("9200")], category="employee", employee_id=1, source="nal", alias="П", uncertain=True),
], version=1)


def markup_html(markup, prefix):
    if markup is None:
        return ""
    rows = []
    for row in markup.inline_keyboard:
        cells = "".join(
            f'<button class="btn">{html.escape(button.text)}</button>' for button in row
        )
        rows.append(f'<div class="row">{cells}</div>')
    return f'<div class="keyboard">{"" .join(rows)}</div>'


def bubble(text, markup=None):
    return (
        '<div class="msg"><div class="author">MAX FINANCE TEST · бот</div>'
        f'<div class="bubble"><pre>{html.escape(text)}</pre>{markup_html(markup, "")}</div></div>'
    )


sections = [
    ("Главное меню тестового режима", bubble(ui.main_text(type("S", (), {"setting": lambda *a: "0"})()),
                                             ui.main_keyboard("demo", has_draft=True))),
    ("Список позиций после распознавания", bubble(ui.items_text(report, 0, book), ui.items_keyboard(report, 0, "demo"))),
    ("Карточка позиции: доступно любое изменение", bubble(ui.item_text(report, 1, book), ui.item_keyboard(report, 1, "demo"))),
    ("Итоги категорий: ручной итог не меняет выплаты", bubble(ui.totals_text(report), ui.totals_keyboard("demo"))),
    ("Проверка и подтверждение", bubble(ui.summary_text(report, book), ui.confirm_keyboard("demo"))),
]

cards = []
for title, content in sections:
    cards.append(f'<section><h2>{html.escape(title)}</h2>{content}</section>')

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(
    """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MAX FINANCE TEST — макет интерфейса</title>
<style>
body{font-family:-apple-system,"Segoe UI",Roboto,sans-serif;background:#dfe7ee;margin:0;padding:24px;color:#17212b}
header{max-width:860px;margin:0 auto 18px;background:#fff;border-radius:14px;padding:16px 20px;box-shadow:0 2px 10px #0001}
header h1{margin:0 0 6px;font-size:20px}header p{margin:0;color:#5b6b7a;font-size:13px}
section{max-width:860px;margin:0 auto 22px;background:#fff;border-radius:14px;padding:14px 16px 18px;box-shadow:0 2px 10px #0001}
h2{font-size:15px;margin:4px 0 12px;color:#2b5278}
.msg{display:flex;flex-direction:column;align-items:flex-start;margin:8px 0}
.author{font-size:11px;color:#2b5278;margin:0 0 4px 10px}
.bubble{background:#fff;border:1px solid #d5e0ea;border-radius:12px 12px 12px 4px;padding:10px 12px;max-width:780px}
pre{white-space:pre-wrap;font-family:inherit;font-size:13px;line-height:1.45;margin:0}
.keyboard{display:flex;flex-direction:column;gap:5px;margin-top:10px}
.row{display:flex;gap:5px}
.btn{flex:1;background:#e8f0f7;border:1px solid #c5d7e6;border-radius:8px;padding:7px 8px;font-size:12px;color:#1f4b73;text-align:center}
.note{max-width:860px;margin:0 auto 18px;font-size:12px;color:#5b6b7a}
</style></head><body>
<header><h1>MAX FINANCE TEST — интерфейс в Telegram</h1>
<p>Макет по реальным текстам и inline-клавиатурам aiogram. Не снимок живого Telegram:
запуск второго обработчика на действующем токене запрещён до согласования владельца.</p></header>
<div class="note">Все суммы и итоги на экране — демонстрационные. Тестовый режим не отправляет данные в рабочую Google-таблицу.</div>
""" + "".join(cards) + "</body></html>",
    encoding="utf-8",
)
print(OUT)

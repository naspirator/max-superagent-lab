"""База подтверждённых примеров и обратная связь.

Никакого дообучения весов нейросети здесь нет. База работает как
retrieval-подсказка: в запрос к модели попадают только примеры, которые
владелец подтвердил. Неподтверждённые суммы в подсказку не попадают.
"""
from __future__ import annotations

import json
from collections import Counter
from typing import Any

from .model import Report

ERROR_LABELS = {
    "amount_changed": "сумма",
    "sign_changed": "знак",
    "employee_changed": "сотрудник",
    "alias_changed": "буквенное обозначение",
    "category_changed": "категория",
    "source_changed": "безнал/наличные",
    "item_added": "добавлена позиция",
    "item_deleted": "удалена позиция",
    "item_split": "разделение",
    "item_merged": "объединение",
    "order_changed": "порядок строк",
    "date_changed": "дата",
    "line_changed": "линия",
    "total_overridden": "итог категории",
}


def error_stats(store) -> dict[str, Any]:
    counter: Counter[str] = Counter()
    for example in store.examples():
        counter.update(example.get("error_types") or [])
    return {
        "examples": len(store.examples()),
        "by_type": {key: counter.get(key, 0) for key in ERROR_LABELS},
        "labels": ERROR_LABELS,
    }


def example_hint(store, limit: int = 3) -> str:
    """Текстовая подсказка из подтверждённых обучающих примеров."""
    examples = store.few_shot(limit)
    lines = []
    for example in examples:
        try:
            report = Report.from_json(json.loads(example["confirmed_json"]))
        except Exception:
            continue
        parts = []
        for item in report.items:
            if item.category == "ignore":
                continue
            marker = item.alias or item.category or "?"
            parts.append(f"{marker}:{item.amount}:{item.category or '?'}:{item.source or '-'}")
        if parts:
            lines.append("Пример " + example["report_date"] + ": " + "; ".join(parts[:20]))
    if not lines:
        return ""
    return (
        "\nПодтверждённые владельцем примеры (используй только как образец оформления, "
        "не переноси суммы на новое фото):\n" + "\n".join(lines) + "\n"
    )


def error_summary_text(store) -> str:
    stats = error_stats(store)
    lines = [f"📚 Подтверждённых примеров: {stats['examples']}"]
    for key, count in stats["by_type"].items():
        if count:
            lines.append(f"• {ERROR_LABELS[key]}: {count}")
    if stats["examples"] == 0:
        lines.append("Пока пусто. Пример появится после подтверждения отчёта в тестовом режиме.")
    return "\n".join(lines)


__all__ = ["ERROR_LABELS", "error_stats", "error_summary_text", "example_hint"]

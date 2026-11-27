"""Ансамбль: старый OCR для сумм + новый OCR для меток и категорий.

Старый механизм (ocr_v3) хорошо извлекает денежные числа, но не знает
сотрудников и категорий. Новый механизм знает структуру, но на трудном
почерке иногда теряет или искажает число. Ансамбль берёт число из старого
результата, если оно относится к той же строке, а метку и категорию — из
нового. Это не дообучение весов и не дорогая модель: оба вызова используют
уже существующий vis-google/gemini-2.5-flash.
"""
from __future__ import annotations

from decimal import Decimal

from .model import Item, Report
from .money import decimal_text


def _vertical_overlap(a, b) -> float:
    if not a or not b:
        return 0.0
    top = max(a[1], b[1])
    bottom = min(a[3], b[3])
    return max(0.0, bottom - top)


def _horizontal_gap(a, b) -> float:
    if not a or not b:
        return 1.0
    if a[2] < b[0]:
        return b[0] - a[2]
    if b[2] < a[0]:
        return a[0] - b[2]
    return 0.0


def _best_old(item: Item, old_positions) -> object | None:
    if not item.bbox:
        return None
    best = None
    best_score = -1.0
    for position in old_positions:
        bbox = getattr(position, "bbox", None)
        if not bbox:
            continue
        # Строгое совпадение области: иначе легко подставить число соседней
        # строки и ухудшить корректный результат нового OCR.
        inter_w = max(0.0, min(item.bbox[2], bbox[2]) - max(item.bbox[0], bbox[0]))
        inter_h = max(0.0, min(item.bbox[3], bbox[3]) - max(item.bbox[1], bbox[1]))
        intersection = inter_w * inter_h
        area_item = max(1e-6, (item.bbox[2] - item.bbox[0]) * (item.bbox[3] - item.bbox[1]))
        area_old = max(1e-6, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))
        iou = intersection / max(1e-6, area_item + area_old - intersection)
        if iou < 0.15:
            continue
        gap = _horizontal_gap(item.bbox, bbox)
        if gap > 0.08:
            continue
        score = iou - gap
        if score > best_score:
            best_score = score
            best = position
    return best


def merge_amounts(report: Report, old_positions) -> tuple[Report, int]:
    """Подставить суммы старого OCR только там, где новый результат сомнителен."""
    replaced = 0
    used = set()
    for item in report.items:
        if not (item.uncertain or item.amount < 0 or (len(item.terms) > 1)):
            continue
        # Старый OCR не умеет минус: нельзя заменять выражение со знаками
        # на положительную сумму.
        if any(sign == "-" for sign in item.signs):
            continue
        # Минус мог быть записан как terms=["-500"] при signs=["+"]:
        # старый OCR не умеет минус, поэтому такую позицию не трогаем.
        if any(term < 0 for term in item.terms):
            continue
        position = _best_old(item, old_positions)
        if position is None or id(position) in used:
            continue
        terms = [Decimal(str(x)) for x in position.terms]
        if not terms:
            continue
        if [decimal_text(x) for x in terms] == [decimal_text(x) for x in item.terms] and all(s == "+" for s in item.signs):
            used.add(id(position))
            continue
        # Старый OCR не поддерживает минус, поэтому переносим только
        # положительные слагаемые и только если это не ломает выражение.
        if any(t < 0 for t in terms):
            continue
        item.terms = terms
        item.signs = ["+"] * len(terms)
        item.origin = "ensemble"
        if "сумма уточнена старым OCR" not in item.note:
            item.note = (item.note + " сумма уточнена старым OCR").strip()[:300]
        replaced += 1
        used.add(id(position))
    if replaced:
        report.warnings.append(f"Суммы сверены со старым OCR: {replaced} поз.")
    report.engine_version = report.engine_version + "+ensemble"
    return report, replaced


async def recognize_ensemble(client, image_bytes, boundary, book, examples: str,
                             old_recognize) -> Report:
    from .ocr import recognize

    report = await recognize(client, image_bytes, boundary, book, examples)
    try:
        old = await old_recognize(client, image_bytes, boundary)
    except Exception:
        return report
    return merge_amounts(report, old.positions)[0]


__all__ = ["merge_amounts", "recognize_ensemble"]

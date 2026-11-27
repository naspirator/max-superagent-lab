"""Линия начала распознавания.

Функции расчёта совместимы с действующим ботом v3: линия задаётся двумя
долями высоты (левый и правый край), всё выше линии игнорируется. Добавлено
ранжирование кандидатов, чтобы Б/Н в верхней таблице работ не принимался
за начало финансового блока автоматически. Ручное управление линией всегда
главнее автоматики.
"""
from __future__ import annotations

import io
import math
import re
import shutil
import subprocess

from PIL import Image, ImageDraw, ImageOps

LABEL_RE = re.compile(r"(?<![А-ЯЁA-Z])(Б/Н|БН|BN|БЕЗНАЛ)(?![А-ЯЁA-Z])")
NUMBER_RE = re.compile(r"^[+\-−–—]?\d{1,7}(?:[.,]\d{1,2})?$")


def _clean(text: object) -> str:
    return str(text or "").strip().upper().replace(" ", "")


def find_labels(rows: list[dict], width: int, height: int) -> list[dict]:
    """Все найденные метки Б/Н с координатами и уверенностью."""
    if not width or not height:
        return []
    result = []
    for row in rows:
        text = _clean(row.get("text"))
        if not LABEL_RE.search(text):
            continue
        try:
            confidence = float(row["confidence"])
            top = int(row["top"])
            left = int(row["left"])
            w = int(row["width"])
            h = int(row["height"])
        except (KeyError, TypeError, ValueError):
            continue
        if not 0 <= top < height or not 0 <= left < width or w <= 0 or h <= 0:
            continue
        result.append({
            "top": top, "left": left, "width": w, "height": h,
            "confidence": confidence, "text": text,
            "y": top / height,
        })
    return sorted(result, key=lambda item: (item["top"], item["left"]))


def find_first_label(rows, width, height):
    """Совместимость с v3: первая уверенная метка."""
    labels = [x for x in find_labels(rows, width, height) if x["confidence"] >= 85]
    if not labels:
        return None
    top = labels[0]["top"]
    return (top / height, top / height)


def _block_score(label: dict, rows: list[dict], width: int, height: int) -> float:
    """Оценить, похоже ли ниже метки на финансовый блок.

    Считаем числовые токены и короткие буквенные обозначения в полосе ниже
    метки. Верхняя таблица работ обычно даёт мало денежных чисел и много
    служебных подписей, поэтому получает меньший вес.
    """
    y0 = label["top"] / height
    if y0 > 0.75:
        return -100.0
    score = 0.0
    numbers = 0
    labels = 0
    for row in rows:
        try:
            text = _clean(row.get("text"))
            top = int(row["top"]) / height
        except (KeyError, TypeError, ValueError):
            continue
        if top <= y0 + 0.01:
            continue
        if top > min(0.98, y0 + 0.55):
            continue
        if NUMBER_RE.match(text):
            numbers += 1
        elif 1 <= len(text) <= 5 and re.fullmatch(r"[А-ЯЁA-Z?]{1,5}", text):
            labels += 1
    score += min(numbers, 25) * 1.0
    score += min(labels, 10) * 0.6
    # Метка в самой верхней полосе — почти наверняка шапка таблицы работ.
    if y0 < 0.18:
        score -= 6.0
    if y0 < 0.10:
        score -= 6.0
    return score


def choose_boundary(rows: list[dict], width: int, height: int) -> tuple[float, float] | None:
    labels = [x for x in find_labels(rows, width, height) if x["confidence"] >= 85]
    if not labels:
        return None
    ranked = sorted(labels, key=lambda x: (_block_score(x, rows, width, height), x["confidence"]), reverse=True)
    best = ranked[0]
    return (best["y"], best["y"])


def detect_boundary_candidates(image_bytes: bytes) -> list[tuple[float, float]]:
    """Все кандидаты линии, отсортированные по вероятности."""
    executable = shutil.which("tesseract")
    if not executable:
        return []
    try:
        with Image.open(io.BytesIO(image_bytes)) as src:
            image = ImageOps.exif_transpose(src).convert("RGB")
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        # Классический OCR (OEM 0): нейросетевые модели видят только обрезанную область.
        result = subprocess.run(
            [executable, "stdin", "stdout", "-l", "rus+eng", "--oem", "0", "tsv"],
            input=buf.getvalue(), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=45, check=True,
        )
        import csv
        rows = []
        for row in csv.DictReader(io.StringIO(result.stdout.decode("utf-8", errors="replace")), delimiter="\t"):
            rows.append({
                "text": row.get("text"), "confidence": row.get("conf"),
                "left": row.get("left"), "top": row.get("top"),
                "width": row.get("width"), "height": row.get("height"),
            })
        labels = [x for x in find_labels(rows, *image.size) if x["confidence"] >= 85]
        ranked = sorted(labels, key=lambda x: (_block_score(x, rows, *image.size), x["confidence"]), reverse=True)
        return [(x["y"], x["y"]) for x in ranked]
    except (OSError, ValueError, subprocess.SubprocessError):
        return []


def detect_boundary(image_bytes: bytes):
    candidates = detect_boundary_candidates(image_bytes)
    return candidates[0] if candidates else None


def validate_boundary(boundary) -> tuple[float, float]:
    if not isinstance(boundary, (tuple, list)) or len(boundary) != 2:
        raise ValueError("Укажите границу БН")
    left, right = boundary
    if any(not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v < 1 for v in (left, right)):
        raise ValueError("Неверная граница")
    return float(left), float(right)


def crop_after_boundary(image_bytes: bytes, boundary) -> tuple[bytes, dict]:
    left, right = validate_boundary(boundary)
    if len(image_bytes) > 20 * 1024 * 1024:
        raise ValueError("Файл больше 20 МБ")
    with Image.open(io.BytesIO(image_bytes)) as src:
        if src.width * src.height > 35_000_000:
            raise ValueError("Изображение больше 35 мегапикселей")
        image = ImageOps.exif_transpose(src).convert("RGB")
    w, h = image.size
    if w < 2 or h < 2:
        raise ValueError("Слишком маленькое изображение")
    ly = math.ceil(left * h)
    ry = math.ceil(right * h)
    top = min(ly, ry)
    if top >= h - 1:
        raise ValueError("Граница ниже листа")
    mask = Image.new("1", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    for x in range(w):
        start = math.ceil(ly + (ry - ly) * x / (w - 1))
        if start < h:
            draw.line((x, start, x, h - 1), fill=1)
    filtered = Image.new("RGB", (w, h), "white")
    filtered.paste(image, (0, 0), mask)
    filtered = filtered.crop((0, top, w, h))
    output = io.BytesIO()
    filtered.save(output, format="PNG")
    return output.getvalue(), {"left": left, "right": right, "top": top, "width": w, "height": h}


def preview_boundary(image_bytes: bytes, boundary) -> bytes:
    left, right = validate_boundary(boundary)
    with Image.open(io.BytesIO(image_bytes)) as src:
        image = ImageOps.exif_transpose(src).convert("RGB")
    width, height = image.size
    ImageDraw.Draw(image).line(
        (0, round(left * height), width - 1, round(right * height)),
        fill="red", width=max(3, width // 300),
    )
    image.thumbnail((1400, 1400))
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=88)
    return out.getvalue()


__all__ = [
    "choose_boundary", "crop_after_boundary", "detect_boundary", "detect_boundary_candidates",
    "find_first_label", "find_labels", "preview_boundary", "validate_boundary",
]

"""Разбить промпт ChatGPT на части по разделам, не более ~28 КБ."""
from pathlib import Path

src = Path(r"E:\MAX-FINANCE-TEST\reports\chatgpt-review-prompt.md").read_text(encoding="utf-8")
sections = src.split("\n## ")
parts = []
current = sections[0]
for section in sections[1:]:
    block = "\n## " + section
    if len(current) + len(block) > 28000 and current.strip():
        parts.append(current)
        current = block
    else:
        current += block
if current.strip():
    parts.append(current)

out = Path(r"E:\MAX-FINANCE-TEST\reports\chatgpt-parts")
out.mkdir(exist_ok=True)
for index, part in enumerate(parts, 1):
    header = f"ЧАСТЬ {index} ИЗ {len(parts)}. Это материалы для независимой проверки. Не давай финальный вердикт, пока не получишь все части; ответь коротко «принято».\n\n"
    path = out / f"part-{index}.md"
    path.write_text(header + part, encoding="utf-8")
    print(path, path.stat().st_size)

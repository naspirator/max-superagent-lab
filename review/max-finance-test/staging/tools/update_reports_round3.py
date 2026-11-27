# -*- coding: utf-8 -*-
from pathlib import Path

root = Path(r"E:\MAX-FINANCE-TEST")
rep = root / "reports" / "MAX_FINANCE_TEST_REPORT.md"
resp = root / "reports" / "REVIEW_RESPONSE.md"

t = rep.read_text(encoding="utf-8")
subs = [
    ("- `tests/*` (103 теста)", "- `tests/*` (108 тестов)"),
    ("103/103 теста нового режима и изоляции — PASS;",
     "108/108 тестов нового режима и изоляции — PASS;"),
    ("M19 закрыт: 103 теста в пакете.",
     "M19 закрыт: 108 тестов в пакете."),
    ("- полный пакет для ревью: `review-package-11.tar.gz`",
     "- полный пакет для ревью: `review-package-12.tar.gz`"),
    ("""Итог: **103 теста нового режима + 7 baseline, 0 failures**. Это по-прежнему
внутренняя проверка, а не независимая приёмка.""",
     """Итог после раунда 2: **103 теста + 7 baseline, 0 failures** (это внутренняя
проверка, а не независимая приёмка).

### 7.1.3. Пятый цикл ChatGPT и исправления B01 (раунд 3)

Цикл 5 (HEAD c536711) дал **VERDICT: REVISE** — два новых пункта B01.

1. **BLOCKER: пустой файл БД.** Проверялось только существование
   `test_finance.db`. Если файл есть, но пуст (0 байт) или без схемы,
   `initialize()` создаёт таблицы и оставляет `recovered=False`; после
   перезапуска `/sync`, текст и фото доходили до WORK через настоящий
   диспетчер aiogram. Пустой файл появляется сам: `sqlite3.connect` создаёт
   его при обычном обращении к хранилищу сразу после потери БД.
   Исправлено: `ModeStore._has_schema()` проверяет наличие `meta` и
   `schema_version` до создания таблиц; при существующем `installed` и
   отсутствии схемы ставится `meta.recovered=1`.
2. **MAJOR: `restore()` терял fail-closed.** `backup`/`restore` не переносили
   файл `installed`, поэтому первый `initialize()` после восстановления
   записывал маркер и выставлял `recovered=False`, не читая флаг из
   восстановленной БД. Исправлено: `installed` копируется в резервную копию и
   при восстановлении; кроме того, при первой установке `initialize()` читает
   `meta.recovered` из уже существующей БД.

Добавлены тесты: пустой файл после потери БД (0 байт), первая установка с
пустым файлом, повреждённый файл БД, сохранение `recovered` через
`backup`/`restore`, здоровое восстановление без `recovered`.

Итог цикла 5: **108 тестов нового режима + 7 baseline, 0 failures**
(`reports/tests-at-head.txt`). Шестой цикл (проверка двух исправлений) ещё не
проводился; APPROVE нет."""),
    ("""10. Независимая проверка Superagent заблокирована настройкой GitHub-источника
    (self-authored элементы пропускаются, комментарии выключены); ChatGPT дал
    REVISE в циклах 1–4, исправление B01 после четвёртого цикла не проверено.
    APPROVE нет.""",
     """10. Независимая проверка Superagent заблокирована настройкой GitHub-источника
    (self-authored элементы пропускаются, комментарии выключены); нужен новый
    Issue от человеческого аккаунта. ChatGPT дал REVISE в циклах 1–5; два
    дефекта B01 из цикла 5 исправлены, но шестым циклом ещё не проверены.
    APPROVE нет."""),
    ("""Внутренние тесты: 103 + 7 baseline, 0 failures. ChatGPT Desktop провёл четыре
цикла проверки; последний вердикт — **REVISE** (B01: потеря БД вместе с
маркером возвращала пользователя в WORK). Это исправлено маркером
`test-mode/installed` и флагом `meta.recovered`, но **пятый цикл не
проводился**. APPROVE нет. Superagent-ревью не получено: нужен новый Issue от
человеческого аккаунта.""",
     """Внутренние тесты: 108 + 7 baseline, 0 failures. ChatGPT Desktop провёл пять
циклов проверки; последний вердикт — **REVISE** (B01: пустой файл БД и
`restore()` без `installed` возвращали пользователя в WORK). Оба дефекта
исправлены: проверка схемы БД и перенос `installed` в backup/restore, плюс
чтение `meta.recovered` при первой установке. **Шестой цикл не проводился**,
APPROVE нет. Superagent-ревью не получено: нужен новый Issue от человеческого
аккаунта."""),
]
for old, new in subs:
    assert t.count(old) == 1, "NOT FOUND OR AMBIGUOUS: " + old[:60]
    t = t.replace(old, new)
rep.write_text(t, encoding="utf-8")

r = resp.read_text(encoding="utf-8")
r = r.rstrip() + """

## Цикл 5 — вердикт и исправления

Цикл 5 (HEAD c536711) дал **VERDICT: REVISE** с двумя новыми пунктами B01:

1. **BLOCKER — пустой файл БД.** `installed` проверялся, но проверялось только
   существование `test_finance.db`. Пустой файл (0 байт) или файл без схемы
   проходил как «база есть»: `initialize()` создавал таблицы, `recovered`
   оставался `False`, и после перезапуска `/sync`, текст и фото доходили до
   WORK через настоящий диспетчер aiogram. Исправлено проверкой схемы
   (`_has_schema`: таблица `meta` и `schema_version`) до создания таблиц.
2. **MAJOR — `restore()` терял fail-closed.** `backup`/`restore` не переносили
   `installed`, поэтому первый `initialize()` после восстановления писал маркер
   и выставлял `recovered=False`, не читая флаг из восстановленной БД. Теперь
   `installed` копируется в копию и при восстановлении, а при первой установке
   `initialize()` читает `meta.recovered` из существующей БД.

Добавлены тесты на пустой файл, первую установку с пустым файлом, повреждённую
БД, сохранение `recovered` через `backup`/`restore` и здоровое восстановление.

Итог: **108 + 7 baseline, 0 failures** (`reports/tests-at-head.txt`). Шестой
цикл не проводился; APPROVE нет.
"""
resp.write_text(r, encoding="utf-8")

verdict = root / "reports" / "chatgpt-review-cycle5-verdict.txt"
verdict.write_text("""# Вердикт ChatGPT, цикл 5

Получен 27.11.2026 из чата «Проведи независимое ревью PR #38» (HEAD c536711).
Текст без изменений:

```text
VERDICT: REVISE
- BLOCKER — B01. Пустой файл БД возвращает пользователя в WORK. При наличии
  installed проверяется только существование test_finance.db. Если файл пуст
  или SQLite ещё не содержит схемы, initialize() создаёт таблицы и оставляет
  recovered=False. Воспроизведено и без ручного создания файла: после потери
  БД обычная проверка режима создаёт файл размером 0 байт. После перезапуска
  /sync, свободный текст и фото дошли до WORK через диспетчер aiogram.
  store.py:79–134
- MAJOR — B01. restore() возвращает хранилище, которое пропускает операции в
  WORK при сохранённом meta.recovered=1. Backup и restore не переносят
  installed, поэтому первый initialize() записывает маркер и выставляет
  self.recovered=False, не прочитав флаг из восстановленной БД. С объектом,
  возвращённым restore(), диспетчер пропустил /sync, текст и фото в WORK.
  Следующий initialize() восстанавливает блокировку. store.py:123–134
```

Полный транскрипт: `reports/chatgpt-review-cycle5-ui.txt`.

Что исправлено после вердикта (раунд 3):

- `ModeStore._has_schema()` — проверка реальной схемы БД перед созданием таблиц;
- при `installed` и отсутствии схемы выставляется `meta.recovered=1`;
- `backup`/`restore` переносят файл `installed`;
- при первой установке `initialize()` читает `meta.recovered` из существующей БД;
- добавлены 5 регрессионных тестов; итого 108 + 7 baseline, 0 failures.

Шестой цикл (точечная проверка этих двух исправлений) не проводился.
""", encoding="utf-8")

prompt = root / "reports" / "chatgpt-cycle6-ask.txt"
prompt.write_text("""Шестой цикл, только два исправления B01 из пятого цикла. PR #38, HEAD — актуальный в ветке review/max-finance-test-20261127 после коммита с проверкой схемы БД.
https://github.com/naspirator/max-superagent-lab/pull/38

Что изменено:
1) BLOCKER (пустой файл БД): добавлен `ModeStore._has_schema()` — до создания таблиц проверяется, что в файле есть таблица `meta` и запись `schema_version`. Если `installed` есть, а схемы нет (файла нет, файл 0 байт, мусор), ставится `meta.recovered=1` и `store.recovered=True`; `/sync`, текст и фото блокируются.
2) MAJOR (restore): `backup` и `restore` теперь переносят файл `installed`. Кроме того, при первой установке `initialize()` читает `meta.recovered` из уже существующей БД, поэтому восстановленная копия не теряет fail-closed.

Проверь:
1. Сценарий из цикла 5 через настоящий диспетчер: create_test_handlers → TEST → удалить test_finance.db и active/<uid> → обычным обращением к хранилищу создать пустой 0-байтный файл → перезапуск/initialize → /sync, текст и фото не доходят до WORK.
2. MAJOR: backup хранилища с recovered=1 → restore → объект, возвращённый restore(), не пропускает /sync, текст и фото в WORK.
3. Обычная первая установка (installed нет) не блокирует WORK; здоровый backup/restore не включает recovered.
4. Повреждённый файл БД и повторный initialize.
5. Не сломаны остальные тесты: 108 + 7 baseline, 0 failures (reports/tests-at-head.txt).

Ответ строго: VERDICT: APPROVE | REVISE | BLOCKED, затем только новые BLOCKER/MAJOR с файлами и строками. Если всё закрыто — APPROVE. Не публикуй review и не меняй PR.
""", encoding="utf-8")

print("OK", rep.stat().st_size, resp.stat().st_size, verdict.stat().st_size, prompt.stat().st_size)

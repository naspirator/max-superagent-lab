# -*- coding: utf-8 -*-
from pathlib import Path

root = Path(r"E:\MAX-FINANCE-TEST")
rep = root / "reports" / "MAX_FINANCE_TEST_REPORT.md"
resp = root / "reports" / "REVIEW_RESPONSE.md"

t = rep.read_text(encoding="utf-8")
subs = [
    ("- `tests/*` (108 тестов)", "- `tests/*` (111 тестов)"),
    ("108/108 тестов нового режима и изоляции — PASS;",
     "111/111 тестов нового режима и изоляции — PASS;"),
    ("M19 закрыт: 108 тестов в пакете.", "M19 закрыт: 111 тестов в пакете."),
    ("""Итог цикла 5: **108 тестов нового режима + 7 baseline, 0 failures**
(`reports/tests-at-head.txt`). Шестой цикл (проверка двух исправлений) ещё не
проводился; APPROVE нет.""",
     """Итог цикла 5: **108 тестов нового режима + 7 baseline, 0 failures**
(`reports/tests-at-head.txt`). Шестой цикл (проверка двух исправлений) ещё не
проводился; APPROVE нет.

### 7.1.4. Шестой цикл ChatGPT и исправления (раунд 4)

Цикл 6 (HEAD ccee903) дал **VERDICT: REVISE** с двумя новыми пунктами:

1. **BLOCKER: неполная схема БД.** `_has_schema()` проверял только таблицу
   `meta` и запись `schema_version`. Если таблица `settings` потеряна, а
   `meta` сохранилась, `initialize()` создавал пустую `settings`, оставляя
   `recovered=False`, и пользователь без маркера возвращался в WORK.
   Исправлено: `REQUIRED_TABLES` перечисляет все девять таблиц схемы v1;
   отсутствие любой из них при существующем `installed` считается потерей
   базы (`meta.recovered=1`).
2. **MAJOR: недостаточное интеграционное покрытие.** Новые тесты вызывали
   обработчики напрямую, минуя диспетчер aiogram; тест восстановления не
   проверял свободный текст. Исправлено: добавлен
   `tests/test_dispatch_isolation.py` — обновления проходят через настоящий
   `Dispatcher.feed_update` и `Bot` с сессией без сети; проверены потеря БД,
   потеря таблицы `settings` и обычный рабочий пользователь. В тест
   `backup`/`restore` добавлена проверка свободного текста.

Итог раунда 4: **111 тестов нового режима + 7 baseline, 0 failures**
(`reports/tests-at-head.txt`). Седьмой цикл (проверка этих исправлений) ещё не
проводился; APPROVE нет."""),
    ("""10. Независимая проверка Superagent заблокирована настройкой GitHub-источника
    (self-authored элементы пропускаются, комментарии выключены); нужен новый
    Issue от человеческого аккаунта. ChatGPT дал REVISE в циклах 1–5; два
    дефекта B01 из цикла 5 исправлены, но шестым циклом ещё не проверены.
    APPROVE нет.""",
     """10. Независимая проверка Superagent заблокирована настройкой GitHub-источника
    (self-authored элементы пропускаются, комментарии выключены); нужен новый
    Issue от человеческого аккаунта. ChatGPT дал REVISE в циклах 1–6; дефекты
    B01 из циклов 5 и 6 исправлены, но седьмым циклом ещё не проверены.
    APPROVE нет."""),
    ("""Внутренние тесты: 108 + 7 baseline, 0 failures. ChatGPT Desktop провёл пять
циклов проверки; последний вердикт — **REVISE** (B01: пустой файл БД и
`restore()` без `installed` возвращали пользователя в WORK). Оба дефекта
исправлены: проверка схемы БД и перенос `installed` в backup/restore, плюс
чтение `meta.recovered` при первой установке. **Шестой цикл не проводился**,
APPROVE нет. Superagent-ревью не получено: нужен новый Issue от человеческого
аккаунта.""",
     """Внутренние тесты: 111 + 7 baseline, 0 failures. ChatGPT Desktop провёл шесть
циклов проверки; последний вердикт — **REVISE** (B01: неполная схема БД,
`meta` без `settings`, возвращала пользователя в WORK; MAJOR: тесты миновали
диспетчер aiogram). Исправлено: проверка всех девяти таблиц схемы, плюс
интеграционные тесты через настоящий `Dispatcher.feed_update`, включая
свободный текст после `backup`/`restore`. **Седьмой цикл не проводился**,
APPROVE нет. Superagent-ревью не получено: нужен новый Issue от человеческого
аккаунта."""),
]
for old, new in subs:
    assert t.count(old) == 1, "NOT FOUND OR AMBIGUOUS: " + old[:70]
    t = t.replace(old, new)
rep.write_text(t, encoding="utf-8")

r = resp.read_text(encoding="utf-8").rstrip()
r += """

## Цикл 6 — вердикт и исправления

Цикл 6 (HEAD ccee903) дал **VERDICT: REVISE**:

1. **BLOCKER — неполная схема БД.** `_has_schema()` проверял только `meta` и
   `schema_version`; при потере таблицы `settings` `initialize()` создавал её
   пустой и оставлял `recovered=False`. Исправлено: `REQUIRED_TABLES` — все
   девять таблиц схемы v1; отсутствие любой при существующем `installed`
   означает потерю базы и включает `meta.recovered=1`.
2. **MAJOR — покрытие.** Добавлены интеграционные тесты через настоящий
   диспетчер aiogram (`tests/test_dispatch_isolation.py`): три сценария —
   потеря БД, потеря `settings` при живой `meta`, обычный рабочий пользователь.
   В тест `backup`/`restore` добавлена проверка свободного текста.

Итог: **111 + 7 baseline, 0 failures** (`reports/tests-at-head.txt`). Седьмой
цикл не проводился; APPROVE нет.
"""
resp.write_text(r + "\n", encoding="utf-8")

verdict = root / "reports" / "chatgpt-review-cycle6-verdict.txt"
verdict.write_text("""# Вердикт ChatGPT, цикл 6

Получен 27.11.2026 из чата «Проведи независимое ревью PR #38» (HEAD ccee903).
Текст без изменений:

```text
VERDICT: REVISE
- BLOCKER — B01. Неполная схема БД допускает возврат в WORK. store.py:85–112,
  126–163. Метод _has_schema() проверяет только таблицу meta и запись
  schema_version. Если таблица settings потеряна, а meta сохранилась,
  initialize() создаёт пустую таблицу settings, оставляя recovered=False. При
  отсутствии active/<uid> пользователь возвращается в WORK. Воспроизведено на
  SQLite. Необходимо проверять наличие всех обязательных таблиц до
  восстановления схемы.
- MAJOR — недостаточное интеграционное покрытие.
  tests/test_cycle3_regressions.py:244–352. Новые тесты вызывают обработчики
  напрямую, минуя настоящий диспетчер aiogram. Тест восстановления
  дополнительно не проверяет свободный текст. Отчёт 108 + 7 PASS подтверждён
  на HEAD ccee903, но независимо повторить полный прогон не удалось: aiogram
  отсутствует, сетевой доступ из среды исполнения недоступен. GitHub CI
  запускает npm test, а не эти Python-тесты.
PR не изменён. Review не опубликовано.
```

Что исправлено после вердикта (раунд 4):

- `REQUIRED_TABLES` — проверка всех девяти таблиц схемы перед восстановлением;
- `tests/test_dispatch_isolation.py` — обновления через настоящий
  `Dispatcher.feed_update` и `Bot` с сессией без сети;
- в тест `backup`/`restore` добавлена проверка свободного текста;
- итого 111 + 7 baseline, 0 failures.

Седьмой цикл (проверка этих исправлений) не проводился.
""", encoding="utf-8")

prompt = root / "reports" / "chatgpt-cycle7-ask.txt"
prompt.write_text("""Седьмой цикл, только исправления из шестого цикла. PR #38, актуальный HEAD ветки review/max-finance-test-20261127 (коммит после ccee903).
https://github.com/naspirator/max-superagent-lab/pull/38

Что изменено:
1) BLOCKER (неполная схема): добавлен `REQUIRED_TABLES` — все девять таблиц схемы v1 (meta, staff, staff_alias, seed_conflicts, settings, drafts, line_settings, examples, audit). `_has_schema()` возвращает False, если нет любой из них; при существующем installed это включает `meta.recovered=1` и блокирует /sync, текст и фото.
2) MAJOR (покрытие): добавлен `tests/test_dispatch_isolation.py`. Тесты прогоняют обновления через настоящий `Dispatcher.feed_update` с `Bot` и сессией без сети: (а) потеря БД → пустой файл → блокировка /sync, текста и фото; (б) `meta` жива, таблица settings удалена → блокировка; (в) обычный пользователь без маркера → /sync, текст и фото доходят до WORK.
3) В тест backup/restore добавлена проверка свободного текста.

Проверь:
1. Сценарий из цикла 6: удалить таблицу settings при живой meta и installed → initialize/recovered → /sync, текст и фото не доходят до WORK.
2. Полнота REQUIRED_TABLES: нет ли таблицы, которую можно потерять и остаться в WORK; нет ли ложного recovered на здоровой базе или после restore.
3. Диспетчерские тесты действительно идут через aiogram Dispatcher и падают, если вернуть старое поведение (например, recovered=False).
4. Прогони 111 + 7 baseline (reports/tests-at-head.txt).

Ответ строго: VERDICT: APPROVE | REVISE | BLOCKED, затем только новые BLOCKER/MAJOR с файлами и строками. Если всё закрыто — APPROVE. Не публикуй review и не меняй PR.
""", encoding="utf-8")

print("OK", rep.stat().st_size, resp.stat().st_size, verdict.stat().st_size, prompt.stat().st_size)

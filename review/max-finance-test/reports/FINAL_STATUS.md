# MAX FINANCE TEST — текущий статус

Дата: 27.11.2026, 22:25 MSK.

## Готово

- Найден действующий бот `@ShinomontazhFinance_bot` на Samsung S20 FE /
  Termux / proot Ubuntu; служба `max-finance` работает (PID 20786).
- Сделана полная резервная копия проекта, `.env`, ключей и `finance.db`
  (32,6 МБ, телефон + Windows). Проверены SHA-256 и восстановление.
- В отдельном staging реализован режим `MAX FINANCE TEST` в том же боте:
  отдельная SQLite, отдельные фото, без записи в рабочую Google-таблицу.
- Полное ручное редактирование: сумма, каждое слагаемое, знак, сотрудник,
  буква, категория, источник, add/delete/split/merge/order/date/line/rerun/undo.
- Линия по SHA фото, словарь П/Р/R/В/V/Т/Д/Л/ДИМ, база подтверждённых
  примеров, backup/restore.
- Fail-closed изоляция TEST: при потере, повреждении или неполной схеме
  тестовой БД блокируются команды, фото и свободный текст.
- **112 тестов нового режима + 7 baseline, 0 failures**, плюс пройденный
  отрицательный контроль регрессионного теста.
  `reports/tests-at-head.txt`, `reports/tests-round5-win.txt`.
- Независимая проверка ChatGPT Desktop: семь циклов, все — **REVISE**.
  Транскрипты и вердикты: `reports/chatgpt-review-*.txt`.

## Вердикты по циклам

1. Цикл 1 — 8 BLOCKER, 19 MAJOR.
2. Цикл 2 — B01, B03, B04 и др.
3. Цикл 3 — OCR −500→+500, B01 при отсутствии файла БД, ошибка установщика;
   MAJOR: сброс «Я сверил фото», подтверждение старой сводкой, restore/verify.
4. Цикл 4 (HEAD 5fd4eab) — B01: потеря БД вместе с маркером возвращала
   пользователя в WORK.
5. Цикл 5 (HEAD c536711) — B01: пустой (0 байт) файл `test_finance.db`
   считался живой базой; MAJOR: `restore()` не переносил `installed`.
6. Цикл 6 (HEAD ccee903) — B01: неполная схема БД (таблица `settings`
   потеряна, `meta` жива) возвращала в WORK; MAJOR: новые тесты вызывали
   обработчики напрямую, минуя диспетчер aiogram.
7. Цикл 7 (HEAD 423ec13) — новых BLOCKER нет. MAJOR: регрессионный тест на
   потерю `settings` стартовал с уже восстановленной базы и проходил на любой
   реализации `_has_schema()`.

## Исправлено после цикла 7 (раунд 5)

1. `tests/test_dispatch_isolation.py`: сценарий шестого цикла начинается со
   **здоровой** базы (`recovered=False`), затем включается TEST, удаляются
   таблица `settings` и маркер `active/1`; предусловие проверяет полноту схемы
   до повреждения.
2. Мета-тест `test_old_schema_check_would_let_user_back_into_work`: с
   `_has_schema()` из `ccee903` тот же сценарий обязан вернуть пользователя в
   WORK (`recovered=False`, все три обновления доставлены). Это доказывает, что
   регрессионный тест не пустой.
3. `tools/verify_regression_catches_settings_bug.py` — тот же контроль вне
   pytest: `OLD_IMPLEMENTATION=FAIL`, `CURRENT_IMPLEMENTATION=PASS`,
   `NEGATIVE_CONTROL=OK`.
4. `tools/make_changes_manifest.py`: манифест больше не включает
   `.pytest_cache` и внутренние скрипты раундов.

Итог: **112 + 7 baseline, 0 failures.** Восьмой цикл вернул **BLOCKED**:
новых BLOCKER/MAJOR нет, замечание седьмого цикла закрыто; причина только в
среде проверки — у ChatGPT нет `aiogram` и сетевого доступа для повторного
прогона. Поэтому пакет получил независимый прогон в чистом окружении CI
(`.github/workflows/ci.yml`, job `maxfinance-test`): **119 passed**
(112 + 7), `NEGATIVE_CONTROL=OK`, установщик 7/7 — `reports/ci-run.txt`.
APPROVE пока нет.

## Исправлено ранее (раунды 1–4)

- Установщик: откат только кода (без живой БД), привязка к `$PROJECT`,
  два замера PID вместо одного `sv status`, `$PREFIX/bin/sv`, проверка
  `sha256sum -c`, атомарная замена, откат только кода при сбое. Проверено
  dry-run на телефоне и симуляцией семи сценариев
  (`reports/installer-simulation.txt`).
- `installed` пишется при первой установке; если БД исчезла, пуста или её
  схема неполная — `meta.recovered=1`, рабочие операции блокируются;
  `REQUIRED_TABLES` требует все девять таблиц схемы v1.
- `backup`/`restore` переносят `installed`; при первой установке
  `initialize()` читает `meta.recovered` из существующей БД.
- Интеграционные тесты через настоящий `Dispatcher.feed_update` и `Bot` с
  сессией без сети (`tests/test_dispatch_isolation.py`).
- Регрессии: устаревшая сводка, завершение отчёта после сбоя OCR, обязательное
  фото в `verify_backup`, путь к фото в Undo после `restore`, числовой
  `item_id`, карточка сотрудника, ID после деактивации, знак в ансамбле.

## Не готово / блокеры

1. **APPROVE ChatGPT не получен.** Восемь циклов; восьмой — **BLOCKED**
   технически (в среде проверки нет `aiogram` и сети), при этом новых дефектов
   в коде нет, замечание седьмого цикла закрыто. Независимый прогон теперь
   есть в CI: run 46059242077, job `maxfinance-test` — `119 passed in 1.81s`,
   `NEGATIVE_CONTROL=OK`, установщик 7/7 (`reports/ci-run.txt`); последний
   прогон на HEAD — run 46059799692, success. Без APPROVE внедрение и отправка
   владельцу не выполнялись.
2. **Superagent-ревью не получено.** Причина подтверждена кодом и настройками:
   - источник пропускает self-authored элементы
     (`src/sources/github.ts:227`);
   - включён только поток Issues, `observeComments: false`;
   - Issue #39 создан `max535max` — это аккаунт агента, поэтому пропущен;
   - поток Issues стартовал `16:08:34Z`, Issue #39 создан `16:07:56Z`.
   Нужен **новый Issue** от человеческого аккаунта `naspirator` —
   `reports/SUPERAGENT_TRIGGER.md`. Проверено 27.11.2026 22:20: новых Issue от
   `naspirator` нет (последний — #37, закрыт 21.11.2026).
3. **Точность OCR недостаточна для автоматической сдачи:** суммы 82,8%,
   сотрудники 42,1%, категории 75,9%, полностью верных 0/5. Нужна ручная
   проверка каждой позиции.
4. Живой Telegram не тестировался: второй polling на действующем токене
   запрещён до согласования.

## PROD

Не изменялся (проверено по SSH на телефон):

- служба `max-finance`: `run`, PID 20786 (uptime 727971 с);
- `/root/max-finance-stage/bot.py`:
  `48FBB5D6852BF5F48741447396739DFC02C9D9F4E5752193061FD74F4DCCC740`;
- `/root/max-finance-stage/finance.db`:
  `438ECC57A92CDBA7541FC1D726F27D0FCBC865429A3872BA788A525D01BF7F06`;
  совпадает с резервной копией;
- `maxfinance_test` и `test-mode` в PROD отсутствуют;
- рабочая БД и Google-таблица не перезаписывались;
- токен и сотрудники не менялись;
- внедрение, merge и отправка владельцу не выполнялись.

Повторная проверка 27.11.2026, 22:47 MSK: служба `run` (pid 20786), оба
SHA-256 совпадают с указанными выше, тестовых артефактов в proot нет.
Отдельно проверены токены: на токене `@ShinomontazhFinance_bot` работает один
процесс; `@Shin_Kas_New_bot` и `@Kas4a_shin_nn_bot` — другие боты
(`max-server/bots/shinomontazh`), второго polling на рабочем токене нет.

## Где смотреть

- Технический отчёт: `reports/MAX_FINANCE_TEST_REPORT.md`
- Ответы на вердикты: `reports/REVIEW_RESPONSE.md`
- Diff и манифест: `reports/changes.diff`
- Метрики: `reports/evaluation.json`
- Тесты и отрицательный контроль: `reports/tests-at-head.txt`
- Независимый прогон в CI: `reports/ci-run.txt`
- Проверка установщика: `reports/installer-simulation.txt`
- Вердикты: `reports/chatgpt-review-cycle5-verdict.txt`,
  `reports/chatgpt-review-cycle6-verdict.txt`,
  `reports/chatgpt-review-cycle7-verdict.txt`
- Вердикт восьмого цикла: `reports/chatgpt-review-cycle8-verdict.txt`
- Промпт следующего цикла: `reports/chatgpt-cycle9-ask.txt`
- Откат: `staging/docs/ROLLBACK.md`
- PR: https://github.com/naspirator/max-superagent-lab/pull/38
  (ветка `review/max-finance-test-20261127`, HEAD `d7e9a3f`;
  архивный снимок — `review-package-13.tar.gz` на `f5f28f1`)

## Следующий шаг

1. Девятый цикл ChatGPT: проверить CI-прогон `reports/ci-run.txt` и снять
   технический BLOCKED.
2. Для снятия блокера Superagent — новый Issue от `naspirator` (человек).
3. При APPROVE — отправить владельцу отчёт с кнопками «Принять / Доработать /
   Полный отчёт / Пауза».
4. Только после явного «Принять» — установка на телефон по
   `deploy/install-test-mode.sh` с `OWNER_APPROVED=1`.

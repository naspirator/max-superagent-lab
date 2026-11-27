# MAX FINANCE TEST — текущий статус

Дата: 27.11.2026, 22:35 MSK.

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
- **111 тестов нового режима + 7 baseline, 0 failures.**
  `reports/tests-at-head.txt`.
- Независимая проверка ChatGPT Desktop: шесть циклов, все — **REVISE**.
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

## Исправлено после цикла 6 (раунд 4)

1. `REQUIRED_TABLES` — `_has_schema()` требует все девять таблиц схемы v1
   (`meta`, `staff`, `staff_alias`, `seed_conflicts`, `settings`, `drafts`,
   `line_settings`, `examples`, `audit`). Отсутствие любой при существующем
   `installed` включает `meta.recovered=1`.
2. `tests/test_dispatch_isolation.py` — обновления проходят через настоящий
   `Dispatcher.feed_update` и `Bot` с сессией без сети:
   - потеря БД и пустой файл → `/sync`, текст и фото не доходят до WORK;
   - `meta` жива, `settings` удалена → блокировка;
   - обычный пользователь без маркера → все три обновления доходят до WORK.
3. В тест `backup`/`restore` добавлена проверка свободного текста.

Итог: **111 + 7 baseline, 0 failures.** Седьмой цикл (проверка исправлений
раунда 4) ещё не проводился; APPROVE нет.

## Исправлено ранее (раунды 1–3)

- Установщик: откат только кода (без живой БД), привязка к `$PROJECT`,
  два замера PID вместо одного `sv status`, `$PREFIX/bin/sv`, проверка
  `sha256sum -c`, атомарная замена, откат только кода при сбое. Проверено
  dry-run на телефоне и симуляцией семи сценариев
  (`reports/installer-simulation.txt`).
- `installed` пишется при первой установке; если БД исчезла, пуста или её
  схема неполная — `meta.recovered=1`, рабочие операции блокируются.
- `backup`/`restore` переносят `installed`; при первой установке
  `initialize()` читает `meta.recovered` из существующей БД.
- Регрессии: устаревшая сводка, завершение отчёта после сбоя OCR, обязательное
  фото в `verify_backup`, путь к фото в Undo после `restore`, числовой
  `item_id`, карточка сотрудника, ID после деактивации, знак в ансамбле.

## Не готово / блокеры

1. **APPROVE ChatGPT не получен.** Шесть циклов, последний вердикт — REVISE.
   Дефекты B01 и MAJOR раунда 4 исправлены, но седьмой цикл не проводился.
   Без APPROVE внедрение и отправка владельцу не выполнялись.
2. **Superagent-ревью не получено.** Причина подтверждена кодом и настройками:
   - источник пропускает self-authored элементы
     (`src/sources/github.ts:227`);
   - включён только поток Issues, `observeComments: false`;
   - Issue #39 создан `max535max` — это аккаунт агента, поэтому пропущен;
   - поток Issues стартовал `16:08:34Z`, Issue #39 создан `16:07:56Z`.
   Нужен **новый Issue** от человеческого аккаунта `naspirator` —
   `reports/SUPERAGENT_TRIGGER.md`.
3. **Точность OCR недостаточна для автоматической сдачи:** суммы 82,8%,
   сотрудники 42,1%, категории 75,9%, полностью верных 0/5. Нужна ручная
   проверка каждой позиции.
4. Живой Telegram не тестировался: второй polling на действующем токене
   запрещён до согласования.

## PROD

Не изменялся (проверено по SSH на телефон):

- служба `max-finance`: `run`, PID 20786;
- `/root/max-finance-stage/bot.py`:
  `48FBB5D6852BF5F48741447396739DFC02C9D9F4E5752193061FD74F4DCCC740`;
- `/root/max-finance-stage/finance.db`:
  `438ECC57A92CDBA7541FC1D726F27D0FCBC865429A3872BA788A525D01BF7F06`;
  совпадает с резервной копией;
- `maxfinance_test` и `test-mode` в PROD отсутствуют;
- рабочая БД и Google-таблица не перезаписывались;
- токен и сотрудники не менялись;
- внедрение, merge и отправка владельцу не выполнялись.

## Где смотреть

- Технический отчёт: `reports/MAX_FINANCE_TEST_REPORT.md`
- Ответы на вердикты: `reports/REVIEW_RESPONSE.md`
- Diff и манифест: `reports/changes.diff`
- Метрики: `reports/evaluation.json`
- Тесты: `reports/tests-at-head.txt`
- Проверка установщика: `reports/installer-simulation.txt`
- Вердикты: `reports/chatgpt-review-cycle4-verdict.txt`,
  `reports/chatgpt-review-cycle5-verdict.txt`,
  `reports/chatgpt-review-cycle6-verdict.txt`
- Промпт следующего цикла: `reports/chatgpt-cycle7-ask.txt`
- Откат: `staging/docs/ROLLBACK.md`
- PR: https://github.com/naspirator/max-superagent-lab/pull/38
  (пакет `review-package-12.tar.gz`)

## Следующий шаг

1. Провести седьмой цикл ChatGPT по исправлениям раунда 4.
2. Для снятия блокера Superagent — новый Issue от `naspirator` (человек).
3. При APPROVE — отправить владельцу отчёт с кнопками «Принять / Доработать /
   Полный отчёт / Пауза».
4. Только после явного «Принять» — установка на телефон по
   `deploy/install-test-mode.sh` с `OWNER_APPROVED=1`.

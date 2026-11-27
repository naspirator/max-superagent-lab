# MAX FINANCE TEST — текущий статус

Дата: 27.11.2026, 22:20 MSK.

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
- Fail-closed изоляция TEST: при потере/повреждении тестовой БД блокируются
  команды, фото и свободный текст.
- **108 тестов нового режима + 7 baseline, 0 failures.**
  `reports/tests-at-head.txt`.
- Независимая проверка ChatGPT Desktop: пять циклов, все — **REVISE**.
  Транскрипты: `reports/chatgpt-review-full.txt`,
  `reports/chatgpt-review-cycle3.txt`, `reports/chatgpt-review-cycle4.txt`,
  `reports/chatgpt-review-cycle5-ui.txt`; вердикты:
  `reports/chatgpt-review-cycle4-verdict.txt`,
  `reports/chatgpt-review-cycle5-verdict.txt`.

### Вердикты по циклам

1. Цикл 1 — 8 BLOCKER, 19 MAJOR.
2. Цикл 2 — B01, B03, B04 и др.
3. Цикл 3 — OCR −500→+500, B01 при отсутствии файла тестовой БД, ошибка
   установщика; MAJOR: сброс «Я сверил фото», подтверждение старой сводкой,
   restore/verify.
4. Цикл 4 (HEAD 5fd4eab) — B01: потеря БД вместе с маркером возвращала
   пользователя в WORK.
5. Цикл 5 (HEAD c536711) — два новых B01:
   - **BLOCKER:** пустой (0 байт) файл `test_finance.db` считался живой базой:
     `initialize()` создавал таблицы, `recovered` оставался `False`, и после
     перезапуска `/sync`, текст и фото доходили до WORK через диспетчер
     aiogram. Пустой файл появляется сам при обычном `sqlite3.connect` после
     потери БД.
   - **MAJOR:** `restore()` возвращал хранилище, пропускающее WORK при
     `meta.recovered=1`: `backup`/`restore` не переносили файл `installed`,
     первый `initialize()` писал маркер и не читал флаг из БД.

### Исправлено после цикла 5 (раунд 3)

1. `ModeStore._has_schema()` — до создания таблиц проверяется реальная схема
   (`meta` и `schema_version`). Файл 0 байт, пустой или повреждённый не
   считается базой: при существующем `installed` ставится `meta.recovered=1`.
2. `backup` и `restore` переносят файл `installed`.
3. При первой установке `initialize()` читает `meta.recovered` из уже
   существующей БД — восстановленная копия не теряет fail-closed.
4. Добавлены тесты: пустой файл после потери БД, первая установка с пустым
   файлом, повреждённый файл, `recovered` через `backup`/`restore`, здоровое
   восстановление.

Итог: **108 + 7 baseline, 0 failures.** Шестой цикл (проверка этих двух
исправлений) ещё не проводился.

### Ранее исправлено (раунды 1–2)

- Установщик: откат только кода (без живой БД), привязка к `$PROJECT`,
  два замера PID вместо одного `sv status`, `$PREFIX/bin/sv`, проверка
  `sha256sum -c`, атомарная замена, откат только кода при сбое. Проверено
  dry-run на телефоне и симуляцией семи сценариев
  (`reports/installer-simulation.txt`).
- `active/` переносится `backup`/`restore`.
- Регрессии: устаревшая сводка, завершение отчёта после сбоя OCR, обязательное
  фото в `verify_backup`, путь к фото в Undo после `restore`, числовой
  `item_id`, карточка сотрудника, ID после деактивации, знак в ансамбле.

## Не готово / блокеры

1. **APPROVE ChatGPT не получен.** Пять циклов, последний вердикт — REVISE.
   Два дефекта B01 исправлены, но шестой цикл не проводился. Без APPROVE
   внедрение и отправка владельцу не выполнялись.
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

Не изменялся (проверено сейчас по SSH на телефон):

- служба `max-finance`: `run`, PID 20786;
- `/root/max-finance-stage/bot.py`:
  `48FBB5D6852BF5F48741447396739DFC02C9D9F4E5752193061FD74F4DCCC740`;
- `/root/max-finance-stage/finance.db`:
  `438ECC57A92CDBA7541FC1D726F27D0FCBC865429A3872BA788A525D01BF7F06`;
  совпадает с резервной копией;
- `maxfinance_test` и `test-mode` в PROD отсутствуют (`NO_TEST_PACKAGE`,
  `NO_TEST_MODE`);
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
  `reports/chatgpt-review-cycle5-verdict.txt`
- Промпт следующего цикла: `reports/chatgpt-cycle6-ask.txt`
- Откат: `staging/docs/ROLLBACK.md`
- PR: https://github.com/naspirator/max-superagent-lab/pull/38
  (пакет `review-package-12.tar.gz`)

## Следующий шаг

1. Провести шестой цикл ChatGPT по двум исправлениям B01.
2. Для снятия блокера Superagent — новый Issue от `naspirator` (человек).
3. При APPROVE — отправить владельцу отчёт с кнопками «Принять / Доработать /
   Полный отчёт / Пауза».
4. Только после явного «Принять» — установка на телефон по
   `deploy/install-test-mode.sh` с `OWNER_APPROVED=1`.

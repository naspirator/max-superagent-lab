# Ответ на независимую приёмку ChatGPT (цикл 1)

Вердикт цикла 1: **REVISE**. Ниже — что исправлено в коде и чем это
подтверждено. Новый пакет и тесты приложены к повторной проверке.

## BLOCKER

### B01 — fail-closed изоляция TEST
Исправлено:
- `bot.py:process_photo` при активном TEST больше не передаёт фото рабочему
  обработчику;
- при сбое инициализации создаётся `UnavailableTestMode` (`integration.py`),
  который читает режим из тестовой БД read-only и блокирует фото;
- любая ошибка тестового обработчика в TEST блокирует фото, а не уходит в WORK.
Тест: `test_ocr_failure_keeps_draft_and_allows_manual`,
`test_prod_sync_command_is_blocked_in_test_mode`.

### B02 — редактор линии
Исправлено: кнопка «Линия» использует `lineedit`, а не конфликтующий `line`.
Тест: `test_items_text_and_keyboard_cover_every_action`.

### B03 — struck при split/merge
Исправлено: `split_item` и `merge_items` переносят `struck`; validate не
пропускает зачёркнутую учитываемую позицию.
Тест: `test_split_and_merge_keep_struck_flag`.

### B04 — полнота OCR
Исправлено: `Report.ocr_complete`; `validate()` требует подтверждения полноты;
кнопка «Я сверил фото» (`ackphoto`). `complete=false` больше не сохраняется
молча.
Тест: `test_ocr_incomplete_and_stale_block_confirmation`.

### B05 — знак одиночной суммы
Исправлено: дефис после метки (`Б/Н-16100`, `П-4500`) трактуется как
разделитель; одиночное отрицательное число без метки остаётся отрицательным и
помечается `uncertain`.
Тест: `test_single_dash_after_label_is_separator_not_minus`,
`test_negative_single_amount_remains_negative_by_default`.

### B06 — коллизии id сотрудников
Исправлено: импорт WORK→TEST сопоставляет сотрудников по имени, а не по id;
id никогда не переиспользуется для другого человека; конфликт обозначения
пишется в `seed_conflicts`, автоматического объединения нет.
Тест: `test_seed_does_not_reuse_id_of_another_person`.

### B07 — symlink/hardlink тестовой БД
Исправлено: `os.path.samefile` при открытии; hardlink/symlink на рабочую БД
отвергается.
Тест: `test_test_db_hardlink_to_prod_is_rejected`.

### B08 — долги
Проверено по действующему коду v3: долги записываются отдельной категорией и
не вычитаются из безнала автоматически; `sheets_v3` ведёт отдельную вкладку
«Долги». Тестовый режим сохраняет это правило: `debt_policy="separate"`,
`totals()["debt_note"]` прямо говорит, что автоматического вычета нет.
Тест: `test_debts_are_separate_and_not_silently_deducted`.
Если владелец захочет автоматический вычет — это новое правило, его нужно
согласовать отдельно.

## MAJOR

- M01: undo линии синхронизирует `line_settings`.
- M02: undo сохраняет монотонную ревизию и `message_id`.
- M03: callback-кнопки позиций используют стабильный `item_id`, а не индекс;
  удалённая позиция отвергается. Тест:
  `test_callback_uses_item_id_and_rejects_deleted_item`.
- M04: `infer_sources` меняет только `unknown` и требует горизонтального
  перекрытия с заголовком.
- M05: `unknown` источник выплаты не проходит validate.
- M06: словарь для назначения берётся только из активных сотрудников;
  `setemp` проверяет активность.
- M07: частичное написание даёт `candidate`, а не автоматическое назначение.
- M08: validate проверяет активный `employee_id` (handlers и store передают
  список).
- M09: UNIQUE-индексы по фото и (фото, дата); INSERT ловит IntegrityError.
- M10: UNIQUE `photo_sha` — одна фотография не может быть и train, и holdout.
- M11: backup включает `input/` (исходные фото черновиков).
- M12: restore обновляет абсолютные пути фото в черновиках.
- M13: verify_backup требует наличие тестовой БД и проверяет манифест.
- M14: стартовые обозначения инициализируются один раз; удалённое не
  восстанавливается. Тест: `test_removed_alias_is_not_restored_on_restart`.
- M15: повторное распознавание требует подтверждения; ручные правки остаются в
  Undo.
- M16: изменение линии после OCR ставит `ocr_stale`; validate блокирует
  подтверждение до повторного распознавания. Тест:
  `test_line_change_after_ocr_blocks_confirmation`.
- M17: `json_repair` удалён; повторяющиеся ключи и битый JSON отвергаются.
- M18: улучшение точности OCR не заявлено. Последний прогон: суммы 82,8%
  (старый 86,2%), сотрудники 42,1%, категории 75,9%, полностью верных 0/5;
  диапазон по прогонам — 82,8–89,7% / 42,1–52,6% / 75,9–82,8%. Это
  ограничение, не успех.
- M19: исходники тестов включены в пакет; 103 теста, 0 failures.

## MINOR

- `classify_errors` различает split/merge и не дублирует added/deleted.
- `add_term` проверяет число до записи истории.
- `set_term` сохраняет знаки в `raw`.
- ручной `itog` проходит validate.
- при пустой рабочей БД обязательный словарь инициализируется.
- ограничение объёма фото не реализовано; вынесено в известные ограничения.

## Что осталось

- Точность автоматического OCR недостаточна (0/5 полностью верных); ручная
  проверка обязательна.
- Живой Telegram не запускался (запрет второго polling).
- Автопоиск линии на рукописи ненадёжен.
- Ограничение размера папки input не реализовано.

## Цикл 3 — что сделано после вердикта

Вердикт цикла 3: **REVISE**. Исправлено:

- отрицательный знак, записанный внутри `terms`, больше не заменяется старым
  OCR; добавлена защита в `ensemble.py` и регрессионный тест;
- `active/<uid>` теперь пишет `ModeStore.set_setting`, а не только меню;
  `ModeHandlers.is_test` при ошибке SQLite возвращает fail-closed `True`;
- числовой `item_id` сначала ищется как ID, затем как индекс с проверкой
  границ;
- карточка `staff:<id>` доступна (ветка списка требует пустых `args`);
- ID нового сотрудника считается по всем записям, включая неактивные;
- `photo_reviewed` сбрасывается при ошибке OCR;
- подтверждение привязано к `report.version`;
- restore обновляет пути в Undo-снимках; verify проверяет фото примеров;
- установщик исправлен.

Добавлены 5 регрессионных тестов `tests/test_cycle3_regressions.py`.
Итог: 103 + 7 baseline, 0 failures. **Четвёртый цикл дал REVISE по B01; это
исправлено, пятый цикл не проводился; APPROVE нет.**

## Раунд 2 — что дополнительно исправлено и проверено

1. **B01, отсутствие файла тестовой БД.** Аварийная заглушка больше не
   разрешает рабочие операции, если каталог тестового хранилища существует, а
   БД исчезла: режим неизвестен → fail-closed. Дополнительно блокируется
   свободный текст (`F.text`), а не только команды и фото. Если каталога нет
   вовсе, TEST никогда не включался, рабочий режим продолжает работать.
   Четвёртый цикл (HEAD 5fd4eab) показал ещё один вариант: БД потеряна **вместе
   с маркером**, после перезапуска `initialize()` создаёт пустую БД и
   пользователь снова WORK. Закрыто маркером `test-mode/installed` и флагом
   `meta.recovered=1`: при потере БД блокируются команды, фото и текст до
   восстановления.
   Тесты: `test_recreated_db_after_marker_loss_fails_closed`,
   `test_first_install_is_not_recovered`,
   `test_unavailable_mode_stays_closed_if_test_db_moves`,
   `test_unavailable_mode_blocks_free_text_for_test_user`.

2. **Установщик.** После внутреннего аудита исправлены: откат живой БД (снимок и
   откат теперь только кода), привязка к имени `max-finance-stage` (теперь
   `$PROJECT`), проверка службы только через `sv status` (теперь два замера PID
   и обнаружение crash-loop), поиск `sv` в `PATH` (теперь `$PREFIX/bin/sv`),
   непроверенный SHA-256 (теперь `sha256sum -c`). Проверено dry-run на телефоне
   (`TEST_PACKAGE_OK`, `DRY_RUN`, `sha256sum -c`, `$PREFIX/bin/sv`) и локальная
   симуляция семи сценариев: `reports/installer-simulation.txt`.

3. **Маркеры режима.** `backup`/`restore` переносят каталог `active/`, поэтому
   fail-closed режим переживает восстановление.

4. **Регрессии:** устаревшая сводка, завершение ручного отчёта после сбоя
   OCR, обязательное фото в `verify_backup`, путь к фото в Undo после
   `restore`.

Итог: **103 + 7 baseline, 0 failures**. Независимой проверки этих изменений
по-прежнему нет.

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

## Цикл 7 — вердикт и исправления

Цикл 7 (HEAD 423ec13) дал **VERDICT: REVISE**; новых BLOCKER нет, один MAJOR:

**MAJOR — регрессионный тест не обнаруживал дефект шестого цикла.**
`tests/test_dispatch_isolation.py:114–127, 156–168`. Тест удаления таблицы
`settings` использовал `recovered_store()`, который заранее ставил
`meta.recovered=1`, поэтому он проходил и со старой `_has_schema()` из
`ccee903`.

Замечание проверено по коду и подтверждено: `recovered_store()` удалял файл БД,
создавал пустой и возвращал хранилище с `recovered=True`; после
`DROP TABLE settings` повторный `initialize()` шёл в ветку `else` и читал уже
записанный `meta.recovered=1`. Утверждение теста выполнялось на любой
реализации проверки схемы.

Исправлено:

1. `damaged_store_root()` — здоровая база (`recovered=False`), включение TEST,
   затем `DROP TABLE settings` и удаление маркера `active/1`; предусловие
   проверяет полноту схемы до повреждения.
2. `test_dispatcher_blocks_when_meta_survives_but_settings_table_is_lost`
   переписан на этот сценарий: `initialize()` → `recovered=True` → `/sync`,
   текст и фото не доходят до WORK.
3. Мета-тест `test_old_schema_check_would_let_user_back_into_work`: с
   `_has_schema()` из `ccee903` тот же сценарий обязан дать `recovered=False` и
   доставку всех трёх обновлений в WORK.
4. `tools/verify_regression_catches_settings_bug.py` — тот же контроль вне
   pytest: `OLD_IMPLEMENTATION=FAIL`, `CURRENT_IMPLEMENTATION=PASS`,
   `NEGATIVE_CONTROL=OK`.
5. `tools/make_changes_manifest.py` больше не включает `.pytest_cache` и
   внутренние скрипты раундов; манифест пересобран по текущим файлам.

Итог: **112 + 7 baseline, 0 failures** (`reports/tests-at-head.txt`). Восьмой
цикл не проводился; APPROVE нет.

## Восьмой цикл — BLOCKED (техническая причина)

Вердикт: `VERDICT: BLOCKED`. Новых BLOCKER/MAJOR нет. Замечание седьмого цикла
подтверждено закрытым: `tests/test_dispatch_isolation.py:156-231` — сценарий
начинается со здоровой БД, мета-тест `old_has_schema` доказывает воспроизведение
дефекта на `ccee903`; `reports/tests-at-head.txt` — 112 + 7 PASS и
`NEGATIVE_CONTROL=OK`.

Единственная причина BLOCKED — среда проверки: нет `aiogram` и сетевого доступа
для независимого повторного прогона. Это не дефект пакета, поэтому добавлено
независимое исполнение:

1. `.github/workflows/ci.yml`, job `maxfinance-test`: Ubuntu, Python 3.12,
   `pip install -r requirements.txt` из PyPI, `pytest tests tests_baseline`,
   отрицательный контроль, `sh deploy/tests/simulate-install.sh`, артефакты.
2. Прогон 46059242077 (коммит `ad8168f`) — success:
   `119 passed in 1.81s`, `NEGATIVE_CONTROL=OK`, установщик 7/7
   (`reports/ci-run.txt`).
3. Код после `cad6262` не менялся: в `a6a798b` и `ad8168f` только CI, счётчик
   тестов в README и строка README в `reports/changes.diff`.

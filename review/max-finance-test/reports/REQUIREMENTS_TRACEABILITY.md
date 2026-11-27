# Трассировка цели → артефакты → проверки

Код проверен на `0fb30c2` (`review/max-finance-test-20261127`, PR #38); этот
файл добавлен docs-коммитом поверх — код с `cad6262` не менялся.
Все прогоны ниже — в чистом клоне ветки на `0fb30c2`, 27.11.2026 23:12 MSK.

## 1. Найти проект, фотобазу и сервер

| Артефакт | Где |
|---|---|
| Проект PROD | `/root/max-finance-stage` на телефоне (proot Ubuntu), служба `max-finance` |
| Фотобаза | `testdata/` (19 снимков + манифесты), рабочая папка фото на телефоне |
| Сервер | Samsung S20 FE, Termux + proot Ubuntu, `runsvdir` |

Проверено раундами 1–2; повторно 27.11.2026 23:01 MSK — служба `run: pid 20786`,
8,4 суток аптайма, `finance.db` 37 отчётов.

## 2. Полная резервная копия

| Код | Проверки |
|---|---|
| `deploy/backup-production.sh` (проект + `.env` + `finance.db`, sha256 и PRAGMA integrity_check) | `tests/test_store.py` (17 passed): `test_backup_includes_input_photos`, `test_backup_restore_and_tamper_detection`, `test_backup_restore_keeps_mode_markers`, `test_restore_rewrites_photo_path_in_undo_history`, `test_verify_backup_requires_photo_from_database` |

Копия 32,6 МБ на телефоне и на Windows, SHA-256 и восстановление проверены:
`reports/backup-verification.json`.

## 3. Изолированный режим «MAX FINANCE TEST» в том же боте

| Код | Проверки |
|---|---|
| `bot.py:13` `import maxfinance_test`; `bot.py:232` перехват фото; `bot.py:598-604` подключение router или заглушки `UnavailableTestMode` | `tests/test_isolation.py` — 7 passed: `test_test_sheet_cannot_equal_prod_sheet`, `test_test_db_cannot_be_prod_db`, `test_test_package_has_no_google_or_prod_sync_calls` и др. |
| Отдельная SQLite и фото, fail-closed при потере/повреждении/неполной схеме | `tests/test_dispatch_isolation.py` — 4 passed (через диспетчер aiogram); `tests/test_cycle3_regressions.py` — 15 passed |

## 4. Полное ручное редактирование

| Код | Проверки |
|---|---|
| `maxfinance_test/model.py`, `maxfinance_test/ui.py` | `tests/test_model.py` — 30 passed: `test_every_item_is_editable_and_signs_change`, `test_split_and_merge`, `test_delete_add_move_undo`, `test_manual_category_total_does_not_change_employee_amounts`, `test_negative_single_amount_remains_negative_by_default`, `test_negative_term_with_plus_sign_is_preserved_as_minus` |
| Клавиатуры и тексты | `tests/test_ui.py` — 11 passed: `test_items_text_and_keyboard_cover_every_action`, `test_item_keyboard_exposes_every_edit`, `test_terms_and_signs_keyboard` |
| Сценарии подтверждения | `tests/test_flow.py` — 7 passed |

## 5. Линия распознавания

| Код | Проверки |
|---|---|
| `maxfinance_test/line.py`, `maxfinance_test/ocr.py` | `tests/test_ocr.py` — 13 passed: `test_minus_sign_is_applied`, `test_struck_line_is_kept_but_requires_confirmation`, `test_no_invented_itog`, `test_bbox_normalized_and_out_of_range_dropped` |
| Привязка линии к SHA-256 фото | `tests/test_flow.py`: `test_line_persists_for_same_photo`; инструмент `tools/check_line.py` |

## 6. Словарь сотрудников

| Код | Проверки |
|---|---|
| `maxfinance_test/aliases.py` | `tests/test_aliases.py` — 8 passed: `test_confirmed_dictionary`, `test_unknown_is_not_guessed`, `test_ambiguous_prefix_not_merged`, `test_add_employee_preserves_history`, `test_latin_homoglyph_is_normalized_not_merged` |
| Добавление/переименование/деактивация в базе | `tests/test_store.py`: `test_seed_preserves_all_staff_and_adds_missing`, `test_conflicting_alias_is_not_silently_merged`, `test_removed_alias_is_not_restored_on_restart`; `tests/test_cycle3_regressions.py`: `test_add_employee_after_deactivating_max_id` |

## 7. База подтверждённых примеров

| Код | Проверки |
|---|---|
| `maxfinance_test/store.py` (эталоны, holdout, ошибки) | `tests/test_store.py`: `test_confirmed_example_requires_valid_report`, `test_duplicate_confirmation_is_rejected`, `test_holdout_never_used_for_few_shot`, `test_error_types_recorded`, `test_export_examples` |

## 8. Тестирование

| Прогон | Результат |
|---|---|
| Полный набор в чистом клоне | 112 + 7 baseline, `exit=0` |
| По файлам (для матрицы) | model 30, ui 11, flow 7, ocr 13, aliases 8, store 17, isolation 7, dispatch 4, cycle3 15, baseline 7 — все exit=0 |
| Отрицательный контроль | `OLD_IMPLEMENTATION=FAIL`, `CURRENT_IMPLEMENTATION=PASS`, `NEGATIVE_CONTROL=OK` |
| Независимый прогон в CI | run 46060253125 (head `0fb30c2`) — success, все шаги |

## 9. Независимая проверка Superagent — **ожидает действия владельца**

Нужен Issue в `naspirator/max-superagent-lab` от `naspirator` (агент пропускает
свои задачи). Текст готов: `reports/SUPERAGENT_TRIGGER.md`.

## 10. Независимая приёмка ChatGPT

Восемь циклов выполнены (вердикты в `reports/chatgpt-review-cycle*.txt`).
Восьмой вернул технический BLOCKED (нет `aiogram` в среде проверки); снятие
подтверждено CI-прогоном и пакетом `review-package-14.tar.gz`. Девятый цикл —
промпт `reports/chatgpt-cycle9-ask.txt`, вердикт ожидается.

## 11. PROD не внедрён без согласования

| Механизм | Где |
|---|---|
| Установщик по умолчанию только проверяет пакет | `deploy/install-test-mode.sh:15,52-53` (`OWNER_APPROVED`), 7 сценариев симуляции PASS |
| Откат к резервной копии | `deploy/rollback-production.sh` (DRY_RUN без `APPLY=1`) |
| PROD не менялся | `bot.py` `48fbb5d6…`, `finance.db` `438ecc57…` — совпадают с копией; тестовых артефактов нет |

Итог: пункты 1–4, 6, 8, 11 закрыты доказательствами; 5 и 7 — покрыты тестами;
9 и 10 — внешние проверки, ожидают человека.

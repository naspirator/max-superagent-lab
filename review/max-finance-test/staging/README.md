# MAX FINANCE TEST — staging

Тестовый режим внутри действующего Telegram-бота MAX FINANCE. Не заменяет
рабочий бот, не создаёт второго бота и не меняет токен. Рабочая база и
Google-таблица не используются.

## Что здесь лежит

- `maxfinance_test/` — новый тестовый режим: модель отчёта, OCR, словарь,
  хранилище, Telegram-интерфейс, база подтверждённых примеров.
- `bot.py` — копия действующего `bot.py` с тремя точками подключения
  (`import`, вызов `handle_photo`, включение router в `main`).
- `finance_v3.py`, `ocr_v3.py`, `reports.py`, `sheets_v3.py` — копии текущих
  рабочих модулей без изменений (для diff и тестов).
- `tests/` — 112 тестов нового режима и изоляции.
- `tests_baseline/` — 7 характеризационных тестов действующего кода.
- `tools/` — проверка API, линий, резервной копии, сравнение OCR, макет UI.
- `deploy/` — скрипты резервного копирования, установки после согласования и
  отката.

## Запуск тестов

```bash
python -m pip install -r requirements.txt
python -m pytest tests tests_baseline -q
python tools/verify_regression_catches_settings_bug.py
```

То же выполняет job `maxfinance-test` в `.github/workflows/ci.yml`:
чистое окружение Ubuntu, зависимости из PyPI.

## Проверка на реальных фото

```powershell
$env:OCR_DEBUG_DIR="E:\MAX-FINANCE-TEST\reports\ocr-raw"
python tools\evaluate.py
```

## Важно

- Не запускать второй polling на действующем токене.
- Установка в `/root/max-finance-stage` — только после явного согласования
  владельца (`OWNER_APPROVED=1`).
- Перед установкой: `sh deploy/tests/simulate-install.sh` (локальная проверка
  логики, PROD не затрагивается).
- Без `OWNER_APPROVED=1` установщик делает только проверку пакета.
- Все секреты остаются в рабочей папке; в staging их нет.

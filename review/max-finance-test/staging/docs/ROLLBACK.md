# Откат MAX FINANCE

## Что уже сохранено

Полная резервная копия действующего проекта:

- на телефоне: `/data/data/com.termux/files/home/max-server/transfer/max-finance-prod-20261127-182625.tar.gz`
- на Windows: `E:\MAX-FINANCE-TEST\backups\max-finance-prod-20261127-182625.tar.gz`
- SHA-256: см. `reports/backup-verification.json`
- внутри архива: `bot.py`, `finance_v3.py`, `ocr_v3.py`, `reports.py`,
  `sheets_v3.py`, `finance.db`, `.env`, `google_credentials.json`,
  `rollback-*.py`, `start-finance.sh`, виртуальное окружение.

Проверено 27.11.2026:

- архив распаковывается;
- SHA-256 файлов совпадают с действующей копией;
- `PRAGMA integrity_check` базы — `ok`;
- 37 отчётов, 9 сотрудников;
- код после порчи восстанавливается из архива, база при этом не меняется.

Отчёт проверки: `reports/backup-verification.json`.

## Вариант A. Откат только кода (рекомендуется)

База, сотрудники, история, токены и текущие настройки остаются на месте.

```sh
# В Termux, не внутри proot
scp max-finance-prod-20261127-182625.tar.gz \
  u0_a357@192.168.0.12:/data/data/com.termux/files/home/max-server/transfer/

ssh -p 8022 u0_a357@192.168.0.12
cd ~
APPLY=1 sh ~/rollback-production.sh \
  ~/max-server/transfer/max-finance-prod-20261127-182625.tar.gz
```

Скрипт:

1. проверяет SHA-256;
2. делает `pre-rollback-*.tar.gz` текущего состояния;
3. останавливает службу `max-finance`;
4. восстанавливает только код (`bot.py`, `finance_v3.py`, `ocr_v3.py`,
   `reports.py`, `sheets_v3.py`);
5. запускает службу и печатает `sv status`.

База не заменяется. Тестовая папка `max-finance-stage/test-mode` не удаляется:
она изолирована и не влияет на рабочий режим.

## Вариант B. Полный откат с базой

Только если база повреждена или владелец явно требует откатить финансовые
данные. Откат базы потеряет отчёты, созданные после резервной копии.

```sh
APPLY=1 RESTORE_DB=1 sh ~/rollback-production.sh \
  ~/max-server/transfer/max-finance-prod-20261127-182625.tar.gz
```

Перед заменой базы скрипт всё равно создаёт `pre-rollback-*.tar.gz`.

## Вариант C. Удалить только тестовый режим

```sh
# после остановки службы и только с согласования владельца
proot-distro login ubuntu -- rm -rf /root/max-finance-stage/maxfinance_test
# вернуть bot.py из резервной копии
APPLY=1 sh ~/rollback-production.sh <архив>
```

Тестовая база `test-mode/` может остаться: она не читается рабочим режимом.

## Проверка после отката

```sh
~/max-server/maxctl status finance
tail -n 100 $PREFIX/var/log/sv/max-finance/current
curl -s "https://api.telegram.org/bot<TOKEN>/getMe"   # не печатать токен в чат
```

Проверить в Telegram:

1. `/start` отвечает;
2. приходит фото и ставится линия;
3. суммы распределяются;
4. `/day` показывает прежние данные;
5. `/sync` не требуется, если Google-таблица не менялась.

## Запрещено

- запускать второй polling на том же токене;
- заменять рабочего бота до `APPROVE` ChatGPT и явного согласования владельца;
- откатывать базу без отдельного подтверждения: это потеря финансовых записей;
- удалять `.env`, `google_credentials.json`, `finance.db` и папку `test-mode`.

#!/data/data/com.termux/files/usr/bin/sh
# Откат действующего проекта к полной резервной копии.
# Запускать в Termux (не внутри proot), из дома:
#   APPLY=1 sh ~/rollback-production.sh /path/to/max-finance-prod-....tar.gz
# Без APPLY=1 скрипт только проверяет архив и печатает план.
set -eu

ARCHIVE="${1:-}"
PROJECT=/root/max-finance-stage
SERVICE=max-finance
APPLY="${APPLY:-0}"
RESTORE_DB="${RESTORE_DB:-0}"

[ -n "$ARCHIVE" ] || { echo "Укажи архив"; exit 2; }
[ -f "$ARCHIVE" ] || { echo "Архив не найден: $ARCHIVE"; exit 2; }

if [ -f "$ARCHIVE.sha256" ]; then
    (cd "$(dirname "$ARCHIVE")" && sha256sum -c "$(basename "$ARCHIVE").sha256")
fi

echo "=== Содержимое архива (ключевые файлы) ==="
tar tzf "$ARCHIVE" | grep -E 'max-finance-stage/(bot.py|finance_v3.py|ocr_v3.py|reports.py|sheets_v3.py|finance.db|\.env)$' || true

if [ "$APPLY" != "1" ]; then
    echo "DRY_RUN: для применения запусти с APPLY=1 (остановит службу $SERVICE)"
    echo "RESTORE_DB=$RESTORE_DB (0 — сохранить текущую базу)"
    exit 0
fi

if [ ! -f "$PROJECT/bot.py" ]; then
    echo "Нет проекта $PROJECT"
    exit 2
fi

STAMP=$(date +%Y%m%d-%H%M%S)
PRE="/data/data/com.termux/files/home/max-server/transfer/pre-rollback-$STAMP.tar.gz"
echo "=== Снимок текущего состояния: $PRE ==="
proot-distro login ubuntu -- tar czf "$PRE" -C /root max-finance-stage
(cd "$(dirname "$PRE")" && sha256sum "$(basename "$PRE")") > "$PRE.sha256"

echo "=== Остановка службы ==="
sv down "$SERVICE" || true
sleep 2

echo "=== Восстановление кода ==="
proot-distro login ubuntu -- tar xzf "$ARCHIVE" -C /root \
    max-finance-stage/bot.py \
    max-finance-stage/finance_v3.py \
    max-finance-stage/ocr_v3.py \
    max-finance-stage/reports.py \
    max-finance-stage/sheets_v3.py

if [ "$RESTORE_DB" = "1" ]; then
    echo "=== Восстановление базы (текущая будет сохранена в pre-rollback) ==="
    proot-distro login ubuntu -- tar xzf "$ARCHIVE" -C /root max-finance-stage/finance.db
fi

echo "=== Запуск службы ==="
sv up "$SERVICE"
sleep 5
sv status "$SERVICE"
echo "ROLLBACK_APPLIED $ARCHIVE"

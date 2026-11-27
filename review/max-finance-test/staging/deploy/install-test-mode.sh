#!/data/data/com.termux/files/usr/bin/sh
# Установка тестового режима в действующий бот.
# ТОЛЬКО после явного согласования владельца:
#   OWNER_APPROVED=1 SOURCE=/root/max-finance-test-deploy sh ~/install-test-mode.sh
# Без OWNER_APPROVED=1 скрипт только проверяет пакет.
set -eu

OWNER_APPROVED="${OWNER_APPROVED:-0}"
SOURCE="${SOURCE:-/root/max-finance-test-deploy}"
PROJECT=/root/max-finance-stage
SERVICE=max-finance

[ -d "$SOURCE/maxfinance_test" ] || { echo "Нет пакета: $SOURCE"; exit 2; }
[ -f "$SOURCE/bot.py" ] || { echo "Нет bot.py в пакете"; exit 2; }

echo "=== Проверка пакета ==="
python3 -m py_compile "$SOURCE/bot.py"
for f in "$SOURCE"/maxfinance_test/*.py; do python3 -m py_compile "$f"; done
echo "PACKAGE_COMPILE_OK"

if [ "$OWNER_APPROVED" != "1" ]; then
    echo "DRY_RUN: установка не выполнена. Нужно явное OWNER_APPROVED=1."
    exit 0
fi

STAMP=$(date +%Y%m%d-%H%M%S)
PRE="/data/data/com.termux/files/home/max-server/transfer/pre-install-$STAMP.tar.gz"
echo "=== Снимок до установки: $PRE ==="
proot-distro login ubuntu -- tar czf "$PRE" -C /root max-finance-stage
(cd "$(dirname "$PRE")" && sha256sum "$(basename "$PRE")") > "$PRE.sha256"

echo "=== Установка файлов ==="
proot-distro login ubuntu -- sh -c "
set -eu
cp -a '$SOURCE/bot.py' '$PROJECT/bot.py'
rm -rf '$PROJECT/maxfinance_test'
cp -a '$SOURCE/maxfinance_test' '$PROJECT/maxfinance_test'
cd '$PROJECT'
.venv/bin/python -c 'import maxfinance_test; print("TEST_PACKAGE_OK")'
"

echo "=== Перезапуск службы ==="
sv restart "$SERVICE"
sleep 6
sv status "$SERVICE"
echo "INSTALLED. Проверь лог: tail -n 100 \$PREFIX/var/log/sv/max-finance/current"

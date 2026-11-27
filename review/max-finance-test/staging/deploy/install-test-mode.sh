#!/data/data/com.termux/files/usr/bin/sh
# Установка тестового режима в действующий бот.
#
# Запуск из Termux, не из proot:
#   OWNER_APPROVED=1 sh ~/install-test-mode.sh
#
# Пакет кладётся в Termux home: ~/max-finance-test-deploy
# (изнутри Ubuntu тот же путь виден как
#  /data/data/com.termux/files/home/max-finance-test-deploy).
#
# Без OWNER_APPROVED=1 скрипт только проверяет пакет и ничего не меняет.
# Установка выполняется только после явного согласования владельца.
set -eu

OWNER_APPROVED="${OWNER_APPROVED:-0}"
SOURCE="${SOURCE:-$HOME/max-finance-test-deploy}"
PROJECT="${PROJECT:-/root/max-finance-stage}"
SERVICE="${SERVICE:-max-finance}"
SNAPSHOT_ROOT="${SNAPSHOT_ROOT:-/root}"
SERVICE_DIR="${SERVICE_DIR:-${PREFIX:-/data/data/com.termux/files/usr}/var/service/$SERVICE}"
PYTHON="$PROJECT/.venv/bin/python"

[ -d "$SOURCE/maxfinance_test" ] || { echo "Нет пакета: $SOURCE"; exit 2; }
[ -f "$SOURCE/bot.py" ] || { echo "Нет bot.py в пакете"; exit 2; }
proot-distro login ubuntu -- test -x "$PYTHON" || { echo "Нет python проекта: $PYTHON"; exit 2; }

# Проверка синтаксиса и импорта выполняется тем же интерпретатором и в том
# же окружении, в котором работает бот. Ничего не копирует.
check_package() {
    src="$1"
    proot-distro login ubuntu -- sh -s "$src" "$PYTHON" <<'INNER_CHECK'
set -eu
src="$1"
python="$2"
"$python" -m py_compile "$src/bot.py"
for f in "$src"/maxfinance_test/*.py; do "$python" -m py_compile "$f"; done
cd "$src"
"$python" -c 'import maxfinance_test; print("TEST_PACKAGE_OK")'
INNER_CHECK
}

echo "=== Проверка пакета ==="
if ! check_package "$SOURCE"; then
    echo "ОШИБКА: пакет не компилируется или не импортируется. Установка не начата."
    exit 2
fi
echo "PACKAGE_COMPILE_OK"

if [ "$OWNER_APPROVED" != "1" ]; then
    echo "DRY_RUN: пакет проверен. Установка не выполнена; нужно явное OWNER_APPROVED=1."
    exit 0
fi

STAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="$HOME/max-server/transfer"
PRE="$BACKUP_DIR/pre-install-$STAMP.tar.gz"
mkdir -p "$BACKUP_DIR"
echo "=== Снимок до установки: $PRE ==="
proot-distro login ubuntu -- tar czf "$PRE" -C "$SNAPSHOT_ROOT" max-finance-stage
sha256sum "$PRE" > "$PRE.sha256"
proot-distro login ubuntu -- tar tzf "$PRE" >/dev/null

rollback() {
    echo "=== ОТКАТ: восстанавливаю снимок $PRE ==="
    if ! proot-distro login ubuntu -- tar tzf "$PRE" >/dev/null 2>&1; then
        echo "ОШИБКА: снимок нечитаем, автоматический откат невозможен: $PRE"
        return 1
    fi
    proot-distro login ubuntu -- sh -c "rm -rf '$SNAPSHOT_ROOT/max-finance-stage' && tar xzf '$PRE' -C '$SNAPSHOT_ROOT'"
    sv restart "$SERVICE_DIR" || true
    sleep 6
    sv status "$SERVICE_DIR" || true
}

echo "=== Установка файлов ==="
if ! proot-distro login ubuntu -- sh -s "$SOURCE" "$PROJECT" "$STAMP" <<'INNER_INSTALL'
set -eu
src="$1"
project="$2"
stamp="$3"
python="$project/.venv/bin/python"
incoming="$project/.incoming-$stamp"
old="$project/.previous-$stamp"
cleanup() { rm -rf "$incoming"; }
trap cleanup EXIT

rm -rf "$incoming" "$old"
mkdir -p "$incoming"
cp -a "$src/bot.py" "$incoming/bot.py"
cp -a "$src/maxfinance_test" "$incoming/maxfinance_test"
rm -rf "$incoming/maxfinance_test/__pycache__"
# Проверяем новый пакет ДО замены рабочих файлов.
cd "$incoming"
"$python" -c 'import maxfinance_test; print("TEST_PACKAGE_OK")'

cd "$project"
if [ -e "$project/maxfinance_test" ]; then
    mv "$project/maxfinance_test" "$old"
fi
mv "$incoming/maxfinance_test" "$project/maxfinance_test"
cp "$incoming/bot.py" "$project/.bot.py.new"
mv "$project/.bot.py.new" "$project/bot.py"
rm -rf "$old"
echo "TEST_PACKAGE_SWAPPED"
INNER_INSTALL
then
    echo "ОШИБКА установки файлов. Рабочие файлы восстанавливаются из снимка."
    rollback
    exit 3
fi

echo "=== Перезапуск службы ==="
sv restart "$SERVICE_DIR" || true
sleep 6
STATUS=$(sv status "$SERVICE_DIR" 2>&1 || true)
echo "$STATUS"
case "$STATUS" in
    run:*) ;;
    *)
        echo "ОШИБКА: служба $SERVICE не запустилась. Выполняю откат."
        rollback
        exit 4
        ;;
esac

echo "INSTALLED. Проверь лог: tail -n 100 \$PREFIX/var/log/sv/max-finance/current"

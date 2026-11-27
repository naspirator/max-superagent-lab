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
PREFIX_DIR="${PREFIX:-/data/data/com.termux/files/usr}"
SV_BIN="${SV_BIN:-$PREFIX_DIR/bin/sv}"
SERVICE_DIR="${SERVICE_DIR:-$PREFIX_DIR/var/service/$SERVICE}"
PYTHON="$PROJECT/.venv/bin/python"

[ -d "$SOURCE/maxfinance_test" ] || { echo "Нет пакета: $SOURCE"; exit 2; }
[ -f "$SOURCE/bot.py" ] || { echo "Нет bot.py в пакете"; exit 2; }
[ -x "$SV_BIN" ] || { echo "Нет sv: $SV_BIN"; exit 2; }
[ -d "$SERVICE_DIR" ] || { echo "Нет службы: $SERVICE_DIR"; exit 2; }
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

echo "=== Снимок кода до установки: $PRE ==="
# Снимок только заменяемых файлов. База, .venv и остальные рабочие данные
# не копируются и не откатываются: откат базы без отдельного подтверждения
# запрещён (docs/ROLLBACK.md).
if ! proot-distro login ubuntu -- sh -s "$PROJECT" "$PRE" <<'INNER_SNAP'
set -eu
project="$1"
pre="$2"
cd "$project"
if [ -e maxfinance_test ]; then
    tar czf "$pre" bot.py maxfinance_test
else
    tar czf "$pre" bot.py
fi
INNER_SNAP
then
    rm -f "$PRE" "$PRE.sha256"
    echo "ОШИБКА: не удалось создать снимок кода. Установка не начата."
    exit 2
fi
sha256sum "$PRE" > "$PRE.sha256"
if ! sha256sum -c "$PRE.sha256" >/dev/null; then
    rm -f "$PRE" "$PRE.sha256"
    echo "ОШИБКА: SHA-256 снимка не совпадает. Установка не начата."
    exit 2
fi
proot-distro login ubuntu -- tar tzf "$PRE" >/dev/null

rollback() {
    echo "=== ОТКАТ: восстанавливаю bot.py и maxfinance_test из $PRE ==="
    if ! sha256sum -c "$PRE.sha256" >/dev/null 2>&1; then
        echo "ОШИБКА: SHA-256 снимка не совпадает, автоматический откат невозможен: $PRE"
        return 0
    fi
    if ! proot-distro login ubuntu -- sh -s "$PROJECT" "$PRE" <<'INNER_ROLLBACK'
set -eu
project="$1"
pre="$2"
cd "$project"
rm -rf maxfinance_test
tar xzf "$pre" -C "$project"
INNER_ROLLBACK
    then
        echo "ОШИБКА: не удалось восстановить код из снимка: $PRE"
        return 0
    fi
    "$SV_BIN" restart "$SERVICE_DIR" || true
    sleep 6
    "$SV_BIN" status "$SERVICE_DIR" || true
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
rm -rf "$project/maxfinance_test/__pycache__"
echo "TEST_PACKAGE_SWAPPED"
INNER_INSTALL
then
    echo "ОШИБКА установки файлов. Рабочий код восстанавливается из снимка."
    rollback
    exit 3
fi

echo "=== Перезапуск службы ==="
"$SV_BIN" restart "$SERVICE_DIR" || true
sleep 6
STATUS1=$("$SV_BIN" status "$SERVICE_DIR" 2>&1 || true)
echo "$STATUS1"
case "$STATUS1" in
    run:*) ;;
    *)
        echo "ОШИБКА: служба $SERVICE не запустилась. Выполняю откат кода."
        rollback
        exit 4
        ;;
esac
PID1=$(printf '%s\n' "$STATUS1" | sed -n 's/.*(pid \([0-9][0-9]*\)).*/\1/p' | head -n 1)
sleep 4
STATUS2=$("$SV_BIN" status "$SERVICE_DIR" 2>&1 || true)
echo "$STATUS2"
PID2=$(printf '%s\n' "$STATUS2" | sed -n 's/.*(pid \([0-9][0-9]*\)).*/\1/p' | head -n 1)
if [ -z "$PID1" ] || [ "$PID1" != "$PID2" ]; then
    echo "ОШИБКА: служба $SERVICE перезапускается (crash-loop). Выполняю откат кода."
    rollback
    exit 4
fi

echo "INSTALLED. Проверь лог: tail -n 100 \$PREFIX/var/log/sv/max-finance/current"

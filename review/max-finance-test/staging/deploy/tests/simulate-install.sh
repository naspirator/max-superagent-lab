#!/bin/sh
# Локальная проверка логики deploy/install-test-mode.sh без телефона.
# Запускать в Linux/POSIX-окружении: sh deploy/tests/simulate-install.sh
# PROD не затрагивается: все пути находятся во временном каталоге.
set -eu

INSTALLER="$(cd "$(dirname "$0")/.." && pwd)/install-test-mode.sh"
BASE=$(mktemp -d)
trap 'rm -rf "$BASE"' EXIT
export LC_ALL=C.UTF-8

BIN="$BASE/bin"
HOME_DIR="$BASE/home"
ROOT="$BASE/root"
PROJ="$ROOT/max-finance-stage"
SRC="$BASE/source"
mkdir -p "$BIN" "$HOME_DIR/max-server/transfer" "$ROOT" "$SRC"

cat > "$BIN/proot-distro" <<'STUB'
#!/bin/sh
if [ "$1" = "login" ]; then
    shift
    [ "${1:-}" = "ubuntu" ] && shift
    [ "${1:-}" = "--" ] && shift
fi
exec "$@"
STUB
chmod +x "$BIN/proot-distro"

make_sv() {
    cat > "$BIN/sv" <<STUB
#!/bin/sh
echo "sv \$*" >> "\${SV_LOG:-/dev/null}"
case "\$1" in
    status) echo "$1";;
    restart) echo "restart ok";;
esac
STUB
    chmod +x "$BIN/sv"
}

make_project() {
    rm -rf "$PROJ"
    mkdir -p "$PROJ/.venv/bin" "$PROJ/maxfinance_test"
    printf '#!/bin/sh\nexec python3 "$@"\n' > "$PROJ/.venv/bin/python"
    chmod +x "$PROJ/.venv/bin/python"
    printf 'print("OLD BOT")\n' > "$PROJ/bot.py"
    printf 'VALUE = "old"\n' > "$PROJ/maxfinance_test/__init__.py"
}

make_source() {
    rm -rf "$SRC"
    mkdir -p "$SRC/maxfinance_test"
    printf 'print("NEW BOT")\n' > "$SRC/bot.py"
    printf 'VALUE = "new"\nprint("import ok")\n' > "$SRC/maxfinance_test/__init__.py"
}

run_installer() {
    HOME="$HOME_DIR" SOURCE="$SRC" PROJECT="$PROJ" SNAPSHOT_ROOT="$ROOT" \
    SERVICE=max-finance PATH="$BIN:$PATH" \
    sh "$INSTALLER"
}

assert_file_contains() {
    grep -q "$2" "$1" || { echo "FAIL: $1 does not contain $2"; exit 1; }
}

echo "=== 1. Успешная установка ==="
make_project
make_source
make_sv "run: max-finance: (pid 100) 1s"
OUT=$(OWNER_APPROVED=1 run_installer 2>&1) || { echo "$OUT"; exit 1; }
echo "$OUT" | grep -q TEST_PACKAGE_SWAPPED || { echo "$OUT"; exit 1; }
assert_file_contains "$PROJ/bot.py" "NEW BOT"
assert_file_contains "$PROJ/maxfinance_test/__init__.py" 'VALUE = "new"'
[ -d "$HOME_DIR/max-server/transfer" ] || exit 1
ls "$HOME_DIR"/max-server/transfer/pre-install-*.tar.gz >/dev/null
echo "PASS: установка заменила файлы"
echo "$OUT" | grep -q "INSTALLED" || exit 1

echo "=== 2. Служба не поднялась — откат ==="
make_project
make_source
make_sv "down: max-finance: 1s, normally up"
set +e
OUT=$(OWNER_APPROVED=1 run_installer 2>&1)
RC=$?
set -e
echo "$OUT" | grep -q "ОТКАТ" || { echo "$OUT"; exit 1; }
[ "$RC" -eq 4 ] || { echo "unexpected rc=$RC"; echo "$OUT"; exit 1; }
assert_file_contains "$PROJ/bot.py" "OLD BOT"
assert_file_contains "$PROJ/maxfinance_test/__init__.py" 'VALUE = "old"'
echo "PASS: при сбое службы восстановлен снимок"

echo "=== 3. Без OWNER_APPROVED — dry-run без изменений ==="
make_project
make_source
make_sv "run: max-finance: (pid 100) 1s"
OUT=$(run_installer 2>&1)
echo "$OUT" | grep -q "DRY_RUN" || { echo "$OUT"; exit 1; }
assert_file_contains "$PROJ/bot.py" "OLD BOT"
assert_file_contains "$PROJ/maxfinance_test/__init__.py" 'VALUE = "old"'
echo "PASS: dry-run ничего не изменил"

echo "=== 4. Пакет не импортируется — до замены файлов ==="
make_project
make_source
printf 'raise ImportError("broken package")\n' > "$SRC/maxfinance_test/__init__.py"
make_sv "run: max-finance: (pid 100) 1s"
set +e
OUT=$(OWNER_APPROVED=1 run_installer 2>&1)
RC=$?
set -e
[ "$RC" -ne 0 ] || { echo "installer unexpectedly succeeded"; exit 1; }
assert_file_contains "$PROJ/bot.py" "OLD BOT"
assert_file_contains "$PROJ/maxfinance_test/__init__.py" 'VALUE = "old"'
echo "PASS: битый пакет отклонён до замены (rc=$RC)"

echo "ALL INSTALLER SIMULATION CHECKS PASSED"

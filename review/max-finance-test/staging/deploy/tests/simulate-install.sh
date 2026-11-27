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
SVC="$BASE/service/max-finance"
mkdir -p "$BIN" "$HOME_DIR/max-server/transfer" "$ROOT" "$SRC" "$SVC"

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

cat > "$BIN/sv" <<'STUB'
#!/bin/sh
echo "sv $*" >> "${SV_LOG:-/dev/null}"
case "$1" in
    status)
        mode="${SV_MODE:-run}"
        if [ "$mode" = "crash" ]; then
            n=$(cat "${SV_COUNTER:-/dev/null}" 2>/dev/null || echo 0)
            n=$((n + 1))
            echo "$n" > "${SV_COUNTER:-/dev/null}"
            echo "run: $2: (pid $((100 + n))) 1s"
        elif [ "$mode" = "down" ]; then
            echo "down: $2: 1s, normally up"
        else
            echo "run: $2: (pid 100) 1s"
        fi
        ;;
    restart) echo "restart ok" ;;
esac
STUB
chmod +x "$BIN/sv"

make_project() {
    target="${1:-$PROJ}"
    rm -rf "$target"
    mkdir -p "$target/.venv/bin" "$target/maxfinance_test"
    printf '#!/bin/sh\nexec python3 "$@"\n' > "$target/.venv/bin/python"
    chmod +x "$target/.venv/bin/python"
    printf 'print("OLD BOT")\n' > "$target/bot.py"
    printf 'VALUE = "old"\n' > "$target/maxfinance_test/__init__.py"
    printf 'WORK-DB\n' > "$target/finance.db"
}

make_source() {
    rm -rf "$SRC"
    mkdir -p "$SRC/maxfinance_test"
    printf 'print("NEW BOT")\n' > "$SRC/bot.py"
    printf 'VALUE = "new"\nprint("import ok")\n' > "$SRC/maxfinance_test/__init__.py"
}

run_installer() {
    target="${1:-$PROJ}"
    svmode="${2:-run}"
    HOME="$HOME_DIR" SOURCE="$SRC" PROJECT="$target" SV_MODE="$svmode" \
    SV_BIN="$BIN/sv" SERVICE_DIR="$SVC" SERVICE=max-finance PATH="$BIN:$PATH" \
    SV_COUNTER="$BASE/sv-counter" SV_LOG="$BASE/sv.log" \
    sh "$INSTALLER"
}

assert_file_contains() {
    grep -q "$2" "$1" || { echo "FAIL: $1 does not contain $2"; exit 1; }
}

echo "=== 1. Успешная установка ==="
make_project
make_source
unset SV_MODE || true
OUT=$(OWNER_APPROVED=1 run_installer 2>&1) || { echo "$OUT"; exit 1; }
echo "$OUT" | grep -q TEST_PACKAGE_SWAPPED || { echo "$OUT"; exit 1; }
assert_file_contains "$PROJ/bot.py" "NEW BOT"
assert_file_contains "$PROJ/maxfinance_test/__init__.py" 'VALUE = "new"'
assert_file_contains "$PROJ/finance.db" "WORK-DB"
[ -d "$HOME_DIR/max-server/transfer" ] || exit 1
ls "$HOME_DIR"/max-server/transfer/pre-install-*.tar.gz >/dev/null
echo "$OUT" | grep -q "INSTALLED" || exit 1
echo "PASS: установка заменила код, БД не тронута"

echo "=== 2. Служба не поднялась — откат только кода, БД цела ==="
make_project
make_source
OUT=$(OWNER_APPROVED=1 run_installer "$PROJ" down 2>&1 || true)
RC=$?
echo "$OUT" | grep -q "ОТКАТ" || { echo "$OUT"; exit 1; }
assert_file_contains "$PROJ/bot.py" "OLD BOT"
assert_file_contains "$PROJ/maxfinance_test/__init__.py" 'VALUE = "old"'
assert_file_contains "$PROJ/finance.db" "WORK-DB"
echo "PASS: при сбое службы восстановлен код, БД не откатывалась"

echo "=== 3. Без OWNER_APPROVED — dry-run без изменений ==="
make_project
make_source
OUT=$(run_installer 2>&1)
echo "$OUT" | grep -q "DRY_RUN" || { echo "$OUT"; exit 1; }
assert_file_contains "$PROJ/bot.py" "OLD BOT"
assert_file_contains "$PROJ/maxfinance_test/__init__.py" 'VALUE = "old"'
echo "PASS: dry-run ничего не изменил"

echo "=== 4. Пакет не импортируется — до замены файлов ==="
make_project
make_source
printf 'raise ImportError("broken package")\n' > "$SRC/maxfinance_test/__init__.py"
set +e
OUT=$(OWNER_APPROVED=1 run_installer 2>&1)
RC=$?
set -e
[ "$RC" -eq 2 ] || { echo "unexpected rc=$RC"; echo "$OUT"; exit 1; }
assert_file_contains "$PROJ/bot.py" "OLD BOT"
assert_file_contains "$PROJ/maxfinance_test/__init__.py" 'VALUE = "old"'
echo "PASS: битый пакет отклонён до замены (rc=$RC)"

echo "=== 5. PROJECT override: снимок и откат по целевому каталогу ==="
make_project "$ROOT/other-project"
make_project "$ROOT/max-finance-stage"
printf 'DECOY BOT\n' > "$ROOT/max-finance-stage/bot.py"
make_source
OUT=$(OWNER_APPROVED=1 run_installer "$ROOT/other-project" down 2>&1 || true)
echo "$OUT" | grep -q "ОТКАТ" || { echo "$OUT"; exit 1; }
assert_file_contains "$ROOT/other-project/bot.py" "OLD BOT"
assert_file_contains "$ROOT/max-finance-stage/bot.py" "DECOY BOT"
echo "PASS: откат затронул PROJECT, посторонний каталог не тронут"

echo "=== 6. Crash-loop службы — откат ==="
make_project
make_source
rm -f "$BASE/sv-counter"
OUT=$(OWNER_APPROVED=1 run_installer "$PROJ" crash 2>&1 || true)
echo "$OUT" | grep -q "crash-loop" || { echo "$OUT"; exit 1; }
assert_file_contains "$PROJ/bot.py" "OLD BOT"
echo "PASS: смена PID обнаружена, выполнен откат"

echo "=== 7. Нет sv — установка не начата ==="
make_project
make_source
set +e
OUT=$(HOME="$HOME_DIR" SOURCE="$SRC" PROJECT="$PROJ" SV_BIN=/nonexistent \
      SERVICE_DIR="$SVC" SERVICE=max-finance PATH="$BIN:$PATH" \
      OWNER_APPROVED=1 sh "$INSTALLER" 2>&1)
RC=$?
set -e
[ "$RC" -eq 2 ] || { echo "unexpected rc=$RC"; echo "$OUT"; exit 1; }
assert_file_contains "$PROJ/bot.py" "OLD BOT"
echo "PASS: отсутствие sv отклонено до изменений"

echo "ALL INSTALLER SIMULATION CHECKS PASSED"

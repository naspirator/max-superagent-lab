#!/data/data/com.termux/files/usr/bin/sh
# Полная резервная копия действующего проекта. Запускать внутри proot Ubuntu:
#   proot-distro login ubuntu -- sh /root/backup-production.sh
set -eu

STAMP=$(date +%Y%m%d-%H%M%S)
TARGET=/data/data/com.termux/files/home/max-server/transfer
OUT="$TARGET/max-finance-prod-$STAMP.tar.gz"
PROJECT=/root/max-finance-stage

[ -f "$PROJECT/bot.py" ] || { echo "Нет проекта: $PROJECT"; exit 2; }
mkdir -p "$TARGET"

tar czf "$OUT" -C /root max-finance-stage
(cd "$TARGET" && sha256sum "$(basename "$OUT")") > "$OUT.sha256"
python3 - "$PROJECT/finance.db" <<'PY'
import sqlite3, sys
with sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True) as db:
    result = db.execute("PRAGMA integrity_check").fetchone()[0]
    count = db.execute("SELECT COUNT(*) FROM daily_reports").fetchone()[0]
print("DB_INTEGRITY", result, "REPORTS", count)
if result != "ok":
    raise SystemExit(3)
PY
echo "BACKUP_OK $OUT"

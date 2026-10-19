#!/usr/bin/env bash
# Copia consistente de la base SQLite (API de backup en caliente, válida con WAL) y retención de 14 días.
set -euo pipefail
cd "$(dirname "$0")/../.."
DEST=/var/backups/radar-minimis
mkdir -p "$DEST"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
.venv/bin/python - "$DEST/radar-$STAMP.db" <<'PY'
import sqlite3, sys
src = sqlite3.connect("data/radar.db")
dst = sqlite3.connect(sys.argv[1])
with dst:
    src.backup(dst)
dst.close(); src.close()
PY
gzip -9 "$DEST/radar-$STAMP.db"
find "$DEST" -name 'radar-*.db.gz' -mtime +14 -delete
echo "Copia creada: $DEST/radar-$STAMP.db.gz"

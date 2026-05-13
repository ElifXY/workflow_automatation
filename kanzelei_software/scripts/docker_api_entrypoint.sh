#!/bin/sh
# Root-Entrypoint: Named Volumes unter /var/lib/kanzlei und /app/data sind oft root:root;
# die App laeuft als User kanzlei (UID 1000) -> SQLite sonst "unable to open database file".
set -e
DATA_ROOT="${DATA_DIR:-/var/lib/kanzlei}"
LOG_ROOT="${API_LOG_DIR:-/app/logfiles}"

mkdir -p "$DATA_ROOT" /app/data /app/data/uploads "$LOG_ROOT" 2>/dev/null || true
chown -R kanzlei:kanzlei "$DATA_ROOT" /app/data "$LOG_ROOT" 2>/dev/null || true

exec gosu kanzlei "$@"
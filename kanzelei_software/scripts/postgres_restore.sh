#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: scripts/postgres_restore.sh <backup.sql.gz>"
  exit 2
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required"
  exit 2
fi

backup_file="$1"
if [[ ! -f "$backup_file" ]]; then
  echo "Backup file not found: $backup_file"
  exit 2
fi

gunzip -c "$backup_file" | psql "$DATABASE_URL"
echo "Restore completed from: $backup_file"

#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required"
  exit 2
fi

mkdir -p data/backups
stamp="$(date +%Y%m%d_%H%M%S)"
out="data/backups/postgres_${stamp}.sql.gz"

pg_dump "$DATABASE_URL" | gzip > "$out"
echo "Backup written: $out"

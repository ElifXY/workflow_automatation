#!/bin/sh
# Kein gzip-Pipe: postgres:16-alpine enthält oft kein gzip → Container-Exit-Schleife.
# -Fc -Z9 = Custom-Format mit Kompression (nur pg_dump).
set -e

INTERVAL="${BACKUP_INTERVAL_SEC:-86400}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"

echo "[backup] Starte Schleife (Intervall ${INTERVAL}s, Aufbewahrung ${KEEP_DAYS} Tage)"
while true; do
  TS=$(date +%Y%m%d_%H%M%S)
  OUT="/backups/kanzlei_${TS}.dump"
  echo "[backup] pg_dump -> ${OUT}"
  if pg_dump -h postgres -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -Fc -Z9 -f "${OUT}.tmp"; then
    mv "${OUT}.tmp" "${OUT}"
    find /backups -name 'kanzlei_*.dump' -type f -mtime "+${KEEP_DAYS}" -exec rm -f {} \; 2>/dev/null || true
  else
    rm -f "${OUT}.tmp"
    echo "[backup] pg_dump fehlgeschlagen" >&2
  fi
  sleep "${INTERVAL}"
done

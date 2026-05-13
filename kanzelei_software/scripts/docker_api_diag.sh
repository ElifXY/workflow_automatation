#!/bin/sh
# API-Stack kurz prüfen (ohne verschachtelte Quotes mit $VAR — geeignet für Hetzner-Webkonsole).
# Aufruf vom Projektroot:  sh scripts/docker_api_diag.sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== Projektverzeichnis ==="
pwd

echo "=== docker compose ps (api) ==="
docker compose ps api 2>/dev/null || true

echo "=== printenv (nur Namen, keine Secrets) ==="
docker compose exec -T api printenv USE_POSTGRES_DATA 2>/dev/null || echo "(exec api fehlgeschlagen — läuft der Container?)"
docker compose exec -T api printenv ENVIRONMENT 2>/dev/null || true
docker compose exec -T api printenv APP_ENV 2>/dev/null || true

echo "=== GET /ready (sollte JSON) ==="
docker compose exec -T api curl -fsS http://127.0.0.1:8000/ready && echo "" || echo "FAIL /ready"

echo "=== GET /health (kann 503 bei DB) ==="
docker compose exec -T api curl -sS -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:8000/health || true

echo "=== letzte api-Logs ==="
docker compose logs api --tail 50

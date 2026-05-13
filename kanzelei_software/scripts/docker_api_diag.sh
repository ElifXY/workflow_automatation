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

echo "=== DATABASE_URL (nur Host/User/DB, kein Passwort) ==="
docker compose exec -T api python -c "
import os
from urllib.parse import urlparse
raw = (os.environ.get('DATABASE_URL') or '').strip()
if not raw:
    print('(DATABASE_URL leer)')
else:
    u = urlparse(raw)
    print('scheme', u.scheme, 'host', u.hostname, 'port', u.port, 'user', u.username, 'path', u.path)
" 2>/dev/null || true

echo "=== Postgres TCP-Login (wie die App; Fehler = meist Passwort/Volumen-Mismatch) ==="
docker compose exec -T api python -c "
import os
import sys
url = (os.environ.get('DATABASE_URL') or '').strip()
if not url.startswith('postgresql'):
    print('(kein postgresql DATABASE_URL — übersprungen)')
    sys.exit(0)
try:
    import psycopg2
    c = psycopg2.connect(url, connect_timeout=5)
    c.close()
    print('OK: psycopg2.connect')
except Exception as e:
    print('FEHLER:', e)
    sys.exit(0)
" 2>/dev/null || true

echo "Hinweis: FATAL password authentication for user kanzlei → POSTGRES_PASSWORD in der .env neben docker-compose.yml"
echo "         muss zum Passwort passen, mit dem das Volume postgres_data angelegt wurde (erster Start), sonst .env"
echo "         anpassen oder Postgres-User mit ALTER ROLE ändern / Volume neu (Datenverlust)."

echo "=== GET /ready (sollte JSON) ==="
docker compose exec -T api curl -fsS http://127.0.0.1:8000/ready && echo "" || echo "FAIL /ready"

echo "=== GET /health (kann 503 bei DB) ==="
docker compose exec -T api curl -sS -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:8000/health || true

echo "=== letzte api-Logs ==="
docker compose logs api --tail 50

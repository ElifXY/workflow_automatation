#!/usr/bin/env bash
# Prüft ob Production wirklich die neue UI + API ausliefert.
set -euo pipefail
cd "$(dirname "$0")/.."

DOMAIN="${DOMAIN:-kanzlei-automation.com}"
BASE="${VERIFY_BASE:-https://${DOMAIN}}"
EXPECTED_UI="${EXPECTED_UI_BUILD:-deploy-20260520o}"
EXPECTED_API="${EXPECTED_API_BUILD:-api-deploy-20260520o}"

echo "==> Git lokal: $(git rev-parse --short HEAD 2>/dev/null || echo '?')"
echo "==> Prüfe ${BASE}"
echo ""

fail=0

check_json() {
  local url="$1" key="$2" expect="$3" label="$4"
  local body
  body="$(curl -fsS "$url" 2>/dev/null || true)"
  if [ -z "$body" ]; then
    echo "FAIL $label — keine Antwort von $url"
    fail=1
    return
  fi
  if echo "$body" | grep -q "$expect"; then
    echo "OK   $label → enthält $expect"
  else
    echo "FAIL $label — erwartet $expect"
    echo "     Antwort: $body"
    fail=1
  fi
}

check_json "${BASE}/build-info.json" build "$EXPECTED_UI" "UI (nginx static)"
check_json "${BASE}/api/system/build" api_build "$EXPECTED_API" "API system/build"
check_json "${BASE}/portal/health" build "portal-deploy-20260520o" "Portal health"

echo ""
echo "==> Docker (lokal auf Server)"
if command -v docker >/dev/null 2>&1; then
  docker compose ps api nginx 2>/dev/null || true
  echo "--- NGINX_ENV (muss production sein, nicht development):"
  docker compose exec -T nginx printenv NGINX_ENV 2>/dev/null || echo "nginx nicht erreichbar"
  echo "--- build-info im nginx-Container:"
  docker compose exec -T nginx cat /usr/share/nginx/html/build-info.json 2>/dev/null || echo "fehlt — nginx neu bauen"
  echo "--- API ready:"
  docker compose exec -T api curl -fsS http://127.0.0.1:8000/ready 2>/dev/null || true
else
  echo "(docker nicht verfügbar — nur URL-Checks)"
fi

echo ""
if [ "$fail" = 0 ]; then
  echo "Deploy-Verifikation OK."
  exit 0
fi
echo "Deploy-Verifikation FEHLGESCHLAGEN — bitte: git pull && bash scripts/deploy_production.sh"
echo "Cloudflare: nach Deploy „Caching → Purge Everything“."
exit 1

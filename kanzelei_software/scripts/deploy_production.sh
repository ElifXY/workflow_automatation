#!/usr/bin/env bash
# Production deploy — UI (nginx) + API/Portal (api). Ohne --no-cache bleiben alte Image-Layer oft aktiv.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "==> Projekt: $(pwd)"
GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
echo "==> Git: ${GIT_SHA} $(git branch --show-current 2>/dev/null || true)"
export GIT_REV="${GIT_SHA}"
export APP_BUILD_ID="${APP_BUILD_ID:-deploy-20260520o}"

# NGINX_ENV=development leitet / an den Frontend-Dev-Container — UI-Änderungen aus Dockerfile.nginx erscheinen dann NICHT.
if [ -f .env ]; then
  if grep -qE '^NGINX_ENV=development' .env 2>/dev/null; then
    echo "FEHLER: .env hat NGINX_ENV=development — für Production auf production setzen!"
    exit 1
  fi
fi

UNCOMMITTED=0
for f in portal.html portal_api.py api.py frontend/src/api.js frontend/src/components/PortalChat.js \
  core/email_sender.py frontend/src/components/KiEmailComposer.js frontend/src/pages/Settings.js \
  Dockerfile.nginx nginx/conf.d/default.prod.conf.template; do
  if ! git diff --quiet HEAD -- "$f" 2>/dev/null; then
    echo "WARNUNG: $f nicht committed — git pull holt das nicht."
    UNCOMMITTED=1
  fi
done
if [ "$UNCOMMITTED" = 1 ]; then
  echo "         Erst: git add … && git commit && git push"
fi

echo "==> Build api + nginx (no cache, BUILD_ID=${APP_BUILD_ID})…"
docker compose build --no-cache api nginx
echo "==> Start (force recreate)…"
docker compose up -d --force-recreate api nginx
echo "==> Warten auf API ready…"
for i in $(seq 1 40); do
  if docker compose exec -T api curl -fsS http://127.0.0.1:8000/ready >/dev/null 2>&1; then
    break
  fi
  sleep 3
done
echo "==> API ready:"
docker compose exec -T api curl -fsS http://127.0.0.1:8000/ready || true
echo ""
echo "==> API system/build:"
docker compose exec -T api curl -fsS http://127.0.0.1:8000/api/system/build || true
echo ""
echo "==> Portal-Build (portal-deploy-20260520o):"
docker compose exec -T api curl -fsS http://127.0.0.1:8000/portal/health || true
echo ""
echo "==> UI build-info im nginx-Container:"
docker compose exec -T nginx cat /usr/share/nginx/html/build-info.json || echo "FEHLT — nginx-Build fehlgeschlagen?"
echo ""
echo "==> NGINX_ENV:"
docker compose exec -T nginx printenv NGINX_ENV || true
echo "==> Nginx reload"
docker compose exec -T nginx nginx -s reload 2>/dev/null || true
echo ""
echo "Fertig. Browser: Strg+Shift+R (oder Inkognito)."
echo "  Prüfen: https://<domain>/build-info.json → build ${APP_BUILD_ID}"
echo "  Prüfen: https://<domain>/api/system/build → api-deploy-20260520o"
echo "  Cloudflare aktiv? → Dashboard: Caching → Purge Everything"
echo "  Optional: bash scripts/verify_deploy.sh"

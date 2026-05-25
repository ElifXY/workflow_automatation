#!/usr/bin/env bash
# Production deploy — UI (nginx) + API/Portal (api). Ohne --no-cache bleiben alte Image-Layer oft aktiv.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "==> Projekt: $(pwd)"
echo "==> Git: $(git rev-parse --short HEAD 2>/dev/null || echo '?') $(git branch --show-current 2>/dev/null || true)"

if ! git diff --quiet HEAD -- portal.html portal_api.py api.py frontend/src/api.js frontend/src/components/PortalChat.js 2>/dev/null; then
  echo "WARNUNG: Portal-/Chat-Änderungen sind nicht committed — git pull auf dem Server holt sie nicht."
  echo "         Erst: git add … && git commit && git push"
fi

echo "==> Build api + nginx (no cache)…"
docker compose build --no-cache api nginx
echo "==> Start…"
docker compose up -d api nginx
echo "==> Warten auf API ready…"
for i in $(seq 1 40); do
  if docker compose exec -T api curl -fsS http://127.0.0.1:8000/ready >/dev/null 2>&1; then
    break
  fi
  sleep 3
done
echo "==> Portal-Build prüfen (muss build=portal-sig-20260519 sein):"
docker compose exec -T api curl -fsS http://127.0.0.1:8000/portal/health || true
echo ""
echo "==> Nginx reload"
docker compose exec -T nginx nginx -s reload 2>/dev/null || true
echo "Fertig. Im Browser: Strg+Shift+R. Prüfen: /portal/health und Portal-Quelltext enthält portal-sig-20260519"

#!/usr/bin/env bash
# Production deploy — UI (nginx) + API/Portal (api). Ohne --no-cache bleiben alte Image-Layer oft aktiv.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "==> Projekt: $(pwd)"
echo "==> Git: $(git rev-parse --short HEAD 2>/dev/null || echo '?') $(git branch --show-current 2>/dev/null || true)"

UNCOMMITTED=0
for f in portal.html portal_api.py api.py frontend/src/api.js frontend/src/components/PortalChat.js \
  core/email_sender.py frontend/src/components/KiEmailComposer.js frontend/src/pages/Settings.js; do
  if ! git diff --quiet HEAD -- "$f" 2>/dev/null; then
    echo "WARNUNG: $f nicht committed — git pull holt das nicht."
    UNCOMMITTED=1
  fi
done
if [ "$UNCOMMITTED" = 1 ]; then
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
echo "==> Portal-Build (build=portal-sig-20260519):"
docker compose exec -T api curl -fsS http://127.0.0.1:8000/portal/health || true
echo ""
echo "==> E-Mail-Absender-API (build=email-absender-20260519, JWT nötig — nur Statuscode):"
docker compose exec -T api curl -fsS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/email/absender 2>/dev/null || echo "401 ohne Token = Route existiert"
echo ""
echo "==> Nginx reload"
docker compose exec -T nginx nginx -s reload 2>/dev/null || true
echo "Fertig. Browser: Strg+Shift+R."
echo "  Portal: /portal/health → build portal-sig-20260519"
echo "  E-Mail: Einstellungen → Kanzlei-Daten + KI-Mail → Absender-Zeile"
echo "  API eingeloggt: GET /api/email/absender → build email-absender-20260519"

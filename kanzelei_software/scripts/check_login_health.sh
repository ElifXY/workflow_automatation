#!/usr/bin/env bash
set -euo pipefail
BASE="${1:-https://kanzlei-automation.com}"
echo "=== /api/ready ==="
curl -fsS "${BASE}/api/ready" && echo || { echo "FAIL"; exit 1; }
echo "=== /api/auth/setup-status ==="
curl -fsS "${BASE}/api/auth/setup-status" && echo || echo "FAIL setup-status"
echo "=== Login-Probe (falsches PW, erwartet 401) ==="
code=$(curl -sS -o /tmp/login_probe.json -w "%{http_code}" -X POST "${BASE}/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"probe@example.com","password":"wrongpassword12"}' || true)
echo "HTTP ${code}"
head -c 400 /tmp/login_probe.json 2>/dev/null; echo

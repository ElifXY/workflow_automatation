#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo "=== Statische Prüfungen ==="
python scripts/full_stack_check.py
if command -v docker >/dev/null 2>&1; then
  echo ""
  echo "=== Docker Stack ==="
  python scripts/full_stack_check.py --docker
else
  echo ""
  echo "Docker nicht im PATH — nur statische Prüfungen. CI: .github/workflows/docker-stack-verify.yml"
fi

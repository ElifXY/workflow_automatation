"""
Go-Live Check für Kanzlei Automation.

Prüft:
- Umgebungsvariablen (kritische Secrets)
- Erreichbarkeit von /health, /ready, /saas/readiness, /compliance/status
- Basisindikatoren für produktiven Betrieb

Usage:
  python scripts/go_live_check.py
  python scripts/go_live_check.py --base-url http://127.0.0.1:8000 --token <JWT>

Ergänzend (Mandanten, Einladungen, ORM ``users`` ohne HTTP):
  python scripts/production_go_live_gate.py
  python scripts/production_go_live_gate.py --strict
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Dict, List, Tuple

import httpx


GREEN = "GREEN"
YELLOW = "YELLOW"
RED = "RED"


def _check_env() -> List[Tuple[str, str, str]]:
    checks: List[Tuple[str, str, str]] = []
    required = [
        "JWT_SECRET",
        "SAAS_MASTER_KEY",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "DATABASE_URL",
        "OPENAI_API_KEY",
    ]
    for key in required:
        val = os.getenv(key, "").strip()
        if not val:
            checks.append((RED, f"ENV {key}", "fehlt"))
        elif len(val) < 12:
            checks.append((YELLOW, f"ENV {key}", "gesetzt, aber sehr kurz"))
        else:
            checks.append((GREEN, f"ENV {key}", "ok"))

    env = (os.getenv("ENVIRONMENT") or os.getenv("APP_ENV") or "development").lower()
    if env == "production":
        gw = os.getenv("API_GATEWAY_KEY", "").strip()
        if len(gw) < 32:
            checks.append((RED, "ENV API_GATEWAY_KEY", "fehlt oder <32 Zeichen (Production)"))
        else:
            checks.append((GREEN, "ENV API_GATEWAY_KEY", "ok (Länge)"))

        jwt = os.getenv("JWT_SECRET", "").strip()
        bad_j = any(x in jwt.lower() for x in ("placeholder", "dev-jwt", "minimum-64", "change-in-prod"))
        if len(jwt) < 48 or bad_j:
            checks.append((RED, "ENV JWT_SECRET", "zu schwach oder Dev-Muster (Production)"))
        else:
            checks.append((GREEN, "ENV JWT_SECRET", "ok (Stärke)"))

        du = os.getenv("DATABASE_URL", "").strip()
        if "KzDevOnly_" in du or "DevOnlyChangeBeforeProd2026X" in du:
            checks.append((RED, "ENV DATABASE_URL", "enthält Dev-Standardpasswort"))
        else:
            checks.append((GREEN, "ENV DATABASE_URL", "kein Dev-Passwort-Muster"))

        ru = os.getenv("REDIS_URL", "").strip()
        if ru and ("KzDevOnly_" in ru or "DevOnlyChangeBeforeProd2026X" in ru):
            checks.append((RED, "ENV REDIS_URL", "enthält Dev-Standardpasswort"))
        elif ru:
            checks.append((GREEN, "ENV REDIS_URL", "ok"))
    return checks


def _call(client: httpx.Client, method: str, path: str, headers: Dict[str, str]) -> Tuple[str, str]:
    try:
        r = client.request(method, path, headers=headers)
        if r.status_code >= 500:
            return RED, f"HTTP {r.status_code}"
        if r.status_code >= 400:
            return YELLOW, f"HTTP {r.status_code}"
        return GREEN, f"HTTP {r.status_code}"
    except Exception as exc:  # noqa: BLE001
        return RED, str(exc)


def _score(results: List[Tuple[str, str, str]]) -> int:
    score = 100
    for color, _, _ in results:
        if color == RED:
            score -= 20
        elif color == YELLOW:
            score -= 8
    return max(0, min(100, score))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("GO_LIVE_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--token", default=os.getenv("GO_LIVE_TOKEN", ""))
    args = parser.parse_args()

    auth_headers = {"Authorization": f"Bearer {args.token}"} if args.token else {}
    checks: List[Tuple[str, str, str]] = []
    checks.extend(_check_env())

    with httpx.Client(base_url=args.base_url, timeout=8.0) as client:
        for path in ["/health", "/ready", "/saas/readiness", "/compliance/status", "/ki/status"]:
            color, info = _call(client, "GET", path, auth_headers)
            checks.append((color, f"GET {path}", info))

    final = _score(checks)
    status = GREEN if final >= 85 else YELLOW if final >= 65 else RED

    print("\n=== KANZLEI AI GO-LIVE CHECK ===")
    print(f"Base URL: {args.base_url}")
    print("")
    for color, name, info in checks:
        print(f"[{color:<6}] {name:<28} {info}")
    print("")
    print(f"Final Score: {final} ({status})")

    if status == RED:
        print("Ergebnis: Nicht go-live bereit.")
        return 2
    if status == YELLOW:
        print("Ergebnis: Eingeschränkt bereit (bitte offene Punkte schließen).")
        return 1
    print("Ergebnis: Go-live bereit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

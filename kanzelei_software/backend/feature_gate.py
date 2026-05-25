"""
Runtime feature gate for advanced domains.

Policy:
- Core auth/tenant/user flows stay available.
- Advanced domains are blocked until explicitly enabled and baseline-proven.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Tuple


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts" / "security_baseline_pass.json"
REQUIRED_CHECKS = {
    "scripts/go_live_rbac_gate.py",
    "scripts/test_api_users_management.py",
    "scripts/test_api_users_invites.py",
    "scripts/tenant_enforcement_audit.py",
}
# Kern (Mandanten, Aufgaben) bleiben immer nutzbar — sonst ist die Suite in Produktion leer.
# Advanced = optionale Module (KI, Automation, Belege, …) bis Baseline + ENABLE_ADVANCED_FEATURES.
ADVANCED_PREFIXES = (
    "/dokumente",
    "/ki",
    "/ai",
    "/workflow",
    "/belege",
    "/rechnungen",
    "/team",
    "/zeit",
    "/bot",
    "/ml",
    "/finanzierung",
    "/lohn",
)


def _enabled(v: str) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_advanced_path(path: str) -> bool:
    p = str(path or "").strip()
    return any(p == pref or p.startswith(pref + "/") for pref in ADVANCED_PREFIXES)


def evaluate_feature_gate() -> Tuple[bool, str]:
    """Return ``(allowed, reason)`` for advanced feature runtime access."""
    if _enabled(os.getenv("SECURITY_BASELINE_BOOTSTRAP")):
        return True, "bootstrap"
    if not _enabled(os.getenv("ENABLE_ADVANCED_FEATURES")):
        return False, "ENABLE_ADVANCED_FEATURES is not enabled"
    if not ARTIFACT.exists():
        return False, "security baseline artifact missing"

    try:
        payload = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    except Exception:
        return False, "security baseline artifact invalid"

    checks = set(payload.get("checks") or [])
    missing = sorted(REQUIRED_CHECKS - checks)
    if missing:
        return False, f"security baseline artifact missing checks: {', '.join(missing)}"

    ts = str(payload.get("passed_at_utc") or "").strip()
    if not ts:
        return False, "security baseline artifact missing passed_at_utc"
    try:
        passed_at = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return False, "security baseline timestamp invalid"

    max_age_h = int(os.getenv("SECURITY_BASELINE_MAX_AGE_HOURS", "24") or "24")
    if datetime.now(timezone.utc) - passed_at > timedelta(hours=max(1, max_age_h)):
        return False, "security baseline artifact expired"

    return True, "ok"


def should_block_advanced_path(path: str) -> Tuple[bool, str]:
    if not _is_advanced_path(path):
        return False, "not advanced path"
    allowed, reason = evaluate_feature_gate()
    if allowed:
        return False, reason
    return True, reason


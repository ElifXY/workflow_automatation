"""
Feature-Flags pro Mandant (Kanzlei) — persistiert in ``DatenSpeicher`` / Einstellungen.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

FEATURE_SETTINGS_KEY = "saas_feature_flags"

# Bekannte Keys — nur diese dürfen per API gesetzt werden (keine beliebigen Keys).
DEFAULT_TENANT_FEATURES: Dict[str, Any] = {
    "advanced_reports": False,
    "invite_links": True,
    # Outbound-Webhook anlegen/löschen/testen — bewusst opt-in (Integration).
    "api_webhooks_write": False,
    # Massen-CSV + Komplett-ZIP; Standard an für bestehende Mandanten-Exports.
    "bulk_export": True,
    # KI-Kernfeatures (Phase 1)
    "ai_assistant": True,
    "ai_document_scan": True,
    "ai_receipt_scan": True,
}


def merged_features(stored: Any) -> Dict[str, Any]:
    out = deepcopy(DEFAULT_TENANT_FEATURES)
    if isinstance(stored, dict):
        for k, v in stored.items():
            if k in DEFAULT_TENANT_FEATURES:
                out[k] = bool(v) if isinstance(v, (bool, int)) else bool(v)
    return out


def merge_patch(current: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    base = merged_features(current)
    for k, v in (patch or {}).items():
        if k not in DEFAULT_TENANT_FEATURES:
            continue
        if isinstance(v, bool):
            base[k] = v
        elif isinstance(v, (int, float)):
            base[k] = bool(int(v))
        elif isinstance(v, str):
            base[k] = v.strip().lower() in ("1", "true", "yes", "on")
        else:
            base[k] = bool(v)
    return base

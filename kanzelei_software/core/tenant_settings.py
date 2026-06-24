"""Tenant-scoped settings reads (blob-backed)."""
from __future__ import annotations

from typing import Any, Optional

from core.daten_speicher import DatenSpeicher


def tenant_setting(store: DatenSpeicher, key: str, default: Any = None) -> Any:
    from modules.settings_manager import setting_holen

    val = setting_holen(key, store=store)
    return default if val is None else val


def tenant_bool(store: DatenSpeicher, key: str, default: bool = True) -> bool:
    val = tenant_setting(store, key, default)
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in ("1", "true", "yes", "on")


def tenant_int(store: DatenSpeicher, key: str, default: int) -> int:
    try:
        return int(tenant_setting(store, key, default))
    except (TypeError, ValueError):
        return default


def tenant_float(store: DatenSpeicher, key: str, default: float) -> float:
    try:
        return float(tenant_setting(store, key, default))
    except (TypeError, ValueError):
        return default

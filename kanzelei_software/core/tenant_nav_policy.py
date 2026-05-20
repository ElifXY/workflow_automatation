"""
Tenant-spezifische Navigation vs. API-Berechtigungen.

Die UI blendet Menüpunkte per ``rollen_nav_steuerberater`` / ``rollen_nav_mitarbeiter`` ein;
dieses Modul spiegelt dieselbe Logik serverseitig, damit APIs nicht weiter bedient werden,
wenn ein Bereich für die Rolle ausgeblendet ist.
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, Optional, Set

from core.daten_speicher import DatenSpeicher
from modules.settings_manager import DEFAULT_SETTINGS, FESTGESCHRIEBEN, SETTINGS_KEY

# Permission → mindestens ein dieser Sidebar-Tabs muss für Steuerberater/Mitarbeiter aktiv sein
PERMISSION_NAV_TABS: Dict[str, FrozenSet[str]] = {
    "users:read": frozenset({"settings"}),
    "users:manage": frozenset({"settings"}),
    "mandanten:read": frozenset({"mandanten", "neu"}),
    "mandanten:write": frozenset({"mandanten", "neu"}),
    "mandanten:delete": frozenset({"mandanten"}),
    "aufgaben:read": frozenset({"aufgaben"}),
    "aufgaben:write": frozenset({"aufgaben"}),
    "kommunikation:read": frozenset({"mandanten"}),
    "kommunikation:write": frozenset({"mandanten"}),
    "belege:read": frozenset({"belege"}),
    "belege:write": frozenset({"belege"}),
    "belege:delete": frozenset({"belege"}),
    "dokumente:read": frozenset({"dokumente"}),
    "dokumente:write": frozenset({"dokumente"}),
    "dokumente:delete": frozenset({"dokumente"}),
    "rechnungen:read": frozenset({"rechnungen"}),
    "rechnungen:write": frozenset({"rechnungen"}),
    "lohn:read": frozenset({"profit"}),
    "lohn:approve": frozenset({"profit"}),
    "payments:release": frozenset({"rechnungen", "profit"}),
    "export:read": frozenset({"analytics", "automation"}),
    "export:datev": frozenset({"analytics", "automation"}),
    "settings:read": frozenset({"settings"}),
    "settings:write": frozenset({"settings"}),
    "billing:manage": frozenset({"settings"}),
    "audit:read": frozenset({"settings"}),
    "engine:run": frozenset({"ki", "steuerbot"}),
    "engine:read": frozenset({"ki", "steuerbot"}),
    "email:send": frozenset({"mandanten", "portalchat"}),
    "portal:read": frozenset({"portalchat", "mandanten"}),
    "portal:write": frozenset({"portalchat", "mandanten"}),
    "reports:read": frozenset({"dashboard", "analytics", "empfehlungen", "profit"}),
    "tenant:manage": frozenset({"settings"}),
}


def merged_settings_for_user(user: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Gleiche Merge-Logik wie Settings-Manager, aber mit tenant-spezifischem DatenSpeicher."""
    kid = str((user or {}).get("tenant_id") or (user or {}).get("kanzlei_id") or "default")
    store = DatenSpeicher() if kid == "default" else DatenSpeicher(kanzlei_id=kid)
    raw = store.setting_holen(SETTINGS_KEY, None)
    if not isinstance(raw, dict):
        raw = {}
    merged: Dict[str, Any] = {**DEFAULT_SETTINGS, **raw}
    merged.update(FESTGESCHRIEBEN)
    try:
        from modules.settings_manager import _normalize_nav_lists

        _normalize_nav_lists(merged)
    except Exception:
        pass
    return merged


def _allowed_tab_ids(canonical_role: str, merged: Dict[str, Any]) -> Optional[Set[str]]:
    """None = keine Nav-Einschränkung (Owner/Admin)."""
    if canonical_role not in {"steuerberater", "mitarbeiter"}:
        return None
    key = "rollen_nav_steuerberater" if canonical_role == "steuerberater" else "rollen_nav_mitarbeiter"
    raw = merged.get(key)
    if not isinstance(raw, list) or len(raw) == 0:
        raw = list(DEFAULT_SETTINGS.get(key) or [])
    tabs = {str(x).strip().lower() for x in raw if str(x).strip()}
    tabs.add("dashboard")
    tabs.add("portalchat")
    return tabs


def navigation_allows_permission(canonical_role: str, permission: str, merged: Dict[str, Any]) -> bool:
    """
    True, wenn die aktivierten Sidebar-Tabs die Permission abdecken.
    Owner/Admin: immer True (Aufrufer sollte vorher nicht filtern).
    """
    allowed = _allowed_tab_ids(canonical_role, merged)
    if allowed is None:
        return True
    required = PERMISSION_NAV_TABS.get(permission)
    if not required:
        return True
    return bool(allowed & required)

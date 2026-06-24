"""
Zentrales RBAC: Rollen, Aliase, Permission-Katalog.

Quelle der Wahrheit für den Server. Wird von ``api.py:require_permission`` und
``backend/deps.py:require_admin`` genutzt. UI-Schichten (z.B.
``frontend/src/components/PermissionGate.js``) spiegeln dies nur, treffen aber
KEINE Sicherheitsentscheidungen.

Designprinzipien:
- ``owner`` ist die unantastbare Top-Rolle pro Tenant (kann nicht herabgestuft
  werden, kann nicht entfernt werden).
- Rollen-Aliase (``assistent``, ``user``, ``worker``, ``MITARBEITER`` …) werden
  via :func:`canonical_role` auf die kanonische Form normalisiert. Bestehende
  DB-Werte bleiben gültig, weil ``ROLE_PERMISSIONS`` weiterhin alle Aliase
  führt.
- Permission-Strings folgen dem Schema ``<bereich>:<aktion>``.
"""

from __future__ import annotations

from typing import Dict, Optional, Set


CANONICAL_ROLES: tuple[str, ...] = (
    "owner",
    "admin",
    "teamleiter",
    "steuerberater",
    "mitarbeiter",
)


ROLE_ALIASES: Dict[str, str] = {
    "owner": "owner",
    "admin": "admin",
    "ADMIN": "admin",
    "teamleiter": "teamleiter",
    "TEAMLEITER": "teamleiter",
    "steuerberater": "steuerberater",
    "STEUERBERATER": "steuerberater",
    "selbststaendig": "steuerberater",
    "mitarbeiter": "mitarbeiter",
    "MITARBEITER": "mitarbeiter",
    "assistent": "mitarbeiter",
    "ASSISTENT": "mitarbeiter",
    "user": "mitarbeiter",
    "USER": "mitarbeiter",
    "worker": "mitarbeiter",
    "WORKER": "mitarbeiter",
}


def canonical_role(role: str) -> str:
    """Liefert den kanonischen Rollennamen oder ``"mitarbeiter"`` als Fallback."""
    if role is None:
        return "mitarbeiter"
    raw = str(role).strip()
    if not raw:
        return "mitarbeiter"
    direct = ROLE_ALIASES.get(raw)
    if direct:
        return direct
    return ROLE_ALIASES.get(raw.lower(), "mitarbeiter")


# Permission-Katalog: zentrale Bereiche und Aktionen.
PERMISSION_CATALOG: tuple[str, ...] = (
    "users:read", "users:manage",
    "mandanten:read", "mandanten:write", "mandanten:delete",
    "aufgaben:read", "aufgaben:write",
    "kommunikation:read", "kommunikation:write",
    "belege:read", "belege:write", "belege:delete",
    "dokumente:read", "dokumente:write", "dokumente:delete",
    "rechnungen:read", "rechnungen:write",
    "lohn:read", "lohn:approve",
    "payments:release",
    "export:read", "export:datev",
    "settings:read", "settings:write",
    "billing:manage",
    "audit:read",
    "engine:run", "engine:read",
    "email:send",
    "portal:read", "portal:write",
    "reports:read",
    "tenant:manage",
)


# Kern-Mapping. Aliase werden zusätzlich gefüllt, damit Bestandsdaten (z.B.
# ``rolle="assistent"`` in der DB) ohne Migration gültig bleiben.
_BASE_ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    "owner": {"*"},
    "admin": {"*"},
    "steuerberater": {
        "users:read",
        "mandanten:read", "mandanten:write",
        "aufgaben:read", "aufgaben:write",
        "kommunikation:read", "kommunikation:write",
        "portal:read", "portal:write",
        "belege:read", "belege:write",
        "dokumente:read", "dokumente:write",
        "rechnungen:read", "rechnungen:write",
        "lohn:read", "lohn:approve",
        "payments:release",
        "export:read", "export:datev",
        "settings:read", "settings:write",
        "engine:run", "engine:read",
        "email:send",
        "reports:read",
    },
    "teamleiter": {
        "users:read",
        "mandanten:read", "mandanten:write",
        "aufgaben:read", "aufgaben:write",
        "kommunikation:read", "kommunikation:write",
        "portal:read", "portal:write",
        "belege:read", "belege:write",
        "dokumente:read", "dokumente:write",
        "rechnungen:read",
        "export:read",
        "settings:read",
        "engine:run", "engine:read",
        "email:send",
        "reports:read",
    },
    "mitarbeiter": {
        "mandanten:read",
        "aufgaben:read", "aufgaben:write",
        "kommunikation:read", "kommunikation:write",
        "portal:read", "portal:write",
        "belege:read", "belege:write",
        "dokumente:read", "dokumente:write",
        "rechnungen:read",
        "settings:read",
        "reports:read",
        "email:send",
    },
}


ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    role: set(perms) for role, perms in _BASE_ROLE_PERMISSIONS.items()
}
# Aliase mit denselben Berechtigungen wie die kanonische Rolle befüllen.
for alias, target in ROLE_ALIASES.items():
    if alias in ROLE_PERMISSIONS:
        continue
    base = _BASE_ROLE_PERMISSIONS.get(target)
    if base is not None:
        ROLE_PERMISSIONS[alias] = set(base)


def has_permission(role: str, permission: str, tenant_settings: Optional[Dict] = None) -> bool:
    """
    True, wenn die Rolle (kanonisch normalisiert) die Permission besitzt.

    ``tenant_settings``: optional zusammengeführte Tenant-Settings (inkl. Defaults).
    Dann wird für ``steuerberater`` / ``mitarbeiter`` zusätzlich geprüft, ob die
    aktivierte Sidebar den API-Bereich abdeckt (``core.tenant_nav_policy``).
    """
    canonical = canonical_role(role)
    perms = ROLE_PERMISSIONS.get(canonical, set())
    base = False
    if "*" in perms or permission in perms:
        base = True
    else:
        raw_perms = ROLE_PERMISSIONS.get((role or "").strip().lower(), set())
        base = "*" in raw_perms or permission in raw_perms
    if not base:
        return False
    if tenant_settings is not None and not _feature_matrix_allows(canonical, permission, tenant_settings):
        return False
    if tenant_settings is None:
        return True
    from core.tenant_nav_policy import navigation_allows_permission

    return navigation_allows_permission(canonical, permission, tenant_settings)


# Settings-Feature-Matrix (Team-Tab) → API-Permissions
_FEATURE_SETTING_KEYS: Dict[str, str] = {
    "mandanten:delete": "rollen_mandant_loeschen",
    "export:datev": "rollen_export_datev",
    "lohn:read": "rollen_lohn_sichtbar",
    "lohn:approve": "rollen_lohn_sichtbar",
    "payments:release": "rollen_zahlungen_freigabe",
    "settings:write": "rollen_einstellungen",
}


def _feature_matrix_allows(canonical: str, permission: str, tenant_settings: Dict) -> bool:
    """Zusätzliche Prüfung gegen rollen_*-Listen in den Tenant-Settings."""
    if canonical in {"owner", "admin"}:
        return True
    setting_key = _FEATURE_SETTING_KEYS.get(permission)
    if not setting_key:
        return True
    raw = tenant_settings.get(setting_key)
    if not isinstance(raw, list):
        try:
            from modules.settings_manager import DEFAULT_SETTINGS
            raw = DEFAULT_SETTINGS.get(setting_key, [])
        except Exception:
            raw = []
    allowed = {canonical_role(str(r)) for r in raw if str(r).strip()}
    return canonical in allowed


def is_owner(role: str) -> bool:
    return canonical_role(role) == "owner"


def is_admin_or_higher(role: str) -> bool:
    return canonical_role(role) in {"owner", "admin"}

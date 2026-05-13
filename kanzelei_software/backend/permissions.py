"""
Zentrale Permission-Fassade für Backend-Routen.

Warum dieses Modul:
- Einheitlicher Importpfad: ``from backend.permissions import require_permission``
- Kapselt Role-Checks (``core.rbac``) + API-Key-Permissions
- Vermeidet RBAC-Logik in einzelnen Routern
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status

from backend.deps import get_current_user
from core.rbac import has_permission
from core.tenant_nav_policy import merged_settings_for_user


def require_permission(permission: str):
    """
    Dependency-Factory für route-spezifische Berechtigungen.

    API-Keys werden gegen ``api_permissions`` geprüft, User gegen
    rollenbasierte Rechte in ``core.rbac``.
    """

    def _dep(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user.get("api_key_id"):
            perms = current_user.get("api_permissions") or []
            if "*" in perms or permission in perms:
                return current_user
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"API-Key ohne Berechtigung: {permission}",
            )
        role = current_user.get("rolle") or current_user.get("role") or ""
        tenant_settings = merged_settings_for_user(current_user)
        if not has_permission(str(role), permission, tenant_settings):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Fehlende Berechtigung: {permission}",
            )
        return current_user

    return _dep


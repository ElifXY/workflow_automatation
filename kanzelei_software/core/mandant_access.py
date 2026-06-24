"""
Mandanten-Zugriff — Betreuer-Zuweisung serverseitig (Pass 10).

Mitarbeiter sehen nur Mandanten ohne Betreuer oder mit eigener betreuer_email.
Owner, Admin und Steuerberater sehen alle Mandanten.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from core.rbac import canonical_role


def betreuer_email(mandant: Optional[Dict[str, Any]]) -> str:
    if not isinstance(mandant, dict):
        return ""
    return str(mandant.get("betreuer_email") or "").strip().lower()


def user_email(user: Optional[Dict[str, Any]]) -> str:
    if not isinstance(user, dict):
        return ""
    return str(user.get("email") or "").strip().lower()


def user_sees_all_mandanten(user: Optional[Dict[str, Any]]) -> bool:
    role = canonical_role((user or {}).get("role") or (user or {}).get("rolle"))
    return role in ("owner", "admin", "steuerberater")


def user_may_access_mandant(user: Optional[Dict[str, Any]], mandant: Optional[Dict[str, Any]]) -> bool:
    if user_sees_all_mandanten(user):
        return True
    assigned = betreuer_email(mandant)
    if not assigned:
        return True
    return assigned == user_email(user)


def assert_mandant_access(user: Optional[Dict[str, Any]], mandant: Dict[str, Any], name: str = "") -> None:
    from fastapi import HTTPException

    if user_may_access_mandant(user, mandant):
        return
    label = name or str(mandant.get("name") or "Mandant")
    raise HTTPException(
        status_code=403,
        detail=f"Kein Zugriff auf Mandant '{label}' — nicht Ihr Betreuungsmandat",
    )

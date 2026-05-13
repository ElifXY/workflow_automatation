"""
Zentrale Tenant-Sicherheitshelfer.

Ziel: einheitliche Mandanten-Isolation in allen Layern (SQLAlchemy + Service/Dict).
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

from fastapi import HTTPException, status


def tenant_id_from_user(user: Mapping[str, Any] | None) -> str:
    """Kanonische tenant_id aus User-Kontext (JWT/Session/API-Key)."""
    u = user or {}
    kid = str(u.get("tenant_id") or u.get("kanzlei_id") or "default").strip()
    return kid or "default"


def require_same_tenant(
    candidate_tenant: Optional[str],
    user: Mapping[str, Any],
    *,
    not_found_if_missing: bool = False,
) -> str:
    """Prüft Ressourcentenant gegen Usertenant und wirft 403/404 bei Abweichung."""
    current = tenant_id_from_user(user)
    if candidate_tenant is None:
        if not_found_if_missing:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Ressource nicht gefunden")
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant-Kontext fehlt")
    if str(candidate_tenant) != current:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-tenant Zugriff blockiert")
    return current


def tenant_query(model, user: Mapping[str, Any], db):
    """
    SQLAlchemy-Helfer: garantiert tenant_id-Filter auf Query-Ebene.
    Erwartet ``model.tenant_id``.
    """
    if not hasattr(model, "tenant_id"):
        raise AttributeError(f"{model} has no tenant_id attribute")
    return db.query(model).filter(model.tenant_id == tenant_id_from_user(user))


def tenant_get(model, obj_id: Any, user: Mapping[str, Any], db):
    """
    SQLAlchemy-Helfer: lädt ein Objekt nur im Tenant-Kontext.
    Erwartet ``model.id`` und ``model.tenant_id``.
    """
    if not hasattr(model, "tenant_id") or not hasattr(model, "id"):
        raise AttributeError(f"{model} must have id and tenant_id attributes")
    return (
        db.query(model)
        .filter(model.id == obj_id, model.tenant_id == tenant_id_from_user(user))
        .first()
    )

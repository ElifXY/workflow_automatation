"""
Mandanten-Isolation (tenant_id / kanzlei_id) — zentrale Helfer für Handler.

Nicht jede Datenquelle nutzt SQLAlchemy; diese Funktionen sind bewusst schlank
und HTTP-freundlich (FastAPI), damit Routen konsistent prüfen können.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

from fastapi import HTTPException, status


def tenant_id_from_user(user: Mapping[str, Any] | None) -> str:
    """Kanonisches Mandanten-Handle aus Session/JWT/API-Key-Userdict."""
    u = user or {}
    return str(u.get("tenant_id") or u.get("kanzlei_id") or "default")


def raise_if_tenant_mismatch(
    actor: Mapping[str, Any],
    claimed_tenant: Optional[str],
    *,
    field: str = "kanzlei_id",
) -> None:
    """
    Wirft 403, wenn ``claimed_tenant`` gesetzt ist und vom Actor-Mandanten abweicht.

    Nutzung: Body/Query enthält explizites Mandantenfeld (z. B. Import-APIs).
    """
    if claimed_tenant is None or str(claimed_tenant).strip() == "":
        return
    mine = tenant_id_from_user(actor)
    if str(claimed_tenant) != str(mine):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=f"Cross-tenant {field} blockiert",
        )


def assert_resource_belongs_tenant(
    resource_tenant: Optional[str],
    actor: Mapping[str, Any],
    *,
    message: str = "Ressource gehört nicht zu Ihrer Kanzlei",
) -> str:
    """Vergleicht Mandanten einer geladenen Zeile mit dem Actor; liefert kanonisches tenant_id."""
    mine = tenant_id_from_user(actor)
    if resource_tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Ressource nicht gefunden")
    if str(resource_tenant) != str(mine):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=message)
    return mine

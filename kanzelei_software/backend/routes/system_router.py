"""
System/status router extracted from ``api.py``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.deps import get_current_user

router = APIRouter(tags=["System"])


def _root():
    import api as root

    return root


@router.get("/health", summary="Healthcheck")
@router.get("/api/health", summary="Healthcheck (API alias)")
def health():
    root = _root()
    return root.health()


@router.get("/ready", summary="Readiness")
@router.get("/api/ready", summary="Readiness (API alias)")
def ready():
    root = _root()
    return root.ready()


@router.get("/api/v1/meta", summary="API v1 Meta")
def api_v1_meta():
    root = _root()
    return root.api_v1_meta()


@router.get("/api/v1/health", summary="API v1 Health")
def api_v1_health():
    root = _root()
    return root.api_v1_health()


@router.get("/compliance/status", summary="Compliance-Dateien prüfen")
def compliance_status(_user: dict = Depends(get_current_user)):
    root = _root()
    root.require_permission("reports:read")(_user)
    return root.compliance_status(_user)


@router.get("/saas/readiness", tags=["SaaS"], summary="SaaS Readiness Snapshot")
def saas_readiness(_user: dict = Depends(get_current_user)):
    root = _root()
    root.require_permission("reports:read")(_user)
    return root.saas_readiness(_user)


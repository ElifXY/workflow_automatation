"""
Auth-Router (aus monolithischem ``api.py`` herausgelöst).

Die Business-Logik bleibt zunächst in ``api.py`` und wird über Wrapper aufgerufen.
So können wir die Registrierung entkoppeln, ohne Verhalten zu ändern.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, Header, Request

from backend.deps import get_current_user

router = APIRouter(tags=["Auth"])


def _root():
    import api as root

    return root


@router.post("/auth/login", summary="Login — Session-Token erhalten")
async def auth_login(request: Request, data: Dict[str, Any] = Body(...)):
    root = _root()
    payload = root.LoginRequest(**data)
    return await root.auth_login(payload, request)


@router.post("/login", summary="Login per E-Mail — JWT + Session (Nginx: /api/login → /login)")
@router.post("/api/login", summary="Login per E-Mail — JWT + Session (direkt auf Uvicorn)")
async def api_login_email_jwt(request: Request, data: Dict[str, Any] = Body(...)):
    root = _root()
    payload = root.EmailPasswordLoginRequest(**data)
    return await root.api_login_email_jwt(payload, request)


@router.get("/me", summary="Kurzprofil (JWT/Session)")
@router.get("/api/me", summary="Kurzprofil — Alias für Nginx /api/")
def api_me_minimal(current_user: dict = Depends(get_current_user)):
    root = _root()
    return root.api_me_minimal(current_user)


@router.post(
    "/register",
    summary="Registrierung per E-Mail (Nginx: /api/register → /register)",
    status_code=201,
)
@router.post(
    "/api/register",
    summary="Registrierung per E-Mail (direkt auf Uvicorn)",
    status_code=201,
)
def api_register_email(request: Request, data: Dict[str, Any] = Body(...)):
    root = _root()
    payload = root.EmailPasswordRegisterRequest(**data)
    return root.api_register_email(payload, request)


@router.post("/auth/logout", summary="Logout — Session beenden")
def auth_logout(
    authorization: Optional[str] = Header(None),
    current_user: dict = Depends(get_current_user),
):
    root = _root()
    return root.auth_logout(authorization, current_user)


@router.post("/auth/refresh", summary="Neues Access-Token aus Refresh-Token")
def auth_refresh(data: Dict[str, Any] = Body(...)):
    root = _root()
    payload = root.RefreshTokenRequest(**data)
    return root.auth_refresh(payload)


@router.post("/auth/registrieren", summary="Neuen Benutzer anlegen", status_code=201)
def auth_registrieren(data: Dict[str, Any] = Body(...)):
    root = _root()
    payload = root.RegistrierRequest(**data)
    return root.auth_registrieren(payload)


@router.get("/auth/me", summary="Eigene Benutzer-Info")
def auth_me(current_user: dict = Depends(get_current_user)):
    root = _root()
    return root.auth_me(current_user)


@router.get("/auth/benutzer", summary="Alle Benutzer (nur Admin)")
def auth_benutzer_liste(current_user: dict = Depends(get_current_user)):
    root = _root()
    root.require_permission("settings:write")(current_user)
    return root.auth_benutzer_liste(current_user)


@router.put("/auth/passwort", summary="Passwort ändern")
def auth_passwort(data: Dict[str, Any] = Body(...), current_user: dict = Depends(get_current_user)):
    root = _root()
    payload = root.PasswortRequest(**data)
    return root.auth_passwort(payload, current_user)


@router.get("/auth/setup-status", summary="Prüft ob System eingerichtet")
def auth_setup_status():
    root = _root()
    return root.auth_setup_status()

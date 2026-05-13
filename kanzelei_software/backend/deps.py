"""
Kanonische FastAPI-Dependencies (Auth, API-Key, Rollenchecks).

Projektweit soll nur dieses Modul importiert werden:
``from backend.deps import get_current_user``.
"""
from __future__ import annotations

import ipaddress
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.auth import (
    algorithm as jwt_algorithm,
    hole_benutzer_kurz_nach_id,
    jwt_secret,
    verifiziere_session,
    verify_access_token,
)
from core.daten_speicher import DatenSpeicher, api_key_verify

security = HTTPBearer(auto_error=False)


def _jose():
    try:
        from jose import JWTError, jwt
    except ImportError as e:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "JWT verification unavailable: python-jose fehlt",
        ) from e
    return JWTError, jwt


def _ensure_tenant_context(user: dict) -> dict:
    kid = (user.get("tenant_id") or user.get("kanzlei_id") or "default") or "default"
    out = dict(user)
    out["kanzlei_id"] = kid
    out["tenant_id"] = kid
    r = (out.get("rolle") or out.get("role") or "assistent")
    if isinstance(r, str):
        r = r.strip().lower() or "assistent"
    else:
        r = str(r or "assistent").strip().lower() or "assistent"
    out["rolle"] = r
    out["role"] = r
    uid = out.get("user_id")
    if uid is None:
        uid = out.get("id")
    if uid is not None and str(uid).isdigit():
        out["id"] = int(uid)
    elif uid is not None:
        out["id"] = uid
    return out


def _user_from_jwt_claims(claims: dict) -> dict:
    sub = (claims.get("sub") or "").strip()
    if not sub or claims.get("typ") != "access":
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Ungültiges Zugriffstoken",
            headers={"WWW-Authenticate": "Bearer"},
        )
    kid = claims.get("tenant_id") or claims.get("kanzlei_id") or "default"
    if sub.isdigit():
        row = hole_benutzer_kurz_nach_id(int(sub), str(kid))
        if not row:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Ungültiges Zugriffstoken",
                headers={"WWW-Authenticate": "Bearer"},
            )
        aktiv = row.get("aktiv")
        if aktiv is not None and aktiv in (0, False, "0"):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Benutzer deaktiviert",
                headers={"WWW-Authenticate": "Bearer"},
            )
        bn = str(row.get("benutzername") or "").strip()
        if not bn:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Ungültiges Zugriffstoken",
                headers={"WWW-Authenticate": "Bearer"},
            )
        uid = row.get("id")
        rolle = row.get("rolle") or claims.get("rolle") or claims.get("role") or "assistent"
        return _ensure_tenant_context(
            {
                "benutzername": bn,
                "kanzlei_id": kid,
                "rolle": rolle,
                "email": (row.get("email") or claims.get("email") or ""),
                "user_id": int(uid) if uid is not None and str(uid).isdigit() else uid,
                "auth_via": "jwt",
            }
        )
    uid = claims.get("uid")
    if uid is None:
        uid = claims.get("user_id")
    return _ensure_tenant_context(
        {
            "benutzername": sub,
            "kanzlei_id": kid,
            "rolle": claims.get("rolle") or claims.get("role") or "assistent",
            "email": claims.get("email") or "",
            "user_id": int(uid) if uid is not None and str(uid).isdigit() else uid,
            "auth_via": "jwt",
        }
    )


def _request_ip(request: Optional[Request]) -> str:
    if request is None:
        return ""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def _enforce_security_settings(user: dict, request: Optional[Request]) -> None:
    from modules.settings_manager import setting_holen as manager_setting_holen

    kid = str(user.get("tenant_id") or user.get("kanzlei_id") or "default").strip() or "default"
    store = DatenSpeicher(kanzlei_id=kid)

    # IP allow-list (optional)
    if bool(manager_setting_holen("ip_whitelist_aktiv")):
        allowed = manager_setting_holen("ip_whitelist") or []
        req_ip_raw = _request_ip(request).strip()
        try:
            req_ip = ipaddress.ip_address(req_ip_raw) if req_ip_raw else None
        except ValueError:
            req_ip = None
        ip_ok = False
        if req_ip and isinstance(allowed, list):
            for item in allowed:
                token = str(item or "").strip()
                if not token:
                    continue
                try:
                    if "/" in token:
                        if req_ip in ipaddress.ip_network(token, strict=False):
                            ip_ok = True
                            break
                    else:
                        if req_ip == ipaddress.ip_address(token):
                            ip_ok = True
                            break
                except ValueError:
                    continue
        if not ip_ok:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Zugriff von dieser IP nicht erlaubt")

    # Session timeout by last activity per user
    username = str(user.get("benutzername") or "").strip()
    timeout_minutes = int(manager_setting_holen("session_timeout_minuten") or 60)
    if username and timeout_minutes > 0:
        now = datetime.utcnow()
        key = "__security_last_seen_v1"
        raw = store.setting_holen(key, {}) or {}
        last_seen_map = raw if isinstance(raw, dict) else {}
        last_iso = str(last_seen_map.get(username) or "").strip()
        if last_iso:
            try:
                last_dt = datetime.fromisoformat(last_iso.replace("Z", "+00:00")).replace(tzinfo=None)
                if now - last_dt > timedelta(minutes=timeout_minutes):
                    raise HTTPException(
                        status.HTTP_401_UNAUTHORIZED,
                        "Session abgelaufen (Inaktivität). Bitte neu anmelden.",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
            except HTTPException:
                raise
            except Exception:
                pass
        # Avoid writing on every request; refresh roughly every 30s.
        needs_update = True
        if last_iso:
            try:
                last_dt = datetime.fromisoformat(last_iso.replace("Z", "+00:00")).replace(tzinfo=None)
                needs_update = (now - last_dt).total_seconds() >= 30
            except Exception:
                needs_update = True
        if needs_update:
            last_seen_map[username] = now.isoformat()
            store.setting_setzen(key, last_seen_map)

    # 2FA enforcement (when enabled) except owner/admin to avoid tenant lockout.
    if bool(manager_setting_holen("2fa_pflicht")):
        role = str(user.get("rolle") or user.get("role") or "").strip().lower()
        if role not in {"owner", "admin"} and username:
            profiles = store.setting_holen("__user_profiles__", {}) or {}
            profile = profiles.get(username, {}) if isinstance(profiles, dict) else {}
            verified = bool(profile.get("twofa_verified") or profile.get("mfa_verified"))
            if not verified:
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    "2FA erforderlich. Bitte 2FA im Benutzerprofil aktivieren.",
                )


def get_bearer_jwt_sub(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    """
    Liefert ``sub`` aus dem Access-Token (nur JWT, keine Session).
    Erfordert ``JWT_SECRET`` und gültiges Bearer-Token.
    """
    secret = jwt_secret()
    if not secret:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "JWT ist nicht konfiguriert (JWT_SECRET)",
        )
    if not creds or not creds.credentials:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Authorization Bearer erforderlich",
            headers={"WWW-Authenticate": "Bearer"},
        )
    JWTError, jwt = _jose()
    try:
        payload = jwt.decode(creds.credentials, secret, algorithms=[jwt_algorithm()])
    except JWTError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Ungültiges Token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if (payload.get("typ") or "") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Ungültiges Token")
    sub = str(payload.get("sub") or "").strip()
    if not sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Ungültiges Token")
    return sub


def get_current_user(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    request: Request = None,
) -> dict:
    if x_api_key:
        api_key = api_key_verify(x_api_key.strip())
        if not api_key:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Ungültiger API-Key")
        kid = api_key["kanzlei_id"]
        return _ensure_tenant_context(
            {
                "benutzername": f"api_key:{api_key['name']}",
                "rolle": "admin",
                "kanzlei_id": kid,
                "tenant_id": kid,
                "api_key_id": api_key["id"],
                "api_permissions": api_key.get("permissions", []),
            }
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Login erforderlich",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.removeprefix("Bearer ").strip()
    session = verifiziere_session(token)
    if session:
        user = _ensure_tenant_context(session)
        _enforce_security_settings(user, request)
        return user
    if jwt_secret():
        claims = verify_access_token(token)
        if claims:
            user = _user_from_jwt_claims(claims)
            _enforce_security_settings(user, request)
            return user
    raise HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Session abgelaufen oder Token ungültig — bitte neu anmelden",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """
    Strikter Rollen-Check für Admin-Routen (nur echte Benutzer-Session/JWT).

    Akzeptiert die kanonischen Rollen ``owner`` und ``admin``. API-Keys mit
    Admin-Berechtigung sind hier bewusst ausgeschlossen — sie haben eigene
    Permission-Listen über ``require_permission``.
    """
    if user.get("api_key_id"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Admin only (API-Key auth cannot use admin user routes)",
        )
    from core.rbac import is_admin_or_higher

    role = user.get("role") or user.get("rolle") or ""
    if not is_admin_or_higher(role):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Admin only")
    return user


def require_owner(user: dict = Depends(get_current_user)) -> dict:
    """Nur ``owner`` darf passieren — für hochkritische Tenant-Operationen."""
    if user.get("api_key_id"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Owner only (API-Key auth cannot use owner routes)",
        )
    from core.rbac import is_owner

    role = user.get("role") or user.get("rolle") or ""
    if not is_owner(role):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Owner only")
    return user

"""
JWT- und Passwort-Helfer (API-/Tutorial-kompatibel).

- Token-Erzeugung läuft über ``core.jwt_tokens`` / ``core.jwt_config`` (ein Secret, ein Algorithmus).
- ``sub`` im Access-JWT ist bei neuen Logins die **numerische User-ID** (String); ältere Tokens können noch
  den Benutzernamen in ``sub`` tragen — beides versteht ``backend.deps._user_from_jwt_claims``.
- ``verify_password`` / ``hash_password``: passlib-bcrypt, kompatibel zu in ``benutzer.hash`` gespeicherten bcrypt-Strings.
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed or plain is None:
        return False
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


def create_access_token(data: dict) -> str:
    """
    HS256-Access-Token. Pflichtfeld: ``sub`` (User-ID als String oder Legacy-Benutzername).
    Optional: ``kanzlei_id``, ``tenant_id``, ``rolle``, ``role``, ``email``, ``uid`` — Claims.
    """
    payload: Dict[str, Any] = dict(data)
    sub = str(payload.pop("sub", "") or "").strip()
    if not sub:
        raise ValueError("JWT claim 'sub' (User-ID oder Benutzername) fehlt")
    payload.pop("exp", None)
    return _create_access_token_core(sub, extra_claims=payload or None)


def access_token_ttl_minutes() -> int:
    raw = (os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES") or "").strip()
    if raw.isdigit():
        return max(1, int(raw))
    return 60


def algorithm() -> str:
    return (os.getenv("JWT_ALGORITHM") or "HS256").strip() or "HS256"


def secret_configured() -> bool:
    return bool(jwt_secret())


def decode_token(token: str) -> Dict[str, Any]:
    """JWT dekodieren und Claims zurückgeben (wirft bei ungültigem Secret/Token)."""
    _, jwt = _jose()
    secret = jwt_secret()
    if not secret:
        raise ValueError("JWT_SECRET ist nicht gesetzt.")
    return jwt.decode(token, secret, algorithms=[algorithm()])


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """JWT verifizieren; bei Fehler ``None`` (für Middleware/Logging)."""
    try:
        JWTError, _ = _jose()
    except ImportError:
        return None
    try:
        return decode_token(token)
    except (JWTError, ValueError):
        return None


def create_refresh_token(subject: str, *, extra_claims: Optional[Dict[str, Any]] = None) -> str:
    JWTError, jwt = _jose()
    secret = jwt_secret()
    if not secret:
        raise ValueError("JWT_SECRET ist nicht gesetzt.")
    now = int(time.time())
    days = refresh_token_expire_days()
    payload: Dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + max(3600, days * 24 * 60 * 60),
        "typ": "refresh",
    }
    if extra_claims:
        for k, v in extra_claims.items():
            if k not in payload:
                payload[k] = v
    return jwt.encode(payload, secret, algorithm=algorithm())


def verify_refresh_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        JWTError, jwt = _jose()
    except ImportError:
        return None
    secret = jwt_secret()
    if not secret:
        return None
    try:
        claims = jwt.decode(token, secret, algorithms=[algorithm()])
    except (JWTError, ValueError):
        return None
    if (claims.get("typ") or "") != "refresh":
        return None
    return claims


def refresh_token_expire_days() -> int:
    raw = (os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS") or "14").strip()
    try:
        days = int(raw)
    except Exception:
        days = 14
    return max(1, min(days, 90))


# Compatibility aliases for existing callsites
verify_access_token = verify_token


def jwt_secret() -> str:
    return (os.getenv("JWT_SECRET") or os.getenv("JWT_SECRET_KEY") or "").strip()


def _jose():
    try:
        from jose import JWTError, jwt
    except ImportError as e:
        raise ImportError(
            "JWT benötigt das Paket python-jose (pip install 'python-jose[cryptography]')."
        ) from e
    return JWTError, jwt


def _create_access_token_core(
    subject: str,
    *,
    extra_claims: Optional[Dict[str, Any]] = None,
    expires_minutes: Optional[int] = None,
) -> str:
    JWTError, jwt = _jose()
    secret = jwt_secret()
    if not secret:
        raise ValueError("JWT_SECRET ist nicht gesetzt.")
    minutes = expires_minutes if expires_minutes is not None else access_token_ttl_minutes()
    now = int(time.time())
    payload: Dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + max(60, minutes * 60),
        "typ": "access",
    }
    if extra_claims:
        for k, v in extra_claims.items():
            if k not in payload:
                payload[k] = v
    return jwt.encode(payload, secret, algorithm=algorithm())


create_access_token_for_subject = _create_access_token_core


# Namens-Aliase (Checklisten / Tutorials)
create_token = create_access_token


# -----------------------------------------------------------------------------
# Single entrypoint facade:
# Expose legacy auth/service functions via ``backend.auth`` so app code only
# imports one module, while implementation remains in ``core.auth`` for now.
# -----------------------------------------------------------------------------
import core.auth as _core_auth


def __getattr__(name: str):
    if hasattr(_core_auth, name):
        return getattr(_core_auth, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

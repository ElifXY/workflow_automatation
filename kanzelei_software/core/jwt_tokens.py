"""Compatibility wrapper: JWT token helpers live in ``backend.auth``."""
from __future__ import annotations

from typing import Any, Dict, Optional

from backend.auth import create_refresh_token
from backend.auth import create_access_token_for_subject as create_access_token
from backend.auth import refresh_token_expire_days
from backend.auth import verify_refresh_token
from backend.auth import verify_token as verify_access_token
from backend.auth import decode_token as decode_access_token
from backend.auth import access_token_ttl_minutes as access_token_expire_minutes


def decode_refresh_token(token: str) -> Dict[str, Any]:
    claims = verify_refresh_token(token)
    if not claims:
        raise ValueError("JWT_REFRESH ungültig")
    return claims


def prepare_refresh_token_pair(subject: str) -> Dict[str, Any]:
    access = create_access_token(subject)
    refresh = create_refresh_token(subject)
    return {
        "access_token": access,
        "token_type": "bearer",
        "expires_in": access_token_expire_minutes() * 60,
        "refresh_token": refresh,
        "refresh_expires_in": refresh_token_expire_days() * 24 * 60 * 60,
    }

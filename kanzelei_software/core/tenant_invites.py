"""
Mandanten-Einladungen: HMAC-signierte Tokens (ohne DB-Tabelle).

- Erstellung nur serverseitig (Admin-Endpunkt).
- Registrierung mit ``invite_token`` tritt der Kanzlei bei; Rolle kommt aus dem Token
  (nicht aus Client-``rolle``), damit keine Privilegien-Eskalation möglich ist.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any, Dict, Optional

_INVITE_VERSION = 1
_MAX_TTL_H = 720  # 30 Tage


def _signing_secret() -> str:
    s = (
        (os.getenv("INVITE_TOKEN_SECRET") or os.getenv("JWT_SECRET") or os.getenv("PORTAL_SECRET") or "")
        .strip()
    )
    return s


def invite_secret_configured() -> bool:
    return len(_signing_secret()) >= 32


def _require_secret() -> bytes:
    s = _signing_secret()
    if len(s) < 32:
        raise ValueError(
            "invite_secret_short: Setze INVITE_TOKEN_SECRET (≥32 Zeichen) oder JWT_SECRET/PORTAL_SECRET."
        )
    return s.encode("utf-8")


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("ascii"))


def _normalize_invite_role(rolle: str) -> str:
    r = (rolle or "assistent").strip().lower()
    if r in {"mitarbeiter", "user"}:
        return "assistent"
    if r in {"admin", "steuerberater", "assistent"}:
        return r
    return "assistent"


def create_tenant_invite_token(
    *,
    kanzlei_id: str,
    invited_by: str,
    rolle: str = "assistent",
    email_lock: Optional[str] = None,
    ttl_hours: int = 168,
) -> str:
    """
    Erzeugt ein Einladungs-Token (URL-tauglich).

    ``email_lock``: wenn gesetzt, muss die Registrierungs-E-Mail exakt dazu passen.
    """
    kid = (kanzlei_id or "").strip()
    if not kid:
        raise ValueError("kanzlei_id required")
    eff_role = _normalize_invite_role(rolle)
    if eff_role == "admin":
        raise ValueError("invite_admin_forbidden: Admins bitte über Benutzer-Anlage anlegen, nicht per Invite.")
    ttl = max(1, min(int(ttl_hours or 168), _MAX_TTL_H))
    now = int(time.time())
    exp = now + ttl * 3600
    el = (email_lock or "").strip().lower() or None
    payload: Dict[str, Any] = {
        "v": _INVITE_VERSION,
        "kid": kid,
        "role": eff_role,
        "el": el,
        "iat": now,
        "exp": exp,
        "by": (invited_by or "")[:120],
        "jti": secrets.token_urlsafe(12),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sig = hmac.new(_require_secret(), raw, hashlib.sha256).hexdigest()
    return _b64e(raw) + "." + sig


def verify_tenant_invite_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Liefert bei Erfolg dict mit kanzlei_id, role, email_lock (oder None), exp, invited_by.
    """
    t = (token or "").strip()
    if not t or "." not in t:
        return None
    enc, sig = t.rsplit(".", 1)
    try:
        raw = _b64d(enc)
    except Exception:
        return None
    try:
        expect = hmac.new(_require_secret(), raw, hashlib.sha256).hexdigest()
    except ValueError:
        return None
    if not hmac.compare_digest(expect, sig):
        return None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    if int(payload.get("v") or 0) != _INVITE_VERSION:
        return None
    kid = (payload.get("kid") or "").strip()
    if not kid:
        return None
    now = int(time.time())
    if now > int(payload.get("exp") or 0):
        return None
    role = _normalize_invite_role(str(payload.get("role") or "assistent"))
    el = payload.get("el")
    if el is not None and str(el).strip() == "":
        el = None
    jti = str(payload.get("jti") or "").strip()
    if jti:
        try:
            from core.tenant_invite_records import invite_token_allowed

            if not invite_token_allowed(jti=jti, kanzlei_id=kid):
                return None
        except Exception:
            pass
    return {
        "kanzlei_id": kid,
        "role": role,
        "email_lock": (str(el).strip().lower() if el else None),
        "exp": int(payload.get("exp") or 0),
        "invited_by": str(payload.get("by") or ""),
        "jti": jti or None,
        "iat": int(payload.get("iat") or 0),
    }

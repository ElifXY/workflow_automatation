#!/usr/bin/env python3
"""
Go-Live Gate: blockiert Deploy bei Auth/RBAC-Regression.

Checks:
1) Register/Login/Me Flow funktioniert
2) Login liefert role/rolle
3) User -> /api/admin/users == 403
4) Admin -> /api/admin/users == 200
5) Keine sensitiven Felder in /api/admin/users

Usage:
  python scripts/go_live_rbac_gate.py
"""
from __future__ import annotations

import os
import sys
import uuid
from typing import Any, Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi.testclient import TestClient  # noqa: E402


def _fail(errors: List[str], msg: str) -> None:
    errors.append(msg)
    print(f"FAIL: {msg}")


def _ok(msg: str) -> None:
    print(f"PASS: {msg}")


def _token(body: Dict[str, Any]) -> str:
    return str(body.get("access_token") or body.get("token") or "")


def main() -> int:
    os.environ.setdefault("ENABLE_ADVANCED_FEATURES", "1")
    os.environ.setdefault("SECURITY_BASELINE_BOOTSTRAP", "1")
    import api  # noqa: WPS433,E402
    from backend.auth import erstelle_benutzer  # noqa: WPS433,E402

    errors: List[str] = []
    c = TestClient(api.app)
    tag = uuid.uuid4().hex[:10]
    pw = "StrongPass8"

    # Public user flow
    user_email = f"gate_user_{tag}@example.com"
    r = c.post("/api/register", json={"email": user_email, "password": pw})
    if r.status_code != 201:
        _fail(errors, f"/api/register expected 201 got {r.status_code}: {r.text}")
    else:
        _ok("/api/register returns 201")
        try:
            reg_j = r.json()
            if reg_j.get("tenant_id") != reg_j.get("kanzlei_id"):
                _fail(errors, f"/api/register tenant_id != kanzlei_id: {reg_j}")
            elif not reg_j.get("kanzlei_id"):
                _fail(errors, f"/api/register ohne kanzlei_id/tenant_id: {reg_j}")
            else:
                _ok("/api/register liefert konsistente Mandanten-IDs")
        except Exception as exc:
            _fail(errors, f"/api/register JSON/tenant-Felder: {exc}")

    r = c.post("/api/login", json={"email": user_email, "password": pw})
    if r.status_code != 200:
        _fail(errors, f"/api/login expected 200 got {r.status_code}: {r.text}")
        user_body: Dict[str, Any] = {}
    else:
        _ok("/api/login returns 200")
        user_body = r.json()

    role_value = user_body.get("role") or user_body.get("rolle")
    if not role_value:
        _fail(errors, "login response missing role/rolle")
    else:
        _ok("login response contains role")

    user_token = _token(user_body)
    if not user_token:
        _fail(errors, "login response missing token")
    else:
        _ok("login response contains token")

    if user_token:
        try:
            from backend.auth import jwt_secret as _jwt_secret_fn
            from backend.auth import verify_access_token as _verify_at

            if _jwt_secret_fn():
                try:
                    import jose  # noqa: F401 — nur Verfügbarkeit; Claims-Check nur mit python-jose
                except ImportError:
                    _ok("JWT_SECRET gesetzt, python-jose fehlt lokal — Mandanten-JWT-Claims-Check übersprungen")
                else:
                    claims = _verify_at(user_token)
                    if not claims:
                        _fail(
                            errors,
                            "JWT_SECRET gesetzt und python-jose installiert, aber access_token nicht "
                            "als JWT verifizierbar (Session-Fallback prüfen)",
                        )
                    elif claims.get("tenant_id") != claims.get("kanzlei_id"):
                        _fail(errors, f"JWT: tenant_id != kanzlei_id in Claims: {claims}")
                    elif not claims.get("kanzlei_id"):
                        _fail(errors, f"JWT ohne kanzlei_id: {claims}")
                    else:
                        _ok("JWT-Mandanten-Claims (tenant_id == kanzlei_id)")
        except Exception as exc:
            _fail(errors, f"JWT-Claim-Prüfung fehlgeschlagen: {exc}")

    if user_token:
        r = c.get("/api/me", headers={"Authorization": f"Bearer {user_token}"})
        if r.status_code != 200:
            _fail(errors, f"/api/me expected 200 got {r.status_code}: {r.text}")
        else:
            me = r.json()
            if (me.get("email") or "").lower() != user_email.lower():
                _fail(errors, f"/api/me email mismatch: {me}")
            elif me.get("id") is None:
                _fail(errors, f"/api/me id missing: {me}")
            elif (me.get("tenant_id") or "") != (me.get("kanzlei_id") or ""):
                _fail(errors, f"/api/me tenant_id != kanzlei_id: {me}")
            else:
                _ok("/api/me returns id+email+tenant")

    # Mandanten-Isolation: User A legt Mandanten an, User B sieht ihn nicht
    iso = uuid.uuid4().hex[:10]
    pw_iso = "StrongPass8"
    em_a = f"iso_a_{iso}@example.com"
    em_b = f"iso_b_{iso}@example.com"
    mandant_name = f"IsoMandant_{iso}"
    ra = c.post("/api/register", json={"email": em_a, "password": pw_iso})
    rb = c.post("/api/register", json={"email": em_b, "password": pw_iso})
    if ra.status_code != 201 or rb.status_code != 201:
        _fail(
            errors,
            f"tenant isolation register failed: a={ra.status_code} b={rb.status_code}",
        )
    else:
        la = c.post("/api/login", json={"email": em_a, "password": pw_iso})
        lb = c.post("/api/login", json={"email": em_b, "password": pw_iso})
        if la.status_code != 200 or lb.status_code != 200:
            _fail(errors, "tenant isolation login failed")
        else:
            ta = _token(la.json())
            tb = _token(lb.json())
            cr = c.post(
                "/mandanten",
                headers={"Authorization": f"Bearer {ta}"},
                json={"name": mandant_name, "umsatz": 0},
            )
            if cr.status_code != 201:
                _fail(errors, f"tenant isolation create mandant expected 201 got {cr.status_code}: {cr.text}")
            else:
                lst = c.get("/mandanten", headers={"Authorization": f"Bearer {tb}"})
                if lst.status_code != 200:
                    _fail(errors, f"tenant isolation list B expected 200 got {lst.status_code}")
                else:
                    body = lst.json()
                    rows = body.get("data") if isinstance(body, dict) else None
                    names = {r.get("name") for r in (rows or []) if isinstance(r, dict)}
                    if mandant_name in names:
                        _fail(errors, "tenant leak: B sees A's mandant in list")
                    else:
                        _ok("tenant isolation: list does not leak other tenant")
                one = c.get(
                    f"/mandanten/{mandant_name}",
                    headers={"Authorization": f"Bearer {tb}"},
                )
                if one.status_code != 404:
                    _fail(
                        errors,
                        f"tenant isolation get other mandant expected 404 got {one.status_code}",
                    )
                else:
                    _ok("tenant isolation: cross-tenant mandant GET is 404")

    # Dedicated admin/user RBAC check
    admin_email = f"gate_admin_{tag}@example.com"
    admin_name = f"gate_admin_{tag}"
    user2_email = f"gate_user2_{tag}@example.com"
    user2_name = f"gate_user2_{tag}"
    try:
        erstelle_benutzer(admin_name, pw, rolle="admin", email=admin_email, kanzlei_id="default")
    except ValueError:
        pass
    try:
        erstelle_benutzer(user2_name, pw, rolle="user", email=user2_email, kanzlei_id="default")
    except ValueError:
        pass

    user2_login = c.post("/api/login", json={"email": user2_email, "password": pw})
    admin_login = c.post("/api/login", json={"email": admin_email, "password": pw})

    if user2_login.status_code != 200 or admin_login.status_code != 200:
        _fail(
            errors,
            "failed to login rbac fixtures: "
            f"user={user2_login.status_code}, admin={admin_login.status_code}",
        )
    else:
        user2_token = _token(user2_login.json())
        admin_token = _token(admin_login.json())

        r_forbidden = c.get("/api/admin/users", headers={"Authorization": f"Bearer {user2_token}"})
        if r_forbidden.status_code != 403:
            _fail(errors, f"user to /api/admin/users expected 403 got {r_forbidden.status_code}")
        else:
            _ok("user gets 403 on /api/admin/users")

        r_allowed = c.get("/api/admin/users", headers={"Authorization": f"Bearer {admin_token}"})
        if r_allowed.status_code != 200:
            _fail(errors, f"admin to /api/admin/users expected 200 got {r_allowed.status_code}")
        else:
            data = r_allowed.json()
            if not isinstance(data, list):
                _fail(errors, f"/api/admin/users payload not list: {type(data).__name__}")
            elif not data:
                _fail(errors, "/api/admin/users returned empty list")
            elif any(any(k in row for k in ("hash", "salt", "password_hash")) for row in data):
                _fail(errors, "sensitive fields leaked in /api/admin/users")
            else:
                _ok("admin gets sanitized list on /api/admin/users")

    print("---")
    if errors:
        print(f"GATE RESULT: FAIL ({len(errors)} issues)")
        return 1
    print("GATE RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


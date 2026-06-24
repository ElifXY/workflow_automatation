#!/usr/bin/env python3
"""
Invite-Flow fuer ``/api/users/invites``:
1) Admin erstellt Invite (persistenter Datensatz)
2) GET Liste + nach Registrierung Status ``used``
3) Zweites Invite widerrufen (DELETE) -> ``revoked``
4) Nicht-Admin: POST/GET -> 403
5) Invite-User tritt derselben Kanzlei bei
6) GET /api/users/invites: Mandant B sieht keine JTI von Mandant A

  python scripts/test_api_users_invites.py
"""
from __future__ import annotations

import os
import sys
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi.testclient import TestClient  # noqa: E402


def _token(login_json: dict) -> str:
    return login_json.get("access_token") or login_json.get("token") or ""


def _unwrap(body: object) -> dict:
    if isinstance(body, dict):
        data = body.get("data")
        if isinstance(data, dict):
            return data
        return body
    return {}


def _unwrap_rows(body: object) -> list:
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        rows = body.get("data")
        if isinstance(rows, list):
            return rows
    return []


def main() -> int:
    import api  # noqa: WPS433

    if len((os.getenv("JWT_SECRET") or os.getenv("PORTAL_SECRET") or os.getenv("INVITE_TOKEN_SECRET") or "").strip()) < 32:
        print("SKIP: kein Secret >=32 (JWT_SECRET/PORTAL_SECRET/INVITE_TOKEN_SECRET)")
        return 0

    c = TestClient(api.app)
    tag = uuid.uuid4().hex[:10]
    pw = "StrongPass8"

    admin_email = f"ui_admin_{tag}@example.com"
    admin_b_email = f"ui_admin_b_{tag}@example.com"
    invited_email = f"ui_inv_{tag}@example.com"

    r_admin_reg = c.post("/api/register", json={"email": admin_email, "password": pw})
    if r_admin_reg.status_code != 201:
        print("register admin", r_admin_reg.status_code, r_admin_reg.text)
        return 1
    r_admin_login = c.post("/api/login", json={"email": admin_email, "password": pw})
    if r_admin_login.status_code != 200:
        print("login admin", r_admin_login.status_code, r_admin_login.text)
        return 1
    admin_token = _token(r_admin_login.json())
    ha = {"Authorization": f"Bearer {admin_token}"}

    # 1) Admin Invite erzeugen
    r_inv = c.post(
        "/api/users/invites",
        headers=ha,
        json={"email": invited_email, "role": "assistent", "ttl_hours": 24, "send_email": False},
    )
    if r_inv.status_code != 201:
        print("admin invite should be 201", r_inv.status_code, r_inv.text)
        return 1
    inv_data = _unwrap(r_inv.json())
    invite_token = inv_data.get("invite_token")
    jti = inv_data.get("jti")
    if not invite_token or not jti:
        print("invite token/jti missing", r_inv.text)
        return 1

    r_list_inv0 = c.get("/api/users/invites", headers=ha)
    if r_list_inv0.status_code != 200:
        print("list invites", r_list_inv0.status_code, r_list_inv0.text)
        return 1
    row0 = next((x for x in _unwrap_rows(r_list_inv0.json()) if x.get("jti") == jti), None)
    if not row0 or row0.get("status") != "pending":
        print("expected pending invite row", row0, r_list_inv0.text)
        return 1

    # Invite-User registriert sich mit Token
    r_inv_reg = c.post("/api/register", json={"email": invited_email, "password": pw, "invite_token": invite_token})
    if r_inv_reg.status_code != 201:
        print("invite register", r_inv_reg.status_code, r_inv_reg.text)
        return 1

    r_inv_login = c.post("/api/login", json={"email": invited_email, "password": pw})
    if r_inv_login.status_code != 200:
        print("invited login", r_inv_login.status_code, r_inv_login.text)
        return 1
    invited_token = _token(r_inv_login.json())
    hu = {"Authorization": f"Bearer {invited_token}"}

    r_list_inv1 = c.get("/api/users/invites", headers=ha)
    if r_list_inv1.status_code != 200:
        print("list invites after use", r_list_inv1.status_code, r_list_inv1.text)
        return 1
    row1 = next((x for x in _unwrap_rows(r_list_inv1.json()) if x.get("jti") == jti), None)
    if not row1 or row1.get("status") != "used":
        print("expected used invite row", row1)
        return 1

    # Zweites Invite + Widerruf
    r_inv2 = c.post(
        "/api/users/invites",
        headers=ha,
        json={"role": "assistent", "ttl_hours": 24, "send_email": False},
    )
    if r_inv2.status_code != 201:
        print("second invite", r_inv2.status_code, r_inv2.text)
        return 1
    inv2 = _unwrap(r_inv2.json())
    jti2 = inv2.get("jti")
    if not jti2:
        print("no jti2", inv2)
        return 1
    r_del = c.delete(f"/api/users/invites/{jti2}", headers=ha)
    if r_del.status_code != 200:
        print("revoke invite", r_del.status_code, r_del.text)
        return 1
    r_list_inv2 = c.get("/api/users/invites", headers=ha)
    row2 = next((x for x in _unwrap_rows(r_list_inv2.json()) if x.get("jti") == jti2), None)
    if not row2 or row2.get("status") != "revoked":
        print("expected revoked", row2)
        return 1

    # 2) Nicht-Admin darf Invite nicht erstellen
    r_forbidden = c.post(
        "/api/users/invites",
        headers=hu,
        json={"email": f"nope_{tag}@example.com", "role": "assistent", "ttl_hours": 24, "send_email": False},
    )
    if r_forbidden.status_code != 403:
        print("non-admin invite should be 403", r_forbidden.status_code, r_forbidden.text)
        return 1
    r_g403 = c.get("/api/users/invites", headers=hu)
    if r_g403.status_code != 403:
        print("non-admin list invites should be 403", r_g403.status_code, r_g403.text)
        return 1

    # 3) Isolation: anderer Admin kann invited_email nicht sehen
    r_admin_b_reg = c.post("/api/register", json={"email": admin_b_email, "password": pw})
    if r_admin_b_reg.status_code != 201:
        print("register admin b", r_admin_b_reg.status_code, r_admin_b_reg.text)
        return 1
    r_admin_b_login = c.post("/api/login", json={"email": admin_b_email, "password": pw})
    if r_admin_b_login.status_code != 200:
        print("login admin b", r_admin_b_login.status_code, r_admin_b_login.text)
        return 1
    hb = {"Authorization": f"Bearer {_token(r_admin_b_login.json())}"}

    r_invites_b = c.get("/api/users/invites", headers=hb)
    if r_invites_b.status_code != 200:
        print("list invites B", r_invites_b.status_code, r_invites_b.text)
        return 1
    jtis_b_invites = {x.get("jti") for x in _unwrap_rows(r_invites_b.json()) if x.get("jti")}
    if jti in jtis_b_invites or jti2 in jtis_b_invites:
        print("tenant B must not see tenant A invite jtis", jtis_b_invites)
        return 1

    r_list_a = c.get("/api/users", headers=ha)
    r_list_b = c.get("/api/users", headers=hb)
    if r_list_a.status_code != 200 or r_list_b.status_code != 200:
        print("list status", r_list_a.status_code, r_list_b.status_code)
        return 1
    emails_a = {x.get("email") for x in _unwrap_rows(r_list_a.json()) if isinstance(x, dict)}
    if invited_email not in emails_a:
        print("tenant A should include invited user", emails_a)
        return 1
    emails_b = {x.get("email") for x in _unwrap_rows(r_list_b.json()) if isinstance(x, dict)}
    if invited_email in emails_b:
        print("tenant isolation failed: B sees invited user")
        return 1

    print("PASS: /api/users/invites invite flow")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

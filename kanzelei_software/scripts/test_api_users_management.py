#!/usr/bin/env python3
"""
REST ``/api/users``: Admin legt Benutzer an, Nicht-Admin erhält 403, Listen nur eigene Kanzlei.

Nutzt echte Mandanten über ``/api/register`` (Kanzlei wird angelegt), kein manuelles ``kanzlei_id``.

  python scripts/test_api_users_management.py
"""
from __future__ import annotations

import os
import sys
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi.testclient import TestClient  # noqa: E402


def _unwrap_list(body: object) -> list:
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        d = body.get("data")
        if isinstance(d, list):
            return d
    return []


def _token(login_json: dict) -> str:
    return login_json.get("access_token") or login_json.get("token") or ""


def main() -> int:
    import api  # noqa: WPS433

    c = TestClient(api.app)
    tag = uuid.uuid4().hex[:10]
    pw = "StrongPass8"

    admin_a_email = f"um_admin_a_{tag}@example.com"
    low_user_email = f"um_user_{tag}@example.com"
    admin_b_email = f"um_admin_b_{tag}@example.com"

    ra = c.post("/api/register", json={"email": admin_a_email, "password": pw})
    if ra.status_code != 201:
        print("register admin A", ra.status_code, ra.text)
        return 1

    la = c.post("/api/login", json={"email": admin_a_email, "password": pw})
    if la.status_code != 200:
        print("login admin A", la.status_code, la.text)
        return 1
    ta = _token(la.json())
    ha = {"Authorization": f"Bearer {ta}"}

    # 1) Admin A erstellt Mitarbeiter in derselben Kanzlei
    cr = c.post("/api/users", headers=ha, json={"email": low_user_email, "password": pw, "role": "user"})
    if cr.status_code != 201:
        print("admin POST /api/users expected 201, got", cr.status_code, cr.text)
        return 1

    lu = c.post("/api/login", json={"email": low_user_email, "password": pw})
    if lu.status_code != 200:
        print("login low user", lu.status_code, lu.text)
        return 1
    tu = _token(lu.json())
    hu = {"Authorization": f"Bearer {tu}"}

    # 2) Normaler User: POST -> 403
    other_em = f"um_other_{tag}@example.com"
    forbidden = c.post("/api/users", headers=hu, json={"email": other_em, "password": pw, "role": "user"})
    if forbidden.status_code != 403:
        print("user POST /api/users expected 403, got", forbidden.status_code, forbidden.text)
        return 1

    g403 = c.get("/api/users", headers=hu)
    if g403.status_code != 403:
        print("user GET /api/users expected 403, got", g403.status_code, g403.text)
        return 1

    # 3a) Admin A: Liste enthält angelegten User + sich selbst
    lst = c.get("/api/users", headers=ha)
    if lst.status_code != 200:
        print("GET /api/users", lst.status_code, lst.text)
        return 1
    rows_a = _unwrap_list(lst.json())
    for row in rows_a:
        if isinstance(row, dict) and row.get("email") == low_user_email:
            if "is_active" not in row or "role" not in row:
                print("GET /api/users row missing is_active/role", row)
                return 1
            break
    else:
        print("GET /api/users missing created user row")
        return 1
    emails = {r.get("email") for r in rows_a if isinstance(r, dict)}
    if low_user_email not in emails or admin_a_email not in emails:
        print("list missing expected emails", emails)
        return 1

    # 3b) Zweite Kanzlei (Admin B) sieht Tenant A nicht
    rb = c.post("/api/register", json={"email": admin_b_email, "password": pw})
    if rb.status_code != 201:
        print("register admin B", rb.status_code, rb.text)
        return 1
    lb = c.post("/api/login", json={"email": admin_b_email, "password": pw})
    if lb.status_code != 200:
        print("login admin B", lb.status_code, lb.text)
        return 1
    tb = _token(lb.json())
    hb = {"Authorization": f"Bearer {tb}"}
    lst_b = c.get("/api/users", headers=hb)
    if lst_b.status_code != 200:
        print("GET /api/users B", lst_b.status_code, lst_b.text)
        return 1
    emails_b = {r.get("email") for r in _unwrap_list(lst_b.json()) if isinstance(r, dict)}
    if low_user_email in emails_b or admin_a_email in emails_b:
        print("tenant isolation failed: B sees A users", emails_b)
        return 1
    if admin_b_email not in emails_b:
        print("B should see at least self", emails_b)
        return 1

    dup = c.post("/api/users", headers=ha, json={"email": low_user_email, "password": pw, "role": "user"})
    if dup.status_code != 409:
        print("duplicate email expected 409, got", dup.status_code, dup.text)
        return 1
    bad_role = c.post(
        "/api/users",
        headers=ha,
        json={"email": f"badrole_{tag}@example.com", "password": pw, "role": "not_a_real_role"},
    )
    if bad_role.status_code != 422:
        print("invalid role expected 422, got", bad_role.status_code, bad_role.text)
        return 1

    print("PASS: /api/users management + tenant isolation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

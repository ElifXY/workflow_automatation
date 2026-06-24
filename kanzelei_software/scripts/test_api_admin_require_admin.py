#!/usr/bin/env python3
"""
Smoke-Test: ``GET /api/admin/test`` mit ``require_admin``.

- Admin (Session-Bearer nach Login): 200 + ``Admin access works``
- Normaler User: 403, ``detail`` enthält ``Admin only``

  python scripts/test_api_admin_require_admin.py
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


def main() -> int:
    import api  # noqa: WPS433

    c = TestClient(api.app)
    tag = uuid.uuid4().hex[:10]
    pw = "StrongPass8"
    admin_em = f"adm_gate_{tag}@example.com"
    user_em = f"usr_gate_{tag}@example.com"

    r1 = c.post("/api/register", json={"email": admin_em, "password": pw})
    if r1.status_code != 201:
        print("register admin", r1.status_code, r1.text)
        return 1
    la = c.post("/api/login", json={"email": admin_em, "password": pw})
    if la.status_code != 200:
        print("login admin", la.status_code, la.text)
        return 1
    ta = _token(la.json())
    ok = c.get("/api/admin/test", headers={"Authorization": f"Bearer {ta}"})
    if ok.status_code != 200 or ok.json().get("message") != "Admin access works":
        print("admin GET /api/admin/test expected 200 + message, got", ok.status_code, ok.text)
        return 1

    cr = c.post("/api/users", headers={"Authorization": f"Bearer {ta}"}, json={"email": user_em, "password": pw, "role": "user"})
    if cr.status_code != 201:
        print("admin create user", cr.status_code, cr.text)
        return 1
    lu = c.post("/api/login", json={"email": user_em, "password": pw})
    if lu.status_code != 200:
        print("login user", lu.status_code, lu.text)
        return 1
    tu = _token(lu.json())
    forbidden = c.get("/api/admin/test", headers={"Authorization": f"Bearer {tu}"})
    if forbidden.status_code != 403:
        print("user GET /api/admin/test expected 403, got", forbidden.status_code, forbidden.text)
        return 1
    body = forbidden.json()
    msg = str(body.get("detail") or body.get("error") or "")
    if "Admin only" not in msg:
        print("expected Admin only in error payload, got", body)
        return 1

    print("PASS: require_admin + /api/admin/test (admin 200, user 403)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

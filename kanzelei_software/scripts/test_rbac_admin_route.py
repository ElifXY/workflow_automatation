#!/usr/bin/env python3
"""
RBAC-Regressiontest:
1) normaler User -> /api/admin/users => 403
2) Admin -> /api/admin/users => 200
"""
from __future__ import annotations

import os
import sys
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi.testclient import TestClient  # noqa: E402


def _fail(msg: str) -> int:
    print(f"FAIL: {msg}")
    return 1


def main() -> int:
    import api  # noqa: WPS433,E402
    from backend.auth import erstelle_benutzer  # noqa: WPS433,E402

    c = TestClient(api.app)
    tag = uuid.uuid4().hex[:10]
    pw = "StrongPass8"

    admin_email = f"rbac_admin_{tag}@example.com"
    user_email = f"rbac_user_{tag}@example.com"
    admin_name = f"rbac_admin_{tag}"
    user_name = f"rbac_user_{tag}"

    # Setup
    try:
        erstelle_benutzer(admin_name, pw, rolle="admin", email=admin_email, kanzlei_id="default")
    except ValueError:
        pass
    try:
        erstelle_benutzer(user_name, pw, rolle="user", email=user_email, kanzlei_id="default")
    except ValueError:
        pass

    # User login
    r_user_login = c.post("/api/login", json={"email": user_email, "password": pw})
    if r_user_login.status_code != 200:
        return _fail(f"user login status={r_user_login.status_code} body={r_user_login.text}")
    user_body = r_user_login.json()
    user_token = user_body.get("access_token") or user_body.get("token")
    if not user_token:
        return _fail("user login returned no token")
    if not (user_body.get("role") or user_body.get("rolle")):
        return _fail("user login returned no role field")

    # Admin login
    r_admin_login = c.post("/api/login", json={"email": admin_email, "password": pw})
    if r_admin_login.status_code != 200:
        return _fail(f"admin login status={r_admin_login.status_code} body={r_admin_login.text}")
    admin_body = r_admin_login.json()
    admin_token = admin_body.get("access_token") or admin_body.get("token")
    if not admin_token:
        return _fail("admin login returned no token")
    if (admin_body.get("role") or admin_body.get("rolle")) != "admin":
        return _fail(f"admin login role mismatch: {admin_body}")

    # Test 1: normaler user darf nicht
    r_forbidden = c.get("/api/admin/users", headers={"Authorization": f"Bearer {user_token}"})
    if r_forbidden.status_code != 403:
        return _fail(f"user should be 403, got {r_forbidden.status_code} body={r_forbidden.text}")

    # Test 2: admin darf
    r_allowed = c.get("/api/admin/users", headers={"Authorization": f"Bearer {admin_token}"})
    if r_allowed.status_code != 200:
        return _fail(f"admin should be 200, got {r_allowed.status_code} body={r_allowed.text}")
    payload = r_allowed.json()
    if not isinstance(payload, list):
        return _fail(f"admin payload should be list, got {type(payload).__name__}")
    if not payload:
        return _fail("admin payload unexpectedly empty")
    for row in payload[:3]:
        if any(k in row for k in ("hash", "salt", "password_hash")):
            return _fail("sensitive fields leaked in admin/users payload")

    print("PASS: RBAC admin route checks succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


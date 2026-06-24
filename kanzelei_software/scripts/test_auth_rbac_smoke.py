#!/usr/bin/env python3
"""
Auth/RBAC smoke test:
- Login with user credentials
- Verify read endpoint works
- Verify write-admin endpoint is blocked for non-admin roles
"""

from __future__ import annotations

import os
import sys
import requests


BASE_URL = (os.getenv("TEST_BASE_URL") or "http://127.0.0.1:8000").rstrip("/")
LOGIN_EMAIL = (os.getenv("TEST_LOGIN_EMAIL") or "").strip()
LOGIN_PASSWORD = (os.getenv("TEST_LOGIN_PASSWORD") or "").strip()


def fail(msg: str, code: int = 1) -> int:
    print(f"[FAIL] {msg}")
    return code


def main() -> int:
    if not LOGIN_EMAIL or not LOGIN_PASSWORD:
        return fail("Set TEST_LOGIN_EMAIL and TEST_LOGIN_PASSWORD first.")

    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/auth/login",
        json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD},
        timeout=20,
    )
    if r.status_code != 200:
        return fail(f"login failed: {r.status_code} {r.text[:300]}")
    data = r.json()
    payload = data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), dict) else data
    token = str(payload.get("access_token") or payload.get("token") or "")
    role = str(payload.get("role") or payload.get("rolle") or "")
    if not token:
        return fail("no token in login response")

    headers = {"Authorization": f"Bearer {token}"}

    # Read endpoint should be reachable for normal users.
    read_resp = s.get(f"{BASE_URL}/settings", headers=headers, timeout=20)
    if read_resp.status_code != 200:
        return fail(f"/settings read denied unexpectedly: {read_resp.status_code} {read_resp.text[:300]}")

    # Write endpoint should be denied for non-admin/non-write roles.
    write_resp = s.put(
        f"{BASE_URL}/settings",
        headers=headers,
        json={"key": "kanzlei_name", "wert": "RBAC Smoke Test"},
        timeout=20,
    )
    if role.lower() == "admin":
        if write_resp.status_code >= 400:
            return fail(f"admin write should pass but failed: {write_resp.status_code} {write_resp.text[:300]}")
    else:
        if write_resp.status_code != 403:
            return fail(f"non-admin write should be 403, got {write_resp.status_code} {write_resp.text[:300]}")

    print(f"[OK] auth/rbac smoke passed for role={role or 'unknown'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())


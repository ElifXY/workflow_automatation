from __future__ import annotations

import secrets
import string

import httpx


BASE = "http://localhost:8000"


def _rand(n: int = 8) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))


def _login(client: httpx.Client, email: str, password: str) -> dict:
    res = client.post("/api/login", json={"email": email, "password": password})
    if res.status_code >= 400:
        raise RuntimeError(f"login failed for {email}: {res.status_code} {res.text[:180]}")
    payload = res.json()
    data = payload.get("data") if isinstance(payload, dict) else None
    return data or payload


def main() -> int:
    suffix = _rand(6)
    owner_email = f"owner_{suffix}@example.com"
    admin_email = f"admin_{suffix}@example.com"
    staff_email = f"staff_{suffix}@example.com"
    owner_pw = "Aa!" + _rand(12)
    admin_pw = "Bb!" + _rand(12)
    staff_pw = "Cc!" + _rand(12)

    with httpx.Client(base_url=BASE, verify=False, timeout=20.0) as c:
        # 1) Owner entsteht bei erstem Register im Tenant
        reg = c.post("/api/register", json={"email": owner_email, "password": owner_pw, "rolle": "mitarbeiter"})
        if reg.status_code != 201:
            raise RuntimeError(f"owner register failed: {reg.status_code} {reg.text[:180]}")
        owner = _login(c, owner_email, owner_pw)
        owner_token = owner.get("access_token") or owner.get("token")
        owner_headers = {"Authorization": f"Bearer {owner_token}"}
        if (owner.get("role") or owner.get("rolle")) != "owner":
            raise RuntimeError(f"expected owner role, got: {owner.get('role') or owner.get('rolle')}")

        # 2) Owner darf Admin anlegen
        res = c.post(
            "/api/tenant/users",
            json={"email": admin_email, "password": admin_pw, "rolle": "admin"},
            headers=owner_headers,
        )
        if res.status_code != 201:
            raise RuntimeError(f"owner create admin failed: {res.status_code} {res.text[:180]}")

        # 3) Owner darf Mitarbeiter anlegen
        res = c.post(
            "/api/tenant/users",
            json={"email": staff_email, "password": staff_pw, "rolle": "mitarbeiter"},
            headers=owner_headers,
        )
        if res.status_code != 201:
            raise RuntimeError(f"owner create staff failed: {res.status_code} {res.text[:180]}")

        # 4) Admin darf KEINEN Admin/Owner anlegen, aber Mitarbeiter
        admin = _login(c, admin_email, admin_pw)
        admin_token = admin.get("access_token") or admin.get("token")
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        res = c.post(
            "/api/tenant/users",
            json={"email": f"blocked_admin_{suffix}@example.com", "password": "Dd!" + _rand(12), "rolle": "admin"},
            headers=admin_headers,
        )
        if res.status_code != 403:
            raise RuntimeError(f"admin should be blocked creating admin, got {res.status_code}: {res.text[:180]}")

        res = c.post(
            "/api/tenant/users",
            json={"email": f"ok_staff_{suffix}@example.com", "password": "Ee!" + _rand(12), "rolle": "mitarbeiter"},
            headers=admin_headers,
        )
        if res.status_code != 201:
            raise RuntimeError(f"admin create staff should pass, got {res.status_code}: {res.text[:180]}")

        # 5) Owner-only Feature-Flags: owner OK, admin 403
        res = c.put("/api/tenant/features", json={"api_webhooks_write": True}, headers=owner_headers)
        if res.status_code != 200:
            raise RuntimeError(f"owner feature put failed: {res.status_code} {res.text[:180]}")

        res = c.put("/api/tenant/features", json={"api_webhooks_write": False}, headers=admin_headers)
        if res.status_code != 403:
            raise RuntimeError(f"admin feature put should be 403, got {res.status_code}: {res.text[:180]}")

        # 6) Mitarbeiter darf keine Admin-Route
        staff = _login(c, staff_email, staff_pw)
        staff_token = staff.get("access_token") or staff.get("token")
        staff_headers = {"Authorization": f"Bearer {staff_token}"}
        res = c.get("/api/tenant/users", headers=staff_headers)
        if res.status_code != 403:
            raise RuntimeError(f"staff should not list users, got {res.status_code}: {res.text[:180]}")

    print("RBAC_MATRIX_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


#!/usr/bin/env python3
"""Pass 11 API Smoke — Betreuer-Matrix, Mandant-Zugriff, M365-Mails Endpoint."""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402


def _unwrap(body):
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def _token(body):
    d = _unwrap(body) or {}
    return d.get("token") or d.get("access_token") or ""


def _ok(resp, msg: str):
    if resp.status_code >= 400:
        raise AssertionError(f"{msg}: {resp.status_code} {resp.text[:320]}")


def main() -> int:
    os.environ["ENVIRONMENT"] = "development"
    os.environ["APP_ENV"] = "development"
    os.environ["USE_POSTGRES_DATA"] = "0"
    os.environ.pop("DATABASE_URL", None)
    os.environ["DATA_DIR"] = f".tmp_pass11_{uuid.uuid4().hex}"
    import api  # noqa: F401

    c = TestClient(api.app)
    tag = uuid.uuid4().hex[:8]
    pw = "StrongPass9!"
    admin_user = f"p11_admin_{tag}"
    admin_mail = f"p11_admin_{tag}@example.com"
    staff_mail = f"p11_staff_{tag}@example.com"

    _ok(
        c.post(
            "/auth/registrieren",
            json={"benutzername": admin_user, "passwort": pw, "rolle": "admin", "email": admin_mail},
        ),
        "register admin",
    )
    login = c.post("/auth/login", json={"benutzername": admin_user, "passwort": pw})
    _ok(login, "login admin")
    h_admin = {"Authorization": f"Bearer {_token(login.json())}"}

    mandant_a = f"Mandant A {tag}"
    mandant_b = f"Mandant B {tag}"
    _ok(
        c.post(
            "/mandanten",
            headers=h_admin,
            json={"name": mandant_a, "email": f"a_{tag}@mandant.de", "betreuer_email": staff_mail},
        ),
        "create mandant A",
    )
    _ok(
        c.post(
            "/mandanten",
            headers=h_admin,
            json={"name": mandant_b, "email": f"b_{tag}@mandant.de", "betreuer_email": admin_mail},
        ),
        "create mandant B",
    )

    matrix = c.get("/mandanten/betreuer-matrix", headers=h_admin)
    _ok(matrix, "betreuer matrix")
    md = _unwrap(matrix.json()) or {}
    names = {row.get("name") for row in (md.get("mandanten") or [])}
    assert mandant_a in names and mandant_b in names, "matrix should list mandanten"

    _ok(
        c.put("/mandanten/" + mandant_a, headers=h_admin, json={"betreuer_email": staff_mail}),
        "update betreuer",
    )

    from backend.auth import erstelle_benutzer, loginname_aus_email

    staff_login_name = loginname_aus_email(staff_mail)
    erstelle_benutzer(
        staff_login_name,
        pw,
        rolle="mitarbeiter",
        email=staff_mail,
        kanzlei_id="default",
    )

    staff_login = c.post("/auth/login", json={"benutzername": staff_login_name, "passwort": pw})
    _ok(staff_login, "login staff")
    h_staff = {"Authorization": f"Bearer {_token(staff_login.json())}"}

    ok_a = c.get(f"/mandanten/{mandant_a}", headers=h_staff)
    _ok(ok_a, "staff reads assigned mandant")

    deny_b = c.get(f"/mandanten/{mandant_b}", headers=h_staff)
    assert deny_b.status_code == 403, f"staff should not read mandant B, got {deny_b.status_code}"

    staff_matrix = c.get("/mandanten/betreuer-matrix", headers=h_staff)
    _ok(staff_matrix, "staff matrix")
    sm = _unwrap(staff_matrix.json()) or {}
    staff_names = {row.get("name") for row in (sm.get("mandanten") or [])}
    assert mandant_a in staff_names, "staff sees assigned mandant in matrix"
    assert mandant_b not in staff_names, "staff must not see other mandant in matrix"

    m365 = c.get(f"/mandanten/{mandant_a}/m365-mails", headers=h_staff)
    _ok(m365, "m365 mails endpoint")
    m365d = _unwrap(m365.json()) or {}
    assert m365d.get("mandant") == mandant_a
    assert "messages" in m365d

    print("PASS pass11 api smoke: betreuer-matrix + mandant access + m365-mails")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

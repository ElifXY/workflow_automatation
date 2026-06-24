#!/usr/bin/env python3
"""Pass 12 API Smoke — M365 Timeline-Sync + Betreuer-Bulk."""
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
    os.environ["DATA_DIR"] = f".tmp_pass12_{uuid.uuid4().hex}"
    import api  # noqa: F401

    c = TestClient(api.app)
    tag = uuid.uuid4().hex[:8]
    pw = "StrongPass9!"
    admin_user = f"p12_admin_{tag}"
    admin_mail = f"p12_admin_{tag}@example.com"
    staff_mail = f"p12_staff_{tag}@example.com"

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

    m1 = f"Mandant One {tag}"
    m2 = f"Mandant Two {tag}"
    _ok(c.post("/mandanten", headers=h_admin, json={"name": m1, "email": f"one_{tag}@x.de"}), "m1")
    _ok(c.post("/mandanten", headers=h_admin, json={"name": m2, "email": f"two_{tag}@x.de"}), "m2")

    bulk = c.patch(
        "/mandanten/betreuer-matrix/bulk",
        headers=h_admin,
        json={"betreuer_email": staff_mail, "nur_ohne_betreuer": True},
    )
    _ok(bulk, "bulk betreuer")
    bulk_data = _unwrap(bulk.json()) or {}
    assert int(bulk_data.get("updated") or 0) >= 2, "expected both mandanten updated"

    sync = c.post(f"/mandanten/{m1}/m365-mails/sync-timeline", headers=h_admin)
    _ok(sync, "m365 timeline sync")
    sync_data = _unwrap(sync.json()) or {}
    assert "imported" in sync_data

    komm = c.get(f"/kommunikation/{m1}", headers=h_admin)
    _ok(komm, "kommunikation list")
    kd = _unwrap(komm.json()) or {}
    assert isinstance(kd.get("kommunikation"), list)

    print("PASS pass12 api smoke: bulk betreuer + m365 timeline sync endpoint")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

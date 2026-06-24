#!/usr/bin/env python3
"""Pass 13 API Smoke — Betreuer-Filter, Portal-Antwort-Hinweis, Workflow-Typen."""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta
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
    os.environ["DATA_DIR"] = f".tmp_pass13_{uuid.uuid4().hex}"
    import api  # noqa: F401

    c = TestClient(api.app)
    tag = uuid.uuid4().hex[:8]
    pw = "StrongPass9!"
    admin_user = f"p13_admin_{tag}"
    admin_mail = f"p13_admin_{tag}@example.com"
    staff_mail = f"p13_staff_{tag}@example.com"

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

    m1 = f"Mandant A {tag}"
    m2 = f"Mandant B {tag}"
    _ok(
        c.post(
            "/mandanten",
            headers=h_admin,
            json={"name": m1, "email": f"a_{tag}@x.de", "betreuer_email": staff_mail},
        ),
        "m1",
    )
    _ok(
        c.post(
            "/mandanten",
            headers=h_admin,
            json={"name": m2, "email": f"b_{tag}@x.de"},
        ),
        "m2",
    )

    filtered = c.get("/mandanten", headers=h_admin, params={"betreuer_email": staff_mail})
    _ok(filtered, "betreuer filter")
    rows = _unwrap(filtered.json()) or []
    names = {str(r.get("name") or "") for r in rows}
    assert m1 in names and m2 not in names, "betreuer filter should only return assigned mandant"

    none_only = c.get("/mandanten", headers=h_admin, params={"nur_ohne_betreuer": True})
    _ok(none_only, "ohne betreuer filter")
    none_rows = _unwrap(none_only.json()) or []
    none_names = {str(r.get("name") or "") for r in none_rows}
    assert m2 in none_names and m1 not in none_names

    triggers = c.get("/regeln/verfuegbare-trigger", headers=h_admin)
    _ok(triggers, "workflow typen")
    td = _unwrap(triggers.json()) or triggers.json()
    assert "m365_timeline_import" in (td.get("aktionen") or {})

    _ok(c.put("/settings", headers=h_admin, json={"key": "portal_aktiv", "wert": True}), "portal on")
    old_antwort = (datetime.now() - timedelta(days=12)).isoformat()
    mm = api.ds.hole_mandant(m2) or {}
    mm["letzte_antwort"] = old_antwort
    api.ds.mandant_speichern(m2, mm)
    pt = c.post(f"/portal/admin/token/{m2}", headers=h_admin)
    _ok(pt, "portal token")
    portal_token = (_unwrap(pt.json()) or {}).get("token")
    assert portal_token, "portal token missing"
    gw = (os.getenv("PORTAL_GATEWAY_KEY") or os.getenv("API_GATEWAY_KEY") or "").strip()
    pl_headers = {"X-Api-Gateway-Key": gw} if gw else {}
    pl = c.post("/portal/login", params={"token": portal_token}, headers=pl_headers)
    _ok(pl, "portal login")
    pl_data = _unwrap(pl.json()) or pl.json()
    assert int(pl_data.get("tage_ohne_antwort") or 0) >= 7
    assert pl_data.get("antwort_hinweis"), "expected antwort_hinweis banner text"

    print("PASS pass13 api smoke: betreuer filter + portal antwort + workflow typen")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

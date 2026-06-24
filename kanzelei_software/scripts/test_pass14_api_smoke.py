#!/usr/bin/env python3
"""Pass 14 API Smoke — 100% Produktstrategie: Suche, Gesundheit, Teamleiter."""
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
    os.environ["DATA_DIR"] = f".tmp_pass14_{uuid.uuid4().hex}"
    import api  # noqa: F401
    from core.rbac import CANONICAL_ROLES, canonical_role

    assert "teamleiter" in CANONICAL_ROLES
    assert canonical_role("teamleiter") == "teamleiter"

    c = TestClient(api.app)
    tag = uuid.uuid4().hex[:8]
    pw = "StrongPass9!"
    admin_user = f"p14_admin_{tag}"

    _ok(
        c.post(
            "/auth/registrieren",
            json={"benutzername": admin_user, "passwort": pw, "rolle": "admin", "email": f"p14_{tag}@example.com"},
        ),
        "register admin",
    )
    login = c.post("/auth/login", json={"benutzername": admin_user, "passwort": pw})
    _ok(login, "login")
    h = {"Authorization": f"Bearer {_token(login.json())}"}

    name = f"Mandant Suche {tag}"
    _ok(c.post("/mandanten", headers=h, json={"name": name, "email": f"s_{tag}@x.de"}), "create")

    suche = c.get("/suche", headers=h, params={"q": tag})
    _ok(suche, "globale suche")
    sd = _unwrap(suche.json()) or {}
    assert any(r.get("typ") == "mandant" for r in (sd.get("ergebnisse") or [])), "mandant in suche"

    detail = c.get(f"/mandanten/{name}", headers=h)
    _ok(detail, "mandant detail")
    dd = _unwrap(detail.json()) or {}
    assert "health_score" in dd and "health_ampel" in dd, "health fields on mandant detail"

    triggers = c.get("/regeln/verfuegbare-trigger", headers=h)
    _ok(triggers, "workflow typen")
    td = _unwrap(triggers.json()) or triggers.json()
    assert "m365_timeline_import" in (td.get("aktionen") or {})

    print("PASS pass14 api smoke: suche + health + teamleiter rolle")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

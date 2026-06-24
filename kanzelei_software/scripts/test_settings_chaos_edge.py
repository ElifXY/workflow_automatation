#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient


def _unwrap(body):
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def _token(body):
    d = _unwrap(body) or {}
    return d.get("token") or d.get("access_token") or ""


def _ok(resp, msg: str):
    if resp.status_code >= 400:
        raise AssertionError(f"{msg}: {resp.status_code} {resp.text[:260]}")


def _set(c: TestClient, h: dict, key: str, wert):
    r = c.put("/settings", headers=h, json={"key": key, "wert": wert})
    _ok(r, f"set {key}")


def _must_4xx(c: TestClient, h: dict, key: str, wert, label: str):
    r = c.put("/settings", headers=h, json={"key": key, "wert": wert})
    if r.status_code < 400:
        raise AssertionError(f"{label}: expected 4xx, got {r.status_code}")


def main() -> int:
    os.environ["ENVIRONMENT"] = "development"
    os.environ["APP_ENV"] = "development"
    os.environ["DATA_DIR"] = f".tmp_settings_chaos_edge_{uuid.uuid4().hex}"
    import api

    c = TestClient(api.app)
    tag = uuid.uuid4().hex[:8]
    pw = "StrongPass8!"
    user = f"chaos_admin_{tag}"
    mail = f"chaos_admin_{tag}@example.com"

    r = c.post("/auth/registrieren", json={"benutzername": user, "passwort": pw, "rolle": "admin", "email": mail})
    _ok(r, "register")
    l = c.post("/auth/login", json={"benutzername": user, "passwort": pw})
    _ok(l, "login")
    h = {"Authorization": f"Bearer {_token(l.json())}"}
    if hasattr(api, "_tenant_rate_store"):
        api._tenant_rate_store.clear()
    _set(c, h, "api_rate_limit_pro_minute", 100000)

    # 1) Rapid toggle sequences (state should remain valid)
    for _ in range(3):
        _set(c, h, "datev_export_aktiv", False)
        r0 = c.get("/export/datev/stammdaten", headers=h)
        if r0.status_code != 503:
            raise AssertionError(f"DATEV gate expected 503, got {r0.status_code}")
        _set(c, h, "datev_export_aktiv", True)

        _set(c, h, "elster_aktiv", False)
        r1 = c.get("/export/nonexistent/elster", headers=h)
        if r1.status_code != 503:
            raise AssertionError(f"ELSTER gate expected 503, got {r1.status_code}")
        _set(c, h, "elster_aktiv", True)

    # 2) Invariant-violating direct writes must always fail
    _set(c, h, "ip_whitelist", [])
    _must_4xx(c, h, "ip_whitelist_aktiv", True, "ip whitelist guard")
    _set(c, h, "ip_whitelist", ["127.0.0.1/32"])
    _set(c, h, "ip_whitelist_aktiv", False)

    _set(c, h, "elster_aktiv", False)
    _must_4xx(c, h, "elster_direktversand", True, "elster dependency guard")
    _set(c, h, "elster_aktiv", True)

    _set(c, h, "billing_aktiv", False)
    _set(c, h, "billing_stripe_key", "")
    _must_4xx(c, h, "billing_stripe_aktiv", True, "stripe dependency guard")

    _must_4xx(c, h, "rollen_einstellungen", ["mitarbeiter"], "settings role guard")
    _must_4xx(c, h, "rollen_mandant_loeschen", ["steuerberater"], "delete role guard")
    _must_4xx(c, h, "rollen_zahlungen_freigabe", ["mitarbeiter"], "payment role guard")

    # 3) Batch request with mixed valid/invalid values should keep invalids rejected
    batch = {
        "api_rate_limit_pro_minute": 500,
        "billing_aktiv": True,
        "billing_stripe_aktiv": True,  # invalid without key
        "server_standort": "EU",
        "rollen_einstellungen": ["mitarbeiter"],  # invalid
    }
    rb = c.put("/settings/batch", headers=h, json=batch)
    _ok(rb, "batch update")
    data = _unwrap(rb.json()) or {}
    details = data.get("details") or {}
    if details.get("billing_stripe_aktiv") is not False:
        raise AssertionError("batch should reject invalid billing_stripe_aktiv")
    if details.get("rollen_einstellungen") is not False:
        raise AssertionError("batch should reject invalid rollen_einstellungen")
    if details.get("server_standort") is not True:
        raise AssertionError("batch should accept valid server_standort")

    rs = c.get("/settings", headers=h)
    _ok(rs, "get settings")
    s = _unwrap(rs.json()) or {}
    if s.get("rollen_einstellungen") == ["mitarbeiter"]:
        raise AssertionError("invalid rollen_einstellungen was persisted")
    if bool(s.get("billing_stripe_aktiv")) is True and not str(s.get("billing_stripe_key") or "").strip():
        raise AssertionError("invalid stripe state persisted without key")

    print("[OK] settings chaos edge checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


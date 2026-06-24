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
        raise AssertionError(f"{msg}: {resp.status_code} {resp.text[:240]}")


def _set(c: TestClient, h: dict, key: str, wert):
    r = c.put("/settings", headers=h, json={"key": key, "wert": wert})
    _ok(r, f"set {key}")


def main() -> int:
    os.environ["ENVIRONMENT"] = "development"
    os.environ["APP_ENV"] = "development"
    os.environ["DATA_DIR"] = f".tmp_schnittstellen_compliance_{uuid.uuid4().hex}"
    import api

    c = TestClient(api.app)
    tag = uuid.uuid4().hex[:8]
    pw = "StrongPass8!"
    admin_user = f"sc_admin_{tag}"
    admin_mail = f"sc_admin_{tag}@example.com"

    r = c.post(
        "/auth/registrieren",
        json={"benutzername": admin_user, "passwort": pw, "rolle": "admin", "email": admin_mail},
    )
    _ok(r, "register admin")
    l = c.post("/auth/login", json={"benutzername": admin_user, "passwort": pw})
    _ok(l, "login admin")
    h = {"Authorization": f"Bearer {_token(l.json())}"}
    api._tenant_rate_store.clear()
    _set(c, h, "api_rate_limit_pro_minute", 100000)

    # Compliance invariants: fail-closed on dependent settings
    _set(c, h, "ip_whitelist", [])
    i0 = c.put("/settings", headers=h, json={"key": "ip_whitelist_aktiv", "wert": True})
    assert i0.status_code == 400, f"ip_whitelist_aktiv without entries should fail, got {i0.status_code}"
    _set(c, h, "ip_whitelist", ["127.0.0.1/32"])
    _set(c, h, "ip_whitelist_aktiv", False)

    _set(c, h, "elster_aktiv", False)
    e_guard = c.put("/settings", headers=h, json={"key": "elster_direktversand", "wert": True})
    assert e_guard.status_code == 400, f"elster_direktversand without elster_aktiv should fail, got {e_guard.status_code}"
    _set(c, h, "elster_aktiv", True)

    _set(c, h, "billing_aktiv", False)
    _set(c, h, "billing_stripe_key", "")
    s_guard = c.put("/settings", headers=h, json={"key": "billing_stripe_aktiv", "wert": True})
    assert s_guard.status_code == 400, f"stripe without billing/key should fail, got {s_guard.status_code}"

    # Roles/compliance invariants: critical actions only owner/admin
    r_settings = c.put("/settings", headers=h, json={"key": "rollen_einstellungen", "wert": ["mitarbeiter"]})
    assert r_settings.status_code == 400, f"rollen_einstellungen with mitarbeiter should fail, got {r_settings.status_code}"
    r_delete = c.put("/settings", headers=h, json={"key": "rollen_mandant_loeschen", "wert": ["steuerberater"]})
    assert r_delete.status_code == 400, f"rollen_mandant_loeschen without admin/owner should fail, got {r_delete.status_code}"
    r_pay = c.put("/settings", headers=h, json={"key": "rollen_zahlungen_freigabe", "wert": ["mitarbeiter"]})
    assert r_pay.status_code == 400, f"rollen_zahlungen_freigabe without admin/owner should fail, got {r_pay.status_code}"

    # DATEV gate
    _set(c, h, "datev_export_aktiv", False)
    d0 = c.get("/export/datev/stammdaten", headers=h)
    assert d0.status_code == 503, f"DATEV disabled should return 503, got {d0.status_code}"
    _set(c, h, "datev_export_aktiv", True)
    d1 = c.get("/export/datev/stammdaten", headers=h)
    assert d1.status_code != 503, "DATEV enabled should not be blocked by gate"

    # ELSTER gate
    _set(c, h, "elster_aktiv", False)
    e0 = c.get("/export/nonexistent/elster", headers=h)
    assert e0.status_code == 503, f"ELSTER disabled should return 503, got {e0.status_code}"
    _set(c, h, "elster_aktiv", True)
    e1 = c.get("/export/nonexistent/elster", headers=h)
    assert e1.status_code != 503, "ELSTER enabled should not be blocked by gate"

    # Webhook URL consistency with settings (only if webhook feature is available)
    _set(c, h, "webhook_url", "https://hooks.example.com/inbox")
    w_bad = c.post(
        "/saas/webhooks",
        headers=h,
        json={"url": "https://hooks.example.com/other", "events": ["settings.changed"]},
    )
    if w_bad.status_code not in (402, 403):
        assert w_bad.status_code == 400, f"webhook mismatch should return 400, got {w_bad.status_code}"

    # Tenant API rate limit runtime gate
    api._tenant_rate_store.clear()
    _set(c, h, "api_rate_limit_pro_minute", 2)
    # Lese-GETs auf /settings, /aufgaben zählen nicht (SPA-Ausnahme)
    r1 = c.get("/api/v1/endpoints", headers=h)
    _ok(r1, "endpoints request 1")
    r2 = c.get("/api/v1/endpoints", headers=h)
    if r2.status_code == 429:
        pass
    else:
        _ok(r2, "endpoints request 2")
        r3 = c.get("/api/v1/endpoints", headers=h)
        assert r3.status_code == 429, f"expected tenant rate limit 429, got {r3.status_code}"

    print("[OK] schnittstellen+compliance runtime checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


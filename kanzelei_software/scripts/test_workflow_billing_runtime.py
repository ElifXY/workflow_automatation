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


def main() -> int:
    os.environ["ENVIRONMENT"] = "development"
    os.environ["APP_ENV"] = "development"
    os.environ["DATA_DIR"] = f".tmp_workflow_billing_{uuid.uuid4().hex}"
    import api
    from core.daten_speicher import DatenSpeicher
    import core.scheduler as scheduler

    c = TestClient(api.app)
    tag = uuid.uuid4().hex[:8]
    pw = "StrongPass8!"
    admin_user = f"wb_admin_{tag}"
    admin_mail = f"wb_admin_{tag}@example.com"

    r = c.post("/auth/registrieren", json={"benutzername": admin_user, "passwort": pw, "rolle": "admin", "email": admin_mail})
    _ok(r, "register admin")
    l = c.post("/auth/login", json={"benutzername": admin_user, "passwort": pw})
    _ok(l, "login admin")
    h = {"Authorization": f"Bearer {_token(l.json())}"}

    # Billing gate
    _ok(c.put("/settings", headers=h, json={"key": "billing_aktiv", "wert": False}), "disable billing")
    b0 = c.get("/billing/usage", headers=h)
    assert b0.status_code == 503, f"billing disabled should block usage endpoint, got {b0.status_code}"
    _ok(c.put("/settings", headers=h, json={"key": "billing_aktiv", "wert": True}), "enable billing")
    b1 = c.get("/billing/usage", headers=h)
    _ok(b1, "billing usage enabled")

    # Scheduler workflow gates
    ds = DatenSpeicher(kanzlei_id="default")
    ds.setting_setzen("auto_workflow_monatsabschluss", False)
    ds.setting_setzen("auto_workflow_lohn", False)
    scheduler._heute_gelaufen.clear()
    jid_workflow = scheduler.job_id("workflow")
    jid_lohn = scheduler.job_id("lohn")
    scheduler.run_workflow_batch()
    scheduler.run_lohnabrechnung()
    assert jid_workflow not in scheduler._heute_gelaufen, "workflow job should be skipped when disabled"
    assert jid_lohn not in scheduler._heute_gelaufen, "lohn job should be skipped when disabled"

    print("[OK] workflow+billing runtime checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

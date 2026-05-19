#!/usr/bin/env python3
from __future__ import annotations

import base64
import os
import sys
import uuid
from datetime import datetime, timedelta
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
    os.environ["DATA_DIR"] = f".tmp_security_portal_{uuid.uuid4().hex}"
    import api
    from core.daten_speicher import DatenSpeicher

    c = TestClient(api.app)
    tag = uuid.uuid4().hex[:8]
    pw = "StrongPass8!"
    admin_user = f"sec_admin_{tag}"
    admin_mail = f"sec_admin_{tag}@example.com"

    r = c.post("/auth/registrieren", json={"benutzername": admin_user, "passwort": pw, "rolle": "admin", "email": admin_mail})
    _ok(r, "register admin")
    l = c.post("/auth/login", json={"benutzername": admin_user, "passwort": pw})
    _ok(l, "login admin")
    admin_token = _token(l.json())
    h_admin = {"Authorization": f"Bearer {admin_token}"}

    mandant = f"Mandant {tag}"
    cm = c.post("/mandanten", headers=h_admin, json={"name": mandant, "email": f"m_{tag}@example.com"})
    _ok(cm, "create mandant")

    # Portal activation gate
    _ok(c.put("/settings", headers=h_admin, json={"key": "portal_aktiv", "wert": False}), "disable portal")
    p1 = c.post(f"/portal/admin/token/{mandant}", headers=h_admin)
    assert p1.status_code == 503, f"portal disabled should block token generation, got {p1.status_code}"
    _ok(c.put("/settings", headers=h_admin, json={"key": "portal_aktiv", "wert": True}), "enable portal")
    p2 = c.post(f"/portal/admin/token/{mandant}", headers=h_admin)
    _ok(p2, "portal token generation")
    portal_token = (_unwrap(p2.json()) or {}).get("token")
    gw = (os.getenv("PORTAL_GATEWAY_KEY") or os.getenv("API_GATEWAY_KEY") or "").strip()
    portal_login_headers = {"X-Api-Gateway-Key": gw} if gw else {}
    pl = c.post("/portal/login", params={"token": portal_token}, headers=portal_login_headers)
    _ok(pl, "portal login")
    portal_bearer = (_unwrap(pl.json()) or {}).get("token")
    h_portal = {"Authorization": f"Bearer {portal_bearer}"}

    # Portal upload rules
    _ok(c.put("/settings", headers=h_admin, json={"key": "portal_projektnummer_pflicht", "wert": True}), "enable project number required")
    _ok(c.put("/settings", headers=h_admin, json={"key": "portal_upload_max_mb", "wert": 1}), "set max upload size")
    up = c.post(
        "/portal/dokumente/hochladen",
        headers=h_portal,
        json={
            "dateiname": "beleg.pdf",
            "dateityp": "application/pdf",
            "inhalt_b64": base64.b64encode(b"small").decode(),
            "kategorie": "Sonstiges",
        },
    )
    assert up.status_code == 400, f"missing project number should fail, got {up.status_code}"
    up2 = c.post(
        "/portal/dokumente/hochladen",
        headers=h_portal,
        json={
            "dateiname": "beleg2.pdf",
            "dateityp": "application/pdf",
            "inhalt_b64": base64.b64encode(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF").decode(),
            "kategorie": "Sonstiges",
            "projektnummer": "PRJ-1",
        },
    )
    _ok(up2, "upload with project number")

    # Signature gate
    _ok(c.put("/settings", headers=h_admin, json={"key": "portal_unterschrift_aktiv", "wert": False}), "disable signatures")
    sig = c.get("/portal/unterschrift/offen", headers=h_portal)
    assert sig.status_code == 503, f"signature endpoint should be disabled, got {sig.status_code}"
    _ok(c.put("/settings", headers=h_admin, json={"key": "portal_unterschrift_aktiv", "wert": True}), "enable signatures")

    # IP whitelist enforcement
    _ok(c.put("/settings", headers=h_admin, json={"key": "ip_whitelist", "wert": ["127.0.0.1"]}), "set ip whitelist")
    _ok(c.put("/settings", headers=h_admin, json={"key": "ip_whitelist_aktiv", "wert": True}), "enable ip whitelist")
    bad_ip = c.get("/settings", headers={**h_admin, "X-Forwarded-For": "10.9.8.7"})
    assert bad_ip.status_code == 403, f"non-whitelisted ip should be blocked, got {bad_ip.status_code}"
    _ok(c.put("/settings", headers={**h_admin, "X-Forwarded-For": "127.0.0.1"}, json={"key": "ip_whitelist_aktiv", "wert": False}), "disable ip whitelist")

    # Session timeout enforcement via stale last_seen
    store = DatenSpeicher(kanzlei_id="default")
    _ok(c.put("/settings", headers=h_admin, json={"key": "session_timeout_minuten", "wert": 5}), "set session timeout")
    stale = {"__dummy__": "x", admin_user: (datetime.utcnow() - timedelta(minutes=10)).isoformat()}
    store.setting_setzen("__security_last_seen_v1", stale)
    timed = c.get("/settings", headers=h_admin)
    assert timed.status_code == 401, f"stale session should be expired, got {timed.status_code}"
    l3 = c.post("/auth/login", json={"benutzername": admin_user, "passwort": pw})
    _ok(l3, "re-login admin")
    h_admin = {"Authorization": f"Bearer {_token(l3.json())}"}
    store.setting_setzen("__security_last_seen_v1", {admin_user: datetime.utcnow().isoformat()})

    # 2FA requirement for non-admin
    assistant_user = f"sec_user_{tag}"
    r2 = c.post("/auth/registrieren", json={"benutzername": assistant_user, "passwort": pw, "rolle": "assistent", "email": f"{assistant_user}@example.com"})
    _ok(r2, "register assistant")
    l2 = c.post("/auth/login", json={"benutzername": assistant_user, "passwort": pw})
    _ok(l2, "login assistant")
    h_user = {"Authorization": f"Bearer {_token(l2.json())}"}
    _ok(c.put("/settings", headers=h_admin, json={"key": "2fa_pflicht", "wert": True}), "enable 2fa requirement")
    blocked = c.get("/settings", headers=h_user)
    assert blocked.status_code == 403, f"non-admin without mfa should be blocked, got {blocked.status_code}"

    print("[OK] security+portal runtime checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Phase 5: Einladung → Registrierung → gemeinsame Mandanten-Daten + Feature-Flags.

  python scripts/test_phase5_tenant_admin.py

Benötigt wie die API üblicherweise JWT_SECRET oder PORTAL_SECRET ≥32 für Einladungen.
"""
from __future__ import annotations

import os
import sys
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi.testclient import TestClient  # noqa: E402


def main() -> int:
    import api  # noqa: WPS433

    if len((os.getenv("JWT_SECRET") or os.getenv("PORTAL_SECRET") or os.getenv("INVITE_TOKEN_SECRET") or "").strip()) < 32:
        print("SKIP: kein Secret ≥32 (JWT_SECRET/PORTAL_SECRET/INVITE_TOKEN_SECRET)")
        return 0

    c = TestClient(api.app)
    tag = uuid.uuid4().hex[:10]
    pw = "StrongPass8"
    admin_em = f"p5_admin_{tag}@example.com"
    invite_em = f"p5_inv_{tag}@example.com"

    r = c.post("/api/register", json={"email": admin_em, "password": pw})
    if r.status_code != 201:
        print("register admin", r.status_code, r.text)
        return 1
    la = c.post("/api/login", json={"email": admin_em, "password": pw})
    if la.status_code != 200:
        print("login admin", la.status_code, la.text)
        return 1
    ta = la.json().get("access_token") or la.json().get("token")
    h = {"Authorization": f"Bearer {ta}"}

    inv = c.post("/api/tenant/invites", json={"rolle": "assistent", "ttl_hours": 24}, headers=h)
    if inv.status_code != 200:
        print("invite", inv.status_code, inv.text)
        return 1
    body = inv.json()
    token = (body.get("data") or body).get("invite_token")
    if not token:
        print("no invite_token", body)
        return 1

    rb = c.post(
        "/api/register",
        json={"email": invite_em, "password": pw, "invite_token": token},
    )
    if rb.status_code != 201:
        print("register invitee", rb.status_code, rb.text)
        return 1

    lb = c.post("/api/login", json={"email": invite_em, "password": pw})
    if lb.status_code != 200:
        print("login invitee", lb.status_code, lb.text)
        return 1
    tb = lb.json().get("access_token") or lb.json().get("token")
    hb = {"Authorization": f"Bearer {tb}"}

    mand = f"P5M_{tag}"
    cr = c.post("/mandanten", headers=h, json={"name": mand, "umsatz": 0})
    if cr.status_code != 201:
        print("create mandant", cr.status_code, cr.text)
        return 1

    lst = c.get("/mandanten", headers=hb)
    if lst.status_code != 200:
        print("list mandanten B", lst.status_code, lst.text)
        return 1
    data = lst.json().get("data") or []
    names = {row.get("name") for row in data if isinstance(row, dict)}
    if mand not in names:
        print("invitee should see shared mandant", names)
        return 1

    fg = c.get("/api/tenant/features", headers=hb)
    if fg.status_code != 200:
        print("features get", fg.status_code, fg.text)
        return 1

    pu = c.put(
        "/api/tenant/features",
        headers=h,
        json={"advanced_reports": True, "unknown_key": True},
    )
    if pu.status_code != 200:
        print("features put", pu.status_code, pu.text)
        return 1
    inner = pu.json().get("data") or pu.json()
    if not inner.get("advanced_reports"):
        print("feature merge failed", pu.json())
        return 1

    wh = c.post(
        "/saas/webhooks",
        headers=h,
        json={"url": "https://example.com/hook", "events": ["email.sent"], "secret": "12345678"},
    )
    if wh.status_code != 403:
        print("expected 403 webhook without api_webhooks_write", wh.status_code)
        return 1

    r_flags = c.put("/api/tenant/features", headers=h, json={"api_webhooks_write": True})
    if r_flags.status_code != 200:
        print("enable webhooks flag", r_flags.status_code, r_flags.text)
        return 1
    wh2 = c.post(
        "/saas/webhooks",
        headers=h,
        json={"url": "https://example.com/hook2", "events": ["email.sent"], "secret": "12345678"},
    )
    if wh2.status_code != 200:
        print("webhook create after flag", wh2.status_code)
        return 1

    csv_r = c.get("/export/csv/mandanten", headers=h)
    if csv_r.status_code != 200:
        print("csv export default on", csv_r.status_code, csv_r.text)
        return 1

    r_off = c.put("/api/tenant/features", headers=h, json={"bulk_export": False})
    if r_off.status_code != 200:
        print("disable bulk_export", r_off.status_code, r_off.text)
        return 1
    csv2 = c.get("/export/csv/mandanten", headers=h)
    if csv2.status_code != 403:
        print("expected 403 csv when bulk_export off", csv2.status_code, csv2.text)
        return 1

    r_on = c.put("/api/tenant/features", headers=h, json={"bulk_export": True})
    if r_on.status_code != 200:
        print("re-enable bulk_export", r_on.status_code, r_on.text)
        return 1
    csv3 = c.get("/export/csv/mandanten", headers=h)
    if csv3.status_code != 200:
        print("csv after re-enable", csv3.status_code, csv3.text)
        return 1

    print("OK phase5 invite + shared mandant + features + webhook/export gates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

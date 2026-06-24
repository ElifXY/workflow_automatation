#!/usr/bin/env python3
"""
End-to-End: E-Mail registrieren → /login → Bearer /me.

Voraussetzung: JWT_SECRET gesetzt (sonst nur Session-Token).
Optional: PORTAL_ADMIN_KEY in der Umgebung, wenn bereits Benutzer existieren.

  python scripts/test_email_auth_flow.py
"""
from __future__ import annotations

import os
import sys
import uuid

# Repo-Root auf sys.path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Standard: Session-Bearer (funktioniert ohne python-jose im Host-Python).
# Mit FORCE_JWT_TEST=1 + installiertem python-jose zusätzlich JWT-Pfad testen.
if (os.environ.get("FORCE_JWT_TEST") or "").strip().lower() in ("1", "true", "yes"):
    os.environ.setdefault("JWT_SECRET", "x" * 64)
else:
    os.environ.pop("JWT_SECRET", None)
    os.environ.pop("JWT_SECRET_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402


def main() -> int:
    import api  # noqa: WPS433

    tag = uuid.uuid4().hex[:12]
    email = f"e2e_{tag}@example.com"
    password = "testpass8"

    client = TestClient(api.app)

    reg_body = {"email": email, "password": password}
    ak = (os.environ.get("PORTAL_ADMIN_KEY") or "").strip()
    if ak:
        reg_body["admin_key"] = ak

    r = client.post("/register", json=reg_body)
    if r.status_code != 201:
        print("REGISTER", r.status_code, r.text)
        return 1
    reg = r.json()
    tid = reg.get("tenant_id")
    kid = reg.get("kanzlei_id")
    if tid != kid or not kid:
        print("REGISTER: tenant_id/kanzlei_id fehlen oder weichen ab:", reg)
        return 1

    r = client.post("/login", json={"email": email, "password": password})
    if r.status_code != 200:
        print("LOGIN", r.status_code, r.text)
        return 1

    body = r.json()
    token = body.get("access_token") or body.get("token")
    if not token:
        print("LOGIN: kein Token in Antwort", body)
        return 1
    if body.get("tenant_id") != body.get("kanzlei_id") or not body.get("kanzlei_id"):
        print("LOGIN: tenant_id/kanzlei_id in Login-Antwort inkonsistent:", body)
        return 1

    r = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    if r.status_code != 200:
        print("ME", r.status_code, r.text)
        return 1

    me = r.json()
    if me.get("email", "").lower() != email.lower():
        print("ME email mismatch", me)
        return 1
    if me.get("id") is None:
        print("ME ohne id", me)
        return 1
    if me.get("tenant_id") != me.get("kanzlei_id") or not me.get("kanzlei_id"):
        print("ME: tenant_id/kanzlei_id fehlen oder weichen ab:", me)
        return 1

    if (os.environ.get("FORCE_JWT_TEST") or "").strip().lower() in ("1", "true", "yes"):
        try:
            import jose  # noqa: F401
        except ImportError:
            print("FORCE_JWT_TEST: python-jose nicht installiert — JWT-Decode übersprungen")
        else:
            from backend.auth import verify_access_token

            cl = verify_access_token(token)
            if not cl:
                print("FORCE_JWT_TEST: Token nicht als JWT verifizierbar")
                return 1
            if cl.get("tenant_id") != cl.get("kanzlei_id"):
                print("FORCE_JWT_TEST: JWT-Claims Mandant inkonsistent:", cl)
                return 1

    print("OK — id=%s email=%s tenant=%s" % (me.get("id"), me.get("email"), me.get("tenant_id")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

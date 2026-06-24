#!/usr/bin/env python3
"""
Production Go-Live Gate — Mandanten, Einladungen, optionales ORM (ohne HTTP).

**Checkliste (ins Deploy-Runbook übernehmen)**

1. ``JWT_SECRET`` / ``PORTAL_SECRET`` / ``INVITE_TOKEN_SECRET`` mindestens 32 Zeichen (Team-Einladungen).
2. ``PORTAL_BASE_URL`` = öffentliche Basis-URL der SPA (Registrierungslinks in E-Mails).
3. ``EMAIL_*`` gesetzt, wenn Einladungen per Outbox/SMTP versendet werden sollen.
4. Production: ``DATABASE_URL`` = ``postgresql://…``; nach frischem Schema ggf.
   ``python scripts/init_postgres_sqlalchemy.py`` (legt u. a. ``users`` an).
5. HTTP/Monitoring: ``python scripts/go_live_check.py`` (``/health``, Readiness, …).
6. Auth/RBAC: ``python scripts/go_live_rbac_gate.py``.
7. Tenant-Invites: ``python scripts/test_api_users_invites.py`` (SKIP ohne Secret mit mind. 32 Zeichen).

Usage::

  python scripts/production_go_live_gate.py
  python scripts/production_go_live_gate.py --strict
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _fail(errors: List[str], msg: str) -> None:
    errors.append(msg)
    print(f"FAIL: {msg}")


def _warn(msg: str) -> None:
    print(f"WARN: {msg}")


def _ok(msg: str) -> None:
    print(f"PASS: {msg}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Production Go-Live Gate (Env + Imports + DB-Hinweise)")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Bei Production: PORTAL_BASE_URL und Invite-Secret (mind. 32 Zeichen) sind Pflicht",
    )
    args = parser.parse_args()
    errors: List[str] = []

    env = (os.getenv("ENVIRONMENT") or os.getenv("APP_ENV") or "development").strip().lower()
    is_prod = env == "production"

    invite_secret = (
        (os.getenv("INVITE_TOKEN_SECRET") or os.getenv("JWT_SECRET") or os.getenv("PORTAL_SECRET") or "").strip()
    )
    if len(invite_secret) < 32:
        msg = "Einladungen: kein Secret mit mind. 32 Zeichen (INVITE_TOKEN_SECRET oder JWT_SECRET/PORTAL_SECRET)"
        if is_prod or args.strict:
            _fail(errors, msg)
        else:
            _warn(msg)
    else:
        _ok("Invite-/JWT-Secret Laenge fuer Einladungen (mind. 32 Zeichen)")

    portal = (os.getenv("PORTAL_BASE_URL") or os.getenv("PUBLIC_APP_URL") or "").strip()
    if is_prod or args.strict:
        if not portal.lower().startswith("http"):
            _fail(errors, "PORTAL_BASE_URL (oder PUBLIC_APP_URL) muss mit http/https beginnen")
        else:
            _ok("PORTAL_BASE_URL gesetzt")
    elif portal:
        _ok("PORTAL_BASE_URL optional gesetzt")
    else:
        _warn("PORTAL_BASE_URL leer - Einladungs-E-Mails nutzen Fallback-URL")

    eu, ep = (os.getenv("EMAIL_USER") or "").strip(), (os.getenv("EMAIL_PASS") or "").strip()
    if not eu or not ep:
        _warn("EMAIL_USER/EMAIL_PASS fehlen - SMTP-Einladungen gehen nicht")
    else:
        _ok("EMAIL_USER/EMAIL_PASS gesetzt")

    try:
        from backend.models import UserRead  # noqa: F401

        _ok("Import backend.models (Pydantic, ohne harte SQLAlchemy-Kette)")
    except Exception as exc:  # noqa: BLE001
        _fail(errors, f"Import backend.models: {exc}")

    try:
        from backend.db.sqlalchemy_models import User
        from sqlalchemy import String

        col = User.__table__.c.tenant_id
        if not isinstance(col.type, String):
            _fail(errors, "ORM User.tenant_id muss String (Mandanten-ID) sein")
        else:
            ln = getattr(col.type, "length", None) or 0
            if int(ln) < 32:
                _warn(f"ORM tenant_id VARCHAR({ln}) -- fuer UUIDs ueblich mind. 36")
            _ok("Import backend.db.sqlalchemy_models.User + tenant_id ist String")
    except Exception as exc:  # noqa: BLE001
        _fail(errors, f"Import ORM User: {exc}")

    du = (os.getenv("DATABASE_URL") or "").strip()
    if du.lower().startswith("postgresql://"):
        try:
            from sqlalchemy import create_engine, inspect

            eng = create_engine(du, pool_pre_ping=True)
            with eng.connect() as conn:
                insp = inspect(conn)
                if not insp.has_table("users"):
                    _warn(
                        "PostgreSQL: Tabelle users fehlt - optional: python scripts/init_postgres_sqlalchemy.py"
                    )
                else:
                    _ok("PostgreSQL: Tabelle users vorhanden")
        except Exception as exc:  # noqa: BLE001
            _warn(f"PostgreSQL-Inspect uebersprungen/fehlgeschlagen: {exc}")
    elif is_prod:
        _fail(errors, "Production erwartet DATABASE_URL=postgresql://...")
    else:
        _ok("DATABASE_URL nicht Postgres - fuer Dev ok")

    print("")
    print("Naechste Schritte (manuell):")
    print("  python scripts/go_live_check.py")
    print("  python scripts/go_live_rbac_gate.py")
    print("  python scripts/test_api_users_invites.py")

    if errors:
        print("")
        print(f"Abbruch mit {len(errors)} Fehler(n).")
        return 1
    print("")
    print("production_go_live_gate: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

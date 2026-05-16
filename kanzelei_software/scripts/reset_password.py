#!/usr/bin/env python3
"""Passwort per E-Mail zurücksetzen (PostgreSQL-Produktion)."""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main() -> int:
    p = argparse.ArgumentParser(description="Benutzer-Passwort per E-Mail setzen")
    p.add_argument("--email", required=True, help="E-Mail des Benutzers")
    p.add_argument("--password", required=True, help="Neues Passwort")
    p.add_argument("--kanzlei-id", default="default")
    args = p.parse_args()

    email = args.email.strip().lower()
    if "@" not in email:
        print("Ungültige E-Mail")
        return 2

    from core.auth import _hash_passwort, _interner_benutzername_fuer_email
    from core.auth_postgres import auth_pg_enabled, pg_aendere_passwort, pg_login_fetch_by_email

    if not auth_pg_enabled():
        print("PostgreSQL-Auth ist nicht aktiv (DATABASE_URL prüfen)")
        return 1

    internal = _interner_benutzername_fuer_email(email)
    row = pg_login_fetch_by_email(email, internal)
    if not row:
        print(f"Kein Benutzer für {email}")
        return 1

    kid = str(row.get("kanzlei_id") or args.kanzlei_id).strip() or "default"
    bname = str(row["benutzername"])
    h, s = _hash_passwort(args.password)
    pg_aendere_passwort(bname, kid, h, s)
    print(f"Passwort gesetzt: {bname} ({email}) kanzlei={kid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

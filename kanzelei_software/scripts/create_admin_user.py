#!/usr/bin/env python3
"""
Einmalig Admin-Benutzer anlegen (idempotent nach benutzername).

Usage:
  python scripts/create_admin_user.py --email admin@kanzlei.de --password "SehrSicher123!"
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.auth import erstelle_benutzer  # noqa: E402


def _name_from_email(email: str) -> str:
    return "u" + hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:24]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--kanzlei-id", default="default")
    args = p.parse_args()

    email = args.email.strip().lower()
    if "@" not in email:
        print("invalid email")
        return 2
    if len(args.password) < 8:
        print("password too short (min 8)")
        return 2

    bname = _name_from_email(email)
    try:
        u = erstelle_benutzer(
            benutzername=bname,
            passwort=args.password,
            rolle="admin",
            email=email,
            kanzlei_id=args.kanzlei_id,
        )
        print(f"created admin: {u.get('benutzername')} ({u.get('email')})")
        return 0
    except ValueError as e:
        if "existiert bereits" in str(e):
            print(f"already exists: {bname}")
            return 0
        print(f"error: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


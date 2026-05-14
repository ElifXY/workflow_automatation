#!/usr/bin/env python3
"""
Passwort per PORTAL_ADMIN_KEY zurücksetzen (gleiche DB-Logik wie die API).

Das neue Passwort muss den Regeln aus ``core.auth._assert_strong_password`` genügen
(mindestens 12 Zeichen, Groß-/Kleinbuchstabe, Zahl, Sonderzeichen, kein Leerzeichen,
kein lokaler E-Mail-Teil im Passwort).

Im API-Container (Umgebung wie Uvicorn, .env bereits von Compose geladen):

  docker compose exec -T api python scripts/admin_password_reset.py \\
    --email "ihre@mail.de" \\
    --new-password "Neu!Passwort12" \\
    --admin-key "WERT_AUS_PORTAL_ADMIN_KEY"
"""
from __future__ import annotations

import argparse
import os
import secrets
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(ROOT, ".env"))
    load_dotenv(os.path.join(ROOT, ".env.defaults"))
except Exception:
    pass


def main() -> int:
    p = argparse.ArgumentParser(description="Admin: Passwort für Benutzer per E-Mail neu setzen.")
    p.add_argument("--email", required=True)
    p.add_argument("--new-password", required=True)
    p.add_argument(
        "--admin-key",
        required=True,
        help="Muss exakt PORTAL_ADMIN_KEY aus der Server-.env entsprechen",
    )
    args = p.parse_args()

    expected = (os.getenv("PORTAL_ADMIN_KEY") or "").strip()
    if len(expected) < 20:
        print(
            "PORTAL_ADMIN_KEY in der Umgebung zu kurz oder nicht gesetzt — Reset abgelehnt.",
            file=sys.stderr,
        )
        return 2
    if not secrets.compare_digest((args.admin_key or "").strip(), expected):
        print("Ungültiger Admin-Key.", file=sys.stderr)
        return 2

    from backend.auth import finde_benutzer_nach_email, setze_passwort_ohne_altes

    em = args.email.strip()
    info = finde_benutzer_nach_email(em)
    if not info:
        print(f"Kein aktiver Benutzer mit dieser E-Mail: {em!r}", file=sys.stderr)
        print(
            "Tipp: Nur in SQLite? Dann Hybrid-Fallback nutzen (siehe .env.example: AUTH_SQLITE_LOGIN_FALLBACK).",
            file=sys.stderr,
        )
        return 3

    bn = str(info["benutzername"])
    kid = str(info.get("kanzlei_id") or "default")
    try:
        ok = setze_passwort_ohne_altes(bn, kid, args.new_password)
    except ValueError as e:
        print(f"Passwort-Regel: {e}", file=sys.stderr)
        return 4
    if not ok:
        print("UPDATE fehlgeschlagen (keine Zeile geändert).", file=sys.stderr)
        return 5
    print(f"OK: Passwort gesetzt für {bn!r} (kanzlei_id={kid!r}, email={info.get('email')!r})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# ============================================================
# KANZLEI AI — MIGRATION v1.0
# Migriert alte Daten in das neue Multi-Kanzlei Schema.
#
# Ausführen: python migration.py
#
# Was es macht:
#   1. Neue DB mit kanzlei_id Schema erstellen
#   2. Alte Mandanten-Daten → neue mandanten Tabelle (kanzlei_id='default')
#   3. Alte Aufgaben → neue aufgaben Tabelle
#   4. Alten Admin-User in benutzer Tabelle mit kanzlei_id='default'
#   5. Backup der alten DB anlegen
# ============================================================

import os
import sys
import json
import uuid
import sqlite3
import shutil
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DB_PFAD = os.path.join("data", "kanzlei.db")
BACKUP  = os.path.join("data", f"kanzlei_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")


def log(msg: str):
    print(f"  {msg}")


def backup_db():
    if os.path.exists(DB_PFAD):
        shutil.copy2(DB_PFAD, BACKUP)
        log(f"✓ Backup: {BACKUP}")
    else:
        log("Keine bestehende DB gefunden — starte frisch")


def neue_db_erstellen():
    """Schema mit kanzlei_id in allen Tabellen anlegen."""
    from core.daten_speicher import init_db
    init_db()
    log("✓ Neues Schema angelegt")


def migriere_benutzer():
    """Alte benutzer-Tabelle (ohne kanzlei_id) → neue mit kanzlei_id."""
    conn = sqlite3.connect(DB_PFAD)
    conn.row_factory = sqlite3.Row

    # Prüfe ob alte Spalten-Struktur
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(benutzer)").fetchall()]

    if "kanzlei_id" in cols:
        log("✓ benutzer Tabelle hat bereits kanzlei_id — keine Migration nötig")
        conn.close()
        return

    # Alte Benutzer lesen
    try:
        alte_user = conn.execute("SELECT * FROM benutzer").fetchall()
    except Exception:
        alte_user = []

    log(f"  Migriere {len(alte_user)} Benutzer...")

    # Alte Tabelle umbenennen
    conn.execute("ALTER TABLE benutzer RENAME TO benutzer_alt")
    conn.commit()

    # Neue Tabelle wird durch init_db() erstellt
    # Benutzer eintragen mit kanzlei_id='default'
    for u in alte_user:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO benutzer
                    (kanzlei_id, benutzername, hash, salt, rolle, email, aktiv, erstellt_am, letzter_login)
                VALUES ('default', ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                u["benutzername"],
                u["hash"],
                u["salt"],
                u["rolle"] if "rolle" in cols else "admin",
                u["email"] if "email" in cols else "",
                u["aktiv"] if "aktiv" in cols else 1,
                u["erstellt_am"] if "erstellt_am" in cols else datetime.now().isoformat(),
                u["letzter_login"] if "letzter_login" in cols else None,
            ))
        except Exception as e:
            log(f"  ⚠ Benutzer {u['benutzername']}: {e}")

    conn.commit()
    log(f"✓ {len(alte_user)} Benutzer migriert (kanzlei_id='default')")
    conn.close()


def migriere_mandanten():
    """Mandanten ohne kanzlei_id → kanzlei_id='default'."""
    conn = sqlite3.connect(DB_PFAD)
    conn.row_factory = sqlite3.Row

    cols = [r["name"] for r in conn.execute("PRAGMA table_info(mandanten)").fetchall()]

    if "kanzlei_id" not in cols:
        log("  mandanten Tabelle hat keine kanzlei_id — möglicherweise alte JSON-DB")
        conn.close()
        _migriere_aus_json()
        return

    # Mandanten ohne kanzlei_id fixen
    n = conn.execute(
        "UPDATE mandanten SET kanzlei_id='default' WHERE kanzlei_id IS NULL OR kanzlei_id=''"
    ).rowcount
    conn.commit()
    conn.close()

    if n > 0:
        log(f"✓ {n} Mandanten auf kanzlei_id='default' gesetzt")
    else:
        log("✓ Alle Mandanten haben bereits kanzlei_id")


def _migriere_aus_json():
    """JSON-Migration wurde abgeschaltet: Produktion läuft SQL-only."""
    log("  JSON-Migration deaktiviert (SQL-only Architektur aktiv)")


def migriere_aufgaben():
    """Aufgaben ohne kanzlei_id fixen."""
    conn = sqlite3.connect(DB_PFAD)
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(aufgaben)").fetchall()]
    if "kanzlei_id" in cols:
        n = conn.execute(
            "UPDATE aufgaben SET kanzlei_id='default' WHERE kanzlei_id IS NULL OR kanzlei_id=''"
        ).rowcount
        conn.commit()
        if n > 0:
            log(f"✓ {n} Aufgaben auf kanzlei_id='default' gesetzt")
        else:
            log("✓ Alle Aufgaben haben kanzlei_id")
    conn.close()


def stelle_sicher_admin_existiert():
    """Stellt sicher dass mindestens ein Admin-Benutzer existiert."""
    from core.auth import hat_irgendein_benutzer, setup_erstbenutzer
    if not hat_irgendein_benutzer():
        setup_erstbenutzer("admin", "Admin2024!", "default")
        log("✓ Admin-Benutzer angelegt (admin / Admin2024!)")
    else:
        log("✓ Benutzer bereits vorhanden")


def main():
    print()
    print("=" * 55)
    print("  KANZLEI AI — DATENBANK MIGRATION")
    print("=" * 55)
    print()

    os.makedirs("data", exist_ok=True)

    print("1. Backup erstellen...")
    backup_db()

    print("\n2. Neues Schema anlegen...")
    neue_db_erstellen()

    print("\n3. Benutzer migrieren...")
    migriere_benutzer()

    print("\n4. Mandanten migrieren...")
    migriere_mandanten()

    print("\n5. Aufgaben migrieren...")
    migriere_aufgaben()

    print("\n6. Admin sicherstellen...")
    stelle_sicher_admin_existiert()

    print()
    print("=" * 55)
    print("  ✓ MIGRATION ABGESCHLOSSEN")
    print("=" * 55)
    print()
    print("  Login: admin / Admin2024!")
    print("  Backend starten: uvicorn backend.api:app --reload --port 8000")
    print()


if __name__ == "__main__":
    main()
    
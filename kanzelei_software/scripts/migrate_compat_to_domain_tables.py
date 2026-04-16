#!/usr/bin/env python3
"""
Migrate compat::* JSON blobs from `einstellungen` into v2 domain tables.

Usage:
  python scripts/migrate_compat_to_domain_tables.py          # dry-run
  python scripts/migrate_compat_to_domain_tables.py --apply  # write changes
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, Any


DB_PATH = Path("data") / "kanzlei.db"
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_compat(conn: sqlite3.Connection, kanzlei_id: str, section: str, default: Any):
    row = conn.execute(
        "SELECT value FROM einstellungen WHERE kanzlei_id = ? AND key = ?",
        (kanzlei_id, f"compat::{section}"),
    ).fetchone()
    if not row:
        return default
    try:
        return json.loads(row["value"])
    except Exception:
        return default


def migrate_tenant(conn: sqlite3.Connection, kanzlei_id: str, apply: bool) -> Dict[str, int]:
    stats = {
        "workflow_rules_v2": 0,
        "bot_questions_v2": 0,
        "time_entries_v2": 0,
        "time_running_v2": 0,
        "steuerfaelle_v2": 0,
        "finanzierungen_v2": 0,
        "payroll_employees_v2": 0,
        "payroll_time_v2": 0,
        "payroll_runs_v2": 0,
    }

    workflow_regeln = _load_compat(conn, kanzlei_id, "workflow_regeln", {})
    bot_fragen = _load_compat(conn, kanzlei_id, "bot_fragen", {})
    zeiterfassung = _load_compat(conn, kanzlei_id, "zeiterfassung", {"eintraege": {}, "laufend": {}})
    steuerfaelle = _load_compat(conn, kanzlei_id, "steuerfaelle", {})
    finanzierungen = _load_compat(conn, kanzlei_id, "finanzierungen", {})
    lohnabrechnung = _load_compat(
        conn,
        kanzlei_id,
        "lohnabrechnung",
        {"mitarbeiter": {}, "zeitdaten": {}, "abrechnungen": {}},
    )

    for rid, regel in (workflow_regeln or {}).items():
        stats["workflow_rules_v2"] += 1
        if apply:
            conn.execute(
                """
                INSERT OR REPLACE INTO workflow_rules_v2
                (id, kanzlei_id, name, aktiv, trigger_type, created_at, updated_at, data_json)
                VALUES (?, ?, ?, ?, ?, COALESCE(?, datetime('now')), datetime('now'), ?)
                """,
                (
                    rid,
                    kanzlei_id,
                    regel.get("name", ""),
                    1 if regel.get("aktiv", True) else 0,
                    (regel.get("trigger") or {}).get("typ", ""),
                    regel.get("erstellt_am"),
                    json.dumps(regel, ensure_ascii=False),
                ),
            )

    for qid, frage in (bot_fragen or {}).items():
        stats["bot_questions_v2"] += 1
        if apply:
            conn.execute(
                """
                INSERT OR REPLACE INTO bot_questions_v2
                (id, kanzlei_id, mandant, status, frage_typ, erstellt_am, ablaeuft_am, data_json)
                VALUES (?, ?, ?, ?, ?, COALESCE(?, datetime('now')), ?, ?)
                """,
                (
                    qid,
                    kanzlei_id,
                    frage.get("mandant", ""),
                    frage.get("status", "offen"),
                    frage.get("typ", "sonstiges"),
                    frage.get("erstellt_am"),
                    frage.get("ablaeuft_am", ""),
                    json.dumps(frage, ensure_ascii=False),
                ),
            )

    eintraege = (zeiterfassung or {}).get("eintraege", {})
    laufend = (zeiterfassung or {}).get("laufend", {})
    for zid, eintrag in (eintraege or {}).items():
        stats["time_entries_v2"] += 1
        if apply:
            conn.execute(
                """
                INSERT OR REPLACE INTO time_entries_v2
                (id, kanzlei_id, mitarbeiter, mandant, start_at, end_at, status, data_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    zid,
                    kanzlei_id,
                    eintrag.get("mitarbeiter", ""),
                    eintrag.get("mandant", ""),
                    eintrag.get("start", ""),
                    eintrag.get("ende", ""),
                    "running" if not eintrag.get("ende") else "closed",
                    json.dumps(eintrag, ensure_ascii=False),
                ),
            )
    for ma, zeit_id in (laufend or {}).items():
        stats["time_running_v2"] += 1
        if apply:
            conn.execute(
                """
                INSERT OR REPLACE INTO time_running_v2
                (kanzlei_id, mitarbeiter, zeit_id, started_at)
                VALUES (?, ?, ?, datetime('now'))
                """,
                (kanzlei_id, ma, zeit_id),
            )

    for fid, fall in (steuerfaelle or {}).items():
        stats["steuerfaelle_v2"] += 1
        if apply:
            conn.execute(
                """
                INSERT OR REPLACE INTO steuerfaelle_v2
                (id, kanzlei_id, mandant, jahr, steuerart, status, konfidenz_score, erstellt_am, data_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now')), ?)
                """,
                (
                    fid,
                    kanzlei_id,
                    fall.get("mandant", ""),
                    int(fall.get("jahr", 0) or 0),
                    fall.get("steuerart", ""),
                    fall.get("status", ""),
                    float(fall.get("konfidenz_score", 0) or 0),
                    fall.get("erstellt_am"),
                    json.dumps(fall, ensure_ascii=False),
                ),
            )

    for aid, angebot in (finanzierungen or {}).items():
        stats["finanzierungen_v2"] += 1
        if apply:
            conn.execute(
                """
                INSERT OR REPLACE INTO finanzierungen_v2
                (id, kanzlei_id, mandant, status, steuerart, betrag, erstellt_am, data_json)
                VALUES (?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now')), ?)
                """,
                (
                    aid,
                    kanzlei_id,
                    angebot.get("mandant", ""),
                    angebot.get("status", "offen"),
                    angebot.get("steuerart", ""),
                    float(angebot.get("betrag", 0) or 0),
                    angebot.get("erstellt_am"),
                    json.dumps(angebot, ensure_ascii=False),
                ),
            )

    mitarbeiter = (lohnabrechnung or {}).get("mitarbeiter", {})
    zeitdaten = (lohnabrechnung or {}).get("zeitdaten", {})
    abrechnungen = (lohnabrechnung or {}).get("abrechnungen", {})

    for mid, ma in (mitarbeiter or {}).items():
        stats["payroll_employees_v2"] += 1
        if apply:
            conn.execute(
                """
                INSERT OR REPLACE INTO payroll_employees_v2
                (id, kanzlei_id, mandant, name, aktiv, eintritt, erstellt_am, data_json)
                VALUES (?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now')), ?)
                """,
                (
                    mid,
                    kanzlei_id,
                    ma.get("mandant", ""),
                    ma.get("name", ""),
                    1 if ma.get("aktiv", True) else 0,
                    ma.get("eintritt", ""),
                    ma.get("erstellt_am"),
                    json.dumps(ma, ensure_ascii=False),
                ),
            )

    for tid, td in (zeitdaten or {}).items():
        stats["payroll_time_v2"] += 1
        if apply:
            conn.execute(
                """
                INSERT OR REPLACE INTO payroll_time_v2
                (id, kanzlei_id, ma_id, monat, importiert_am, data_json)
                VALUES (?, ?, ?, ?, COALESCE(?, datetime('now')), ?)
                """,
                (
                    tid,
                    kanzlei_id,
                    td.get("ma_id", ""),
                    td.get("monat", ""),
                    td.get("importiert_am"),
                    json.dumps(td, ensure_ascii=False),
                ),
            )

    for rid, run in (abrechnungen or {}).items():
        stats["payroll_runs_v2"] += 1
        if apply:
            conn.execute(
                """
                INSERT OR REPLACE INTO payroll_runs_v2
                (id, kanzlei_id, ma_id, mandant, monat, status, berechnet_am, data_json)
                VALUES (?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now')), ?)
                """,
                (
                    rid,
                    kanzlei_id,
                    run.get("ma_id", ""),
                    run.get("mandant", ""),
                    run.get("monat", ""),
                    run.get("status", "berechnet"),
                    run.get("berechnet_am"),
                    json.dumps(run, ensure_ascii=False),
                ),
            )

    return stats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Persist migration writes")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}")
        return 1

    try:
        from core.daten_speicher import init_db
        init_db()
    except Exception as exc:
        print(f"Warning: init_db could not run ({exc})")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    kanzleien = [r["id"] for r in conn.execute("SELECT id FROM kanzleien").fetchall()]
    if not kanzleien:
        kanzleien = ["default"]

    print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN'}")
    grand = {}
    for kid in kanzleien:
        stats = migrate_tenant(conn, kid, args.apply)
        print(f"[{kid}] " + ", ".join(f"{k}={v}" for k, v in stats.items()))
        for k, v in stats.items():
            grand[k] = grand.get(k, 0) + v

    if args.apply:
        conn.commit()
    conn.close()

    print("TOTAL: " + ", ".join(f"{k}={v}" for k, v in grand.items()))
    if not args.apply:
        print("Dry-run only. Re-run with --apply to persist.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# ============================================================
# KANZLEI AI — SCHEDULER v1.0
# Datei: scheduler.py
#
# Läuft als eigener Prozess (Docker-Service "scheduler")
# Führt täglich aus:
#   06:00 — Workflow-Batch (alle aktiven Regeln)
#   07:00 — Bot-Analyse (proaktive Fragen für alle Mandanten)
#   07:30 — Mahnwesen-Check (überfällige Rechnungen)
#   08:00 — Bank-Import (wenn aktiv)
#   02:00 — Backup
#   01:00  — Monatliche Lohnabrechnung (am 1. jeden Monats)
# ============================================================

import time
import logging
import os
import sys
from datetime import datetime

log = logging.getLogger("kanzlei_scheduler")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SCHEDULER] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join("data", "scheduler.log"), encoding="utf-8"),
    ]
)

# Sicherstellen dass alle Module erreichbar sind
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.daten_speicher import DatenSpeicher
ds = DatenSpeicher()

BOT_UHRZEIT       = os.getenv("BOT_ANALYSE_UHRZEIT",  "07:00")
WORKFLOW_UHRZEIT  = os.getenv("WORKFLOW_BATCH_UHRZEIT","06:00")
BACKUP_UHRZEIT    = os.getenv("BACKUP_UHRZEIT",        "02:00")
LOHN_TAG          = 1   # Am 1. jeden Monats
CHECK_INTERVAL    = 60  # Sekunden zwischen Checks

# Tracking: welche Jobs heute bereits liefen
_heute_gelaufen: set = set()


def uhrzeit_erreicht(uhrzeit_str: str) -> bool:
    """Gibt True zurück wenn aktuelle Uhrzeit >= Zielzeit."""
    jetzt = datetime.now().strftime("%H:%M")
    return jetzt >= uhrzeit_str


def job_id(name: str) -> str:
    """Eindeutige Job-ID pro Tag."""
    return f"{datetime.now().strftime('%Y-%m-%d')}_{name}"


def run_workflow_batch():
    """Alle aktiven Workflow-Regeln ausführen."""
    jid = job_id("workflow")
    if jid in _heute_gelaufen:
        return
    try:
        from core.workflow_builder import WorkflowBaukasten
        from core.proaktiver_bot   import ProaktiverBot
        bot     = ProaktiverBot(ds)
        builder = WorkflowBaukasten(ds, bot=bot)
        result  = builder.fuehre_alle_aus()
        log.info(f"Workflow-Batch: {result['regeln_geprueft']} Regeln, "
                 f"{result['aktionen']} Aktionen")
        _heute_gelaufen.add(jid)
        ds.log_eintrag(
            f"SCHEDULER_WORKFLOW | {result['regeln_geprueft']} Regeln | "
            f"{result['aktionen']} Aktionen"
        )
    except Exception as e:
        log.error(f"Workflow-Batch Fehler: {e}")


def run_bot_analyse():
    """Proaktive Bot-Analyse aller Mandanten."""
    jid = job_id("bot")
    if jid in _heute_gelaufen:
        return
    try:
        from core.proaktiver_bot import ProaktiverBot
        bot    = ProaktiverBot(ds)
        fragen = bot.analysiere_alle_mandanten()
        log.info(f"Bot-Analyse: {len(fragen)} neue Fragen erstellt")
        _heute_gelaufen.add(jid)
        ds.log_eintrag(f"SCHEDULER_BOT | {len(fragen)} neue Fragen")
    except Exception as e:
        log.error(f"Bot-Analyse Fehler: {e}")


def run_mahnwesen():
    """Überfällige Rechnungen prüfen und Aufgaben anlegen."""
    jid = job_id("mahnwesen")
    if jid in _heute_gelaufen:
        return
    try:
        from core.rechnungs_service import pruefe_offene_rechnungen
        mahnungen = pruefe_offene_rechnungen(ds)
        for m in mahnungen:
            if m["tage_ueberfaellig"] >= 14:
                # Aufgabe anlegen
                import uuid
                from datetime import timedelta
                aufgabe_id = str(uuid.uuid4())
                frist = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
                ds.aufgabe_speichern(aufgabe_id, {
                    "id":           aufgabe_id,
                    "mandant":      m["mandant"],
                    "beschreibung": f"Mahnung senden: {m['rechnungsnummer']} ({m['tage_ueberfaellig']}d überfällig)",
                    "frist":        frist,
                    "prioritaet":   "hoch" if m["tage_ueberfaellig"] < 30 else "kritisch",
                    "kategorie":    "Mahnwesen",
                    "erledigt":     False,
                    "erstellt_am":  datetime.now().isoformat(),
                    "quelle":       "scheduler_mahnwesen",
                })
        log.info(f"Mahnwesen: {len(mahnungen)} überfällige Rechnungen geprüft")
        _heute_gelaufen.add(jid)
        ds.log_eintrag(f"SCHEDULER_MAHNWESEN | {len(mahnungen)} überfällig")
    except Exception as e:
        log.error(f"Mahnwesen Fehler: {e}")


def run_lohnabrechnung():
    """Monatliche Lohnabrechnung am 1. des Monats."""
    heute = datetime.now()
    if heute.day != LOHN_TAG:
        return
    jid = job_id("lohn")
    if jid in _heute_gelaufen:
        return
    try:
        from core.lohn_service import LohnService
        ls     = LohnService(ds)
        monat  = heute.strftime("%Y-%m")
        mandanten = ds.hole_mandanten()
        gesamt = 0
        for name in mandanten:
            abrechnungen = ls.batch_abrechnung(name, monat)
            gesamt += len(abrechnungen)
        log.info(f"Lohnabrechnung {monat}: {gesamt} Abrechnungen erstellt")
        _heute_gelaufen.add(jid)
        ds.log_eintrag(f"SCHEDULER_LOHN | {monat} | {gesamt} Abrechnungen")
    except Exception as e:
        log.error(f"Lohnabrechnung Fehler: {e}")


def run_backup():
    """Legacy-File-Backups deaktiviert: Single Source of Truth = PostgreSQL."""
    jid = job_id("backup")
    if jid in _heute_gelaufen:
        return
    log.info("Backup-Job übersprungen (Datei-Backups deaktiviert, PostgreSQL-Backup extern ausführen).")
    _heute_gelaufen.add(jid)


def reset_tagesflags():
    """Mitternacht: Reset der Tages-Flags."""
    jetzt = datetime.now()
    if jetzt.hour == 0 and jetzt.minute < 2:
        gestern = (jetzt.replace(hour=0, minute=0) - __import__("datetime").timedelta(days=1))
        gestern_str = gestern.strftime("%Y-%m-%d")
        for key in list(_heute_gelaufen):
            if key.startswith(gestern_str):
                _heute_gelaufen.discard(key)


def main():
    log.info("=" * 60)
    log.info("KANZLEI AI SCHEDULER — gestartet")
    log.info(f"  Workflow:    {WORKFLOW_UHRZEIT}")
    log.info(f"  Bot-Analyse: {BOT_UHRZEIT}")
    log.info(f"  Backup:      {BACKUP_UHRZEIT}")
    log.info(f"  Lohn:        am {LOHN_TAG}. jeden Monats")
    log.info("=" * 60)

    while True:
        try:
            reset_tagesflags()

            # Workflow-Batch
            if uhrzeit_erreicht(WORKFLOW_UHRZEIT):
                run_workflow_batch()

            # Bot-Analyse (30 Min nach Workflow)
            bot_hhmm = WORKFLOW_UHRZEIT[:2] + ":" + str(
                (int(WORKFLOW_UHRZEIT[3:]) + 30) % 60
            ).zfill(2)
            if uhrzeit_erreicht(BOT_UHRZEIT):
                run_bot_analyse()

            # Mahnwesen (07:30)
            if uhrzeit_erreicht("07:30"):
                run_mahnwesen()

            # Lohnabrechnung (08:00)
            if uhrzeit_erreicht("08:00"):
                run_lohnabrechnung()

            # Backup (Nachts)
            if uhrzeit_erreicht(BACKUP_UHRZEIT):
                run_backup()

        except KeyboardInterrupt:
            log.info("Scheduler wird beendet...")
            break
        except Exception as e:
            log.error(f"Scheduler-Fehler: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
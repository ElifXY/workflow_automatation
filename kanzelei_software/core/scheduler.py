#!/usr/bin/env python3
# ============================================================
# KANZLEI AI — SCHEDULER v1.0
# Datei: core/scheduler.py — Docker: python backend/scheduler.py (Wrapper unter backend/).
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
import hashlib
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
from core.daten_speicher import email_outbox_enqueue
ds = DatenSpeicher()

BOT_UHRZEIT       = os.getenv("BOT_ANALYSE_UHRZEIT",  "07:00")
WORKFLOW_UHRZEIT  = os.getenv("WORKFLOW_BATCH_UHRZEIT","06:00")
BACKUP_UHRZEIT    = os.getenv("BACKUP_UHRZEIT",        "02:00")
LOHN_TAG          = 1   # Am 1. jeden Monats
CHECK_INTERVAL    = 60  # Sekunden zwischen Checks
REVENUE_OPS_UHRZEIT = os.getenv("REVENUE_OPS_UHRZEIT", "09:00")
REVENUE_OPS_MIN_VIEWS_7D = int(os.getenv("REVENUE_OPS_MIN_VIEWS_7D", "20") or "20")
REVENUE_OPS_MIN_VIEW_TO_PAID_PCT = float(os.getenv("REVENUE_OPS_MIN_VIEW_TO_PAID_PCT", "2.0") or "2.0")

# Tracking: welche Jobs heute bereits liefen
_heute_gelaufen: set = set()


def _setting(key: str, default):
    val = ds.setting_holen(key, default)
    return default if val is None else val


def uhrzeit_erreicht(uhrzeit_str: str) -> bool:
    """Gibt True zurück wenn aktuelle Uhrzeit >= Zielzeit."""
    jetzt = datetime.now().strftime("%H:%M")
    return jetzt >= uhrzeit_str


def job_id(name: str) -> str:
    """Eindeutige Job-ID pro Tag."""
    return f"{datetime.now().strftime('%Y-%m-%d')}_{name}"


def run_workflow_batch():
    """Alle aktiven Workflow-Regeln ausführen."""
    if not bool(_setting("auto_workflow_monatsabschluss", True)):
        return
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
        fragen, _pruefung = bot.analysiere_alle_mandanten()
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
    if not bool(_setting("auto_workflow_lohn", True)):
        return
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


def _billing_obs_get_for_kid(kanzlei_id: str) -> dict:
    try:
        st = DatenSpeicher(kanzlei_id=kanzlei_id)
        raw = st.setting_holen("__billing_observability_v1", {}) or {}
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _billing_funnel_7d_for_kid(kanzlei_id: str) -> dict:
    try:
        st = DatenSpeicher(kanzlei_id=kanzlei_id)
        raw = st.setting_holen("__billing_funnel_events_v1", []) or []
        events = raw if isinstance(raw, list) else []
    except Exception:
        events = []
    from datetime import timedelta
    threshold = datetime.utcnow() - timedelta(hours=168)
    views = 0
    paid = 0
    for ev in events:
        if not isinstance(ev, dict):
            continue
        try:
            ts = datetime.fromisoformat(str(ev.get("ts") or "").replace("Z", ""))
        except Exception:
            continue
        if ts < threshold:
            continue
        stg = str(ev.get("stage") or "").strip().lower()
        if stg == "cta_view":
            views += 1
        elif stg == "checkout_success":
            paid += 1
    return {"views": views, "paid": paid, "view_to_paid_percent": round(100 * paid / max(1, views), 2)}


def _digest_recipients_for_kid(kanzlei_id: str) -> list:
    try:
        from backend.auth import liste_benutzer
        from core.rbac import canonical_role
        rows = liste_benutzer(kanzlei_id) or []
    except Exception:
        rows = []
    out = []
    seen = set()
    for u in rows:
        role = canonical_role((u or {}).get("rolle") or (u or {}).get("role"))
        if role not in {"owner", "admin"}:
            continue
        mail = str((u or {}).get("email") or "").strip().lower()
        if not mail or mail in seen:
            continue
        out.append(mail)
        seen.add(mail)
    return out[:20]


def _enqueue_ops_alert(kanzlei_id: str, recipients: list, lines: list) -> int:
    sent = 0
    subject = f"Revenue Ops Alert ({datetime.utcnow().strftime('%Y-%m-%d')})"
    body = "\n".join(["Revenue Ops Monitor", ""] + lines)
    for email in recipients:
        idem_src = f"{kanzlei_id}|revenue-ops|{datetime.utcnow().strftime('%Y-%m-%d')}|{email}|{body[:160]}"
        idem = hashlib.sha256(idem_src.encode("utf-8")).hexdigest()
        enq = email_outbox_enqueue(
            kanzlei_id=kanzlei_id,
            mandant="revenue_ops",
            to_email=email,
            subject=subject,
            body_text=body,
            body_html="",
            idempotency_key=idem,
            max_attempts=5,
        )
        if enq and (enq.get("created") or enq.get("id")):
            sent += 1
    return sent


def run_revenue_ops_check():
    """Täglicher automatischer Revenue-Ops Check mit Alert-Mail an Owner/Admin."""
    jid = job_id("revenue_ops")
    if jid in _heute_gelaufen:
        return
    try:
        from backend.auth import liste_kanzleien
        tenants = liste_kanzleien() or []
    except Exception as e:
        log.error(f"Revenue-Ops: konnte Kanzleien nicht laden: {e}")
        return
    total_alerts = 0
    for t in tenants:
        kid = str((t or {}).get("id") or "").strip()
        if not kid:
            continue
        obs = _billing_obs_get_for_kid(kid)
        funnel = _billing_funnel_7d_for_kid(kid)
        alerts = []
        if int(obs.get("digest_skipped_no_recipients", 0) or 0) > 0:
            alerts.append("Digest wurde mindestens einmal ohne Empfänger übersprungen.")
        if int(obs.get("channel_shift_detected", 0) or 0) > 0:
            alerts.append("Kanal-Shift erkannt: Top-UTM hat gewechselt.")
        if (
            funnel.get("views", 0) >= REVENUE_OPS_MIN_VIEWS_7D
            and float(funnel.get("view_to_paid_percent", 0.0)) < REVENUE_OPS_MIN_VIEW_TO_PAID_PCT
        ):
            alerts.append(
                f"7d View->Paid nur {funnel.get('view_to_paid_percent', 0)}% bei {funnel.get('views', 0)} Views."
            )
        if not alerts:
            continue
        rec = _digest_recipients_for_kid(kid)
        if not rec:
            log.warning("Revenue-Ops Alert übersprungen (keine Owner/Admin Empfänger): %s", kid)
            continue
        sent = _enqueue_ops_alert(kid, rec, alerts)
        total_alerts += int(sent)
        log.warning("Revenue-Ops Alert: kanzlei=%s sent=%s issues=%s", kid, sent, len(alerts))
    _heute_gelaufen.add(jid)
    ds.log_eintrag(f"SCHEDULER_REVENUE_OPS | alert_emails={total_alerts}")


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
    workflow_time = str(_setting("workflow_batch_uhrzeit", WORKFLOW_UHRZEIT))[:5]
    bot_time = str(_setting("ki_bot_analyse_uhrzeit", BOT_UHRZEIT))[:5]
    log.info("=" * 60)
    log.info("KANZLEI AI SCHEDULER — gestartet")
    log.info(f"  Workflow:    {workflow_time}")
    log.info(f"  Bot-Analyse: {bot_time}")
    log.info(f"  Backup:      {BACKUP_UHRZEIT}")
    log.info(f"  Revenue-Ops: {REVENUE_OPS_UHRZEIT}")
    log.info(f"  Revenue-Ops Schwellen: min_views_7d={REVENUE_OPS_MIN_VIEWS_7D}, min_view_to_paid_pct={REVENUE_OPS_MIN_VIEW_TO_PAID_PCT}")
    log.info(f"  Lohn:        am {LOHN_TAG}. jeden Monats")
    log.info("=" * 60)

    while True:
        try:
            reset_tagesflags()

            # Workflow-Batch
            workflow_time = str(_setting("workflow_batch_uhrzeit", WORKFLOW_UHRZEIT))[:5]
            if uhrzeit_erreicht(workflow_time):
                run_workflow_batch()

            # Bot-Analyse (30 Min nach Workflow)
            bot_time = str(_setting("ki_bot_analyse_uhrzeit", BOT_UHRZEIT))[:5]
            if uhrzeit_erreicht(bot_time):
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

            # Revenue Ops Monitor (Daily)
            if uhrzeit_erreicht(REVENUE_OPS_UHRZEIT):
                run_revenue_ops_check()

        except KeyboardInterrupt:
            log.info("Scheduler wird beendet...")
            break
        except Exception as e:
            log.error(f"Scheduler-Fehler: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    log.warning(
        "Scheduler direkt aus core/scheduler.py gestartet — bevorzugt: python backend/scheduler.py"
    )
    main()
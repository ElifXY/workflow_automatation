# Monatlicher ROI-Bericht per E-Mail an die Kanzlei
from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Any, Dict, List

from core.dashboard_ops import roi_monatsbericht
from modules.settings_manager import load_settings_for_store

log = logging.getLogger("kanzlei_roi_email")


def _empfaenger(cfg: Dict[str, Any]) -> List[str]:
    raw = (
        (cfg.get("roi_email_empfaenger") or "")
        or (cfg.get("kanzlei_email") or "")
        or (cfg.get("eskalation_stufe_1_empfaenger") or "")
    )
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip() and "@" in str(x)]
    s = str(raw or "").strip()
    if not s or "@" not in s:
        return []
    return [e.strip() for e in s.replace(";", ",").split(",") if e.strip() and "@" in e]


def send_roi_monatsbericht_email(store) -> Dict[str, Any]:
    """ROI-Zusammenfassung in die Outbox stellen (idempotent pro Monat/Empfänger)."""
    cfg = load_settings_for_store(store)
    if not bool(cfg.get("auto_roi_email_aktiv", True)):
        return {"status": "deaktiviert", "gesendet": 0}

    emps = _empfaenger(cfg)
    if not emps:
        log.warning("ROI-Mail: kein Empfänger für kanzlei=%s", store.kanzlei_id)
        return {"status": "kein_empfaenger", "gesendet": 0}

    bericht = roi_monatsbericht(store)
    monat = bericht.get("monat") or datetime.now().strftime("%Y-%m")
    stunden = bericht.get("geschaetzte_stunden_gespart", 0)
    body = (
        f"Kanzlei Automation — ROI-Bericht {monat}\n\n"
        f"Erinnerungen: {bericht.get('erinnerungen', 0)}\n"
        f"Dokumente eingesammelt: {bericht.get('dokumente_eingesammelt', 0)}\n"
        f"Automationen ausgeführt: {bericht.get('automationen', 0)}\n"
        f"Geschätzte Stunden gespart: {stunden}\n\n"
        f"{bericht.get('text', '')}\n\n"
        f"Dashboard: Mandanten liefern rechtzeitig — ohne liegengebliebene Fälle."
    )
    subject = f"ROI-Bericht {monat} — ca. {stunden} Std. gespart"

    sent = 0
    try:
        from core.daten_speicher import email_outbox_enqueue
    except Exception as e:
        log.error("ROI-Mail outbox import: %s", e)
        return {"status": "fehler", "gesendet": 0, "detail": str(e)}

    kid = str(getattr(store, "kanzlei_id", None) or "default")
    for addr in emps:
        idem = hashlib.sha256(f"roi_monat|{kid}|{monat}|{addr}".encode()).hexdigest()
        try:
            enq = email_outbox_enqueue(
                kanzlei_id=kid,
                mandant="",
                to_email=addr,
                subject=subject[:200],
                body_text=body,
                body_html="",
                idempotency_key=idem,
            )
            if enq.get("created") or enq.get("status") in ("pending", "sending", "sent"):
                sent += 1
        except Exception as e:
            log.warning("ROI-Mail enqueue %s: %s", addr, e)

    if sent:
        store.log_eintrag(f"ROI_EMAIL | {monat} | {sent} Empfänger")
    return {"status": "ok", "gesendet": sent, "monat": monat, "empfaenger": len(emps)}

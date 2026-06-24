# Automatische Eskalation (Tag 3/7/14/21/30) — Scheduler
from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Any, Dict, List

from core.escalation_policy import aktuelle_eskalations_stufe
from modules.settings_manager import load_settings_for_store

log = logging.getLogger("kanzlei_escalation")


def _bool_cfg(cfg: Dict[str, Any], key: str, default: bool = True) -> bool:
    v = cfg.get(key)
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _empfaenger_fuer_stufe(cfg: Dict[str, Any], aktion: str) -> List[str]:
    if aktion == "eskalation_intern":
        raw = (
            cfg.get("eskalation_stufe_2_empfaenger")
            or cfg.get("eskalation_stufe_1_empfaenger")
            or cfg.get("kanzlei_email")
            or ""
        )
    else:
        raw = cfg.get("eskalation_stufe_1_empfaenger") or cfg.get("kanzlei_email") or ""
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip() and "@" in str(x)]
    s = str(raw or "").strip()
    if not s or "@" not in s:
        return []
    return [e.strip() for e in s.replace(";", ",").split(",") if e.strip() and "@" in e]


def _enqueue_email(store, *, mandant: str, to_email: str, subject: str, body: str, idem: str) -> bool:
    if not to_email or "@" not in to_email:
        return False
    try:
        from core.daten_speicher import email_outbox_enqueue

        enq = email_outbox_enqueue(
            kanzlei_id=str(getattr(store, "kanzlei_id", None) or "default"),
            mandant=mandant or "",
            to_email=to_email,
            subject=subject[:200],
            body_text=body,
            body_html="",
            idempotency_key=idem,
        )
        return bool(enq.get("created") or enq.get("status") in ("pending", "sending", "sent"))
    except Exception as e:
        log.warning("Eskalation E-Mail %s: %s", mandant, e)
        return False


def _mandant_erinnerung_text(name: str, stufe: Dict[str, Any], fehlende: int, tage: int) -> str:
    label = stufe.get("label") or "Erinnerung"
    docs = f"\n\nEs fehlen noch {fehlende} Unterlage(n)." if fehlende else ""
    tage_txt = f"\n\nWir haben seit {tage} Tagen keine Rückmeldung erhalten." if tage >= 3 else ""
    return (
        f"Sehr geehrte/r {name},\n\n"
        f"{label}: Bitte reichen Sie fehlende Unterlagen ein oder melden Sie sich im Mandantenportal.{docs}{tage_txt}\n\n"
        f"Mit freundlichen Grüßen\nIhre Kanzlei"
    )


def _fuehre_eskalation_aus(
    store,
    name: str,
    m: Dict[str, Any],
    stufe: Dict[str, Any],
    fehlende: int,
    tage: int,
    cfg: Dict[str, Any],
) -> bool:
    aktion = (stufe.get("aktion") or "").strip()
    tag = int(stufe.get("tag") or 0)
    if not aktion or aktion == "dokument_angefordert":
        return False

    tag_key = datetime.now().strftime("%Y-%m-%d")
    idem_base = hashlib.sha256(
        f"eskalation|{store.kanzlei_id}|{name}|{aktion}|{tag}|{tag_key}".encode()
    ).hexdigest()

    if aktion in ("erinnerung_1", "erinnerung_2", "erinnerung_deutlich"):
        email = (m.get("email") or "").strip()
        if not email:
            return False
        body = _mandant_erinnerung_text(name, stufe, fehlende, tage)
        ok = _enqueue_email(
            store,
            mandant=name,
            to_email=email,
            subject=f"Erinnerung — {name}",
            body=body,
            idem=idem_base,
        )
        if ok:
            store.kommunikation_hinzufuegen(name, {
                "typ": "eskalation_erinnerung",
                "text": stufe.get("label", aktion)[:120],
                "timestamp": datetime.now().isoformat(),
            })
        return ok

    if aktion == "eskalation_intern":
        sent = False
        for addr in _empfaenger_fuer_stufe(cfg, aktion):
            body = (
                f"Interne Eskalation — {datetime.now().strftime('%d.%m.%Y')}\n\n"
                f"Mandant: {name}\n"
                f"Tage ohne Antwort: {tage}\n"
                f"Fehlende Unterlagen: {fehlende}\n"
                f"Stufe: {stufe.get('label', aktion)} (Tag {tag})\n\n"
                f"Bitte im Dashboard prüfen."
            )
            if _enqueue_email(
                store,
                mandant=name,
                to_email=addr,
                subject=f"Eskalation: {name} — {tage} Tage ohne Antwort",
                body=body,
                idem=f"{idem_base}|{addr}",
            ):
                sent = True
        return sent

    if aktion == "mandant_rot":
        return True

    return False


def run_escalation_for_store(store) -> Dict[str, Any]:
    """Eskalations-Stufen für alle relevanten Mandanten einer Kanzlei ausführen."""
    cfg = load_settings_for_store(store)
    if not _bool_cfg(cfg, "auto_eskalation_aktiv", True):
        return {"geprueft": 0, "aktionen": 0, "deaktiviert": True}

    mandanten = store.hole_mandanten() or {}
    aktionen = 0
    geprueft = 0

    for name, m in mandanten.items():
        if not name or not isinstance(m, dict):
            continue
        fehlende_liste = m.get("fehlende_dokumente_liste") or []
        fehlende = len(fehlende_liste) if isinstance(fehlende_liste, list) else 0
        try:
            tage = int(store.berechne_tage_ohne_antwort(name) or 0)
        except Exception:
            tage = 0

        if fehlende == 0 and tage < 3:
            continue

        geprueft += 1
        info = aktuelle_eskalations_stufe(tage, store)
        stufe = info.get("stufe") or {}
        aktion = (stufe.get("aktion") or "").strip()
        if not aktion or aktion == "dokument_angefordert":
            continue

        last = (m.get("eskalation_letzte_aktion") or "").strip()
        if last == aktion:
            continue

        try:
            ok = _fuehre_eskalation_aus(store, name, m, stufe, fehlende, tage, cfg)
        except Exception as e:
            log.warning("Eskalation %s: %s", name, e)
            ok = False

        if ok:
            mm = dict(m)
            mm["eskalation_letzte_aktion"] = aktion
            mm["eskalation_letzte_am"] = datetime.now().isoformat()
            if aktion == "mandant_rot":
                mm["gesundheit_override"] = "rot"
            store.mandant_speichern(name, mm)
            aktionen += 1
            store.log_eintrag(f"ESKALATION | {name} | {aktion} | tag={stufe.get('tag')}")

    return {"geprueft": geprueft, "aktionen": aktionen}

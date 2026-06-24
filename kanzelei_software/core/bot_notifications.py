# E-Mail-Benachrichtigungen für proaktiven Bot
from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from modules.settings_manager import setting_holen

log = logging.getLogger("kanzlei_bot_notify")


def _portal_base_url() -> str:
    base = (os.getenv("PORTAL_BASE_URL") or os.getenv("REACT_APP_API_URL") or "").strip().rstrip("/")
    if not base:
        return "https://localhost/portal"
    if base.endswith("/api"):
        base = base[:-4]
    if not base.endswith("/portal"):
        return f"{base}/portal"
    return base


def _bool_setting(key: str, default: bool = True) -> bool:
    v = setting_holen(key)
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _kanzlei_notify_emails(store) -> List[str]:
    from modules.settings_manager import load_settings_for_store

    cfg = load_settings_for_store(store)
    raw = (
        (cfg.get("bot_analyse_benachrichtigung_email") or "")
        or (cfg.get("eskalation_stufe_1_empfaenger") or "")
        or (cfg.get("kanzlei_email") or "")
        or (os.getenv("EMAIL_FROM") or "")
    )
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip() and "@" in str(x)]
    s = str(raw).strip()
    if not s or "@" not in s:
        return []
    return [e.strip() for e in s.replace(";", ",").split(",") if e.strip() and "@" in e]


def _enqueue(
    store,
    *,
    mandant: str,
    to_email: str,
    subject: str,
    body_text: str,
    body_html: str = "",
    idempotency_key: str,
) -> bool:
    if not to_email or "@" not in to_email:
        return False
    try:
        from core.daten_speicher import email_outbox_enqueue

        enq = email_outbox_enqueue(
            kanzlei_id=store.kanzlei_id,
            mandant=mandant or "",
            to_email=to_email,
            subject=subject[:200],
            body_text=body_text,
            body_html=body_html or "",
            idempotency_key=idempotency_key,
            max_attempts=5,
        )
        return enq.get("created") or enq.get("status") in ("pending", "sending", "sent")
    except Exception as e:
        log.warning("bot notify enqueue failed: %s", e)
        return False


def notify_mandant_new_bot_frage(store, mandant: str, frage: Dict[str, Any]) -> bool:
    """Mandant erhält E-Mail bei neuer Portal-Frage."""
    if not _bool_setting("bot_email_mandant_aktiv", True):
        return False
    m = store.hole_mandant(mandant) if hasattr(store, "hole_mandant") else (store.hole_mandanten() or {}).get(mandant)
    if not m:
        return False
    email = (m.get("email") or "").strip()
    if not email:
        log.info("Bot-Mail Mandant %s: keine E-Mail", mandant)
        return False

    portal = _portal_base_url()
    text = (frage.get("text") or "Ihre Kanzlei hat eine Rückfrage.").strip()
    opts = frage.get("antwort_optionen") or []
    opts_txt = "\n".join(f"  • {o}" for o in opts[:6]) if opts else ""
    fid = frage.get("id") or ""

    body = (
        f"Guten Tag,\n\n"
        f"Ihre Steuerkanzlei hat eine Rückfrage:\n\n"
        f"{text}\n\n"
        f"{('Antwortmöglichkeiten:\n' + opts_txt + '\n\n') if opts_txt else ''}"
        f"Bitte antworten Sie im Mandantenportal:\n{portal}\n\n"
        f"(Persönlicher Zugangslink erhalten Sie von Ihrer Kanzlei, falls Sie noch keinen haben.)\n\n"
        f"Mit freundlichen Grüßen\nIhre Kanzlei"
    )
    html = (
        f"<p>Guten Tag,</p><p>Ihre Steuerkanzlei hat eine Rückfrage:</p>"
        f"<p><strong>{text}</strong></p>"
        f"<p><a href=\"{portal}\">Zum Mandantenportal</a></p>"
    )
    idk = hashlib.sha256(
        f"bot_frage_mandant|{store.kanzlei_id}|{fid}|{mandant}".encode()
    ).hexdigest()
    ok = _enqueue(
        store,
        mandant=mandant,
        to_email=email,
        subject=f"Rückfrage Ihrer Kanzlei — {mandant}",
        body_text=body,
        body_html=html,
        idempotency_key=idk,
    )
    if ok:
        store.log_eintrag(f"BOT_MAIL_MANDANT | {mandant} | {email}")
    return ok


def notify_kanzlei_bot_analyse(
    store,
    neue_fragen: List[Dict[str, Any]],
) -> int:
    """Kanzlei: Zusammenfassung nach Bot-Analyse (Scheduler oder manuell)."""
    if not neue_fragen:
        return 0
    if not _bool_setting("bot_email_kanzlei_aktiv", True):
        return 0

    emails = _kanzlei_notify_emails(store)
    if not emails:
        log.warning("Bot-Mail Kanzlei: kein Empfänger konfiguriert")
        return 0

    lines = []
    for f in neue_fragen[:20]:
        lines.append(f"• {f.get('mandant', '?')}: {(f.get('text') or '')[:70]}…")
    body = (
        f"Bot-Analyse — {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
        f"{len(neue_fragen)} neue Frage(n) für Mandanten im Portal:\n\n"
        + "\n".join(lines)
        + "\n\nBitte prüfen Sie unter Automation → Proaktiver Bot."
    )
    sent = 0
    tag = datetime.now().strftime("%Y-%m-%d")
    for addr in emails:
        idk = hashlib.sha256(
            f"bot_analyse_kanzlei|{store.kanzlei_id}|{tag}|{addr}|{len(neue_fragen)}".encode()
        ).hexdigest()
        if _enqueue(
            store,
            mandant="",
            to_email=addr,
            subject=f"Bot: {len(neue_fragen)} neue Mandanten-Frage(n)",
            body_text=body,
            idempotency_key=idk,
        ):
            sent += 1
    if sent:
        store.log_eintrag(f"BOT_MAIL_KANZLEI | {len(neue_fragen)} Fragen | {sent} Empfänger")
    return sent

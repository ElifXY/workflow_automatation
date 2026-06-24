# Absender & SMTP pro Kanzlei (Mandanten-E-Mails)

from __future__ import annotations



import logging

import os

import re

import smtplib

from email.mime.multipart import MIMEMultipart

from email.mime.text import MIMEText

from email.utils import formataddr

from typing import Any, Dict, Optional



log = logging.getLogger(__name__)



SMTP_PASS_MASK = "********"

SMTP_SECRET_KEYS = frozenset({"smtp_pass"})





def _parse_email_from_env(raw: str) -> tuple[str, str]:

    s = (raw or "").strip()

    if not s:

        return "", ""

    if "<" in s and ">" in s:

        name = s.split("<", 1)[0].strip().strip('"').strip("'")

        addr = s.split("<", 1)[1].split(">", 1)[0].strip()

        return name, addr

    if "@" in s:

        return "", s

    return s, ""





def _norm_email(addr: str) -> str:

    return (addr or "").strip().lower()





def mask_secret_settings(settings: Dict[str, Any]) -> Dict[str, Any]:

    out = dict(settings)

    for key in SMTP_SECRET_KEYS:

        if (out.get(key) or "").strip():

            out[key] = SMTP_PASS_MASK

            out[f"{key}_gesetzt"] = True

        else:

            out[f"{key}_gesetzt"] = False

    return out





def is_smtp_pass_placeholder(wert: Any) -> bool:

    s = ("" if wert is None else str(wert)).strip()

    return not s or s == SMTP_PASS_MASK or s.startswith("****")





def global_smtp_transport() -> Optional[Dict[str, Any]]:

    """Optionaler System-Fallback (.env) — nicht für Mandanten-Mails wenn Tenant-SMTP fehlt."""

    user = (os.getenv("EMAIL_USER") or "").strip()

    password = (os.getenv("EMAIL_PASS") or "").strip()

    if not user or not password:

        return None

    return {

        "host": (os.getenv("EMAIL_HOST") or os.getenv("SMTP_HOST") or "smtp.gmail.com").strip(),

        "port": int(os.getenv("EMAIL_PORT") or os.getenv("SMTP_PORT") or "587"),

        "user": user,

        "password": password,

        "tls": True,

        "source": "global",

    }





def tenant_smtp_transport(store: Any) -> Optional[Dict[str, Any]]:

    from modules.settings_manager import load_settings_for_store



    cfg = load_settings_for_store(store)

    if not cfg.get("smtp_aktiv"):

        return None

    user = (cfg.get("smtp_user") or "").strip()

    password = (cfg.get("smtp_pass") or "").strip()

    if not user or not password or "@" not in user:

        return None

    host = (cfg.get("smtp_host") or "").strip() or "smtp.gmail.com"

    return {

        "host": host,

        "port": int(cfg.get("smtp_port") or 587),

        "user": user,

        "password": password,

        "tls": bool(cfg.get("smtp_tls", True)),

        "source": "tenant",

    }





def resolve_smtp_transport(

    store: Optional[Any] = None,

    *,

    allow_global: bool = False,

) -> Optional[Dict[str, Any]]:

    """SMTP-Zugang: zuerst Kanzlei-Einstellungen, optional global (.env)."""

    if store is not None:

        t = tenant_smtp_transport(store)

        if t:

            return t

    if allow_global:

        return global_smtp_transport()

    return None





def resolve_email_from(

    kanzlei_id: str = "default",

    store: Optional[Any] = None,

) -> Dict[str, Any]:

    """Absender-Header für eine Kanzlei (Anzeigename + From-Adresse des SMTP-Kontos)."""

    display = "Ihre Steuerkanzlei"

    configured = ""

    transport = resolve_smtp_transport(store, allow_global=False)

    global_t = global_smtp_transport() if not transport else None



    if store is not None:

        try:

            from modules.settings_manager import load_settings_for_store



            cfg = load_settings_for_store(store)

            abs_name = (cfg.get("email_absender_name") or "").strip()

            k_name = (cfg.get("kanzlei_name") or "").strip()

            configured = (cfg.get("kanzlei_email") or "").strip()

            if abs_name:

                display = abs_name

            elif k_name and k_name.lower() not in ("steuerkanzlei", "standard-kanzlei"):

                display = k_name

        except Exception:

            pass



    from_addr = ""

    smtp_account = ""

    smtp_configured = False

    if transport:

        from_addr = transport["user"]

        smtp_account = transport["user"]

        smtp_configured = True

    elif global_t:

        from_addr = global_t["user"]

        smtp_account = global_t["user"]

    elif configured and "@" in configured:

        from_addr = configured



    if not from_addr:

        _, env_addr = _parse_email_from_env((os.getenv("EMAIL_FROM") or "").strip())

        from_addr = env_addr or "noreply@kanzlei-ai.local"



    reply_to = ""

    if configured and "@" in configured and _norm_email(configured) != _norm_email(from_addr):

        reply_to = configured



    display = (display or "Ihre Steuerkanzlei").strip()

    if re.fullmatch(r"kanzlei\s*ai", display, re.I):

        display = "Ihre Steuerkanzlei"



    return {

        "display_name": display,

        "from_email": from_addr,

        "configured_email": configured,

        "smtp_account": smtp_account,

        "smtp_configured": smtp_configured,

        "reply_to": reply_to,

        "address_mismatch": bool(reply_to),

        "from_header": formataddr((display, from_addr)),

    }





def send_email_via_transport(

    transport: Dict[str, Any],

    to_email: str,

    subject: str,

    body: str,

    html_body: Optional[str] = None,

    from_header: Optional[str] = None,

    reply_to: Optional[str] = None,

) -> bool:

    if not transport:

        return False

    try:

        msg = MIMEMultipart("alternative")

        msg["From"] = (from_header or "").strip() or formataddr(

            ("Kanzlei Automation", transport["user"])

        )

        if (reply_to or "").strip() and "@" in reply_to:

            msg["Reply-To"] = reply_to.strip()

        msg["To"] = to_email

        msg["Subject"] = subject

        msg.attach(MIMEText(body or "", "plain", "utf-8"))

        if html_body:

            msg.attach(MIMEText(html_body, "html", "utf-8"))



        host = transport["host"]

        port = int(transport["port"])

        with smtplib.SMTP(host, port, timeout=60) as server:

            server.ehlo()

            if transport.get("tls", True):

                server.starttls()

                server.ehlo()

            server.login(transport["user"], transport["password"])

            server.send_message(msg)

        log.info("Email gesendet → %s | %s", to_email, subject[:40])

        return True

    except smtplib.SMTPAuthenticationError:

        log.error("SMTP Auth-Fehler (%s)", transport.get("source"))

        return False

    except smtplib.SMTPException as e:

        log.error("SMTP Fehler: %s", e)

        return False

    except Exception as e:

        log.error("Email-Fehler: %s", e)

        return False





def send_tenant_email(

    store: Any,

    to_email: str,

    subject: str,

    body: str,

    html_body: Optional[str] = None,

    *,

    allow_global: bool = False,

) -> bool:

    transport = resolve_smtp_transport(store, allow_global=allow_global)

    if not transport:

        log.warning(

            "Kein SMTP für Kanzlei %s — Einstellungen → E-Mail-Versand konfigurieren",

            getattr(store, "kanzlei_id", "?"),

        )

        return False

    resolved = resolve_email_from(getattr(store, "kanzlei_id", "default"), store)

    return send_email_via_transport(

        transport,

        to_email,

        subject,

        body,

        html_body,

        from_header=resolved["from_header"],

        reply_to=resolved.get("reply_to") or None,

    )



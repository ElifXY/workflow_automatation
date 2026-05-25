# Absender für Mandanten-E-Mails (SMTP From-Header, pro Kanzlei)
from __future__ import annotations

import os
import re
from email.utils import formataddr
from typing import Any, Dict, Optional


def _parse_email_from_env(raw: str) -> tuple[str, str]:
    """„Name <mail@x.de>“ oder nur Adresse."""
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


def resolve_email_from(
    kanzlei_id: str = "default",
    store: Optional[Any] = None,
) -> Dict[str, str]:
    """
    SMTP-Absender für eine Kanzlei.
    Anzeigename aus Einstellungen (nicht „Kanzlei AI“), Adresse aus kanzlei_email oder SMTP-Konto.
    """
    display = "Ihre Steuerkanzlei"
    addr = (os.getenv("EMAIL_USER") or "").strip()
    env_from = (os.getenv("EMAIL_FROM") or "").strip()
    env_name, env_addr = _parse_email_from_env(env_from)
    if env_addr:
        addr = env_addr
    if env_name and not re.search(r"kanzlei\s*ai", env_name, re.I):
        display = env_name

    if store is not None:
        try:
            abs_name = (store.setting_holen("email_absender_name") or "").strip()
            k_name = (store.setting_holen("kanzlei_name") or "").strip()
            k_mail = (store.setting_holen("kanzlei_email") or "").strip()
            if abs_name:
                display = abs_name
            elif k_name and k_name.lower() not in ("steuerkanzlei", "standard-kanzlei"):
                display = k_name
            if k_mail and "@" in k_mail:
                addr = k_mail
        except Exception:
            pass

    if not addr and env_addr:
        addr = env_addr
    if not addr:
        addr = "noreply@example.com"

    display = (display or "Ihre Steuerkanzlei").strip()
    # Produktname nicht als Mandanten-Mail-Absender
    if re.fullmatch(r"kanzlei\s*ai", display, re.I):
        display = (store.setting_holen("kanzlei_name") if store else None) or "Ihre Steuerkanzlei"
        if re.fullmatch(r"kanzlei\s*ai", str(display), re.I):
            display = "Ihre Steuerkanzlei"

    return {
        "display_name": display,
        "from_email": addr,
        "from_header": formataddr((display, addr)),
    }

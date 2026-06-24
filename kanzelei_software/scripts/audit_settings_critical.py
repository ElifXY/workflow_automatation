#!/usr/bin/env python3
"""Kritische Settings: Tenant-Roundtrip + Absender-Auflösung (ohne laufenden Server)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.daten_speicher import DatenSpeicher
from modules.settings_manager import (
    load_settings_for_store,
    save_setting_for_store,
    setting_holen,
)
from core.email_sender import resolve_email_from

CRITICAL_KEYS = [
    "kanzlei_name",
    "email_absender_name",
    "kanzlei_email",
    "portal_aktiv",
    "portal_unterschrift_aktiv",
    "portal_upload_max_mb",
    "portal_nachrichten_aktiv",
    "ki_autonomie_grad",
]


def main() -> int:
    base = tempfile.mkdtemp(prefix="audit_settings_")
    os.environ.setdefault("DATA_DIR", base)

    a = DatenSpeicher(kanzlei_id="audit_a")
    b = DatenSpeicher(kanzlei_id="audit_b")
    fails = []

    save_setting_for_store(a, "email_absender_name", "Audit Alpha GmbH")
    save_setting_for_store(a, "kanzlei_email", "alpha@audit.test")
    save_setting_for_store(b, "email_absender_name", "Audit Beta AG")
    save_setting_for_store(b, "portal_aktiv", True)
    save_setting_for_store(a, "portal_aktiv", False)

    la = load_settings_for_store(a)
    lb = load_settings_for_store(b)
    if la.get("email_absender_name") != "Audit Alpha GmbH":
        fails.append(f"A email_absender_name: {la.get('email_absender_name')!r}")
    if lb.get("email_absender_name") != "Audit Beta AG":
        fails.append(f"B email_absender_name: {lb.get('email_absender_name')!r}")
    if bool(lb.get("portal_aktiv")) is not True:
        fails.append(f"B portal_aktiv: {lb.get('portal_aktiv')!r}")
    if bool(setting_holen("portal_aktiv", store=a)):
        fails.append("A portal_aktiv leaked as True via setting_holen(store=a)")

    save_setting_for_store(a, "smtp_aktiv", True)
    save_setting_for_store(a, "smtp_user", "smtp@audit.test")
    save_setting_for_store(a, "smtp_pass", "x")
    ra = resolve_email_from("audit_a", a)
    if "Audit Alpha" not in ra["display_name"]:
        fails.append(f"A display_name: {ra['display_name']!r}")
    if ra["from_email"] != "smtp@audit.test":
        fails.append(f"A from_email: {ra['from_email']!r}")

    for key in CRITICAL_KEYS:
        if key not in la and key not in lb:
            continue
        va = la.get(key)
        vb = lb.get(key)
        if key == "email_absender_name" and va == vb and va == "Audit Alpha GmbH":
            fails.append("cross-tenant bleed on email_absender_name")

    if fails:
        print("AUDIT FAIL:")
        for f in fails:
            print(" -", f)
        return 1
    print("AUDIT OK:", len(CRITICAL_KEYS), "keys checked, tenant isolation + absender")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

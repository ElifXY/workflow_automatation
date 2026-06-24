#!/usr/bin/env python3
"""Settings: speichern/laden pro tenant_id + Absender-Auflösung."""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    os.environ["ENVIRONMENT"] = "development"
    os.environ["APP_ENV"] = "development"
    os.environ["DATA_DIR"] = f".tmp_settings_rt_{uuid.uuid4().hex}"

    from core.daten_speicher import DatenSpeicher
    from core.email_sender import resolve_email_from
    from modules.settings_manager import load_settings_for_store, save_setting_for_store

    kid_a = f"kanzlei_a_{uuid.uuid4().hex[:8]}"
    kid_b = f"kanzlei_b_{uuid.uuid4().hex[:8]}"
    store_a = DatenSpeicher(kanzlei_id=kid_a)
    store_b = DatenSpeicher(kanzlei_id=kid_b)

    save_setting_for_store(store_a, "email_absender_name", "Kanzlei Alpha GmbH")
    save_setting_for_store(store_a, "kanzlei_email", "alpha@example.com")
    save_setting_for_store(store_b, "email_absender_name", "Kanzlei Beta AG")
    save_setting_for_store(store_b, "kanzlei_email", "beta@example.com")

    la = load_settings_for_store(store_a)
    lb = load_settings_for_store(store_b)
    if la.get("email_absender_name") != "Kanzlei Alpha GmbH":
        print("FAIL A name", la.get("email_absender_name"))
        return 1
    if lb.get("email_absender_name") != "Kanzlei Beta AG":
        print("FAIL B name", lb.get("email_absender_name"))
        return 1

    ra = resolve_email_from(kid_a, store_a)
    rb = resolve_email_from(kid_b, store_b)
    if "Alpha" not in ra["display_name"]:
        print("FAIL absender A", ra)
        return 1
    if "Beta" not in rb["display_name"]:
        print("FAIL absender B", rb)
        return 1
    save_setting_for_store(store_a, "smtp_aktiv", True)
    save_setting_for_store(store_a, "smtp_user", "kanzlei@alpha.example.com")
    save_setting_for_store(store_a, "smtp_pass", "secret-test")
    save_setting_for_store(store_a, "smtp_host", "smtp.example.com")
    rc = resolve_email_from(kid_a, store_a)
    if not rc.get("smtp_configured"):
        print("FAIL smtp_configured", rc)
        return 1
    if rc["from_email"] != "kanzlei@alpha.example.com":
        print("FAIL smtp from A", rc["from_email"])
        return 1

    print("PASS: settings tenant roundtrip + email absender")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

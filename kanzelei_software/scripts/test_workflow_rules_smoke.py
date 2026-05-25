#!/usr/bin/env python3
"""Smoke: Workflow-Regeln Trigger + RBAC settings:write für Steuerberater."""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    os.environ.setdefault("ENVIRONMENT", "development")
    os.environ.setdefault("APP_ENV", "development")
    os.environ["DATA_DIR"] = f".tmp_wf_smoke_{uuid.uuid4().hex}"

    from core.rbac import has_permission
    from core.workflow_builder import WorkflowBaukasten, TRIGGER_TYPEN
    from core.daten_speicher import DatenSpeicher
    from core.proaktiver_bot import ProaktiverBot

    merged = {
        "rollen_nav_steuerberater": [
            "dashboard", "mandanten", "settings", "automation",
        ],
    }
    if not has_permission("steuerberater", "settings:write", merged):
        print("FAIL: steuerberater needs settings:write with settings tab")
        return 1
    if not has_permission("steuerberater", "engine:run", merged):
        print("FAIL: steuerberater needs engine:run with automation tab")
        return 1

    ds = DatenSpeicher(kanzlei_id="default")
    b = WorkflowBaukasten(ds, bot=ProaktiverBot(ds))

    # monatlich: nur am konfigurierten Tag
    t_mon = {"typ": "monatlich", "parameter": datetime.now().day}
    assert b._prüfe_trigger(t_mon, "Test", {"umsatz": 0}) is True
    wrong_day = 29 if datetime.now().day != 29 else 28
    t_wrong = {"typ": "monatlich", "parameter": wrong_day}
    if datetime.now().day != wrong_day:
        assert b._prüfe_trigger(t_wrong, "Test", {"umsatz": 0}) is False

    # unbekannter Trigger → False (nicht still True)
    assert b._prüfe_trigger({"typ": "beleg_erkannt", "parameter": "x"}, "T", {}) is False

    for typ in TRIGGER_TYPEN:
        if typ in ("manuell", "taeglich", "monatlich"):
            continue
        # nur prüfen dass kein Crash
        b._prüfe_trigger({"typ": typ, "parameter": 7}, "T", {"umsatz": 1000, "email": "t@ex.de"})

    regel = b.regel_erstellen(
        name="Smoke Aufgabe",
        beschreibung="test",
        trigger={"typ": "manuell", "parameter": None},
        bedingungen=[],
        aktionen=[{
            "typ": "aufgabe_anlegen",
            "parameter": {"beschreibung": "WF-Smoke", "frist_tage": 3, "prioritaet": "normal"},
        }],
        aktiv=True,
    )
    res = b.fuehre_alle_aus()
    if res.get("aktionen", 0) < 1:
        print(f"FAIL: expected at least 1 action, got {res}")
        return 1

    print("PASS: workflow rules smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Integrationstest: Proaktiver Bot-Analyse (SQLite, isoliert)."""
from __future__ import annotations

import os
import sys
import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ["ENVIRONMENT"] = "development"
os.environ.pop("USE_POSTGRES_DATA", None)
os.environ.pop("DATABASE_URL", None)
os.environ["USE_DOMAIN_TABLES_V2"] = "0"

from core.daten_speicher import DatenSpeicher, init_db, _local  # noqa: E402
from core.proaktiver_bot import ProaktiverBot  # noqa: E402


def _fresh_store() -> DatenSpeicher:
    import core.daten_speicher as ds_mod

    if hasattr(_local, "conn") and _local.conn is not None:
        try:
            _local.conn.close()
        except Exception:
            pass
        _local.conn = None

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    ds_mod.DB_PFAD = tmp.name
    init_db()
    return DatenSpeicher("test-kanzlei")


def test_fehlende_docs_persist_and_trigger() -> None:
    store = _fresh_store()
    name = "Test Mandant GmbH"
    store.mandant_speichern(name, {
        "email": "t@test.de",
        "umsatz": 12000.0,
        "letzte_antwort": (datetime.now() - timedelta(days=20)).isoformat(),
        "fehlende_dokumente_liste": ["Beleg A", "Beleg B"],
    })
    m = store.hole_mandant(name)
    assert m is not None
    assert len(m.get("fehlende_dokumente_liste") or []) >= 2, m

    bot = ProaktiverBot(store)
    neu, pruef = bot.analysiere_alle_mandanten()
    typen = {f.get("typ") for f in neu}
    assert "beleg_fehlend" in typen or "kontakt_erinnerung" in typen, (neu, pruef)
    assert store.bot_fragen_liste(), "Fragen müssen gespeichert sein"
    stats = bot.statistiken()
    assert stats["fragen_gesamt"] >= len(neu)
    print("ok: fehlende_docs + kontakt", typen)


def test_ueberfaellige_frist() -> None:
    store = _fresh_store()
    name = "Frist Test"
    store.mandant_speichern(name, {
        "email": "f@test.de",
        "letzte_antwort": datetime.now().isoformat(),
    })
    aid = str(uuid.uuid4())
    store.aufgabe_speichern(aid, {
        "id": aid,
        "mandant": name,
        "beschreibung": "USt Q1 nachreichen",
        "frist": (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d"),
        "erledigt": False,
    })
    bot = ProaktiverBot(store)
    neu, _ = bot.analysiere_alle_mandanten()
    assert any(f.get("typ") == "frist_erinnerung" for f in neu), neu
    print("ok: frist_erinnerung")


def test_antwort_statistik() -> None:
    store = _fresh_store()
    name = "Stat Test"
    store.mandant_speichern(name, {"email": "s@test.de", "letzte_antwort": datetime.now().isoformat()})
    bot = ProaktiverBot(store)
    f = bot.frage_stellen(name, "Testfrage?", "sonstiges")
    bot.antwort_erfassen(f["id"], "Ja, korrekt")
    stats = bot.statistiken()
    assert stats["fragen_gesamt"] == 1
    assert stats["fragen_beantwortet"] == 1
    assert stats["gesparte_telefonate"] == 1
    print("ok: statistiken nach antwort")


def main() -> int:
    test_fehlende_docs_persist_and_trigger()
    test_ueberfaellige_frist()
    test_antwort_statistik()
    print("ok: alle Bot-Analyse-Tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

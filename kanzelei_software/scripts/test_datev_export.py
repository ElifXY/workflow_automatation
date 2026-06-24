#!/usr/bin/env python3
"""DATEV EXTF + ZIP Komplett-Export — Smoke-Tests ohne Server."""
from __future__ import annotations

import csv
import io
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.datev_export_utils import (
    DATEV_NCOL,
    assess_datev_export_relevance,
    debitoren_konto_fuer_mandant,
    mandanten_in_stammdaten_reihenfolge,
    normalize_berater_nr,
    validate_datev_buchungsstapel_csv,
)
from core.export_service import (
    export_datev_buchungsstapel,
    export_datev_stammdaten,
    export_komplettpaket,
)


def _data_rows(csv_bytes: bytes):
    text = csv_bytes.decode("windows-1252")
    rows = list(csv.reader(io.StringIO(text), delimiter=";"))
    return [r for r in rows[2:] if any(str(c).strip() for c in r)]


def test_buchungsstapel_extf():
    m = {"umsatz": 120000, "email": "test@example.de", "branche": "IT"}
    aufgaben = [
        {"mandant": "Test GmbH", "beschreibung": "UStVA Q1", "erledigt": True, "betrag": 150.5, "frist": "2026-03-15"},
        {"mandant": "Test GmbH", "beschreibung": "Offen", "erledigt": False},
    ]
    raw = export_datev_buchungsstapel("Test GmbH", m, aufgaben, berater_nr="10001", mandanten_nr="12345")
    meta = validate_datev_buchungsstapel_csv(raw, strict=True)
    assert meta["ok"]
    assert meta["buchungen"] >= 1, "mindestens Honorar-Buchung erwartet"
    text = raw.decode("windows-1252")
    assert "EXTF" in text.split("\r\n")[0]
    assert "Umsatz" in text.split("\r\n")[1]
    for row in _data_rows(raw):
        assert len(row) == DATEV_NCOL
    print("OK test_buchungsstapel_extf", meta)


def test_debitoren_konsistenz():
    mandanten = {"Alpha GmbH": {"email": "a@b.de", "umsatz": 50000}, "Beta": {"email": "b@b.de"}}
    names = mandanten_in_stammdaten_reihenfolge(mandanten)
    assert debitoren_konto_fuer_mandant("Alpha GmbH", mandanten) == "10001"
    assert debitoren_konto_fuer_mandant("Beta", mandanten) == "10002"
    m = {"umsatz": 12000, "email": "a@b.de"}
    raw = export_datev_buchungsstapel("Alpha GmbH", m, [], alle_mandanten=mandanten)
    data = _data_rows(raw)
    assert data, "Honorar-Zeile erwartet"
    gegen = data[0][7]
    assert gegen == "10001", f"Gegenkonto muss Debitorenkonto sein, war {gegen}"
    stamm = export_datev_stammdaten(mandanten, "10001").decode("windows-1252")
    assert ";10001;" in stamm or stamm.split(";")[0] == "EXTF" or "10001" in stamm.split("\r\n")[2]
    print("OK test_debitoren_konsistenz", gegen)


def test_no_zero_amount_rows():
    m = {"umsatz": 0}
    aufgaben = [{"mandant": "X", "beschreibung": "Erledigt ohne Betrag", "erledigt": True}]
    raw = export_datev_buchungsstapel("X", m, aufgaben)
    meta = validate_datev_buchungsstapel_csv(raw, strict=True)
    assert meta["buchungen"] == 0
    assert not _data_rows(raw)
    print("OK test_no_zero_amount_rows", meta.get("warnings"))


def test_relevance():
    rel = assess_datev_export_relevance(
        "Kunde",
        {"umsatz": 60000, "email": "k@example.de"},
        [],
        "10001",
        {"Kunde": {"email": "k@example.de"}},
    )
    assert rel["exportierbar"]
    assert rel["nutzen"] in ("hoch", "mittel", "gering")
    assert rel["buchungen_erwartet"] >= 1
    print("OK test_relevance", rel["nutzen"], rel["buchungen_erwartet"])


def test_stammdaten():
    mandanten = {
        "Alpha; GmbH": {"email": "a@b.de", "umsatz": 50000, "branche": "Handel"},
        "Beta": {"email": "b@b.de", "umsatz": 0},
    }
    raw = export_datev_stammdaten(mandanten, "10001")
    assert b"EXTF" in raw
    assert len(raw) > 200
    print("OK test_stammdaten", len(raw))


def test_komplettpaket_zip():
    m = {"umsatz": 60000, "email": "k@example.de"}
    mandanten = {"Kunde": m}
    zip_bytes, manifest = export_komplettpaket(
        "Kunde", m, [], mandanten, {}, [], berater_nr="10001", datev_aktiv=True
    )
    assert manifest.get("datev_relevanz", {}).get("nutzen")
    assert manifest["dateien_gesamt"] >= 1
    assert "datev_buchungsstapel" in manifest["dateien"] or "datev_stammdaten" in manifest["dateien"]
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        names = zf.namelist()
        assert "README.txt" in names
        assert "EXPORT_MANIFEST.json" in names
        assert "DATEV/DATEV_NUTZEN.txt" in names
        assert any(n.startswith("DATEV/") and n.endswith(".csv") for n in names)
    print("OK test_komplettpaket_zip", manifest["dateien_gesamt"], "files")


def test_komplett_ohne_datev():
    m = {"umsatz": 60000, "email": "k@example.de"}
    zip_bytes, manifest = export_komplettpaket(
        "Kunde", m, [], {"Kunde": m}, {}, [], datev_aktiv=False
    )
    assert "datev_buchungsstapel" not in manifest["dateien"]
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        assert not any(n.endswith("_Buchungsstapel.csv") for n in zf.namelist())
    print("OK test_komplett_ohne_datev")


def test_berater_normalize():
    assert normalize_berater_nr("12-34-5") == "12345"
    print("OK test_berater_normalize")


if __name__ == "__main__":
    test_berater_normalize()
    test_buchungsstapel_extf()
    test_debitoren_konsistenz()
    test_no_zero_amount_rows()
    test_relevance()
    test_stammdaten()
    test_komplettpaket_zip()
    test_komplett_ohne_datev()
    print("Alle DATEV-Tests bestanden.")

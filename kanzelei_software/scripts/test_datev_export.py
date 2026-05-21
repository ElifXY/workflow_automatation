#!/usr/bin/env python3
"""DATEV EXTF + ZIP Komplett-Export — Smoke-Tests ohne Server."""
from __future__ import annotations

import sys
import zipfile
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.datev_export_utils import validate_datev_buchungsstapel_csv, normalize_berater_nr
from core.export_service import (
    export_datev_buchungsstapel,
    export_datev_stammdaten,
    export_komplettpaket,
)


def test_buchungsstapel_extf():
    m = {"umsatz": 120000, "email": "test@example.de", "branche": "IT"}
    aufgaben = [
        {"mandant": "Test GmbH", "beschreibung": "UStVA Q1", "erledigt": True, "betrag": 150.5, "frist": "2026-03-15"},
        {"mandant": "Test GmbH", "beschreibung": "Offen", "erledigt": False},
    ]
    raw = export_datev_buchungsstapel("Test GmbH", m, aufgaben, berater_nr="10001", mandanten_nr="12345")
    meta = validate_datev_buchungsstapel_csv(raw)
    assert meta["ok"]
    assert meta["buchungen"] >= 1, "mindestens Honorar-Buchung erwartet"
    text = raw.decode("windows-1252")
    assert "EXTF" in text.split("\n")[0]
    assert "Umsatz" in text.split("\n")[1]
    print("OK test_buchungsstapel_extf", meta)


def test_no_zero_amount_rows():
    m = {"umsatz": 0}
    aufgaben = [{"mandant": "X", "beschreibung": "Erledigt ohne Betrag", "erledigt": True}]
    raw = export_datev_buchungsstapel("X", m, aufgaben)
    meta = validate_datev_buchungsstapel_csv(raw)
    assert meta["buchungen"] == 0
    print("OK test_no_zero_amount_rows", meta.get("warnings"))


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
        "Kunde", m, [], mandanten, {}, [], berater_nr="10001"
    )
    assert manifest["dateien_gesamt"] >= 1
    assert "datev_buchungsstapel" in manifest["dateien"] or "datev_stammdaten" in manifest["dateien"]
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        names = zf.namelist()
        assert "README.txt" in names
        assert "EXPORT_MANIFEST.json" in names
        assert any(n.startswith("DATEV/") for n in names)
    print("OK test_komplettpaket_zip", manifest["dateien_gesamt"], "files")


def test_berater_normalize():
    assert normalize_berater_nr("12-34-5") == "12345"
    print("OK test_berater_normalize")


if __name__ == "__main__":
    test_berater_normalize()
    test_buchungsstapel_extf()
    test_no_zero_amount_rows()
    test_stammdaten()
    test_komplettpaket_zip()
    print("Alle DATEV-Tests bestanden.")

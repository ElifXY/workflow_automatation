"""Offline-Test: Beleg-Normalisierung (ohne API-Keys)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.ai_service import (  # noqa: E402
    _normalize_receipt_payload,
    _receipt_model_from_normalized,
)


def test_austrian_kassenbon_aliases() -> None:
    raw = {
        "summe": "4,70",
        "netto": "4,16",
        "mwst": "0,54",
        "steuersatz": "13",
        "datum": "24.06.2021",
        "beleg_nr": "001620211750059",
        "lieferant": "Kasse",
        "kategorie": "sonstiges",
        "vertrauens_score": 0.92,
    }
    norm = _normalize_receipt_payload(raw)
    rec = _receipt_model_from_normalized(norm)
    assert rec.betrag_brutto == 4.7, rec.betrag_brutto
    assert rec.betrag_netto == 4.16, rec.betrag_netto
    assert rec.mwst_betrag == 0.54, rec.mwst_betrag
    assert rec.mwst_satz == 13, rec.mwst_satz
    assert rec.datum == "2021-06-24", rec.datum
    print("[OK] AT-Kassenbon Aliase + Beträge")


def test_nested_totals() -> None:
    raw = {
        "totals": {"betrag_brutto": 119.0, "betrag_netto": 100.0, "mwst_betrag": 19.0},
        "mwst_satz": 19,
    }
    rec = _receipt_model_from_normalized(_normalize_receipt_payload(raw))
    assert rec.betrag_brutto == 119.0
    print("[OK] verschachtelte totals")


def main() -> int:
    test_austrian_kassenbon_aliases()
    test_nested_totals()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Prüft Konsistenz: Dashboard Heute-Ops, /dashboard KPIs, Decision-Engine pro Mandant.
Exit 0 = alles konsistent, 2 = Abweichungen.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("USE_POSTGRES_DATA", os.getenv("USE_POSTGRES_DATA", "0"))


def main() -> int:
    from core.daten_speicher import DatenSpeicher
    from core.dashboard_ops import heute_operations
    from core.decision_engine import analysiere_alle_mandanten, _berechne_risiko_daten

    store = DatenSpeicher(kanzlei_id="default")
    ops = heute_operations(store)
    dash_ueber = ops.get("aufgaben_ueberfaellig", 0)

    mandanten = store.hole_mandanten() or {}
    summe_kpi = 0
    problems: list[str] = []

    for name, m in mandanten.items():
        if not isinstance(m, dict):
            continue
        risiko = _berechne_risiko_daten(name, m, store)
        n = int(risiko.get("aufgaben_ueberfaellig") or 0)
        summe_kpi += n
        if n > 0:
            print(f"  {name}: {n} überfällig, Status={risiko.get('status')}")

    if summe_kpi != dash_ueber:
        problems.append(
            f"Summe Mandanten-KPI ({summe_kpi}) != heute_operations ({dash_ueber})"
        )

    alle = analysiere_alle_mandanten(store)
    summe_analyse = sum(int(x.get("aufgaben_ueberfaellig") or 0) for x in alle)
    if summe_analyse != dash_ueber:
        problems.append(
            f"analysiere_alle_mandanten Summe ({summe_analyse}) != heute_operations ({dash_ueber})"
        )

    print(f"Heute-Ops überfällig: {dash_ueber}")
    print(f"Summe KPI pro Mandant: {summe_kpi}")
    print(f"Summe analyse_alle:   {summe_analyse}")

    if problems:
        print("KPI-Konsistenz: FAIL")
        for p in problems:
            print(f"  - {p}")
        return 2
    print("KPI-Konsistenz: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

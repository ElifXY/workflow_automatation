#!/usr/bin/env python3
"""
Geschäfts- und Kennzellen-Audit: KPI, Dashboard, Profit, Billing-Gates, Module-Imports.
Exit 0 = alle automatisierten Checks bestanden.
"""
from __future__ import annotations

import os
import sys
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("USE_POSTGRES_DATA", "0")
os.environ.setdefault("DATA_DIR", os.path.join(ROOT, "data"))


def _fail(msg: str, problems: list[str]) -> None:
    problems.append(msg)


def main() -> int:
    problems: list[str] = []
    print("=== Business Readiness Audit ===\n")

    # 1) KPI-Konsistenz
    from core.daten_speicher import DatenSpeicher
    from core.dashboard_ops import heute_operations
    from core.decision_engine import analysiere_alle_mandanten, _berechne_risiko_daten

    store = DatenSpeicher(kanzlei_id="default")
    ops = heute_operations(store)
    dash_ueber = int(ops.get("aufgaben_ueberfaellig") or 0)
    summe_kpi = 0
    mandanten = store.hole_mandanten() or {}
    if not mandanten:
        _fail("Keine Mandanten in DB — Profit/KPI-Tests übersprungen", problems)
    else:
        for name, m in mandanten.items():
            if not isinstance(m, dict):
                continue
            risiko = _berechne_risiko_daten(name, m, store)
            summe_kpi += int(risiko.get("aufgaben_ueberfaellig") or 0)
        if summe_kpi != dash_ueber:
            _fail(f"KPI: Summe Mandanten ({summe_kpi}) != Heute-Ops ({dash_ueber})", problems)
        else:
            print(f"[OK] KPI/Heute-Ops überfällig: {dash_ueber}")

    # 2) Dashboard /dashboard vs heute_operations
    from datetime import datetime
    from core.aufgabe_erledigt import aufgabe_ist_erledigt
    from core.frist_utils import tage_bis_frist

    aufgaben = store.hole_fristen()
    heute = datetime.now().date()
    dash_count = 0
    for a in aufgaben.values():
        if not isinstance(a, dict) or aufgabe_ist_erledigt(a):
            continue
        t = tage_bis_frist(a.get("frist"), heute=heute)
        if t is not None and t < 0:
            dash_count += 1
    if dash_count != dash_ueber:
        _fail(f"Dashboard-Zählung ({dash_count}) != heute_operations ({dash_ueber})", problems)
    else:
        print(f"[OK] /dashboard KPI Überfällig = {dash_count}")

    # 3) Profit Monitor (erster Mandant)
    if mandanten:
        first = next(iter(mandanten.keys()))
        from core.profit_monitor import ProfitMonitor

        pm = ProfitMonitor(store)
        try:
            p = pm.berechne_profit(first, 30)
            for key in ("honorar_netto", "aufwand_euro", "profit_euro", "marge_prozent", "status"):
                if key not in p:
                    _fail(f"Profit fehlt Feld {key}", problems)
            if p.get("status") not in ("profitabel", "ok", "warnung", "verlust"):
                _fail(f"Profit ungültiger status: {p.get('status')}", problems)
            ranking = pm.profit_ranking(30)
            if not isinstance(ranking, list):
                _fail("profit_ranking liefert keine Liste", problems)
            ue = pm.kanzlei_uebersicht(30)
            if "gesamt_profit" not in ue:
                _fail("kanzlei_uebersicht fehlt gesamt_profit", problems)
            if not problems or problems[-1].startswith("Profit"):
                pass
            print(f"[OK] Profit Monitor ({first}: status={p.get('status')}, marge={p.get('marge_prozent')}%)")
        except Exception as e:
            _fail(f"Profit Monitor: {e}", problems)

    # 4) Finanzierung + ML-Buchung Import
    try:
        from core.finanzierung_service import FinanzierungService, FINANZIERUNGS_PARTNER
        from core.ml_buchung import MLBuchungsassistent

        assert FINANZIERUNGS_PARTNER
        FinanzierungService(store)
        MLBuchungsassistent()
        print("[OK] Finanzierung + ML-Buchung Module laden")
    except Exception as e:
        _fail(f"Module Finanzierung/ML: {e}", problems)

    # 5) Billing + Dashboard API (TestClient, bestehendes DATA_DIR)
    try:
        import api
        from fastapi.testclient import TestClient
    except Exception as e:
        _fail(f"API-Import: {e}", problems)
        api = None  # type: ignore

    auth_ok = False
    h: dict[str, str] = {}
    if api is not None:
        c = TestClient(api.app)
        tag = uuid.uuid4().hex[:8]
        pw = "AuditPass9!Extra"
        user = f"biz_{tag}"
        mail = f"biz_{tag}@example.com"
        try:
            r = c.post(
                "/auth/registrieren",
                json={"benutzername": user, "passwort": pw, "rolle": "admin", "email": mail},
            )
            if r.status_code >= 400:
                _fail(f"Registrierung: {r.status_code} {r.text[:120]}", problems)
            else:
                l = c.post("/auth/login", json={"benutzername": user, "passwort": pw})
                if l.status_code >= 400:
                    _fail(f"Login: {l.status_code}", problems)
                else:
                    body = l.json()
                    tok = (body.get("data") or body).get("token") or (body.get("data") or body).get("access_token")
                    h = {"Authorization": f"Bearer {tok}"}
                    auth_ok = bool(tok)
                    c.put("/settings", headers=h, json={"key": "billing_aktiv", "wert": True})
                    b = c.get("/billing/usage", headers=h)
                    if b.status_code != 200:
                        _fail(f"billing/usage: {b.status_code}", problems)
                    else:
                        print("[OK] Billing usage (aktiviert)")
                    m = c.get("/billing/metrics", headers=h)
                    if m.status_code != 200:
                        _fail(f"billing/metrics: {m.status_code}", problems)
                    else:
                        data = m.json().get("data") or m.json()
                        if "mrr_estimate" not in data:
                            _fail("billing/metrics ohne mrr_estimate", problems)
                        else:
                            print(f"[OK] Billing metrics MRR-Schätzung: {data.get('mrr_estimate')}")
                    f = c.post("/billing/funnel/event", headers=h, json={"stage": "audit_check", "meta": {}})
                    if f.status_code >= 400:
                        _fail(f"billing/funnel/event: {f.status_code}", problems)
                    else:
                        print("[OK] Billing-Funnel Event")
        except Exception as e:
            _fail(f"Billing-API-Laufzeit: {e}", problems)

        if auth_ok:
            ho = c.get("/dashboard/heute-ops", headers=h)
            if ho.status_code != 200:
                _fail(f"dashboard/heute-ops: {ho.status_code}", problems)
            else:
                print("[OK] GET /dashboard/heute-ops")
            kp = c.get("/kpis", headers=h)
            if kp.status_code != 200:
                _fail(f"/kpis: {kp.status_code}", problems)
            else:
                print("[OK] GET /kpis")

    print()
    if problems:
        print("ERGEBNIS: FAIL")
        for p in problems:
            print(f"  - {p}")
        print("\nHinweis Produktion: billing_aktiv=1, STRIPE_* Keys, Mandanten-Umsatz/Zeiterfassung für echte Profit-Zahlen.")
        return 2
    print("ERGEBNIS: PASS (automatisierte Business-Checks)")
    print("\nProduktion für Umsatz/Verkauf zusätzlich prüfen:")
    print("  - Einstellungen: billing_aktiv, Stripe Price-IDs, stundensatz")
    print("  - Profit: Rechnungen + Zeiterfassung pflegen (sonst Schätzung aus Umsatz)")
    print("  - Pilot/Bot: Fragen stellen/beantworten für Scorecard > 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# ============================================================
# KANZLEI AI — PROFIT MONITOR v1.0
# Datei: core/profit_monitor.py
#
# Beantwortet die wichtigste Frage jeder Kanzlei:
# "Verdiene ich an diesem Mandant Geld — oder lege ich drauf?"
#
# Features:
#   ✓ Echtzeit-Profitabilität pro Mandant
#   ✓ Aufwand vs. Honorar (aus Zeiterfassung)
#   ✓ Automatischer Honoraranpassungsvorschlag
#   ✓ Mandanten-Ranking nach Profitabilität
#   ✓ Trend-Analyse (wird es besser/schlechter?)
#   ✓ Stundensatz-Optimierung
# ============================================================

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

log = logging.getLogger("kanzlei_profit")

STANDARD_STUNDENSATZ = 150.0   # €/h — aus Settings überschreibbar
ZIEL_MARGE_PROZENT   = 40.0    # 40% Gewinnmarge als Ziel
WARNUNG_MARGE        = 20.0    # Unter 20% → Warnung
KRITISCH_MARGE       = 0.0     # Unter 0% → kritisch (Verlust)


class ProfitMonitor:

    def __init__(self, ds):
        self.ds = ds

    def _stundensatz(self) -> float:
        from core.tenant_settings import tenant_float
        return tenant_float(self.ds, "stundensatz", STANDARD_STUNDENSATZ)

    # ── Profit für einen Mandant ─────────────────────────────
    def berechne_profit(
        self,
        mandant: str,
        zeitraum_tage: int = 30,
    ) -> Dict:
        """
        Berechnet Profitabilität für einen Mandant im Zeitraum.

        Returns:
            {
              honorar, aufwand_stunden, aufwand_euro,
              profit_euro, marge_prozent, status,
              honoraranpassung_vorschlag
            }
        """
        m = self.ds.hole_mandanten().get(mandant, {})
        if not m:
            raise ValueError(f"Mandant '{mandant}' nicht gefunden")

        stundensatz = self._stundensatz()
        jetzt       = datetime.now()
        von         = (jetzt - timedelta(days=zeitraum_tage)).isoformat()

        # ── Honorar aus Rechnungen ────────────────────────────
        rechnungen_alle = self.ds.rechnungen_liste()
        zeiterfassung = self.ds.zeiterfassung_holen()
        rechnungen = [
            r for r in rechnungen_alle
            if r.get("mandant") == mandant and
            r.get("datum", "") >= von[:10] and
            r.get("status") in ["offen", "bezahlt"]
        ]
        honorar_brutto = sum(r.get("gesamt_brutto", 0) for r in rechnungen)
        honorar_netto  = sum(r.get("gesamt_netto",  0) for r in rechnungen)

        # ── Aufwand aus Zeiterfassung ─────────────────────────
        zeiteintraege = [
            e for e in zeiterfassung.get("eintraege", {}).values()
            if e.get("mandant") == mandant and e.get("start", "") >= von and e.get("ende")
        ]
        aufwand_min    = sum(e.get("dauer_min", 0) for e in zeiteintraege)
        aufwand_std    = round(aufwand_min / 60, 2)
        aufwand_euro   = round(aufwand_std * stundensatz, 2)

        # ── Wenn keine Zeiteinträge: Pauschalstunden aus Mandant oder 0 ─
        aufwand_geschaetzt = False
        if aufwand_std == 0:
            pauschal_std = float(m.get("schaetz_stunden_monat") or m.get("bearbeitungsstunden_monat") or 0)
            if pauschal_std > 0:
                aufwand_std = round(pauschal_std, 2)
                aufwand_geschaetzt = True
            aufwand_euro = round(aufwand_std * stundensatz, 2)

        honorar_geschaetzt = False
        # ── Honorar: Rechnungen > Pauschalhonorar > Soll aus Aufwand ─────
        if honorar_netto == 0:
            pauschal = float(m.get("honorar_monat") or m.get("pauschal_honorar") or 0)
            if pauschal > 0:
                honorar_netto = round(pauschal, 2)
                honorar_brutto = round(pauschal * 1.19, 2)
            elif aufwand_euro > 0:
                honorar_netto = round(aufwand_euro / (1 - ZIEL_MARGE_PROZENT / 100), 2)
                honorar_brutto = round(honorar_netto * 1.19, 2)
                honorar_geschaetzt = True

        # ── Profit-Berechnung ─────────────────────────────────
        if honorar_netto <= 0 and aufwand_euro <= 0:
            profit_euro = 0.0
            marge_prozent = 0.0
            status = "keine_daten"
        else:
            profit_euro  = round(honorar_netto - aufwand_euro, 2)
            marge_prozent = round(profit_euro / honorar_netto * 100, 1) if honorar_netto > 0 else -100.0
            if marge_prozent >= ZIEL_MARGE_PROZENT:
                status = "profitabel"
            elif marge_prozent >= WARNUNG_MARGE:
                status = "ok"
            elif marge_prozent >= KRITISCH_MARGE:
                status = "warnung"
            else:
                status = "verlust"

        anpassung = None
        if status not in ("keine_daten",):
            anpassung = self._honoraranpassung_vorschlag(
                mandant, m, honorar_netto, aufwand_euro, marge_prozent, aufwand_std
            )

        # ── Tatsächlicher Stundensatz (was verdiene ich wirklich?) ─
        effektiver_stundensatz = round(honorar_netto / aufwand_std, 2) if aufwand_std > 0 else stundensatz

        return {
            "mandant":                  mandant,
            "zeitraum_tage":            zeitraum_tage,
            "von":                      von[:10],
            "bis":                      jetzt.strftime("%Y-%m-%d"),
            "honorar_netto":            honorar_netto,
            "honorar_brutto":           honorar_brutto,
            "aufwand_stunden":          aufwand_std,
            "aufwand_euro":             aufwand_euro,
            "profit_euro":              profit_euro,
            "marge_prozent":            marge_prozent,
            "status":                   status,
            "effektiver_stundensatz":   effektiver_stundensatz,
            "ziel_stundensatz":         stundensatz,
            "rechnungen_anzahl":        len(rechnungen),
            "zeiteintraege_anzahl":     len(zeiteintraege),
            "honoraranpassung":         anpassung,
            "berechnet_am":             datetime.now().isoformat(),
            "daten_vollstaendig":       len(zeiteintraege) > 0 and len(rechnungen) > 0,
            "honorar_geschaetzt":       honorar_geschaetzt,
            "aufwand_geschaetzt":       aufwand_geschaetzt,
            "hinweis": (
                "Honorar/Aufwand geschätzt — Zeiterfassung und Rechnungen erfassen für belastbare Marge."
                if (honorar_geschaetzt or aufwand_geschaetzt or not len(rechnungen))
                else ""
            ),
        }

    def _honoraranpassung_vorschlag(
        self,
        mandant: str,
        m: Dict,
        honorar: float,
        aufwand: float,
        marge: float,
        stunden: float,
    ) -> Optional[Dict]:
        """Automatischer Honoraranpassungsvorschlag wenn Marge zu niedrig."""
        if marge >= ZIEL_MARGE_PROZENT:
            return None  # Alles gut, keine Anpassung nötig

        stundensatz = self._stundensatz()

        # Ziel-Honorar für 40% Marge
        ziel_honorar   = round(aufwand / (1 - ZIEL_MARGE_PROZENT/100), 2)
        differenz      = round(ziel_honorar - honorar, 2)
        differenz_pct  = round(differenz / honorar * 100, 1) if honorar > 0 else 0

        if differenz <= 0:
            return None

        jahres_differenz = round(differenz * 12, 2)

        grund = (
            "Verlustgeschäft — sofortige Anpassung empfohlen" if marge < 0 else
            f"Marge {marge}% liegt unter Ziel von {ZIEL_MARGE_PROZENT}%"
        )

        return {
            "empfohlen":          True,
            "grund":              grund,
            "aktuelles_honorar":  honorar,
            "empfohlenes_honorar":ziel_honorar,
            "differenz_euro":     differenz,
            "differenz_prozent":  differenz_pct,
            "jahres_mehreinnahme":jahres_differenz,
            "dringlichkeit":      "kritisch" if marge < 0 else "hoch" if marge < 20 else "mittel",
            "email_vorlage":      self._honorar_email(mandant, honorar, ziel_honorar, differenz_pct),
        }

    def _honorar_email(self, mandant: str, aktuell: float, neu: float, pct: float) -> str:
        return f"""Sehr geehrte/r {mandant},

aufgrund des gestiegenen Bearbeitungsaufwands für Ihr Mandat
möchten wir Ihnen mitteilen, dass wir eine Honoraranpassung
vornehmen werden.

Aktuelles Honorar: €{aktuell:,.2f}/Monat
Neues Honorar:     €{neu:,.2f}/Monat (+{pct:.1f}%)

Die Anpassung ist erforderlich, da der tatsächliche Aufwand
für die Betreuung Ihres Mandats gestiegen ist.

Wir stehen Ihnen für Rückfragen gerne zur Verfügung.

Mit freundlichen Grüßen
Ihre Kanzlei"""

    # ── Alle Mandanten ranken ───────────────────────────────
    def profit_ranking(self, zeitraum_tage: int = 30) -> List[Dict]:
        """
        Alle Mandanten nach Profitabilität ranken.
        Zeigt sofort: Wer bringt Geld, wer kostet Geld?
        """
        mandanten = self.ds.hole_mandanten()
        ranking   = []

        for name in mandanten:
            try:
                p = self.berechne_profit(name, zeitraum_tage)
                ranking.append({
                    "mandant":            name,
                    "profit_euro":        p["profit_euro"],
                    "marge_prozent":      p["marge_prozent"],
                    "honorar_netto":      p["honorar_netto"],
                    "aufwand_stunden":    p["aufwand_stunden"],
                    "status":             p["status"],
                    "anpassung_nötig":    p["honoraranpassung"] is not None,
                })
            except Exception as e:
                log.warning(f"Profit-Berechnung für {name}: {e}")

        return sorted(ranking, key=lambda x: x["profit_euro"], reverse=True)

    def kanzlei_uebersicht(self, zeitraum_tage: int = 30) -> Dict:
        """Gesamtübersicht der Kanzlei-Profitabilität."""
        ranking = self.profit_ranking(zeitraum_tage)
        if not ranking:
            return {"fehler": "Keine Mandanten"}

        gesamt_honorar = sum(r["honorar_netto"] for r in ranking)
        gesamt_aufwand = sum(
            r["aufwand_stunden"] * self._stundensatz() for r in ranking
        )
        gesamt_profit  = sum(r["profit_euro"] for r in ranking)
        gesamt_marge   = round(gesamt_profit / gesamt_honorar * 100, 1) if gesamt_honorar else 0

        verlust_mandanten  = [r for r in ranking if r["status"] == "verlust"]
        warnung_mandanten  = [r for r in ranking if r["status"] == "warnung"]
        anpassung_mandanten= [r for r in ranking if r["anpassung_nötig"]]

        potenzial_euro = sum(
            max(0, r["honorar_netto"] * (ZIEL_MARGE_PROZENT/100) - r["profit_euro"])
            for r in ranking
        )

        return {
            "zeitraum_tage":          zeitraum_tage,
            "mandanten_gesamt":       len(ranking),
            "gesamt_honorar":         round(gesamt_honorar, 2),
            "gesamt_aufwand":         round(gesamt_aufwand, 2),
            "gesamt_profit":          round(gesamt_profit, 2),
            "gesamt_marge_prozent":   gesamt_marge,
            "verlust_mandanten":      len(verlust_mandanten),
            "warnung_mandanten":      len(warnung_mandanten),
            "anpassung_empfohlen":    len(anpassung_mandanten),
            "potenzial_euro_jährlich":round(potenzial_euro * 12, 2),
            "top3_profitabel":        ranking[:3],
            "top3_verlustreich":      sorted(ranking, key=lambda x: x["profit_euro"])[:3],
            "ranking":                ranking,
            "berechnet_am":           datetime.now().isoformat(),
        }

    def branchen_benchmarking(self, mandant: str) -> Dict:
        """
        Vergleicht Mandant mit Branchendurchschnitt der anderen Mandanten.
        "Dein Personalaufwand ist 15% höher als beim Durchschnitt deiner Branche."
        """
        mandanten = self.ds.hole_mandanten()
        m         = mandanten.get(mandant, {})
        branche   = m.get("branche", "")

        # Alle Mandanten der gleichen Branche
        gleiche_branche = {
            name: md for name, md in mandanten.items()
            if md.get("branche") == branche and name != mandant and branche
        }

        if not gleiche_branche:
            # Fallback: alle Mandanten
            gleiche_branche = {n: md for n, md in mandanten.items() if n != mandant}
            branche_label   = "alle Mandanten"
        else:
            branche_label = branche

        if not gleiche_branche:
            return {"hinweis": "Keine Vergleichsdaten verfügbar"}

        # Profit-Daten für Vergleichsgruppe
        vergleich_profits = []
        for vname in list(gleiche_branche.keys())[:10]:  # Max 10
            try:
                vp = self.berechne_profit(vname, 30)
                vergleich_profits.append(vp)
            except Exception:
                pass

        if not vergleich_profits:
            return {"hinweis": "Keine Vergleichsdaten verfügbar"}

        # Mein Profit
        mein_profit = self.berechne_profit(mandant, 30)

        # Durchschnitte
        ø_honorar  = sum(p["honorar_netto"]    for p in vergleich_profits) / len(vergleich_profits)
        ø_stunden  = sum(p["aufwand_stunden"]  for p in vergleich_profits) / len(vergleich_profits)
        ø_marge    = sum(p["marge_prozent"]    for p in vergleich_profits) / len(vergleich_profits)

        # Abweichungen
        honorar_diff = round((mein_profit["honorar_netto"] - ø_honorar) / ø_honorar * 100, 1) if ø_honorar else 0
        stunden_diff = round((mein_profit["aufwand_stunden"] - ø_stunden) / ø_stunden * 100, 1) if ø_stunden else 0
        marge_diff   = round(mein_profit["marge_prozent"] - ø_marge, 1)

        # Insights generieren
        insights = []
        if abs(stunden_diff) > 15:
            richtung = "höher" if stunden_diff > 0 else "niedriger"
            insights.append(
                f"Der Bearbeitungsaufwand ist {abs(stunden_diff):.0f}% {richtung} "
                f"als beim Durchschnitt ({branche_label})."
            )
        if abs(honorar_diff) > 10:
            richtung = "über" if honorar_diff > 0 else "unter"
            insights.append(
                f"Das Honorar liegt {abs(honorar_diff):.0f}% {richtung} dem Branchenschnitt."
            )
        if marge_diff < -10:
            insights.append(
                f"Die Marge ist {abs(marge_diff):.0f} Prozentpunkte unter dem Schnitt — "
                f"Honoraranpassung prüfen."
            )
        if not insights:
            insights.append(f"Liegt im normalen Bereich für {branche_label}.")

        return {
            "mandant":             mandant,
            "branche":             branche_label,
            "vergleichsgruppe":    len(vergleich_profits),
            "mein_honorar":        mein_profit["honorar_netto"],
            "ø_honorar":           round(ø_honorar, 2),
            "mein_aufwand_std":    mein_profit["aufwand_stunden"],
            "ø_aufwand_std":       round(ø_stunden, 2),
            "meine_marge":         mein_profit["marge_prozent"],
            "ø_marge":             round(ø_marge, 1),
            "honorar_abweichung":  honorar_diff,
            "aufwand_abweichung":  stunden_diff,
            "marge_abweichung":    marge_diff,
            "insights":            insights,
            "berechnet_am":        datetime.now().isoformat(),
        }
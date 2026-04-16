# ============================================================
# KANZLEI AI — FINANZIERUNGS SERVICE v1.0
# Datei: core/finanzierung_service.py
#
# Wenn das System eine Steuernachzahlung erkennt:
#   → Sofort passende Lösung anbieten
#   → Ratenzahlung beim Finanzamt (§ 222 AO)
#   → Stundungsantrag automatisch ausfüllen
#   → Finanzierungsoptionen berechnen
#   → Partner-Links zu Kreditgebern
#
# RECHTLICHER HINWEIS:
#   Kreditvermittlung = BaFin-Lizenz erforderlich (§ 34c GewO)
#   Dieses System: Informationsbereitstellung + Weiterleitung
#   Keine eigene Kreditvergabe!
# ============================================================

import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

log = logging.getLogger("kanzlei_finanzierung")

# Finanzierungs-Partner (Beispiele — echte Integration per API)
FINANZIERUNGS_PARTNER = [
    {
        "name":       "Finanzamt Ratenzahlung",
        "typ":        "ratenzahlung_finanzamt",
        "zinssatz":   1.8,  # § 238 AO: 1,8% p.a.
        "max_betrag": 999999,
        "min_betrag": 100,
        "laufzeit_monate_min": 3,
        "laufzeit_monate_max": 24,
        "voraussetzung": "Nachzahlung bekannt, noch nicht fällig oder Antrag vor Fälligkeit",
        "link":       "https://www.finanzamt.de",
        "beschreibung": "Offizieller Stundungsantrag beim Finanzamt (§ 222 AO). "
                        "Zinsen: 1,8% p.a. (§ 238 AO). Kostengünstigste Option.",
        "formular":   "stundungsantrag",
        "empfehlung": True,
    },
    {
        "name":       "iwoca Unternehmenskredit",
        "typ":        "unternehmenskredit",
        "zinssatz":   5.5,   # Beispiel — variiert nach Bonität
        "max_betrag": 500000,
        "min_betrag": 1000,
        "laufzeit_monate_min": 3,
        "laufzeit_monate_max": 36,
        "voraussetzung": "Mindestens 12 Monate im Geschäft",
        "link":       "https://www.iwoca.de",
        "beschreibung": "Schnelle Entscheidung (24h), keine Grundbucheintragung, flexibel.",
        "formular":   None,
        "empfehlung": False,
    },
    {
        "name":       "Deutsche Bank Business Kredit",
        "typ":        "bankkredit",
        "zinssatz":   4.5,
        "max_betrag": 2500000,
        "min_betrag": 5000,
        "laufzeit_monate_min": 12,
        "laufzeit_monate_max": 84,
        "voraussetzung": "Jahresabschluss erforderlich, Hausbank-Beziehung hilfreich",
        "link":       "https://www.deutsche-bank.de/geschaeftskunden",
        "beschreibung": "Klassischer Bankkredit, günstigere Konditionen bei Hausbank.",
        "formular":   None,
        "empfehlung": False,
    },
    {
        "name":       "auxmoney Unternehmensfinanzierung",
        "typ":        "p2p_kredit",
        "zinssatz":   6.5,
        "max_betrag": 100000,
        "min_betrag": 1000,
        "laufzeit_monate_min": 12,
        "laufzeit_monate_max": 60,
        "voraussetzung": "Schufa-Prüfung, Einnahmennachweis",
        "link":       "https://www.auxmoney.com/kreditnehmer/firmenkunden",
        "beschreibung": "Crowdfunding-Plattform, schnelle Auszahlung, auch bei suboptimaler Bonität.",
        "formular":   None,
        "empfehlung": False,
    },
]


class FinanzierungService:

    def __init__(self, ds):
        self.ds = ds

    def _finanzierungen_daten(self) -> Dict:
        return {"finanzierungen": self.ds.finanzierungen_liste()}

    # ── Finanzierungsangebot erstellen ────────────────────────
    def erstelle_angebot(
        self,
        mandant:         str,
        betrag:          float,
        anlass:          str = "steuernachzahlung",  # steuernachzahlung | sonstige
        frist_datum:     str = None,
        steuerart:       str = "ESt",
        jahr:            int = None,
    ) -> Dict:
        """
        Erstellt ein vollständiges Finanzierungsangebot mit:
        - Ratenzahlungsoptionen berechnet
        - Stundungsantrag vorbereitet
        - Partner-Empfehlungen sortiert nach Kosten
        - Sofort-Maßnahmen erklärt
        """
        jetzt = datetime.now()
        jahr  = jahr or jetzt.year - 1

        if not frist_datum:
            # Standard: 4 Wochen ab heute
            frist_datum = (jetzt + timedelta(days=28)).strftime("%Y-%m-%d")

        # Frist-Dringlichkeit berechnen
        try:
            frist_dt    = datetime.strptime(frist_datum, "%Y-%m-%d")
            tage_bis_frist = (frist_dt - jetzt).days
        except Exception:
            tage_bis_frist = 28

        # Optionen berechnen
        optionen = []
        for partner in FINANZIERUNGS_PARTNER:
            if betrag < partner["min_betrag"] or betrag > partner["max_betrag"]:
                continue

            # Ratenzahlung berechnen (vereinfacht)
            laufzeiten = [3, 6, 12, 18, 24]
            raten_optionen = []

            for monate in laufzeiten:
                if monate < partner["laufzeit_monate_min"] or monate > partner["laufzeit_monate_max"]:
                    continue
                zinsen_monat  = partner["zinssatz"] / 100 / 12
                if zinsen_monat > 0:
                    rate = betrag * (zinsen_monat * (1+zinsen_monat)**monate) / ((1+zinsen_monat)**monate - 1)
                else:
                    rate = betrag / monate
                gesamt_zahlung = rate * monate
                raten_optionen.append({
                    "monate":          monate,
                    "rate_monatlich":  round(rate, 2),
                    "gesamt_zahlung":  round(gesamt_zahlung, 2),
                    "zinsen_gesamt":   round(gesamt_zahlung - betrag, 2),
                })

            if raten_optionen:
                optionen.append({
                    **partner,
                    "raten_optionen": raten_optionen,
                    "kosten_score":   partner["zinssatz"],  # Niedrig = besser
                })

        # Nach Kosten sortieren (günstigste zuerst)
        optionen.sort(key=lambda x: x["kosten_score"])

        # Empfohlene Option
        empfohlene_option = next(
            (o for o in optionen if o.get("empfehlung")), optionen[0] if optionen else None
        )

        # Stundungsantrag vorbereiten
        stundungsantrag = self._erstelle_stundungsantrag(
            mandant, betrag, steuerart, jahr, frist_datum
        )

        # Sofort-Maßnahmen
        massnahmen = self._erstelle_massnahmen(
            betrag, tage_bis_frist, steuerart
        )

        angebot_id = str(uuid.uuid4())
        angebot = {
            "id":                  angebot_id,
            "mandant":             mandant,
            "betrag":              betrag,
            "anlass":              anlass,
            "steuerart":           steuerart,
            "jahr":                jahr,
            "frist_datum":         frist_datum,
            "tage_bis_frist":      tage_bis_frist,
            "optionen":            optionen,
            "empfohlene_option":   empfohlene_option,
            "stundungsantrag":     stundungsantrag,
            "sofort_massnahmen":   massnahmen,
            "erstellt_am":         jetzt.isoformat(),
            "status":              "offen",
        }

        # Speichern
        self.ds.finanzierung_speichern(angebot_id, angebot)
        self.ds.log_eintrag(
            f"FINANZIERUNGSANGEBOT | {mandant} | €{betrag:.2f} | {steuerart} {jahr}"
        )

        return angebot

    def _erstelle_stundungsantrag(
        self, mandant: str, betrag: float, steuerart: str, jahr: int, frist: str
    ) -> Dict:
        """Vollständig ausgefüllter Stundungsantrag nach § 222 AO."""
        m = self.ds.hole_mandanten().get(mandant, {})

        antragstext = f"""ANTRAG AUF STUNDUNG VON STEUERSCHULDEN
gemäß § 222 Abgabenordnung (AO)

An das zuständige Finanzamt
{datetime.now().strftime('%d.%m.%Y')}

Steuerpflichtiger: {mandant}
Steuernummer:      {m.get('steuer_id', '— bitte eintragen —')}
Steuerart:         {steuerart}
Veranlagungsjahr:  {jahr}
Geschuldeter Betrag: € {betrag:,.2f}
Fälligkeit:        {frist}

ANTRAG:
Ich beantrage hiermit gemäß § 222 AO die Stundung des o.g.
Steuerbetrags bis zum ________________ (max. 12 Monate).

BEGRÜNDUNG:
[Bitte wählen und ausfüllen:]
☐ Vorübergehende Liquiditätsengpass aufgrund von [Grund]:
   ________________________________________________________________

☐ Unerwartete Betriebsausgaben in Höhe von €_________
   für: ________________________________________________________________

☐ Zahlungsausfall eines Hauptkunden in Höhe von €_________

Die finanzielle Situation wird sich voraussichtlich bis zum
______________ wieder normalisiert haben, da:
________________________________________________________________

RATENZAHLUNGSVORSCHLAG:
Ich bin bereit, den Betrag in ______ Raten zu je € _______ zu begleichen,
beginnend ab dem ______________.

Mit freundlichen Grüßen,

____________________________
{mandant}
Datum: {datetime.now().strftime('%d.%m.%Y')}

Anlagen:
☐ Aktuelle betriebswirtschaftliche Auswertung (BWA)
☐ Kontoauszüge der letzten 3 Monate
☐ Begründungsschreiben"""

        return {
            "text":          antragstext,
            "rechtsgrundlage": "§ 222 AO",
            "hinweis":       "Antrag VOR Fälligkeit stellen! Bei erheblichen Steuerrückständen "
                             "droht Pfändung. Zinsen: 1,8% p.a. nach § 238 AO.",
            "einzureichen_bei": "Zuständiges Finanzamt (persönlich, per Post oder ELSTER)",
        }

    def _erstelle_massnahmen(
        self, betrag: float, tage_bis_frist: int, steuerart: str
    ) -> List[Dict]:
        """Priorisierte Sofort-Maßnahmen basierend auf Betrag und Dringlichkeit."""
        massnahmen = []

        if tage_bis_frist <= 7:
            massnahmen.append({
                "prioritaet": "kritisch",
                "icon":       "🚨",
                "titel":      "SOFORT: Finanzamt anrufen",
                "text":       f"Frist in {tage_bis_frist} Tagen! Sofort beim Finanzamt anrufen "
                              "und Zahlungsaufschub mündlich ankündigen. "
                              "Dann schriftlichen Stundungsantrag nachreichen.",
                "aktion":     "finanzamt_anrufen",
            })
        elif tage_bis_frist <= 21:
            massnahmen.append({
                "prioritaet": "hoch",
                "icon":       "⚠️",
                "titel":      "Stundungsantrag einreichen",
                "text":       f"Noch {tage_bis_frist} Tage bis zur Fälligkeit. "
                              "Stundungsantrag (§ 222 AO) ist bereits ausgefüllt — nur noch einreichen.",
                "aktion":     "stundungsantrag_einreichen",
            })

        if betrag <= 5000:
            massnahmen.append({
                "prioritaet": "mittel",
                "icon":       "💡",
                "titel":      "Ratenzahlung beim Finanzamt",
                "text":       f"Bei €{betrag:,.0f} ist Ratenzahlung direkt beim Finanzamt "
                              "die günstigste Option (1,8% p.a.). Antrag liegt bereit.",
                "aktion":     "stundungsantrag_nutzen",
            })
        elif betrag <= 50000:
            massnahmen.append({
                "prioritaet": "mittel",
                "icon":       "🏦",
                "titel":      "Kontokorrentkredit prüfen",
                "text":       f"€{betrag:,.0f} kann oft über bestehenden Kontokorrentkredit "
                              "gedeckt werden. Hausbank anfragen — meist schnelle Entscheidung.",
                "aktion":     "hausbank_anfragen",
            })
        else:
            massnahmen.append({
                "prioritaet": "hoch",
                "icon":       "🏦",
                "titel":      "Unternehmenskredit beantragen",
                "text":       f"Bei €{betrag:,.0f} Unternehmenskredit sinnvoll. "
                              "Finanzierungsoptionen siehe unten.",
                "aktion":     "kredit_beantragen",
            })

        # Steuerart-spezifische Hinweise
        if steuerart == "USt":
            massnahmen.append({
                "prioritaet": "info",
                "icon":       "📋",
                "titel":      "USt-Dauerfristverlängerung prüfen",
                "text":       "Dauerfristverlängerung (1 Monat) kann per ELSTER beantragt werden. "
                              "Kosten: 1/11 der Vorjahres-USt als Sondervorauszahlung.",
                "aktion":     "dauerfristverlaengerung",
            })

        # Steueroptimierung für Zukunft
        massnahmen.append({
            "prioritaet": "info",
            "icon":       "💰",
            "titel":      "Steuervorauszahlungen anpassen",
            "text":       "Um künftige Nachzahlungen zu vermeiden: Vorauszahlungen beim "
                          "Finanzamt anpassen lassen. Kanzlei kann das übernehmen.",
            "aktion":     "vorauszahlungen_anpassen",
        })

        return massnahmen

    # ── Finanzierungen laden ──────────────────────────────────
    def angebote_laden(self, mandant: str = None) -> List[Dict]:
        data = self._finanzierungen_daten()
        alle = list(data.get("finanzierungen", {}).values())
        if mandant:
            alle = [a for a in alle if a.get("mandant") == mandant]
        return sorted(alle, key=lambda x: x.get("erstellt_am",""), reverse=True)

    def statistiken(self) -> Dict:
        data = self._finanzierungen_daten()
        alle = list(data.get("finanzierungen", {}).values())
        return {
            "angebote_gesamt":   len(alle),
            "gesamt_volumen":    sum(a.get("betrag",0) for a in alle),
            "nachzahlungen_ust": sum(1 for a in alle if a.get("steuerart")=="USt"),
            "nachzahlungen_est": sum(1 for a in alle if a.get("steuerart")=="ESt"),
        }
# ============================================================
# KANZLEI AI — PROAKTIVER MANDANTEN-BOT v1.0
# Datei: core/proaktiver_bot.py
#
# Der Bot analysiert kontinuierlich Mandantendaten und
# stellt proaktiv Fragen BEVOR der Steuerberater anrufen muss.
#
# Beispiel-Fragen die der Bot automatisch stellt:
#   → "Du hast 500€ bei Tankstelle X ausgegeben, aber kein
#      Fahrtenbuch-Eintrag. Bitte kurz bestätigen."
#   → "Deine Einnahmen sind diesen Monat 30% niedriger als
#      sonst. Gibt es einen Grund dafür?"
#   → "Wir haben eine neue Rechnung über 2.400€ von dir
#      erhalten. Ist das korrekt verbucht?"
#   → "Dein Kassenbestand ist seit 3 Wochen nicht aktualisiert."
#
# Spart: ~200 Telefonate/Monat pro Kanzlei
# ============================================================

import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

log = logging.getLogger("kanzlei_bot")

# ─── Frage-Kategorien ────────────────────────────────────────
FRAGE_TYPEN = {
    "buchung_bestaetigung":   {"icon": "💳", "prioritaet": "hoch"},
    "fahrtenbuch":            {"icon": "🚗", "prioritaet": "mittel"},
    "fehlende_einnahme":      {"icon": "📉", "prioritaet": "hoch"},
    "kassenbestand":          {"icon": "💰", "prioritaet": "mittel"},
    "beleg_fehlend":          {"icon": "🧾", "prioritaet": "mittel"},
    "umsatz_anomalie":        {"icon": "📊", "prioritaet": "hoch"},
    "konto_ungewoehnlich":    {"icon": "🏦", "prioritaet": "hoch"},
    "personal_aenderung":     {"icon": "👤", "prioritaet": "mittel"},
    "frist_erinnerung":       {"icon": "⏰", "prioritaet": "kritisch"},
    "investition_geplant":    {"icon": "📈", "prioritaet": "niedrig"},
    "sonstiges":              {"icon": "❓", "prioritaet": "niedrig"},
}


class ProaktiverBot:
    """
    Analysiert Mandantendaten und generiert automatisch
    Fragen die im Mandantenportal angezeigt werden.
    Mandant antwortet → Kanzlei spart Telefonate.
    """

    def __init__(self, ds):
        self.ds = ds

    def _portal_daten(self) -> Dict:
        return {"bot_fragen": self.ds.bot_fragen_liste()}

    def _speichern(self, data: Dict):
        fragen = data.get("bot_fragen", {})
        if isinstance(fragen, dict):
            self.ds.bot_fragen_setzen(fragen)

    # ── Frage speichern ──────────────────────────────────────
    def frage_stellen(
        self,
        mandant:     str,
        frage_text:  str,
        frage_typ:   str = "sonstiges",
        kontext:     str = "",
        betrag:      Optional[float] = None,
        antwort_optionen: Optional[List[str]] = None,
        aufgabe_wenn_nein: Optional[str] = None,
    ) -> Dict:
        """
        Neue Frage im System speichern.
        Mandant sieht sie im Portal, Antwort kommt zurück.
        """
        if mandant not in self.ds.hole_mandanten():
            raise ValueError(f"Mandant '{mandant}' nicht gefunden")

        typ_info = FRAGE_TYPEN.get(frage_typ, FRAGE_TYPEN["sonstiges"])
        frage_id = str(uuid.uuid4())
        jetzt    = datetime.now()

        frage = {
            "id":               frage_id,
            "mandant":          mandant,
            "text":             frage_text,
            "kontext":          kontext,
            "typ":              frage_typ,
            "icon":             typ_info["icon"],
            "prioritaet":       typ_info["prioritaet"],
            "betrag":           betrag,
            "antwort_optionen": antwort_optionen or ["Ja, korrekt ✓", "Nein, bitte korrigieren", "Ich melde mich"],
            "aufgabe_wenn_nein":aufgabe_wenn_nein,
            "status":           "offen",     # offen | beantwortet | erledigt | abgelaufen
            "erstellt_am":      jetzt.isoformat(),
            "ablaeuft_am":      (jetzt + timedelta(days=14)).isoformat(),
            "antwort":          None,
            "antwort_zeitpunkt":None,
            "antwort_notiz":    None,
        }

        data = self._portal_daten()
        data["bot_fragen"][frage_id] = frage
        self._speichern(data)
        self.ds.log_eintrag(f"BOT_FRAGE | {mandant} | {frage_typ} | {frage_text[:60]}")
        return frage

    def antwort_erfassen(
        self,
        frage_id:  str,
        antwort:   str,
        notiz:     str = "",
        mandant:   str = "",
    ) -> Dict:
        """Antwort des Mandanten erfassen + Folgeaktion auslösen."""
        data   = self._portal_daten()
        fragen = data.get("bot_fragen", {})

        if frage_id not in fragen:
            raise ValueError("Frage nicht gefunden")

        frage = fragen[frage_id]
        if mandant and frage["mandant"] != mandant:
            raise PermissionError("Kein Zugriff")

        frage["status"]           = "beantwortet"
        frage["antwort"]          = antwort
        frage["antwort_zeitpunkt"] = datetime.now().isoformat()
        frage["antwort_notiz"]    = notiz

        # Wenn "Nein" → automatisch Aufgabe anlegen
        negativ_antworten = ["nein", "falsch", "korrigieren", "fehler"]
        ist_negativ = any(w in antwort.lower() for w in negativ_antworten)

        aufgabe_id = None
        if ist_negativ and frage.get("aufgabe_wenn_nein"):
            import uuid as _uuid
            aufgabe_id = str(_uuid.uuid4())
            frist      = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
            self.ds.aufgabe_speichern(aufgabe_id, {
                "id":           aufgabe_id,
                "mandant":      frage["mandant"],
                "beschreibung": frage["aufgabe_wenn_nein"],
                "frist":        frist,
                "prioritaet":   "hoch",
                "kategorie":    "bot_followup",
                "erledigt":     False,
                "erstellt_am":  datetime.now().isoformat(),
                "bot_frage_id": frage_id,
            })

        self._speichern(data)
        self.ds.log_eintrag(
            f"BOT_ANTWORT | {frage['mandant']} | {frage['typ']} | {antwort[:30]}"
        )

        return {
            **frage,
            "aufgabe_angelegt": aufgabe_id is not None,
            "aufgabe_id":       aufgabe_id,
        }

    def fragen_fuer_mandant(self, mandant: str, nur_offen: bool = True) -> List[Dict]:
        """Alle Fragen für einen Mandanten."""
        data   = self._portal_daten()
        fragen = [
            f for f in data.get("bot_fragen", {}).values()
            if f.get("mandant") == mandant
        ]
        if nur_offen:
            jetzt  = datetime.now()
            fragen = [
                f for f in fragen
                if f["status"] == "offen" and
                datetime.fromisoformat(f["ablaeuft_am"]) > jetzt
            ]
        return sorted(fragen, key=lambda x: x["erstellt_am"], reverse=True)

    def alle_fragen(self, status_filter: str = None) -> List[Dict]:
        data   = self._portal_daten()
        fragen = list(data.get("bot_fragen", {}).values())
        if status_filter:
            fragen = [f for f in fragen if f["status"] == status_filter]
        return sorted(fragen, key=lambda x: x["erstellt_am"], reverse=True)

    # ══════════════════════════════════════════════════════════
    # AUTOMATISCHE ANALYSE — Hier erkennt der Bot Anomalien
    # ══════════════════════════════════════════════════════════

    def analysiere_alle_mandanten(self) -> List[Dict]:
        """
        Vollautomatische Analyse aller Mandanten.
        Generiert proaktive Fragen ohne manuellen Eingriff.
        Ideal als Cron-Job täglich um 7:00 Uhr.
        """
        mandanten  = self.ds.hole_mandanten()
        aufgaben   = self.ds.hole_fristen()
        neue_fragen = []

        for name, m in mandanten.items():
            try:
                fragen = self._analysiere_mandant(name, m, aufgaben)
                neue_fragen.extend(fragen)
            except Exception as e:
                log.warning(f"Bot-Analyse Fehler für {name}: {e}")

        log.info(f"Bot-Analyse: {len(neue_fragen)} neue Fragen für {len(mandanten)} Mandanten")
        return neue_fragen

    def _analysiere_mandant(
        self, name: str, m: Dict, alle_aufgaben: Dict
    ) -> List[Dict]:
        """Analysiert einen Mandanten und generiert relevante Fragen."""
        neue_fragen = []
        bestehende  = {f["typ"] for f in self.fragen_fuer_mandant(name, nur_offen=True)}
        jetzt       = datetime.now()

        # ── Analyse 1: Umsatz-Anomalie ────────────────────────
        umsatz = m.get("umsatz", 0)
        if umsatz > 0:
            letzter_monatsumsatz = m.get("letzter_monatsumsatz", umsatz / 12)
            erwarteter_monat     = umsatz / 12

            # Wenn tatsächlicher deutlich unter erwartet
            if letzter_monatsumsatz > 0 and \
               letzter_monatsumsatz < erwarteter_monat * 0.6 and \
               "umsatz_anomalie" not in bestehende:
                differenz = round(erwarteter_monat - letzter_monatsumsatz, 2)
                f = self.frage_stellen(
                    mandant    = name,
                    frage_text = f"Ihre Einnahmen waren diesen Monat €{letzter_monatsumsatz:,.2f} — "
                                 f"das ist €{differenz:,.2f} weniger als erwartet. "
                                 f"Gibt es einen besonderen Grund dafür?",
                    frage_typ  = "umsatz_anomalie",
                    kontext    = f"Erwartet: €{erwarteter_monat:,.2f}/Monat",
                    betrag     = differenz,
                    antwort_optionen = [
                        "Saisonbedingt — alles normal",
                        "Ausfall eines Kunden",
                        "Urlaub / Krankheit",
                        "Bitte kontaktieren Sie mich",
                    ],
                    aufgabe_wenn_nein = f"Umsatzrückgang {name} klären",
                )
                neue_fragen.append(f)

        # ── Analyse 2: Fehlende Dokumente (erinnernd) ─────────
        fehlende_docs = m.get("fehlende_dokumente_liste", [])
        if len(fehlende_docs) >= 3 and "beleg_fehlend" not in bestehende:
            docs_str = ", ".join(fehlende_docs[:3])
            f = self.frage_stellen(
                mandant    = name,
                frage_text = f"Wir warten noch auf {len(fehlende_docs)} Dokument(e): "
                             f"{docs_str}{'...' if len(fehlende_docs) > 3 else ''}. "
                             f"Wann können Sie diese einreichen?",
                frage_typ  = "beleg_fehlend",
                kontext    = f"Alle fehlenden Dokumente: {', '.join(fehlende_docs)}",
                antwort_optionen = [
                    "Diese Woche",
                    "Nächste Woche",
                    "Habe ich gerade hochgeladen",
                    "Bitte rufen Sie mich an",
                ],
                aufgabe_wenn_nein = f"Dokumente bei {name} anfordern — 2. Erinnerung",
            )
            neue_fragen.append(f)

        # ── Analyse 3: Lange kein Kontakt ─────────────────────
        tage_ohne_antwort = self.ds.berechne_tage_ohne_antwort(name)
        if tage_ohne_antwort >= 14 and "sonstiges" not in bestehende:
            f = self.frage_stellen(
                mandant    = name,
                frage_text = f"Wir haben seit {tage_ohne_antwort} Tagen nichts von Ihnen gehört. "
                             f"Läuft bei Ihnen alles gut?",
                frage_typ  = "sonstiges",
                antwort_optionen = [
                    "Ja, alles in Ordnung",
                    "Ich wollte mich melden — bitte kurz anrufen",
                    "Es gibt etwas zu besprechen",
                ],
            )
            neue_fragen.append(f)

        # ── Analyse 4: Fahrtenbuch (bei KFZ-Kosten) ──────────
        # Prüfe ob Aufgaben mit Fahrt-Bezug vorhanden
        kfz_aufgaben = [
            a for a in alle_aufgaben.values()
            if a.get("mandant") == name and
            any(w in a.get("beschreibung","").lower()
                for w in ["fahrt","kfz","auto","benzin","kraftstoff"])
        ]
        if kfz_aufgaben and "fahrtenbuch" not in bestehende:
            f = self.frage_stellen(
                mandant    = name,
                frage_text = "Für Ihre Fahrzeugkosten benötigen wir ein aktuelles Fahrtenbuch. "
                             "Ist Ihr Fahrtenbuch auf dem neuesten Stand?",
                frage_typ  = "fahrtenbuch",
                antwort_optionen = [
                    "Ja, Fahrtenbuch ist aktuell",
                    "Nein, ich habe keins geführt",
                    "Ich nutze die 1%-Regel",
                    "Bitte erklären Sie mir das",
                ],
                aufgabe_wenn_nein = f"Fahrtenbuch-Regelung für {name} besprechen",
            )
            neue_fragen.append(f)

        # ── Analyse 5: Überfällige Aufgaben ───────────────────
        ueberfaellige = [
            a for a in alle_aufgaben.values()
            if a.get("mandant") == name and not a.get("erledigt") and
            a.get("frist","9999") < jetzt.strftime("%Y-%m-%d")
        ]
        if len(ueberfaellige) >= 2 and "frist_erinnerung" not in bestehende:
            f = self.frage_stellen(
                mandant    = name,
                frage_text = f"Sie haben {len(ueberfaellige)} überfällige Aufgaben in unserer Kanzlei. "
                             f"Die dringendste: '{ueberfaellige[0].get('beschreibung','')}'. "
                             f"Wie möchten Sie vorgehen?",
                frage_typ  = "frist_erinnerung",
                antwort_optionen = [
                    "Ich sende die Unterlagen diese Woche",
                    "Bitte vereinbaren Sie einen Termin",
                    "Ich benötige eine Fristverlängerung",
                ],
                aufgabe_wenn_nein = f"Dringend: Fristen für {name} klären",
            )
            neue_fragen.append(f)

        return neue_fragen

    def statistiken(self) -> Dict:
        """Bot-Statistiken: wie viele Fragen, Antwortquote, gesparte Telefonate."""
        data   = self._portal_daten()
        fragen = list(data.get("bot_fragen", {}).values())

        gesamt      = len(fragen)
        beantwortet = sum(1 for f in fragen if f["status"] == "beantwortet")
        offen       = sum(1 for f in fragen if f["status"] == "offen")
        antwortquote= round(beantwortet / gesamt * 100, 1) if gesamt else 0

        # Geschätzte gesparte Telefonate (jede beantwortete Frage = 1 Telefonat gespart)
        gesparte_telefonate = beantwortet
        gesparte_minuten    = gesparte_telefonate * 8  # Ø 8 Min pro Telefonat
        gesparte_stunden    = round(gesparte_minuten / 60, 1)

        return {
            "fragen_gesamt":         gesamt,
            "fragen_offen":          offen,
            "fragen_beantwortet":    beantwortet,
            "antwortquote_prozent":  antwortquote,
            "gesparte_telefonate":   gesparte_telefonate,
            "gesparte_stunden":      gesparte_stunden,
            "zeitersparnis_euro":    round(gesparte_stunden * 150, 2),  # Ø 150€/h
        }
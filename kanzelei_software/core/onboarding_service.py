# ============================================================
# KANZLEI AI — ONBOARDING SERVICE v1.0
# Datei: core/onboarding_service.py
#
# Neue Kanzlei in 5 Minuten live:
#   Schritt 1: Kanzlei-Daten eingeben (30 Sek)
#   Schritt 2: Demo-Mandanten anlegen (automatisch)
#   Schritt 3: Erstes Erlebnis — KI bucht einen Demo-Beleg (60 Sek)
#
# Warum wichtig:
#   Time-to-Value < 5 Min → höchste Conversion
#   Jede Minute länger → 20% mehr Churn
# ============================================================

import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, List

log = logging.getLogger("kanzlei_onboarding")


# ─── Demo-Mandanten für sofortiges Erlebnis ──────────────────
DEMO_MANDANTEN = [
    {
        "name":       "Müller GmbH",
        "email":      "mueller@beispiel.de",
        "telefon":    "+49 89 123456",
        "branche":    "IT / Software",
        "umsatz":     180000,
        "betriebsausgaben": 95000,
        "beschreibung": "IT-Dienstleister, 4 Mitarbeiter",
        "fehlende_dokumente_liste": ["Kontoauszug Dezember", "Kreditkartenabrechnung Q4"],
        "steuer_id":  "123/456/78901",
    },
    {
        "name":       "Bäckerei Schmidt",
        "email":      "schmidt@baeckerei.de",
        "telefon":    "+49 30 987654",
        "branche":    "Gastronomie / Lebensmittel",
        "umsatz":     320000,
        "betriebsausgaben": 270000,
        "beschreibung": "Familienbäckerei, 8 Mitarbeiter",
        "fehlende_dokumente_liste": [],
        "steuer_id":  "234/567/89012",
    },
    {
        "name":       "Praxis Dr. Weber",
        "email":      "weber@praxis.de",
        "telefon":    "+49 69 555123",
        "branche":    "Gesundheitswesen",
        "umsatz":     420000,
        "betriebsausgaben": 180000,
        "beschreibung": "Hausarztpraxis, 3 Angestellte",
        "fehlende_dokumente_liste": ["Jahresabschluss 2024"],
        "steuer_id":  "345/678/90123",
    },
]

# ─── Demo-Aufgaben ────────────────────────────────────────────
DEMO_AUFGABEN = [
    {"mandant": "Müller GmbH",     "beschreibung": "USt-Voranmeldung Januar einreichen",
     "frist_tage": 5,  "prioritaet": "hoch",    "kategorie": "Steuern"},
    {"mandant": "Müller GmbH",     "beschreibung": "Kontoauszüge anfordern",
     "frist_tage": 3,  "prioritaet": "kritisch","kategorie": "Dokumente"},
    {"mandant": "Bäckerei Schmidt", "beschreibung": "Lohnabrechnung Januar erstellen",
     "frist_tage": 7,  "prioritaet": "normal",  "kategorie": "Lohn"},
    {"mandant": "Praxis Dr. Weber","beschreibung": "Jahresabschluss 2024 finalisieren",
     "frist_tage": 21, "prioritaet": "hoch",    "kategorie": "Jahresabschluss"},
    {"mandant": "Bäckerei Schmidt", "beschreibung": "Betriebsprüfung Unterlagen zusammenstellen",
     "frist_tage": 14, "prioritaet": "kritisch","kategorie": "Prüfung"},
]

# ─── Demo-Buchungen für ML-Training ──────────────────────────
DEMO_BUCHUNGEN = [
    {"lieferant": "Amazon",          "betrag": 47.90,  "kategorie": "buero",     "branche": "IT / Software"},
    {"lieferant": "Amazon",          "betrag": 389.00, "kategorie": "hardware",  "branche": "IT / Software"},
    {"lieferant": "Aral Tankstelle", "betrag": 68.50,  "kategorie": "benzin",    "branche": "IT / Software"},
    {"lieferant": "Telekom",         "betrag": 49.99,  "kategorie": "telefon",   "branche": "IT / Software"},
    {"lieferant": "Metro",           "betrag": 234.80, "kategorie": "material",  "branche": "Gastronomie / Lebensmittel"},
    {"lieferant": "Amazon",          "betrag": 89.00,  "kategorie": "material",  "branche": "Gastronomie / Lebensmittel"},
    {"lieferant": "Deutsche Bahn",   "betrag": 112.00, "kategorie": "reise",     "branche": "IT / Software"},
    {"lieferant": "DATEV",           "betrag": 299.00, "kategorie": "software",  "branche": "IT / Software"},
    {"lieferant": "Steuerberater",   "betrag": 450.00, "kategorie": "steuerberater","branche": "Gesundheitswesen"},
    {"lieferant": "Shell",           "betrag": 55.20,  "kategorie": "benzin",    "branche": "Gesundheitswesen"},
]


class OnboardingService:

    def __init__(self, ds):
        self.ds = ds

    def schnell_onboarding(
        self,
        kanzlei_name:  str,
        inhaber_email: str,
        stundensatz:   float = 150.0,
        mit_demo_daten: bool = True,
    ) -> Dict:
        """
        Komplettes Onboarding in einem API-Aufruf.
        Ergebnis: Vollständig eingerichtete Kanzlei mit Demo-Mandanten.
        """
        schritte  = []
        fehler    = []
        jetzt     = datetime.now()

        # ── Schritt 1: Settings konfigurieren ─────────────────
        try:
            from modules.settings_manager import setting_setzen
            setting_setzen("kanzlei_name",  kanzlei_name)
            setting_setzen("kanzlei_email", inhaber_email)
            setting_setzen("stundensatz",   stundensatz)
            setting_setzen("ki_autonomie_grad", 75)
            setting_setzen("ki_bot_proaktiv_aktiv", True)
            setting_setzen("portal_aktiv",  True)
            schritte.append("✓ Kanzlei-Einstellungen konfiguriert")
        except Exception as e:
            fehler.append(f"Settings: {e}")

        # ── Schritt 2: Demo-Mandanten anlegen ─────────────────
        angelegte_mandanten = []
        if mit_demo_daten:
            for m_data in DEMO_MANDANTEN:
                try:
                    m_copy = {**m_data}
                    m_copy["erstellt_am"]    = jetzt.isoformat()
                    m_copy["letzte_antwort"] = jetzt.isoformat()
                    m_copy["aufgaben_offen"] = 0
                    m_copy["letzte_email"]   = None
                    self.ds.mandant_speichern(m_copy["name"], m_copy)
                    angelegte_mandanten.append(m_copy["name"])
                except Exception as e:
                    fehler.append(f"Mandant {m_data['name']}: {e}")

            schritte.append(f"✓ {len(angelegte_mandanten)} Demo-Mandanten angelegt")

        # ── Schritt 3: Demo-Aufgaben ───────────────────────────
        angelegte_aufgaben = 0
        if mit_demo_daten:
            for a_data in DEMO_AUFGABEN:
                try:
                    if a_data["mandant"] not in angelegte_mandanten:
                        continue
                    aufgabe_id = str(uuid.uuid4())
                    frist = (jetzt + timedelta(days=a_data["frist_tage"])).strftime("%Y-%m-%d")
                    self.ds.aufgabe_speichern(aufgabe_id, {
                        "id":           aufgabe_id,
                        "mandant":      a_data["mandant"],
                        "beschreibung": a_data["beschreibung"],
                        "frist":        frist,
                        "prioritaet":   a_data["prioritaet"],
                        "kategorie":    a_data["kategorie"],
                        "erledigt":     False,
                        "erstellt_am":  jetzt.isoformat(),
                        "quelle":       "demo",
                    })
                    angelegte_aufgaben += 1
                except Exception as e:
                    fehler.append(f"Aufgabe: {e}")

            schritte.append(f"✓ {angelegte_aufgaben} Demo-Aufgaben erstellt")

        # ── Schritt 4: ML-Buchungsassistent trainieren ────────
        buchungen_trainiert = 0
        if mit_demo_daten:
            try:
                from core.ml_buchung import MLBuchungsassistent
                ml = MLBuchungsassistent()
                for b in DEMO_BUCHUNGEN:
                    from core.beleg_service import SKR03_KATEGORIEN
                    konto = SKR03_KATEGORIEN.get(b["kategorie"], SKR03_KATEGORIEN["sonstiges"])
                    ml.buchung_bestätigt(
                        lieferant   = b["lieferant"],
                        betrag      = b["betrag"],
                        kategorie   = b["kategorie"],
                        skr03_konto = konto["soll"],
                        branche     = b["branche"],
                    )
                    buchungen_trainiert += 1
                schritte.append(f"✓ ML-Buchungsassistent mit {buchungen_trainiert} Demo-Buchungen vortrainiert")
            except Exception as e:
                fehler.append(f"ML-Training: {e}")

        # ── Schritt 5: Standard-Workflows anlegen ─────────────
        try:
            from core.workflow_builder import WorkflowBaukasten
            from core.proaktiver_bot   import ProaktiverBot
            bot     = ProaktiverBot(self.ds)
            builder = WorkflowBaukasten(self.ds, bot=bot)
            erstellt = builder.erstelle_standard_workflows()
            schritte.append(f"✓ {len(erstellt)} Standard-Workflows aktiviert")
        except Exception as e:
            fehler.append(f"Workflows: {e}")

        # ── Schritt 6: Bot-Analyse starten ────────────────────
        try:
            from core.proaktiver_bot import ProaktiverBot
            bot    = ProaktiverBot(self.ds)
            fragen, _pruefung = bot.analysiere_alle_mandanten()
            schritte.append(f"✓ Bot-Analyse: {len(fragen)} proaktive Fragen erstellt")
        except Exception as e:
            fehler.append(f"Bot: {e}")

        self.ds.log_eintrag(
            f"ONBOARDING_ABGESCHLOSSEN | {kanzlei_name} | "
            f"{len(angelegte_mandanten)} Mandanten | {len(fehler)} Fehler"
        )

        return {
            "status":               "fertig" if not fehler else "teilweise_fertig",
            "kanzlei_name":         kanzlei_name,
            "schritte":             schritte,
            "fehler":               fehler,
            "mandanten_angelegt":   len(angelegte_mandanten),
            "aufgaben_angelegt":    angelegte_aufgaben,
            "ml_buchungen":         buchungen_trainiert,
            "naechste_schritte":    [
                "Mandantenportal testen: /portal",
                "Ersten echten Mandanten anlegen",
                "OPENAI_API_KEY in .env eintragen",
                f"Stundensatz anpassen (aktuell: €{stundensatz}/h)",
                "Team-Mitglieder einladen",
            ],
            "dauer_sekunden":       round((datetime.now() - jetzt).total_seconds(), 1),
        }

    def onboarding_status(self) -> Dict:
        """Prüft ob Onboarding abgeschlossen ist."""
        mandanten = self.ds.hole_mandanten()
        from modules.settings_manager import setting_holen
        api_key = __import__("os").getenv("OPENAI_API_KEY", "")

        checks = {
            "kanzlei_name":      bool(setting_holen("kanzlei_name") and
                                      setting_holen("kanzlei_name") != "Steuerkanzlei"),
            "mandanten":         len(mandanten) > 0,
            "api_key":           bool(api_key),
            "stundensatz":       (setting_holen("stundensatz") or 0) > 0,
            "kanzlei_email":     bool(setting_holen("kanzlei_email")),
            "portal_aktiv":      bool(setting_holen("portal_aktiv")),
        }

        abgeschlossen = sum(checks.values())
        gesamt        = len(checks)
        prozent       = round(abgeschlossen / gesamt * 100)

        return {
            "prozent":        prozent,
            "abgeschlossen":  abgeschlossen,
            "gesamt":         gesamt,
            "checks":         checks,
            "bereit":         prozent >= 80,
            "fehlende_schritte": [k for k, v in checks.items() if not v],
        }
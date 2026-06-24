#!/usr/bin/env python3
# ============================================================
# KANZLEI AI — DEMO SEED DATEN v1.0
# Datei: seed_demo.py
#
# Erstellt realistische Beispiel-Daten für:
#   - Demo-Präsentationen
#   - Neue Mitarbeiter-Onboarding
#   - System-Tests
#
# Aufruf: python seed_demo.py
# ============================================================

import sys
import os
import uuid
from datetime import datetime, timedelta
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.daten_speicher import DatenSpeicher
from backend.auth import erstelle_benutzer, hat_benutzer

ds = DatenSpeicher()


def seed_benutzer():
    """Demo-Benutzer anlegen."""
    print("\n👤 BENUTZER ANLEGEN...")

    if hat_benutzer():
        print("   Benutzer bereits vorhanden — übersprungen")
        return

    benutzer = [
        {"name": "admin",       "pw": "Admin2024!",   "rolle": "admin",           "anzeige": "Dr. Klaus Müller (Admin)"},
        {"name": "mueller",     "pw": "Kanzlei2024!", "rolle": "steuerberater",   "anzeige": "Dr. Klaus Müller"},
        {"name": "schmidt",     "pw": "Kanzlei2024!", "rolle": "steuerberater",   "anzeige": "Lisa Schmidt"},
        {"name": "assistenz",   "pw": "Kanzlei2024!", "rolle": "assistent",       "anzeige": "Tom Weber (Assistenz)"},
    ]

    for b in benutzer:
        try:
            erstelle_benutzer(b["name"], b["pw"], b["rolle"], anzeigename=b["anzeige"])
            print(f"   ✓ {b['anzeige']} ({b['rolle']})")
        except ValueError as e:
            print(f"   ⚠ {b['name']}: {e}")


def seed_mandanten():
    """Realistische Demo-Mandanten anlegen."""
    print("\n🏢 MANDANTEN ANLEGEN...")

    mandanten = [
        {
            "name":     "Immobilien Hoffmann GmbH",
            "umsatz":   24000.0,
            "email":    "hoffmann@immo-hoffmann.de",
            "telefon":  "+49 89 123456",
            "branche":  "Immobilien",
            "steuer_id": "123/456/78901",
            "notizen":  "Bevorzugt Kontakt per Email. Quartalsweise Abrechnung.",
            "letzte_antwort_tage": 2,
            "fehlende_docs": [],
        },
        {
            "name":     "Bäckerei Schmid OHG",
            "umsatz":   8400.0,
            "email":    "buchhaltung@baeckerei-schmid.de",
            "telefon":  "+49 89 234567",
            "branche":  "Gastronomie / Lebensmittel",
            "steuer_id": "124/567/89012",
            "notizen":  "Familienbetrieb, 3. Generation. Jahresabschluss immer März.",
            "letzte_antwort_tage": 8,
            "fehlende_docs": ["Kassenbuch Q4", "Inventarliste 2025"],
        },
        {
            "name":     "TechStart Solutions GmbH",
            "umsatz":   36000.0,
            "email":    "cfo@techstart.io",
            "telefon":  "+49 89 345678",
            "branche":  "IT / Software",
            "steuer_id": "125/678/90123",
            "notizen":  "Wächst stark. Internationale Umsätze in USD. R&D-Förderung prüfen.",
            "letzte_antwort_tage": 1,
            "fehlende_docs": [],
        },
        {
            "name":     "Dr. Petra Wagner (Arztpraxis)",
            "umsatz":   15600.0,
            "email":    "wagner@praxis-wagner.de",
            "telefon":  "+49 89 456789",
            "branche":  "Medizin / Gesundheit",
            "steuer_id": "126/789/01234",
            "notizen":  "Angestellte Ärztin + Selbstständigkeit. KV-Abzug beachten.",
            "letzte_antwort_tage": 15,
            "fehlende_docs": ["Honorarabrechnung Q3", "Privatarztrechnung Nov"],
        },
        {
            "name":     "Autohaus Bergmann KG",
            "umsatz":   42000.0,
            "email":    "verwaltung@autohaus-bergmann.de",
            "telefon":  "+49 89 567890",
            "branche":  "Kfz-Handel",
            "steuer_id": "127/890/12345",
            "notizen":  "Großer Mandant. Vorsicht bei Vorsteuer Neu- vs. Gebrauchtwagen.",
            "letzte_antwort_tage": 3,
            "fehlende_docs": [],
        },
        {
            "name":     "Eventmanagement Fischer",
            "umsatz":   12000.0,
            "email":    "info@fischer-events.de",
            "telefon":  "+49 89 678901",
            "branche":  "Veranstaltungen / Event",
            "steuer_id": "128/901/23456",
            "notizen":  "Saisonales Geschäft. Hohe Schwankungen Mai-Oktober.",
            "letzte_antwort_tage": 21,
            "fehlende_docs": ["Rechnungseingang Oktober", "Kassenbuch Q3"],
        },
        {
            "name":     "Kita Sonnenschein gGmbH",
            "umsatz":   6000.0,
            "email":    "leitung@kita-sonnenschein.de",
            "telefon":  "+49 89 789012",
            "branche":  "Bildung / Soziales",
            "steuer_id": "129/012/34567",
            "notizen":  "Gemeinnützig — Sonderregeln beachten. Zuschüsse von Stadt prüfen.",
            "letzte_antwort_tage": 5,
            "fehlende_docs": [],
        },
        {
            "name":     "Architektur Reiter & Partner",
            "umsatz":   28800.0,
            "email":    "partner@reiter-architektur.de",
            "telefon":  "+49 89 890123",
            "branche":  "Architektur / Ingenieurwesen",
            "steuer_id": "130/123/45678",
            "notizen":  "2 Partner mit unterschiedlichen Gewinnbeteiligungen (60/40).",
            "letzte_antwort_tage": 4,
            "fehlende_docs": ["Teilabrechnungen Projekt Bauvorhaben München"],
        },
    ]

    jetzt = datetime.now()
    bestehende = ds.hole_mandanten()

    for m in mandanten:
        if m["name"] in bestehende:
            print(f"   ⚠ {m['name']}: bereits vorhanden")
            continue

        letzte_antwort = (jetzt - timedelta(days=m["letzte_antwort_tage"])).isoformat()

        ds.mandant_speichern(m["name"], {
            "umsatz":                   m["umsatz"],
            "email":                    m["email"],
            "telefon":                  m["telefon"],
            "branche":                  m["branche"],
            "steuer_id":                m["steuer_id"],
            "notizen":                  m["notizen"],
            "fehlende_dokumente_liste": m["fehlende_docs"],
            "letzte_antwort":           letzte_antwort,
            "letzte_email":             None,
            "erstellt_am":              (jetzt - timedelta(days=random.randint(30, 365))).isoformat(),
            "aktiv":                    True,
        })
        print(f"   ✓ {m['name']} (€{m['umsatz']:,.0f}/Jahr)")


def seed_aufgaben():
    """Realistische Aufgaben mit verschiedenen Dringlichkeitsstufen."""
    print("\n📋 AUFGABEN ANLEGEN...")

    jetzt = datetime.now()

    aufgaben_templates = [
        # Überfällig
        {"mandant": "Bäckerei Schmid OHG",         "beschreibung": "Jahresabschluss 2024 einreichen",      "tage": -5,   "prio": "kritisch", "kat": "jahresabschluss"},
        {"mandant": "Eventmanagement Fischer",      "beschreibung": "USt-Voranmeldung Q3 nachholen",        "tage": -3,   "prio": "kritisch", "kat": "umsatzsteuer"},
        {"mandant": "Dr. Petra Wagner (Arztpraxis)","beschreibung": "Einkommensteuer 2024 Unterlagen prüfen","tage": -1,   "prio": "hoch",    "kat": "einkommensteuer"},

        # Heute / Morgen
        {"mandant": "Autohaus Bergmann KG",         "beschreibung": "Lohnabrechnung Dezember prüfen",        "tage": 0,    "prio": "hoch",    "kat": "lohnbuchhaltung"},
        {"mandant": "TechStart Solutions GmbH",     "beschreibung": "R&D-Förderantrag Deadline",              "tage": 1,    "prio": "kritisch","kat": "foerderung"},

        # Diese Woche
        {"mandant": "Immobilien Hoffmann GmbH",     "beschreibung": "Quartalsabschluss Q4 fertigstellen",   "tage": 3,    "prio": "hoch",    "kat": "quartal"},
        {"mandant": "Architektur Reiter & Partner", "beschreibung": "Gewinnverteilung 2024 berechnen",       "tage": 5,    "prio": "hoch",    "kat": "jahresabschluss"},
        {"mandant": "Kita Sonnenschein gGmbH",       "beschreibung": "Gemeinnützigkeits-Antrag verlängern",   "tage": 7,    "prio": "hoch",    "kat": "compliance"},

        # Nächste Wochen
        {"mandant": "Bäckerei Schmid OHG",          "beschreibung": "Inventarliste für Jahresabschluss",     "tage": 10,   "prio": "normal",  "kat": "jahresabschluss"},
        {"mandant": "TechStart Solutions GmbH",     "beschreibung": "Betriebsprüfung vorbereiten",           "tage": 14,   "prio": "hoch",    "kat": "betriebspruefung"},
        {"mandant": "Autohaus Bergmann KG",         "beschreibung": "Vorsteuer Jahreskorrektur",             "tage": 14,   "prio": "normal",  "kat": "umsatzsteuer"},
        {"mandant": "Immobilien Hoffmann GmbH",     "beschreibung": "Grundsteuer-Bescheide prüfen",          "tage": 21,   "prio": "normal",  "kat": "grundsteuer"},
        {"mandant": "Dr. Petra Wagner (Arztpraxis)","beschreibung": "Rentenversicherung-Nachweis einreichen", "tage": 25,   "prio": "normal",  "kat": "sozialversicherung"},
        {"mandant": "Eventmanagement Fischer",      "beschreibung": "Steuererklärung 2024 einreichen",       "tage": 30,   "prio": "hoch",    "kat": "einkommensteuer"},
        {"mandant": "Architektur Reiter & Partner", "beschreibung": "Honorar-Rechnungen Q4 buchen",          "tage": 35,   "prio": "normal",  "kat": "buchfuehrung"},

        # Erledigte Aufgaben (für Statistiken)
        {"mandant": "TechStart Solutions GmbH",     "beschreibung": "USt-Voranmeldung November",            "tage": -30,  "prio": "hoch",    "kat": "umsatzsteuer",   "erledigt": True},
        {"mandant": "Autohaus Bergmann KG",         "beschreibung": "Lohnabrechnung November",               "tage": -25,  "prio": "normal",  "kat": "lohnbuchhaltung","erledigt": True},
        {"mandant": "Bäckerei Schmid OHG",          "beschreibung": "Kassenbuch Oktober kontrolliert",       "tage": -20,  "prio": "normal",  "kat": "buchfuehrung",   "erledigt": True},
        {"mandant": "Immobilien Hoffmann GmbH",     "beschreibung": "Mieteinnahmen Q3 verbucht",            "tage": -15,  "prio": "normal",  "kat": "buchfuehrung",   "erledigt": True},
        {"mandant": "Kita Sonnenschein gGmbH",       "beschreibung": "Förderabrechnung H1 eingereicht",      "tage": -10,  "prio": "hoch",    "kat": "foerderung",     "erledigt": True},
    ]

    bestehende_aufgaben = ds.hole_fristen()
    # Prüfe ob schon Demo-Aufgaben da sind
    demo_exists = any("erledigt_am" in a for a in bestehende_aufgaben.values())
    if demo_exists and len(bestehende_aufgaben) > 10:
        print("   ⚠ Demo-Aufgaben bereits vorhanden — übersprungen")
        return

    for tpl in aufgaben_templates:
        mandant = tpl["mandant"]
        if mandant not in ds.hole_mandanten():
            continue

        aufgabe_id = str(uuid.uuid4())
        frist_dt   = jetzt + timedelta(days=tpl["tage"])
        erledigt   = tpl.get("erledigt", False)

        aufgabe = {
            "id":           aufgabe_id,
            "mandant":      mandant,
            "beschreibung": tpl["beschreibung"],
            "frist":        frist_dt.strftime("%Y-%m-%d"),
            "prioritaet":   tpl["prio"],
            "kategorie":    tpl["kat"],
            "erledigt":     erledigt,
            "erstellt_am":  (jetzt - timedelta(days=random.randint(5, 60))).isoformat(),
        }

        if erledigt:
            aufgabe["erledigt_am"] = (frist_dt + timedelta(days=random.randint(1, 5))).isoformat()

        ds.aufgabe_speichern(aufgabe_id, aufgabe)

    gesamt = len(aufgaben_templates)
    erledigt_count = sum(1 for t in aufgaben_templates if t.get("erledigt"))
    print(f"   ✓ {gesamt} Aufgaben ({erledigt_count} erledigt, {gesamt - erledigt_count} offen)")


def seed_kommunikation():
    """Beispiel-Kommunikationshistorie."""
    print("\n💬 KOMMUNIKATION ANLEGEN...")

    jetzt   = datetime.now()
    eintraege = [
        ("Immobilien Hoffmann GmbH",      -2,  "email",   "Quartalsreport zugesendet. Mandant zufrieden."),
        ("Bäckerei Schmid OHG",           -8,  "anruf",   "Kurzes Telefonat zu fehlenden Belegen."),
        ("TechStart Solutions GmbH",      -1,  "meeting", "Strategiegespräch zu R&D-Steueroptimierung. 2h."),
        ("Dr. Petra Wagner (Arztpraxis)", -15,  "email",   "Erinnerung zu fehlenden Honorarabrechnungen gesendet."),
        ("Autohaus Bergmann KG",          -3,  "notiz",   "Rückruf von Herrn Bergmann: Frist bekannt, kommt."),
        ("Eventmanagement Fischer",       -21, "email",   "2. Mahnung für Q3 USt-Voranmeldung gesendet."),
        ("Kita Sonnenschein gGmbH",       -5,  "meeting", "Jahresgespräch. Gemeinnützigkeit für 2025 gesichert."),
    ]

    for mandant, tage, typ, text in eintraege:
        if mandant not in ds.hole_mandanten():
            continue
        ds.kommunikation_hinzufuegen(mandant, {
            "typ":       typ,
            "text":      text,
            "timestamp": (jetzt + timedelta(days=tage)).isoformat(),
        })

    print(f"   ✓ {len(eintraege)} Kommunikationseinträge")


def seed_logs():
    """Beispiel-Audit-Logs."""
    print("\n📜 AUDIT-LOGS ANLEGEN...")

    jetzt = datetime.now()
    logs  = [
        "Systemstart",
        "MANDANT_ERSTELLT | TechStart Solutions GmbH | Umsatz: 36000€",
        "ENGINE_DAILY_CHECK | 8 Mandanten | 0 Emails | 0 Warnungen | 0.42s",
        "PORTAL_TOKEN_ERSTELLT | Bäckerei Schmid OHG",
        "AUFGABE_ERLEDIGT | TechStart Solutions GmbH | USt-Voranmeldung November",
        "EXPORT_KOMPLETT | Immobilien Hoffmann GmbH",
        "BANK_IMPORT | kontoauszug_nov.xml | 47 Buchungen | €28400 Einnahmen",
        "MANDANT_AKTUALISIERT | Dr. Petra Wagner (Arztpraxis) | ['email']",
        "ENGINE_DAILY_CHECK | 8 Mandanten | 2 Emails | 1 Warnungen | 0.38s",
        "PORTAL_LOGIN | Bäckerei Schmid OHG",
        "PORTAL_UPLOAD | Bäckerei Schmid OHG | kassenbuch_nov.pdf | 245000 bytes",
        "WORKFLOW_MONATSABSCHLUSS | Autohaus Bergmann KG | 12/2025 | 7 Aufgaben erstellt",
        "SIMULATION | TechStart Solutions GmbH | Ersparnis: 4500EUR",
        "EXPORT_KOMPLETT | TechStart Solutions GmbH",
    ]

    for i, log_text in enumerate(logs):
        _ = (jetzt - timedelta(days=len(logs) - i, hours=random.randint(0, 12))).isoformat()
        ds.log_eintrag(log_text, benutzer="seed_demo")
    print(f"   ✓ {len(logs)} Audit-Log-Einträge")


def main():
    print("=" * 50)
    print("  KANZLEI AI — DEMO SEED")
    print("=" * 50)

    # Warnung
    mandanten = ds.hole_mandanten()
    if mandanten:
        print(f"\n⚠  ACHTUNG: Es sind bereits {len(mandanten)} Mandanten vorhanden!")
        antwort = input("   Demo-Daten trotzdem anlegen? (ja/n): ").strip().lower()
        if antwort != "ja":
            print("   Abgebrochen.")
            return

    seed_benutzer()
    seed_mandanten()
    seed_aufgaben()
    seed_kommunikation()
    seed_logs()

    print("\n" + "=" * 50)
    print("  ✓ DEMO-DATEN ERFOLGREICH ANGELEGT")
    print("=" * 50)
    print()
    print("  System starten:")
    print("  → Backend:  uvicorn backend.api:app --reload --port 8000")
    print("  → Portal:   gleiche App — uvicorn backend.api:app (Pfade unter /portal/*)")
    print("  → Frontend: npm start")
    print()
    print("  Demo-Login:")
    print("  → Benutzername: admin")
    print("  → Passwort:     Admin2024!")
    print()
    print("  Mandanten: 8 Demo-Mandanten mit Aufgaben, Fristen und Kommunikation")
    print()


if __name__ == "__main__":
    main()
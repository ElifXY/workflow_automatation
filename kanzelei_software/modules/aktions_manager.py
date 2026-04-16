# ============================================================
# KANZLEI AI — AKTIONS MANAGER v2.0
# Datei: modules/aktions_manager.py
# Vollständig überarbeitet — alle Workflows integriert
# ============================================================

from core.daten_speicher import DatenSpeicher
from modules.email_manager import email_generieren
from modules.aufgaben_manager import aufgabe_hinzufuegen
from datetime import datetime

ds = DatenSpeicher()


def aktionen_anzeigen(mandant_name: str):
    """Aktions-Menü für einen bestimmten Mandanten."""

    while True:
        print("\n" + "=" * 40)
        print(f"  AKTIONEN: {mandant_name}")
        print("=" * 40)
        print("  A - Email erstellen")
        print("  B - Aufgabe erstellen")
        print("  C - Kommunikations-Notiz")
        print("  W - Workflow starten")
        print("  D - Zurück")
        print("=" * 40)

        wahl = input("  Auswahl: ").strip().upper()

        if wahl == "A":
            email_generieren(mandant_name)
            ds.log_eintrag(f"AKTION_EMAIL | {mandant_name}")

        elif wahl == "B":
            beschreibung = input("  Aufgabe: ").strip()
            frist        = input("  Frist (YYYY-MM-DD): ").strip()

            if not beschreibung or not frist:
                print("  Ungültige Eingabe.")
                continue

            try:
                datetime.strptime(frist, "%Y-%m-%d")
            except ValueError:
                print("  Ungültiges Datum.")
                continue

            print("  Priorität: 1=niedrig  2=normal  3=hoch  4=kritisch")
            prio_map = {"1": "niedrig", "2": "normal", "3": "hoch", "4": "kritisch"}
            prio = prio_map.get(input("  Priorität [2]: ").strip(), "normal")

            aufgabe_hinzufuegen(mandant_name, beschreibung, frist, prio)

        elif wahl == "C":
            text = input("  Notiz: ").strip()
            if not text:
                print("  Abgebrochen.")
                continue

            ds.kommunikation_hinzufuegen(mandant_name, {
                "typ":       "notiz",
                "text":      text,
                "timestamp": datetime.now().isoformat(),
            })
            ds.log_eintrag(f"NOTIZ | {mandant_name}")
            print("  ✔ Notiz gespeichert.")

        elif wahl == "W":
            _workflow_submenu(mandant_name)

        elif wahl == "D":
            break

        else:
            print("  Ungültige Eingabe.")


def _workflow_submenu(mandant_name: str):
    """Workflow-Untermenü."""
    from core.engine import Engine
    engine = Engine(ds)

    print("\n  Verfügbare Workflows:")
    print("  1 - Steuererklärung")
    print("  2 - Monatsabschluss")
    print("  3 - Jahresabschluss")
    print("  4 - Onboarding")

    wf = input("  Auswahl: ").strip()

    try:
        if wf == "1":
            from modules.workflow_manager import workflow_steuererklaerung
            workflow_steuererklaerung(mandant_name)

        elif wf == "2":
            jetzt = datetime.now()
            try:
                monat = int(input(f"  Monat [{jetzt.month}]: ") or jetzt.month)
                jahr  = int(input(f"  Jahr  [{jetzt.year}]: ")  or jetzt.year)
            except ValueError:
                monat, jahr = jetzt.month, jetzt.year

            result = engine.workflow_monatsabschluss(mandant_name, monat, jahr)
            print(f"  ✔ {result['aufgaben_erstellt']} Aufgaben erstellt")

        elif wf == "3":
            try:
                jahr = int(input(f"  Jahr [{datetime.now().year}]: ") or datetime.now().year)
            except ValueError:
                jahr = datetime.now().year

            result = engine.workflow_jahresabschluss(mandant_name, jahr)
            print(f"  ✔ {result['aufgaben_erstellt']} Aufgaben erstellt")

        elif wf == "4":
            result = engine.workflow_neuer_mandant(mandant_name)
            print(f"  ✔ {result['aufgaben_erstellt']} Onboarding-Aufgaben erstellt")

        else:
            print("  Ungültige Auswahl.")

    except Exception as e:
        print(f"  Fehler: {e}")
        
# ============================================================
# KANZLEI AI — MAIN.PY v2.0
# CLI-Interface | Alle Bugs behoben | Neue Engine integriert
# ============================================================

import os
import sys
from datetime import datetime

# Projektroot zum Python-Pfad hinzufügen
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.daten_speicher import DatenSpeicher
from core.engine import Engine
from core.decision_engine import prioritaeten_sortieren

from modules.mandanten_manager import (
    mandant_hinzufuegen,
    mandanten_anzeigen,
    mandant_suchen,
    mandant_loeschen,
)
from modules.aufgaben_manager import (
    aufgabe_hinzufuegen,
    aufgaben_anzeigen,
    aufgabe_erledigen,
)
from modules.kommunikation_manager import kommunikation_dialog
from modules.dokumenten_manager import (
    dokument_anfordern,
    dokument_erhalten,
    dokumente_anzeigen,
)
from modules.email_manager import email_generieren
from modules.mandantenakte import mandantenakte_anzeigen
from modules.settings_manager import settings_anzeigen, settings_aendern

# ─── Globale Instanzen ───────────────────────────────────────
ds     = DatenSpeicher()
engine = Engine(ds)

# ============================================================
# STARTUP DASHBOARD
# ============================================================

def systemstart():
    """Zeigt beim Start sofort was heute wichtig ist."""

    _trennlinie("KANZLEI AI v2.0 — SYSTEMSTART")
    ds.log_eintrag("Systemstart CLI")

    try:
        # Tages-Prioritäten
        _heute_aufgaben()

        # Engine Daily Checks (non-blocking, nur loggen)
        result = engine.run_daily_checks()
        mandanten_count = result.get("mandanten_geprueft", 0)
        warnungen_count = len(result.get("plausibilitaet", []))

        print(f"\n  Engine: {mandanten_count} Mandanten geprüft", end="")
        if warnungen_count:
            print(f" | {warnungen_count} Hinweise (siehe Menü 16)", end="")
        print()

    except Exception as e:
        print(f"  Systemstart-Hinweis: {e}")

# ============================================================
# INTERNE HILFSFUNKTIONEN
# ============================================================

def _trennlinie(titel: str = ""):
    """Formatierte Trennlinie."""
    print("\n" + "=" * 40)
    if titel:
        print(f"  {titel}")
        print("=" * 40)

def _heute_aufgaben():
    """Zeigt dringende Aufgaben für heute."""
    mandanten = ds.hole_mandanten()
    aufgaben  = ds.hole_fristen()
    jetzt     = datetime.now()
    tasks     = []

    # Keine Antwort
    for name, m in mandanten.items():
        tage   = ds.berechne_tage_ohne_antwort(name)
        umsatz = m.get("umsatz", 0)
        if tage >= 7:
            tasks.append((umsatz + tage * 100,
                          f"📞 {name} — keine Antwort seit {tage} Tagen"))

    # Fällige Aufgaben
    for a in aufgaben.values():
        if a.get("erledigt"):
            continue
        try:
            frist = datetime.strptime(a["frist"], "%Y-%m-%d")
            tage  = (frist - jetzt).days
            if tage < 0:
                tasks.append((15000 + abs(tage) * 50,
                              f"⛔ {a['mandant']} — ÜBERFÄLLIG ({abs(tage)}d): {a['beschreibung']}"))
            elif tage == 0:
                tasks.append((12000,
                              f"🔥 {a['mandant']} — HEUTE fällig: {a['beschreibung']}"))
            elif tage <= 2:
                tasks.append((8000,
                              f"⚠  {a['mandant']} — in {tage} Tag(en): {a['beschreibung']}"))
        except (ValueError, KeyError):
            continue

    tasks.sort(reverse=True)

    _trennlinie("HEUTE MACHEN")
    if not tasks:
        print("  ✔ Alles im grünen Bereich — keine dringenden Punkte")
    else:
        for _, text in tasks[:8]:
            print(f"  {text}")
    print("=" * 40)

# ============================================================
# MENÜ-FUNKTIONEN
# ============================================================

def top_mandanten_anzeigen():
    """Top-Mandanten nach Priorität sortiert."""
    try:
        mandanten   = ds.hole_mandanten()
        aufgaben    = ds.hole_fristen()
        prioritaeten = prioritaeten_sortieren(mandanten, aufgaben, ds)

        _trennlinie("TOP MANDANTEN — FOKUS: GELD")

        if not prioritaeten:
            print("  Keine Mandanten vorhanden.")
            return

        symbole = {"KRITISCH": "✖", "WICHTIG": "⚠", "NORMAL": "✔"}

        for m in prioritaeten[:10]:
            symbol = symbole.get(m.get("status", "NORMAL"), "·")
            print(f"  {symbol} {m['name']:<30} Score: {int(m['score']):>6,}  "
                  f"Umsatz: {m.get('umsatz', 0):>8,.0f}€")

        print("=" * 40)

    except Exception as e:
        print(f"  Fehler: {e}")
        ds.log_eintrag(f"TopMandanten Fehler: {e}")


def smart_empfehlungen():
    """KI-Empfehlungen für alle Mandanten."""
    try:
        analyse = engine.run_full_analysis()
        _trennlinie("KI-EMPFEHLUNGEN")

        mandanten_liste = analyse.get("mandanten", [])
        if not mandanten_liste:
            print("  Keine Mandanten vorhanden.")
            return

        gezeigt = 0
        for m in mandanten_liste:
            entscheidungen = m.get("entscheidungen", [])
            # Nur Mandanten mit echtem Handlungsbedarf
            relevante = [e for e in entscheidungen if e.get("action") != "nichts"]
            if not relevante:
                continue

            print(f"\n  {m['mandant']} (Score: {int(m.get('score', 0)):,})")
            for e in relevante[:2]:
                print(f"    → {e.get('text', '')}")
            gezeigt += 1
            if gezeigt >= 10:
                break

        if gezeigt == 0:
            print("  ✔ Kein akuter Handlungsbedarf für alle Mandanten")

        # Compliance-Warnungen
        compliance = analyse.get("mandanten", [])
        engine_result = engine.run_daily_checks()
        comp_warn = engine_result.get("compliance", [])
        if comp_warn:
            print(f"\n  Gesetzliche Fristen ({len(comp_warn)} aktuell):")
            for c in comp_warn[:3]:
                print(f"    ⚖  {c.get('warnung', '')}")

        print("\n" + "=" * 40)

    except Exception as e:
        print(f"  Fehler: {e}")
        ds.log_eintrag(f"Empfehlungen Fehler: {e}")


def engine_ausfuehren():
    """Engine manuell triggern — alle Checks sofort."""
    _trennlinie("ENGINE — TAGES-CHECK")
    try:
        result = engine.run_daily_checks()
        print(f"  Mandanten geprüft:   {result.get('mandanten_geprueft', 0)}")
        print(f"  Emails vorgeschlagen: {result.get('emails_vorgeschlagen', 0)}")
        print(f"  Emails gesendet:      {result.get('emails_gesendet', 0)}")
        print(f"  Aktionen gesamt:      {len(result.get('aktionen', []))}")
        print(f"  Dauer:                {result.get('dauer_sekunden', 0):.2f}s")

        plausib = result.get("plausibilitaet", [])
        if plausib:
            print(f"\n  Plausibilitäts-Hinweise ({len(plausib)}):")
            for p in plausib[:5]:
                print(f"    [{p.get('schwere', '?').upper()}] "
                      f"{p.get('mandant', '?')}: {p.get('text', '')}")

        comp = result.get("compliance", [])
        if comp:
            print(f"\n  Gesetzliche Fristen ({len(comp)}):")
            for c in comp[:3]:
                print(f"    ⚖  {c.get('warnung', '')}")

        print("=" * 40)
    except Exception as e:
        print(f"  Fehler: {e}")
        ds.log_eintrag(f"Engine Fehler: {e}")


def workflow_menu():
    """One-Click Workflow-Auswahl."""
    _trennlinie("WORKFLOWS")
    print("  1 - Monatsabschluss anlegen")
    print("  2 - Jahresabschluss anlegen")
    print("  3 - Neuer Mandant Onboarding")
    print("  0 - Zurück")
    print("=" * 40)

    auswahl = input("  Auswahl: ").strip()
    if auswahl == "0":
        return

    mandant = input("  Mandant: ").strip()
    if not mandant:
        print("  Abgebrochen.")
        return

    if mandant not in ds.hole_mandanten():
        print(f"  Mandant '{mandant}' nicht gefunden.")
        return

    try:
        if auswahl == "1":
            jetzt = datetime.now()
            try:
                monat = int(input(f"  Monat [{jetzt.month}]: ") or jetzt.month)
                jahr  = int(input(f"  Jahr  [{jetzt.year}]: ")  or jetzt.year)
            except ValueError:
                monat, jahr = jetzt.month, jetzt.year

            result = engine.workflow_monatsabschluss(mandant, monat, jahr)
            print(f"\n  ✔ {result['aufgaben_erstellt']} Aufgaben für {monat}/{jahr} erstellt:")
            for a in result.get("aufgaben", []):
                print(f"    · {a}")

        elif auswahl == "2":
            try:
                jahr = int(input(f"  Jahr [{datetime.now().year}]: ") or datetime.now().year)
            except ValueError:
                jahr = datetime.now().year

            result = engine.workflow_jahresabschluss(mandant, jahr)
            print(f"\n  ✔ {result['aufgaben_erstellt']} Aufgaben für JA {jahr} erstellt:")
            for a in result.get("aufgaben", []):
                print(f"    · {a}")

        elif auswahl == "3":
            result = engine.workflow_neuer_mandant(mandant)
            print(f"\n  ✔ {result['aufgaben_erstellt']} Onboarding-Aufgaben erstellt:")
            for a in result.get("aufgaben", []):
                print(f"    · {a}")
            if result.get("email_vorbereitet"):
                print("  ✔ Willkommens-Email vorbereitet")

        else:
            print("  Ungültige Auswahl.")

    except Exception as e:
        print(f"  Fehler: {e}")
        ds.log_eintrag(f"Workflow Fehler: {e}")

    print("=" * 40)


def tagesbericht_anzeigen():
    """Automatischen Tagesbericht anzeigen."""
    try:
        bericht = engine.erstelle_tagesbericht()
        print()
        print(bericht)
    except Exception as e:
        print(f"  Fehler: {e}")


def prognose_anzeigen():
    """Predictive Analytics — Fristen & Umsatz."""
    _trennlinie("PROGNOSE")
    try:
        fp = engine.predictive_fristenbelastung(30)
        up = engine.predictive_umsatz_prognose()

        print(f"  Fristen nächste 30 Tage: {fp['gesamt_fristen']}")
        for kw, anzahl in list(fp.get("belastung_pro_woche", {}).items())[:4]:
            print(f"    {kw}: {anzahl} Frist(en)")

        if fp.get("kritische_fristen"):
            print(f"\n  Kritisch (≤3 Tage): {len(fp['kritische_fristen'])}")
            for f in fp["kritische_fristen"][:3]:
                print(f"    ⛔ {f['mandant']}: {f['beschreibung']} (in {f['tage']}d)")

        print(f"\n  Jahresumsatz erwartet: €{up['gesamt_jahresumsatz']:,.2f}")
        print(f"  Monatsumsatz:          €{up['monatsumsatz_erwartet']:,.2f}")
        print(f"  Risiko-Score:          {up['risiko_score_prozent']}%")
        print(f"  Hinweis: {up['hinweis']}")
        print("=" * 40)

    except Exception as e:
        print(f"  Fehler: {e}")


def dokument_menu():
    """Dokumenten-Untermenü."""
    _trennlinie("DOKUMENTENMANAGER")
    print("  1 - Dokument anfordern")
    print("  2 - Dokument erhalten")
    print("  3 - Dokumente anzeigen")
    print("=" * 40)

    auswahl = input("  Auswahl: ").strip()
    if auswahl == "1":
        dokument_anfordern()
    elif auswahl == "2":
        dokument_erhalten()
    elif auswahl == "3":
        dokumente_anzeigen()
    else:
        print("  Ungültige Eingabe.")


def settings_menu():
    """Einstellungs-Untermenü."""
    _trennlinie("EINSTELLUNGEN")
    print("  1 - Anzeigen")
    print("  2 - Ändern")
    print("=" * 40)

    auswahl = input("  Auswahl: ").strip()
    if auswahl == "1":
        settings_anzeigen()
    elif auswahl == "2":
        settings_aendern()
    else:
        print("  Ungültige Eingabe.")


# ============================================================
# HAUPTMENÜ
# ============================================================

def menue_anzeigen():
    _trennlinie("KANZLEI AI — HAUPTMENÜ")
    items = [
        ("1",  "Mandant hinzufügen"),
        ("2",  "Mandanten anzeigen"),
        ("3",  "Mandant suchen"),
        ("4",  "Mandant löschen"),
        ("5",  "Mandantenakte öffnen"),
        ("6",  "Aufgabe hinzufügen"),
        ("7",  "Aufgaben anzeigen"),
        ("8",  "Aufgabe erledigen"),
        ("9",  "Email erstellen"),
        ("10", "Kommunikation"),
        ("11", "Dokumente"),
        ("12", "Engine ausführen"),
        ("13", "Einstellungen"),
        ("14", "Heute / Dringend"),
        ("15", "Top Mandanten"),
        ("16", "KI-Empfehlungen"),
        ("17", "Workflow starten"),
        ("18", "Tagesbericht"),
        ("19", "Prognose"),
        ("0",  "Beenden"),
    ]
    for nr, label in items:
        print(f"  {nr:>2} — {label}")
    print("=" * 40)


def menue_aktion(auswahl: str) -> bool:
    """Führt die gewählte Aktion aus. Gibt False zurück wenn Programm beendet."""

    aktionen = {
        "1":  mandant_hinzufuegen,
        "2":  mandanten_anzeigen,
        "3":  mandant_suchen,
        "4":  mandant_loeschen,
        "5":  mandantenakte_anzeigen,
        "6":  aufgabe_hinzufuegen,
        "7":  aufgaben_anzeigen,
        "8":  aufgabe_erledigen,
        "9":  email_generieren,
        "10": kommunikation_dialog,
        "11": dokument_menu,
        "12": engine_ausfuehren,
        "13": settings_menu,
        "14": _heute_aufgaben,
        "15": top_mandanten_anzeigen,
        "16": smart_empfehlungen,
        "17": workflow_menu,
        "18": tagesbericht_anzeigen,
        "19": prognose_anzeigen,
    }

    if auswahl == "0":
        print("\n  Auf Wiedersehen.\n")
        ds.log_eintrag("Systemende CLI")
        return False

    aktion = aktionen.get(auswahl)
    if aktion:
        try:
            aktion()
        except Exception as e:
            print(f"\n  Fehler: {e}")
            ds.log_eintrag(f"Aktion {auswahl} Fehler: {e}")
    else:
        print("  Ungültige Eingabe — bitte Nummer aus dem Menü wählen.")

    return True


# ============================================================
# HAUPTPROGRAMM
# ============================================================

def main():
    systemstart()

    running = True
    while running:
        menue_anzeigen()
        try:
            auswahl = input("  Auswahl: ").strip()
            running = menue_aktion(auswahl)
        except KeyboardInterrupt:
            print("\n\n  Abgebrochen (Strg+C).")
            ds.log_eintrag("Systemende via KeyboardInterrupt")
            break
        except Exception as e:
            print(f"  Unerwarteter Fehler: {e}")
            ds.log_eintrag(f"Runtime Fehler: {e}")


if __name__ == "__main__":
    main()
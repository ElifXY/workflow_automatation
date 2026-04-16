# ============================================================
# KANZLEI AI — KOMMUNIKATION MANAGER v2.0
# Datei: modules/kommunikation_manager.py
# Bugs: ds.daten.get() + ds._speichern ohne () → behoben
# ============================================================

from core.daten_speicher import DatenSpeicher
from datetime import datetime

ds = DatenSpeicher()


def kommunikation_dialog():
    print("\n" + "=" * 40)
    print("  KOMMUNIKATIONSMANAGER")
    print("=" * 40)
    print("  1 - Eintrag hinzufügen")
    print("  2 - Verlauf anzeigen")
    print("=" * 40)

    auswahl = input("  Auswahl: ").strip()
    if auswahl == "1":
        eintrag_hinzufuegen()
    elif auswahl == "2":
        verlauf_anzeigen()
    else:
        print("  Ungültige Eingabe.")


def eintrag_hinzufuegen():
    mandant = input("  Mandant: ").strip()
    if not mandant:
        print("  Abgebrochen.")
        return

    if mandant not in ds.hole_mandanten():
        print(f"  Mandant '{mandant}' nicht gefunden.")
        return

    print("  Typ: 1=Notiz  2=Anruf  3=Meeting  4=Email")
    typ_map = {"1": "notiz", "2": "anruf", "3": "meeting", "4": "email"}
    typ = typ_map.get(input("  Typ: ").strip(), "notiz")

    text = input("  Inhalt: ").strip()
    if not text:
        print("  Abgebrochen.")
        return

    eintrag = {
        "typ":       typ,
        "text":      text,
        "timestamp": datetime.now().isoformat(),
    }

    ds.kommunikation_hinzufuegen(mandant, eintrag)

    # Letzte Antwort aktualisieren bei Anruf/Meeting
    if typ in ["anruf", "meeting", "antwort"]:
        m = ds.hole_mandanten().get(mandant, {})
        m["letzte_antwort"] = datetime.now().isoformat()
        ds.mandant_speichern(mandant, m)  # BUGFIX: war ds._speichern (ohne ())

    ds.log_eintrag(f"KOMMUNIKATION | {mandant} | {typ}")
    print("  ✔ Kommunikation gespeichert.")


def verlauf_anzeigen():
    mandant = input("  Mandant: ").strip()

    # BUGFIX: war ds.daten.get("kommunikation", {}) — ds hat kein .daten Attribut
    logs = ds.hole_kommunikation(mandant)

    if not logs:
        print("  Keine Einträge vorhanden.")
        return

    print(f"\n  === VERLAUF: {mandant} ===")
    for eintrag in logs[-10:]:
        try:
            dt   = datetime.fromisoformat(
                eintrag.get("timestamp", eintrag.get("zeit", ""))
            ).strftime("%d.%m.%Y %H:%M")
        except (ValueError, TypeError):
            dt = "—"
        typ  = eintrag.get("typ", "?")
        text = eintrag.get("text", eintrag.get("inhalt", ""))
        print(f"  [{dt}] {typ.upper():<10} {text[:60]}")
    print()
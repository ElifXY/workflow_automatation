# ============================================================
# KANZLEI AI — AUFGABEN MANAGER v2.0
# Datei: modules/aufgaben_manager.py
# Funktioniert weitgehend — Signatur erweitert um prioritaet

from core.daten_speicher import DatenSpeicher
from datetime import datetime
import uuid

ds = DatenSpeicher()


def aufgabe_hinzufuegen(mandant: str = None, beschreibung: str = None,
                        frist: str = None, prioritaet: str = "normal"):
    """Aufgabe für einen Mandanten anlegen."""

    if not mandant:
        mandant = input("  Mandant: ").strip()
    if not beschreibung:
        beschreibung = input("  Beschreibung: ").strip()
    if not frist:
        frist = input("  Frist (YYYY-MM-DD): ").strip()

    if not mandant or not beschreibung or not frist:
        print("  Ungültige Eingabe.")
        return

    try:
        datetime.strptime(frist, "%Y-%m-%d")
    except ValueError:
        print("  Ungültiges Datum — Format: YYYY-MM-DD")
        return

    if mandant not in ds.hole_mandanten():
        print(f"  Warnung: Mandant '{mandant}' nicht gefunden.")

    aufgabe_id = str(uuid.uuid4())
    ds.aufgabe_speichern(aufgabe_id, {
        "id":           aufgabe_id,
        "mandant":      mandant,
        "beschreibung": beschreibung,
        "frist":        frist,
        "prioritaet":   prioritaet,
        "erledigt":     False,
        "erstellt_am":  datetime.now().isoformat(),
    })
    ds.log_eintrag(f"AUFGABE_ERSTELLT | {mandant} | {beschreibung} | {frist}")
    print(f"  ✔ Aufgabe erstellt (ID: {aufgabe_id[:8]}…)")


def aufgaben_anzeigen():
    """Alle Aufgaben anzeigen — sortiert nach Dringlichkeit."""
    aufgaben = ds.hole_fristen()
    jetzt    = datetime.now()

    print("\n" + "=" * 40)
    print("  AUFGABENLISTE")
    print("=" * 40)

    if not aufgaben:
        print("  Keine Aufgaben vorhanden.")
        return

    # Sortieren: überfällig zuerst
    def sort_key(a):
        try:
            tage = (datetime.strptime(a["frist"], "%Y-%m-%d") - jetzt).days
            return (1 if a.get("erledigt") else 0, tage)
        except (ValueError, KeyError):
            return (0, 9999)

    sortiert = sorted(aufgaben.values(), key=sort_key)

    for a in sortiert:
        erledigt = a.get("erledigt", False)
        symbol   = "✔" if erledigt else "·"

        try:
            frist = datetime.strptime(a["frist"], "%Y-%m-%d")
            tage  = (frist - jetzt).days
            if not erledigt:
                if tage < 0:
                    symbol = f"⛔({abs(tage)}d)"
                elif tage == 0:
                    symbol = "🔥"
                elif tage <= 3:
                    symbol = "⚠"
        except (ValueError, KeyError):
            tage = None

        mandant = a.get("mandant", "?")
        beschr  = a.get("beschreibung", "?")[:35]
        frist_s = a.get("frist", "?")
        prio    = a.get("prioritaet", "")

        print(f"  {symbol:<8} {mandant:<20} {beschr:<36} {frist_s}"
              + (f" [{prio}]" if prio and prio != "normal" else ""))

    offen    = sum(1 for a in aufgaben.values() if not a.get("erledigt"))
    erledigt = len(aufgaben) - offen
    print(f"\n  Gesamt: {len(aufgaben)} | Offen: {offen} | Erledigt: {erledigt}")
    print("=" * 40)


def aufgabe_erledigen(aufgabe_id: str = None):
    """Aufgabe als erledigt markieren."""

    if not aufgabe_id:
        aufgabe_id = input("  Aufgaben-ID (oder Teil davon): ").strip()

    aufgaben = ds.hole_fristen()

    # Exakte oder Teilsuche
    gefunden = None
    if aufgabe_id in aufgaben:
        gefunden = aufgabe_id
    else:
        treffer = [k for k in aufgaben if k.startswith(aufgabe_id)]
        if len(treffer) == 1:
            gefunden = treffer[0]
        elif len(treffer) > 1:
            print(f"  Mehrere Treffer — bitte mehr Zeichen eingeben:")
            for t in treffer[:5]:
                print(f"    {t[:16]}… {aufgaben[t].get('beschreibung', '?')}")
            return

    if not gefunden:
        print("  Aufgabe nicht gefunden.")
        return

    a = aufgaben[gefunden]
    a["erledigt"]    = True
    a["erledigt_am"] = datetime.now().isoformat()
    ds.aufgabe_speichern(gefunden, a)
    ds.log_eintrag(f"AUFGABE_ERLEDIGT | {a.get('mandant')} | {a.get('beschreibung')}")
    print(f"  ✔ Erledigt: {a.get('beschreibung', '?')} ({a.get('mandant', '?')})")
    
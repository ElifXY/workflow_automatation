# ============================================================
# KANZLEI AI — DOKUMENTEN MANAGER v2.0
# Datei: modules/dokumenten_manager.py
# Bugs: ds.hole_mandanten ohne () + ds._speichern() falsch + mandanten() Aufruf → behoben
# ============================================================

from core.daten_speicher import DatenSpeicher
from datetime import datetime

ds = DatenSpeicher()


def dokument_anfordern():
    mandant  = input("  Mandant: ").strip()
    mandanten = ds.hole_mandanten()

    if mandant not in mandanten:
        print(f"  Mandant '{mandant}' nicht gefunden.")
        return

    dokument = input("  Dokument anfordern: ").strip()
    if not dokument:
        print("  Abgebrochen.")
        return

    m = mandanten[mandant]
    fehlende = m.get("fehlende_dokumente_liste", [])

    if dokument in fehlende:
        print(f"  '{dokument}' ist bereits angefordert.")
        return

    fehlende.append(dokument)
    m["fehlende_dokumente_liste"] = fehlende
    ds.mandant_speichern(mandant, m)  # BUGFIX: war ds._speichern() — falsche Methode
    ds.log_eintrag(f"DOKUMENT_ANGEFORDERT | {mandant} | {dokument}")
    print(f"  ✔ Dokument angefordert: {dokument}")


def dokument_erhalten():
    mandant  = input("  Mandant: ").strip()
    mandanten = ds.hole_mandanten()

    if mandant not in mandanten:  # BUGFIX: war mandanten() — mandanten ist Dict, kein callable
        print(f"  Mandant '{mandant}' nicht gefunden.")
        return

    m       = mandanten[mandant]
    fehlende = m.get("fehlende_dokumente_liste", [])

    if not fehlende:
        print("  Keine fehlenden Dokumente vorhanden.")
        return

    print(f"  Fehlende Dokumente für {mandant}:")
    for i, d in enumerate(fehlende, 1):
        print(f"    {i} - {d}")

    dokument = input("  Dokument (Name oder Nummer): ").strip()

    # Nummer-Eingabe
    if dokument.isdigit():
        idx = int(dokument) - 1
        if 0 <= idx < len(fehlende):
            dokument = fehlende[idx]
        else:
            print("  Ungültige Nummer.")
            return

    if dokument not in fehlende:
        print("  Dokument nicht in der Liste.")
        return

    fehlende.remove(dokument)
    m["fehlende_dokumente_liste"] = fehlende
    m["letzte_antwort"] = datetime.now().isoformat()
    ds.mandant_speichern(mandant, m)
    ds.log_eintrag(f"DOKUMENT_ERHALTEN | {mandant} | {dokument}")
    print(f"  ✔ '{dokument}' als erhalten markiert. Noch fehlend: {len(fehlende)}")


def dokumente_anzeigen():
    mandanten = ds.hole_mandanten()  # BUGFIX: war ds.hole_mandanten (ohne ())

    print("\n" + "=" * 40)
    print("  FEHLENDE DOKUMENTE — ALLE MANDANTEN")
    print("=" * 40)

    irgendwas = False
    for name, m in mandanten.items():
        docs = m.get("fehlende_dokumente_liste", [])
        if docs:
            irgendwas = True
            print(f"\n  {name}:")
            for d in docs:
                print(f"    · {d}")

    if not irgendwas:
        print("  ✔ Alle Dokumente vollständig.")

    print("=" * 40)
# ============================================================
# KANZLEI AI — MANDANTEN MANAGER v2.0
# Datei: modules/mandanten_manager.py
# Alle Bugs behoben
# ============================================================

from core.daten_speicher import DatenSpeicher
from datetime import datetime

ds = DatenSpeicher()


def mandant_hinzufuegen():
    name = input("  Name des Mandanten: ").strip()
    if not name:
        print("  Ungültiger Name.")
        return

    mandanten = ds.hole_mandanten()  # BUGFIX: war ds.hole_mandanten (ohne ())
    if name in mandanten:
        print("  Mandant existiert bereits.")
        return

    try:
        umsatz_input = input("  Jahresumsatz in € (Enter = 0): ").strip()
        umsatz = float(umsatz_input) if umsatz_input else 0.0
    except ValueError:
        umsatz = 0.0

    email   = input("  E-Mail (optional): ").strip()
    telefon = input("  Telefon (optional): ").strip()
    branche = input("  Branche (optional): ").strip()

    ds.mandant_speichern(name, {
        "umsatz":                   umsatz,
        "email":                    email,
        "telefon":                  telefon,
        "branche":                  branche,
        "fehlende_dokumente_liste": [],
        "letzte_antwort":           datetime.now().isoformat(),
        "letzte_email":             None,
        "erstellt_am":              datetime.now().isoformat(),
        "aktiv":                    True,
    })

    ds.log_eintrag(f"MANDANT_ERSTELLT | {name} | {umsatz}€")
    print(f"  ✔ Mandant '{name}' erfolgreich angelegt.")


def mandanten_anzeigen():
    mandanten = ds.hole_mandanten()

    print("\n" + "=" * 40)
    print("  MANDANTENLISTE")
    print("=" * 40)

    if not mandanten:
        print("  Keine Mandanten vorhanden.")
        return

    for name, m in mandanten.items():
        umsatz = m.get("umsatz", 0)
        email  = m.get("email", "—")
        docs   = len(m.get("fehlende_dokumente_liste", []))
        tage   = ds.berechne_tage_ohne_antwort(name)
        symbol = "⚠" if tage >= 7 or docs > 0 else "✔"
        print(f"  {symbol} {name:<28} €{umsatz:>8,.0f}  "
              f"Docs fehlend: {docs}  Kontakt: vor {tage}d")

    print("=" * 40)


def mandant_suchen():
    name = input("  Mandant suchen: ").strip()
    mandanten = ds.hole_mandanten()

    if name not in mandanten:
        # Teilsuche
        treffer = [n for n in mandanten if name.lower() in n.lower()]
        if treffer:
            print(f"\n  Ähnliche Mandanten:")
            for t in treffer:
                print(f"    · {t}")
        else:
            print("  Nicht gefunden.")
        return

    m    = mandanten[name]
    tage = ds.berechne_tage_ohne_antwort(name)

    print(f"\n  === {name} ===")
    print(f"  Umsatz:          €{m.get('umsatz', 0):,.2f}")
    print(f"  E-Mail:          {m.get('email') or '—'}")
    print(f"  Telefon:         {m.get('telefon') or '—'}")
    print(f"  Branche:         {m.get('branche') or '—'}")
    print(f"  Letzte Antwort:  vor {tage} Tagen")
    fehlende = m.get("fehlende_dokumente_liste", [])
    if fehlende:
        print(f"  Fehlende Docs:   {', '.join(fehlende)}")
    print()


def mandant_loeschen():
    name = input("  Mandant löschen: ").strip()
    mandanten = ds.hole_mandanten()

    if name not in mandanten:
        print("  Mandant nicht gefunden.")
        return

    bestaetigung = input(f"  Wirklich '{name}' löschen? (ja/n): ").strip().lower()
    if bestaetigung != "ja":
        print("  Abgebrochen.")
        return

    ds.mandant_loeschen(name)
    ds.log_eintrag(f"MANDANT_GELOESCHT | {name}")
    print(f"  ✔ Mandant '{name}' gelöscht.")
        
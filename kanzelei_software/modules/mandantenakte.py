# ============================================================
# KANZLEI AI — MANDANTENAKTE v2.0
# Datei: modules/mandantenakte.py
# Bugs: prioritaeten_sortieren falsch aufgerufen + ds.hole_kommunikation() falsch + 
#       Aufgaben-Loop-Bug (print außerhalb for) → alle behoben
# ============================================================

from core.daten_speicher import DatenSpeicher
from core.decision_engine import entscheide, berechne_score
from datetime import datetime

ds = DatenSpeicher()


def mandantenakte_anzeigen():
    name = input("  Mandant: ").strip()
    mandanten = ds.hole_mandanten()

    if name not in mandanten:
        # Teilsuche
        treffer = [n for n in mandanten if name.lower() in n.lower()]
        if treffer:
            print("  Meintest du:")
            for t in treffer:
                print(f"    · {t}")
        else:
            print("  Mandant nicht gefunden.")
        return

    mandant       = mandanten[name]
    aufgaben_alle = ds.hole_fristen()
    aufgaben      = [
        a for a in aufgaben_alle.values()
        if a.get("mandant") == name
    ]

    # BUGFIX: war ds.hole_kommunikation().get(name, []) — Methode erwartet name als Parameter
    kommunikation = ds.hole_kommunikation(name)
    tage          = ds.berechne_tage_ohne_antwort(name)

    # BUGFIX: war prioritaeten_sortieren(mandant, aufgaben) — falsche Signatur
    try:
        score_data = berechne_score(name, aufgaben_alle, ds)
        score      = score_data.get("score", 0)
        status     = "KRITISCH" if score >= 12000 else "WICHTIG" if score >= 5000 else "NORMAL"
    except Exception:
        score, status = 0, "NORMAL"

    symbole = {"KRITISCH": "✖", "WICHTIG": "⚠", "NORMAL": "✔"}
    symbol  = symbole.get(status, "·")

    # ── HEADER ───────────────────────────────────────────────
    print("\n" + "=" * 40)
    print(f"  MANDANTENAKTE: {name}")
    print("=" * 40)

    # ── STAMMDATEN ───────────────────────────────────────────
    print("\n  STAMMDATEN")
    print("  " + "-" * 36)
    print(f"  Jahresumsatz: €{mandant.get('umsatz', 0):,.2f}")
    print(f"  E-Mail:       {mandant.get('email') or '—'}")
    print(f"  Telefon:      {mandant.get('telefon') or '—'}")
    print(f"  Branche:      {mandant.get('branche') or '—'}")

    # ── STATUS ───────────────────────────────────────────────
    print("\n  STATUS")
    print("  " + "-" * 36)
    print(f"  Priorität:        {symbol} {status} (Score: {int(score):,})")
    print(f"  Tage ohne Antwort: {tage}")
    fehlende = mandant.get("fehlende_dokumente_liste", [])
    if fehlende:
        print(f"  Fehlende Dokumente: {', '.join(fehlende)}")
    else:
        print("  Fehlende Dokumente: keine ✔")

    # ── KI-EMPFEHLUNG ────────────────────────────────────────
    print("\n  KI-EMPFEHLUNG")
    print("  " + "-" * 36)
    try:
        decision = entscheide(name, aufgaben_alle, ds)
        for e in decision.get("entscheidungen", [])[:3]:
            if e.get("action") != "nichts":
                print(f"  → {e.get('text', '')}")
    except Exception:
        if status == "KRITISCH":
            print("  → Sofort handeln — Mandant kontaktieren!")
        elif status == "WICHTIG":
            print("  → Baldige Bearbeitung empfohlen")
        else:
            print("  → Kein akuter Handlungsbedarf")

    # ── AUFGABEN ─────────────────────────────────────────────
    print("\n  AUFGABEN")
    print("  " + "-" * 36)
    jetzt = datetime.now()

    if not aufgaben:
        print("  Keine Aufgaben vorhanden.")
    else:
        offen    = [a for a in aufgaben if not a.get("erledigt")]
        erledigt = [a for a in aufgaben if a.get("erledigt")]

        # BUGFIX: print war außerhalb der for-Schleife (falsche Einrückung)
        for a in offen:
            try:
                frist = datetime.strptime(a["frist"], "%Y-%m-%d")
                tage_frist = (frist - jetzt).days
                if tage_frist < 0:
                    st = f"⛔ ÜBERFÄLLIG ({abs(tage_frist)}d)"
                elif tage_frist == 0:
                    st = "🔥 HEUTE"
                elif tage_frist <= 3:
                    st = f"⚠  in {tage_frist}d"
                else:
                    st = f"· in {tage_frist}d"
            except (ValueError, KeyError):
                st = "OFFEN"

            prio = a.get("prioritaet", "")
            prio_str = f" [{prio}]" if prio and prio != "normal" else ""
            print(f"  {st:<20} {a.get('beschreibung', '?')[:35]}{prio_str}")

        if erledigt:
            print(f"\n  Erledigt: {len(erledigt)} Aufgabe(n)")

    # ── KOMMUNIKATION ────────────────────────────────────────
    print("\n  LETZTE KOMMUNIKATION")
    print("  " + "-" * 36)

    if not kommunikation:
        print("  Keine Einträge vorhanden.")
    else:
        for e in kommunikation[-5:]:
            try:
                dt = datetime.fromisoformat(
                    e.get("timestamp", e.get("zeit", ""))
                ).strftime("%d.%m.%Y")
            except (ValueError, TypeError):
                dt = "—"
            typ  = e.get("typ", "?").upper()
            text = e.get("text", e.get("inhalt", ""))[:40]
            print(f"  [{dt}] {typ:<12} {text}")

    print("\n" + "=" * 40)
    ds.log_eintrag(f"MANDANTENAKTE_GEOEFFNET | {name}")
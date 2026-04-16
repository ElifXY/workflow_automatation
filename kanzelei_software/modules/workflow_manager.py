# ============================================================
# KANZLEI AI — WORKFLOW MANAGER v2.0
# Datei: modules/workflow_manager.py
# Bugs: ds.speichern() + vorlage_fehlende_dokumente Import → behoben
# Jetzt: Delegiert an core/engine.py (Single Source of Truth)
# ============================================================

from core.daten_speicher import DatenSpeicher
from core.engine import Engine
from datetime import datetime

ds     = DatenSpeicher()
engine = Engine(ds)


def workflow_steuererklaerung(mandant_name: str):
    """Steuererklärung-Workflow — erstellt Aufgaben + Email."""

    print(f"\n  Starte Workflow: Steuererklärung für {mandant_name}\n")

    frist = input("  Frist für Steuererklärung (YYYY-MM-DD): ").strip()
    try:
        datetime.strptime(frist, "%Y-%m-%d")
    except ValueError:
        print("  Ungültiges Datum.")
        return

    # Aufgabe über DatenSpeicher anlegen
    import uuid
    aufgabe_id = str(uuid.uuid4())
    ds.aufgabe_speichern(aufgabe_id, {
        "id":           aufgabe_id,
        "mandant":      mandant_name,
        "beschreibung": "Steuererklärung erstellen",
        "frist":        frist,
        "prioritaet":   "hoch",
        "kategorie":    "steuererklaerung",
        "erledigt":     False,
        "erstellt_am":  datetime.now().isoformat(),
    })
    print(f"  ✔ Aufgabe erstellt: Steuererklärung bis {frist}")

    # Fehlende Dokumente setzen
    mandanten = ds.hole_mandanten()
    if mandant_name in mandanten:
        m = mandanten[mandant_name]
        standard_docs = [
            "Einkommensnachweise",
            "Betriebsausgaben-Belege",
            "Versicherungsnachweise",
            "Kontoauszüge",
        ]
        fehlende = m.get("fehlende_dokumente_liste", [])
        for d in standard_docs:
            if d not in fehlende:
                fehlende.append(d)
        m["fehlende_dokumente_liste"] = fehlende
        ds.mandant_speichern(mandant_name, m)  # BUGFIX: war ds.speichern() — existiert nicht
        print(f"  ✔ {len(standard_docs)} Dokumente als fehlend markiert")

    # Email-Vorschau
    from core.ai_email import generiere_email_text
    email = generiere_email_text(
        mandant_name, "DOKUMENTE_FEHLEN",
        mandanten.get(mandant_name, {}).get("fehlende_dokumente_liste", [])
    )

    print("\n  Email-Vorschlag:")
    print("  " + "-" * 36)
    for line in email.split("\n")[:8]:
        print(f"  {line}")
    print("  " + "-" * 36)

    if input("\n  Email speichern? (j/n): ").strip().lower() == "j":
        email_id = f"wf_{int(datetime.now().timestamp())}"
        ds.email_speichern(email_id, {
            "id":      email_id,
            "mandant": mandant_name,
            "inhalt":  email,
            "zeit":    datetime.now().isoformat(),
            "typ":     "WORKFLOW_STEUERERKLAERUNG",
            "status":  "gespeichert",
        })
        ds.kommunikation_hinzufuegen(mandant_name, {
            "typ":       "workflow_email",
            "text":      "Steuererklärung-Email vorbereitet",
            "timestamp": datetime.now().isoformat(),
        })
        print("  ✔ Email gespeichert")

    ds.log_eintrag(f"WORKFLOW_STEUERERKLAERUNG | {mandant_name}")
    print("\n  ✔ Workflow abgeschlossen.\n")


def workflow_monatsabschluss(mandant_name: str, monat: int = None, jahr: int = None):
    """Delegiert an Engine.workflow_monatsabschluss."""
    jetzt = datetime.now()
    return engine.workflow_monatsabschluss(
        mandant_name,
        monat or jetzt.month,
        jahr  or jetzt.year,
    )


def workflow_jahresabschluss(mandant_name: str, jahr: int = None):
    """Delegiert an Engine.workflow_jahresabschluss."""
    return engine.workflow_jahresabschluss(
        mandant_name,
        jahr or datetime.now().year,
    )


def workflow_onboarding(mandant_name: str):
    """Delegiert an Engine.workflow_neuer_mandant."""
    return engine.workflow_neuer_mandant(mandant_name)

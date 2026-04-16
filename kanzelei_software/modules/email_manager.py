# ============================================================
# KANZLEI AI — EMAIL MANAGER v2.0
# Datei: modules/email_manager.py
# Nutzt jetzt die intelligente KI-Engine statt statische Templates
# ============================================================

from core.daten_speicher import DatenSpeicher
from core.ai_email import generate_ai_email, generiere_email_text
from datetime import datetime

ds = DatenSpeicher()


def email_generieren(mandant_name: str = None):
    """Interaktiver Email-Generator mit KI-Unterstützung."""

    if not mandant_name:
        mandant_name = input("  Mandant: ").strip()

    mandanten = ds.hole_mandanten()
    if mandant_name not in mandanten:
        print(f"  Mandant '{mandant_name}' nicht gefunden.")
        return

    m = mandanten[mandant_name]

    print("\n" + "=" * 40)
    print("  EMAIL SYSTEM")
    print("=" * 40)
    print("  1 - KI-Email generieren (empfohlen)")
    print("  2 - Fehlende Dokumente anfordern")
    print("  3 - Frist-Erinnerung")
    print("  4 - Keine-Antwort Erinnerung")
    print("=" * 40)

    auswahl = input("  Typ: ").strip()

    if auswahl == "1":
        aufgaben   = ds.hole_fristen()
        email_text = generate_ai_email(mandant_name, m, aufgaben, ds)

    elif auswahl == "2":
        docs = m.get("fehlende_dokumente_liste", [])
        email_text = generiere_email_text(mandant_name, "DOKUMENTE_FEHLEN", docs)

    elif auswahl == "3":
        frist = input("  Frist (YYYY-MM-DD): ").strip()
        try:
            datetime.strptime(frist, "%Y-%m-%d")
        except ValueError:
            print("  Ungültiges Datum.")
            return
        email_text = generiere_email_text(mandant_name, "FRIST")

    elif auswahl == "4":
        email_text = generiere_email_text(mandant_name, "KEINE_ANTWORT")

    else:
        print("  Ungültige Auswahl.")
        return

    print("\n" + "=" * 40)
    print("  GENERIERTE EMAIL")
    print("=" * 40)
    print(email_text)
    print("=" * 40)

    if input("\n  Email speichern? (j/n): ").strip().lower() == "j":
        email_id = f"cli_{int(datetime.now().timestamp())}"
        ds.email_speichern(email_id, {
            "id":      email_id,
            "mandant": mandant_name,
            "inhalt":  email_text,
            "zeit":    datetime.now().isoformat(),
            "typ":     f"cli_auswahl_{auswahl}",
            "status":  "gespeichert",
        })
        ds.kommunikation_hinzufuegen(mandant_name, {
            "typ":       "email_erstellt",
            "text":      email_text[:100] + "...",
            "timestamp": datetime.now().isoformat(),
        })
        ds.log_eintrag(f"EMAIL_GESPEICHERT | {mandant_name}")
        print("  ✔ Email gespeichert.")


# Kompatibilitäts-Alias für alten Code
def vorlage_fehlende_dokumente(mandant: str) -> str:
    return generiere_email_text(mandant, "DOKUMENTE_FEHLEN")

def vorlage_frist_erinnerung(mandant: str, frist: str) -> str:
    return generiere_email_text(mandant, "FRIST")

def vorlage_keine_antwort(mandant: str) -> str:
    return generiere_email_text(mandant, "KEINE_ANTWORT")
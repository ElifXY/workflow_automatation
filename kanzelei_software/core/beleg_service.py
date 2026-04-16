# ============================================================
# KANZLEI AI — BELEG SERVICE v1.0
# KI-gestützte Belegverarbeitung mit Claude Vision API
# Datei: core/beleg_service.py
#
# Das ist der #1 Zeitsparer für Steuerberater:
# Beleg hochladen → KI liest alles → Buchungsvorschlag
#
# Was erkannt wird:
#   ✓ Betrag (Netto, MwSt, Brutto)
#   ✓ Datum
#   ✓ Lieferant/Empfänger
#   ✓ Kategorie (Büro, Reise, Personal, Miete...)
#   ✓ SKR03/SKR04 Kontonummer (Buchungsvorschlag)
#   ✓ Vorsteuer-Abzugsfähigkeit
#   ✓ Rechnungsnummer
#   ✓ Steuersatz (7% / 19% / 0%)
# ============================================================

import base64
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List

log = logging.getLogger("kanzlei_beleg")

# ─── SKR03 Kontenrahmen (die wichtigsten Kategorien) ─────────
SKR03_KATEGORIEN = {
    "buero":          {"soll": "4930", "haben": "1200", "name": "Bürokosten",              "mwst": 19},
    "porto":          {"soll": "4910", "haben": "1200", "name": "Porto / Versand",         "mwst": 19},
    "telefon":        {"soll": "4920", "haben": "1200", "name": "Telefon / Internet",      "mwst": 19},
    "software":       {"soll": "0680", "haben": "1200", "name": "Software / IT",           "mwst": 19},
    "hardware":       {"soll": "0680", "haben": "1200", "name": "Hardware / IT",           "mwst": 19},
    "miete":          {"soll": "4210", "haben": "1200", "name": "Miete Geschäftsräume",    "mwst": 19},
    "strom":          {"soll": "4240", "haben": "1200", "name": "Strom / Heizung",         "mwst": 19},
    "reise":          {"soll": "4670", "haben": "1200", "name": "Reisekosten",             "mwst": 19},
    "bewirtung":      {"soll": "4650", "haben": "1200", "name": "Bewirtung (70%)",         "mwst": 19},
    "kfz":            {"soll": "4520", "haben": "1200", "name": "Kfz-Kosten",             "mwst": 19},
    "benzin":         {"soll": "4530", "haben": "1200", "name": "Kraftstoff",              "mwst": 19},
    "personal":       {"soll": "4120", "haben": "1700", "name": "Löhne / Gehälter",        "mwst": 0},
    "versicherung":   {"soll": "4360", "haben": "1200", "name": "Versicherungen",          "mwst": 0},
    "steuerberater":  {"soll": "4815", "haben": "1200", "name": "Rechts-/Beratungskosten","mwst": 19},
    "werbung":        {"soll": "4600", "haben": "1200", "name": "Werbung / Marketing",     "mwst": 19},
    "weiterbildung":  {"soll": "4900", "haben": "1200", "name": "Weiterbildung",           "mwst": 19},
    "material":       {"soll": "3200", "haben": "1200", "name": "Material / Waren",        "mwst": 19},
    "einnahme":       {"soll": "1200", "haben": "8400", "name": "Einnahme 19% USt",        "mwst": 19},
    "einnahme_7":     {"soll": "1200", "haben": "8300", "name": "Einnahme 7% USt",         "mwst": 7},
    "einnahme_0":     {"soll": "1200", "haben": "8100", "name": "Einnahme steuerfreí",     "mwst": 0},
    "sonstiges":      {"soll": "4980", "haben": "1200", "name": "Sonstige Betriebskosten", "mwst": 19},
}

# ─── System-Prompt für Beleganalyse ──────────────────────────
BELEG_SYSTEM_PROMPT = """Du bist ein spezialisierter KI-Buchhalter für deutsche Steuerberater.
Analysiere den Beleg im Bild und extrahiere alle relevanten Buchungsdaten.

Antworte NUR mit einem validen JSON-Objekt, ohne Markdown-Backticks, ohne Erklärungen:

{
  "typ": "ausgabe|einnahme|gutschrift",
  "datum": "YYYY-MM-DD",
  "betrag_brutto": 119.00,
  "betrag_netto": 100.00,
  "mwst_betrag": 19.00,
  "mwst_satz": 19,
  "waehrung": "EUR",
  "lieferant": "Name des Lieferanten/Absenders",
  "rechnungsnummer": "RE-2024-001 oder leer",
  "kategorie": "buero|porto|telefon|software|hardware|miete|strom|reise|bewirtung|kfz|benzin|personal|versicherung|werbung|weiterbildung|material|einnahme|sonstiges",
  "skr03_soll": "4930",
  "skr03_haben": "1200",
  "buchungstext": "Kurzer Buchungstext max 30 Zeichen",
  "vorsteuer_abzugsfaehig": true,
  "notiz": "Besonderheiten oder Hinweise",
  "vertrauens_score": 0.95
}

Wichtige Regeln:
- Bewirtungsbelege: vorsteuer_abzugsfaehig = true, aber nur 70% abzugsfähig (notiz setzen)
- Privatanteile: in der notiz erwähnen
- Wenn Datum fehlt: heutiges Datum verwenden
- vertrauens_score: 0.0-1.0 (wie sicher du dir bist)
- Bei unlesbaren Belegen: vertrauens_score < 0.5 und notiz mit Hinweis"""


# ============================================================
# HAUPT-ANALYSEFUNKTION
# ============================================================

async def analysiere_beleg(
    bild_data: bytes,
    dateiname: str,
    mandant: str = "",
    api_key: str = None,
) -> Dict[str, Any]:
    """
    Analysiert einen Beleg mit Claude Vision API.

    Args:
        bild_data: Rohe Bilddaten (JPG, PNG, PDF erste Seite)
        dateiname: Originaldateiname (für Mime-Type Erkennung)
        mandant:   Mandantenname (für Kontext)
        api_key:   Anthropic API Key (aus .env wenn None)

    Returns:
        Strukturierter Buchungsvorschlag mit allen Feldern
    """
    import httpx

    key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        raise ValueError("ANTHROPIC_API_KEY fehlt in .env")

    # Mime-Type bestimmen
    name_lower = dateiname.lower()
    if name_lower.endswith(".pdf"):
        media_type = "application/pdf"
    elif name_lower.endswith(".png"):
        media_type = "image/png"
    elif name_lower.endswith(".jpg") or name_lower.endswith(".jpeg"):
        media_type = "image/jpeg"
    elif name_lower.endswith(".webp"):
        media_type = "image/webp"
    else:
        media_type = "image/jpeg"  # Fallback

    # Bild als Base64
    bild_b64 = base64.standard_b64encode(bild_data).decode("utf-8")

    # User-Nachricht mit Mandanten-Kontext
    user_text = f"Analysiere diesen Beleg"
    if mandant:
        user_text += f" für Mandant '{mandant}'"
    user_text += ". Extrahiere alle Buchungsdaten als JSON."

    # Claude API Request
    payload = {
        "model":      "claude-opus-4-5",
        "max_tokens": 1024,
        "system":     BELEG_SYSTEM_PROMPT,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type":   "image",
                    "source": {
                        "type":       "base64",
                        "media_type": media_type,
                        "data":       bild_b64,
                    }
                },
                {
                    "type": "text",
                    "text": user_text,
                }
            ]
        }]
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key":         key,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json",
            },
            json=payload,
        )

    if response.status_code != 200:
        error_detail = response.text[:200]
        raise RuntimeError(f"Claude API Fehler {response.status_code}: {error_detail}")

    # Antwort parsen
    response_data = response.json()
    raw_text = (
        response_data.get("content", [{}])[0]
        .get("text", "{}")
        .strip()
    )

    # JSON sauber extrahieren (manchmal mit ```json wrapped)
    if "```" in raw_text:
        import re
        match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        raw_text = match.group(0) if match else "{}"

    try:
        buchung = json.loads(raw_text)
    except json.JSONDecodeError:
        log.warning(f"JSON-Parse Fehler für Beleg {dateiname}")
        buchung = {"fehler": "JSON konnte nicht geparst werden", "raw": raw_text[:200]}

    # SKR03-Daten anreichern wenn Kategorie bekannt
    kategorie = buchung.get("kategorie", "sonstiges")
    if kategorie in SKR03_KATEGORIEN and "skr03_soll" not in buchung:
        konto = SKR03_KATEGORIEN[kategorie]
        buchung["skr03_soll"]  = konto["soll"]
        buchung["skr03_haben"] = konto["haben"]
        buchung["kategorie_name"] = konto["name"]

    # Metadaten ergänzen
    buchung["beleg_id"]      = str(uuid.uuid4())
    buchung["dateiname"]     = dateiname
    buchung["mandant"]       = mandant
    buchung["analysiert_am"] = datetime.now().isoformat()
    buchung["status"]        = "vorschlag"  # vorschlag | bestaetigt | abgelehnt

    log.info(
        f"Beleg analysiert: {dateiname} | {buchung.get('betrag_brutto', '?')}€ | "
        f"Score: {buchung.get('vertrauens_score', '?')}"
    )

    return buchung


def beleg_ohne_ki_parsen(dateiname: str, manuell: Dict) -> Dict[str, Any]:
    """
    Fallback: Beleg manuell erfassen (wenn keine API-Key vorhanden).
    Gibt Template zurück das der Steuerberater ausfüllen kann.
    """
    kategorie = manuell.get("kategorie", "sonstiges")
    konto     = SKR03_KATEGORIEN.get(kategorie, SKR03_KATEGORIEN["sonstiges"])

    return {
        "beleg_id":      str(uuid.uuid4()),
        "dateiname":     dateiname,
        "typ":           manuell.get("typ", "ausgabe"),
        "datum":         manuell.get("datum", datetime.now().strftime("%Y-%m-%d")),
        "betrag_brutto": manuell.get("betrag_brutto", 0.0),
        "betrag_netto":  manuell.get("betrag_netto", 0.0),
        "mwst_betrag":   manuell.get("mwst_betrag", 0.0),
        "mwst_satz":     manuell.get("mwst_satz", 19),
        "lieferant":     manuell.get("lieferant", ""),
        "kategorie":     kategorie,
        "kategorie_name": konto["name"],
        "skr03_soll":    konto["soll"],
        "skr03_haben":   konto["haben"],
        "buchungstext":  manuell.get("buchungstext", ""),
        "mandant":       manuell.get("mandant", ""),
        "vorsteuer_abzugsfaehig": manuell.get("vorsteuer_abzugsfaehig", True),
        "notiz":         manuell.get("notiz", ""),
        "vertrauens_score": 1.0,
        "analysiert_am": datetime.now().isoformat(),
        "status":        "manuell",
    }


# ============================================================
# BELEG-SPEICHER (in DatenSpeicher integriert)
# ============================================================

def beleg_speichern(ds, beleg: Dict) -> str:
    """Beleg im DatenSpeicher ablegen."""
    beleg_id = beleg.get("beleg_id", str(uuid.uuid4()))
    ds.beleg_speichern(beleg_id, beleg)

    ds.log_eintrag(
        f"BELEG_GESPEICHERT | {beleg.get('mandant', '?')} | "
        f"€{beleg.get('betrag_brutto', 0):.2f} | {beleg.get('kategorie', '?')}"
    )
    return beleg_id


def belege_laden(ds, mandant: str = None, status: str = None) -> List[Dict]:
    """Belege aus DatenSpeicher laden."""
    belege = ds.belege_liste()

    if mandant:
        belege = [b for b in belege if b.get("mandant") == mandant]
    if status:
        belege = [b for b in belege if b.get("status") == status]

    return sorted(belege, key=lambda x: x.get("analysiert_am", ""), reverse=True)


def beleg_bestaetigen(ds, beleg_id: str, korrekturen: Dict = None) -> Dict:
    """
    Buchungsvorschlag bestätigen (mit optionalen Korrekturen).
    Nach Bestätigung wird der Beleg als 'gebucht' markiert.
    """
    beleg = ds.beleg_holen(beleg_id)
    if not beleg:
        raise ValueError(f"Beleg {beleg_id} nicht gefunden")

    if korrekturen:
        beleg.update(korrekturen)

    beleg["status"]          = "bestaetigt"
    beleg["bestaetigt_am"]   = datetime.now().isoformat()

    ds.beleg_speichern(beleg_id, beleg)
    ds.log_eintrag(
        f"BELEG_BESTAETIGT | {beleg.get('mandant', '?')} | "
        f"€{beleg.get('betrag_brutto', 0):.2f} | {beleg.get('skr03_soll', '?')}"
    )
    return beleg


def beleg_ablehnen(ds, beleg_id: str) -> Dict:
    """Beleg als abgelehnt markieren."""
    beleg = ds.beleg_holen(beleg_id)
    if not beleg:
        raise ValueError(f"Beleg {beleg_id} nicht gefunden")
    beleg["status"] = "abgelehnt"
    beleg["abgelehnt_am"] = datetime.now().isoformat()
    ds.beleg_speichern(beleg_id, beleg)
    ds.log_eintrag(f"BELEG_ABGELEHNT | {beleg_id}")
    return {"status": "abgelehnt", "id": beleg_id}


def belege_statistiken(ds, mandant: str = None) -> Dict:
    """Statistiken über verarbeitete Belege."""
    belege = belege_laden(ds, mandant)

    ausgaben = [b for b in belege if b.get("typ") == "ausgabe"]
    einnahmen = [b for b in belege if b.get("typ") == "einnahme"]

    total_ausgaben  = sum(b.get("betrag_brutto", 0) for b in ausgaben)
    total_einnahmen = sum(b.get("betrag_brutto", 0) for b in einnahmen)
    total_vst       = sum(
        b.get("mwst_betrag", 0) for b in ausgaben
        if b.get("vorsteuer_abzugsfaehig", True)
    )

    kategorien: Dict[str, float] = {}
    for b in ausgaben:
        kat = b.get("kategorie_name", b.get("kategorie", "Sonstiges"))
        kategorien[kat] = kategorien.get(kat, 0) + b.get("betrag_brutto", 0)

    return {
        "gesamt_belege":      len(belege),
        "ausgaben_belege":    len(ausgaben),
        "einnahmen_belege":   len(einnahmen),
        "vorschlaege_offen":  sum(1 for b in belege if b.get("status") == "vorschlag"),
        "bestaetigt":         sum(1 for b in belege if b.get("status") == "bestaetigt"),
        "total_ausgaben":     round(total_ausgaben, 2),
        "total_einnahmen":    round(total_einnahmen, 2),
        "total_vorsteuer":    round(total_vst, 2),
        "ergebnis":           round(total_einnahmen - total_ausgaben, 2),
        "kategorien":         dict(sorted(kategorien.items(), key=lambda x: x[1], reverse=True)),
    }
# DATEV EXTF Hilfsfunktionen — Validierung, Normalisierung, Buchungszeilen
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Tuple

from core.aufgabe_erledigt import aufgabe_ist_erledigt

DATEV_VERSION = "700"
DATEV_CATEGORY_BUCHUNGSSTAPEL = "21"
DATEV_ENCODING = "windows-1252"

# Spalten Zeile 2 (Buchungsstapel) — muss mit Datenzeilen übereinstimmen
DATEV_BUCHUNG_SPALTEN: Tuple[str, ...] = (
    "Umsatz (ohne Soll/Haben-Kz)",
    "Soll/Haben-Kennzeichen",
    "WKZ Umsatz",
    "Kurs",
    "Basis-Umsatz",
    "WKZ Basis-Umsatz",
    "Konto",
    "Gegenkonto (ohne BU-Schlüssel)",
    "BU-Schlüssel",
    "Belegdatum",
    "Belegfeld 1",
    "Belegfeld 2",
    "Skonto",
    "Buchungstext",
    "Postensperre",
    "Diverse Adressnummer",
    "Geschäftspartnerbank",
    "Sachverhalt",
    "Zinssperre",
    "Beleglink",
    "Beleginfo - Art 1",
    "Beleginfo - Inhalt 1",
    "KOST1 - Kostenstelle",
    "KOST2 - Kostenstelle",
    "KOST-Menge",
    "EU-Land u. UStID",
    "EU-Steuersatz",
    "Abw. Versteuerungsart",
    "Sachkonto-L/K-Schlüssel",
    "Funktionsergänzung",
    "BU 49 Hauptfunktionstyp",
    "BU 49 Hauptfunktionsnummer",
    "BU 49 Funktionsergänzung",
    "Zusatzinformation - Art 1",
    "Zusatzinformation - Inhalt 1",
    "Stück",
    "Gewicht",
    "Zahlweise",
    "Forderungsart",
    "Veranlagungsjahr",
    "Zugeordnete Fälligkeit",
    "Skontotyp",
    "Auftragsnummer",
    "Buchungstyp",
    "USt-Schlüssel (Anzahlungen)",
    "EU-Land (Anzahlungen)",
    "Sachverhalt L+L",
    "Funktionsergänzung L+L",
    "BU 49 L+L",
    "BU 49 Funktionsergänzung L+L",
    "Zusatzinformation - Art 20",
    "Zusatzinformation - Inhalt 20",
)

DATEV_BUCHUNG_LEER = [""] * (len(DATEV_BUCHUNG_SPALTEN) - 14)


def normalize_berater_nr(raw: Any) -> str:
    s = re.sub(r"\D", "", str(raw or "").strip())[:7]
    return s or "12345"


def normalize_mandanten_nr(
    mandant_name: str,
    mandant_daten: Optional[Mapping[str, Any]] = None,
    fallback: Any = None,
) -> str:
    m = mandant_daten or {}
    explicit = str(m.get("datev_mandanten_nr") or fallback or "").strip()
    if explicit and explicit not in ("00000", "0"):
        digits = re.sub(r"\D", "", explicit)[:5]
        if digits:
            return digits.zfill(5)[-5:]
    # Stabile 5-stellige Nr. pro Mandant (10001–99999)
    base = sum(ord(c) for c in (mandant_name or "M")) % 89999
    return str(10001 + base).zfill(5)


def datev_betrag_str(value: float) -> str:
    return f"{float(value):.2f}".replace(".", ",")


def belegdatum_ddmm(frist: Any, fallback: Optional[datetime] = None) -> str:
    jetzt = fallback or datetime.now()
    if frist:
        s = str(frist).strip()[:10]
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
            try:
                dt = datetime.strptime(s, fmt)
                return dt.strftime("%d%m")
            except ValueError:
                continue
    return jetzt.strftime("%d%m")


def sanitize_datev_text(text: Any, max_len: int = 60) -> str:
    s = str(text or "").replace("\r", " ").replace("\n", " ").replace(";", ",").strip()
    return s[:max_len] if s else ""


def build_datev_buchungen(
    mandant: str,
    mandant_daten: Mapping[str, Any],
    aufgaben: List[Dict[str, Any]],
    jetzt: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Buchungszeilen für EXTF — nur Zeilen mit Betrag > 0 (DATEV-kompatibel)."""
    jetzt = jetzt or datetime.now()
    heute_str = jetzt.strftime("%d%m")
    buchungen: List[Dict[str, Any]] = []

    try:
        umsatz = float(mandant_daten.get("umsatz") or 0)
    except (TypeError, ValueError):
        umsatz = 0.0

    if umsatz > 0:
        monat = max(round(umsatz / 12, 2), 0.01)
        buchungen.append({
            "betrag": monat,
            "sh": "H",
            "konto": "8400",
            "gegenkonto": "14000",
            "datum": heute_str,
            "beleg": f"RE{jetzt.strftime('%Y%m')}001",
            "text": sanitize_datev_text(f"Honorar SB {mandant}", 30),
        })

    # Abgeschlossene Aufgaben mit explizitem Betrag (optional am Aufgaben-Objekt)
    for i, aufgabe in enumerate(aufgaben[:20]):
        if not aufgabe_ist_erledigt(aufgabe):
            continue
        try:
            betrag = float(aufgabe.get("betrag") or aufgabe.get("buchungsbetrag") or 0)
        except (TypeError, ValueError):
            betrag = 0.0
        if betrag <= 0:
            continue
        buchungen.append({
            "betrag": round(betrag, 2),
            "sh": str(aufgabe.get("soll_haben") or "S").upper()[:1] or "S",
            "konto": str(aufgabe.get("konto") or "6300")[:8],
            "gegenkonto": str(aufgabe.get("gegenkonto") or "1200")[:8],
            "datum": belegdatum_ddmm(aufgabe.get("frist"), jetzt),
            "beleg": sanitize_datev_text(aufgabe.get("beleg") or f"AU{i+1:03d}", 12),
            "text": sanitize_datev_text(aufgabe.get("beschreibung") or "Aufgabe", 30),
        })

    return buchungen


def buchung_to_row(b: Mapping[str, Any]) -> List[str]:
    return [
        datev_betrag_str(b["betrag"]),
        str(b.get("sh") or "S"),
        "EUR",
        "",
        "",
        "",
        str(b.get("konto") or ""),
        str(b.get("gegenkonto") or ""),
        "",
        str(b.get("datum") or ""),
        str(b.get("beleg") or ""),
        "",
        "",
        sanitize_datev_text(b.get("text"), 60),
        *DATEV_BUCHUNG_LEER,
    ]


def validate_datev_buchungsstapel_csv(csv_bytes: bytes) -> Dict[str, Any]:
    """Prüft Mindeststruktur EXTF; wirft ValueError bei hartem Fehler."""
    try:
        text = csv_bytes.decode(DATEV_ENCODING)
    except UnicodeDecodeError as e:
        raise ValueError(f"DATEV-Datei Encoding ungültig: {e}") from e

    lines = [ln for ln in text.replace("\r\n", "\n").split("\n") if ln.strip()]
    if len(lines) < 2:
        raise ValueError("DATEV-Datei zu kurz (EXTF-Header fehlt)")

    first = lines[0].split(";")
    if not first or "EXTF" not in first[0].upper().replace('"', ""):
        raise ValueError("Kein gültiger EXTF-Header in Zeile 1")

    col_header = lines[1].split(";")
    if len(col_header) < 10:
        raise ValueError("Spaltenheader (Zeile 2) unvollständig")

    data_lines = lines[2:]
    warnings: List[str] = []
    if not data_lines:
        warnings.append(
            "Keine Buchungszeilen — nur Header. In DATEV prüfen oder Stammdaten importieren; "
            "Buchungen ggf. manuell ergänzen."
        )

    for idx, line in enumerate(data_lines[:50], start=3):
        parts = line.split(";")
        if len(parts) < len(DATEV_BUCHUNG_SPALTEN):
            warnings.append(f"Zeile {idx}: Spaltenanzahl {len(parts)} < {len(DATEV_BUCHUNG_SPALTEN)}")

    return {
        "ok": True,
        "zeilen": len(lines),
        "buchungen": len(data_lines),
        "warnings": warnings,
        "format": f"EXTF v{DATEV_VERSION}",
    }

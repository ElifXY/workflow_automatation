# DATEV EXTF Hilfsfunktionen — Validierung, Normalisierung, Relevanz
from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Tuple

from core.aufgabe_erledigt import aufgabe_ist_erledigt

DATEV_VERSION = "700"
DATEV_CATEGORY_BUCHUNGSSTAPEL = "21"
DATEV_FORMAT_VERSION_BUCHUNGSSTAPEL = "12"  # EXTF 700 Buchungsstapel
DATEV_ENCODING = "windows-1252"

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
DATEV_NCOL = len(DATEV_BUCHUNG_SPALTEN)


def mandanten_in_stammdaten_reihenfolge(mandanten: Mapping[str, Any]) -> List[str]:
    """Stabile Sortierung — identisch in Stammdaten- und Buchungsstapel-Export."""
    return sorted(
        n for n, m in (mandanten or {}).items()
        if n and isinstance(m, dict)
    )


def debitoren_konto_fuer_mandant(
    mandant_name: str,
    mandanten: Optional[Mapping[str, Any]] = None,
    mandant_daten: Optional[Mapping[str, Any]] = None,
) -> str:
    """Debitorenkonto (10001+) konsistent mit Stammdaten-Export."""
    if mandant_daten:
        explicit = str(mandant_daten.get("datev_debitor_konto") or "").strip()
        if explicit.isdigit():
            return explicit.zfill(5)[-8:]
    if mandanten:
        names = mandanten_in_stammdaten_reihenfolge(mandanten)
        if mandant_name in names:
            return str(10001 + names.index(mandant_name))
    base = sum(ord(c) for c in (mandant_name or "M")) % 89999
    return str(10001 + base)


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
    base = sum(ord(c) for c in (mandant_name or "M")) % 89999
    return str(10001 + base).zfill(5)[-5:]


def datev_betrag_str(value: float) -> str:
    v = max(0.0, float(value))
    return f"{v:.2f}".replace(".", ",")


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


def assess_datev_export_relevance(
    mandant: str,
    mandant_daten: Mapping[str, Any],
    aufgaben: List[Dict[str, Any]],
    berater_nr: str = "",
    alle_mandanten: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Nutzen/Relevanz vor Export — transparent für UI und Manifest.
    nutzen: hoch | mittel | gering
    """
    hinweise: List[str] = []
    empfehlungen: List[str] = []

    name = (mandant or "").strip()
    if not name:
        return {
            "nutzen": "keiner",
            "exportierbar": False,
            "buchungen_erwartet": 0,
            "stammdaten_sinnvoll": False,
            "hinweise": ["Kein Mandantenname."],
            "empfehlungen": ["Mandant in der Akte speichern."],
        }

    try:
        umsatz = float(mandant_daten.get("umsatz") or 0)
    except (TypeError, ValueError):
        umsatz = 0.0

    aufgaben_mit_betrag = 0
    for a in aufgaben or []:
        if not aufgabe_ist_erledigt(a):
            continue
        try:
            if float(a.get("betrag") or a.get("buchungsbetrag") or 0) > 0:
                aufgaben_mit_betrag += 1
        except (TypeError, ValueError):
            pass

    buchungen = build_datev_buchungen(
        name, mandant_daten, aufgaben or [], alle_mandanten=alle_mandanten
    )
    n_buch = len(buchungen)

    email = str(mandant_daten.get("email") or "").strip()
    stammdaten_ok = bool(name) and ("@" in email or umsatz > 0 or mandant_daten.get("telefon"))

    bnr = normalize_berater_nr(berater_nr)
    if bnr == "12345" and not str(berater_nr or "").strip():
        hinweise.append(
            "Beraternummer nicht in Einstellungen — Standard 12345. "
            "Bitte unter Einstellungen → Schnittstellen eintragen."
        )
        empfehlungen.append("DATEV Beraternummer hinterlegen.")

    if n_buch == 0:
        hinweise.append(
            "Keine Buchungszeilen mit Betrag > 0. "
            "Stammdaten-Import in DATEV ist trotzdem sinnvoll; Buchungen in DATEV ergänzen."
        )
        empfehlungen.append(
            "Optional: Jahresumsatz am Mandanten pflegen oder Aufgaben mit Feld „betrag“."
        )

    if n_buch > 0:
        hinweise.append(
            f"{n_buch} Buchungszeile(n): Plausibilisierung aus Umsatz/Aufgaben — "
            "in DATEV prüfen, nicht als finale Fibu."
        )

    debitor = debitoren_konto_fuer_mandant(name, alle_mandanten, mandant_daten)
    hinweise.append(f"Debitorenkonto (Stammdaten): {debitor}")

    if n_buch >= 1 and umsatz > 0:
        nutzen = "hoch"
    elif stammdaten_ok or (alle_mandanten and len(mandanten_in_stammdaten_reihenfolge(alle_mandanten)) > 0):
        nutzen = "mittel"
    else:
        nutzen = "gering"
        empfehlungen.append("Stammdaten (E-Mail, Telefon, Umsatz) ergänzen.")

    return {
        "nutzen": nutzen,
        "exportierbar": True,
        "buchungen_erwartet": n_buch,
        "stammdaten_sinnvoll": stammdaten_ok,
        "debitoren_konto": debitor,
        "berater_nr": bnr,
        "hinweise": hinweise,
        "empfehlungen": empfehlungen,
        "rechtlicher_hinweis": (
            "Übergabe an DATEV (EXTF v700). Kanzlei Automation ersetzt keine Buchführung. "
            "DATEV bleibt System of Record."
        ),
    }


def build_datev_buchungen(
    mandant: str,
    mandant_daten: Mapping[str, Any],
    aufgaben: List[Dict[str, Any]],
    jetzt: Optional[datetime] = None,
    alle_mandanten: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Nur Buchungen mit Betrag > 0; Gegenkonto = Debitorenkonto aus Stammdaten."""
    jetzt = jetzt or datetime.now()
    heute_str = jetzt.strftime("%d%m")
    debitor = debitoren_konto_fuer_mandant(mandant, alle_mandanten, mandant_daten)
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
            "gegenkonto": debitor,
            "datum": heute_str,
            "beleg": f"RE{jetzt.strftime('%Y%m')}001",
            "text": sanitize_datev_text(f"PLAUSIB Honorar {mandant}", 30),
        })

    for i, aufgabe in enumerate(aufgaben[:50]):
        if not aufgabe_ist_erledigt(aufgabe):
            continue
        try:
            betrag = float(aufgabe.get("betrag") or aufgabe.get("buchungsbetrag") or 0)
        except (TypeError, ValueError):
            betrag = 0.0
        if betrag <= 0:
            continue
        sh = str(aufgabe.get("soll_haben") or "S").upper()[:1]
        if sh not in ("S", "H"):
            sh = "S"
        buchungen.append({
            "betrag": round(betrag, 2),
            "sh": sh,
            "konto": str(aufgabe.get("konto") or "6300")[:8] or "6300",
            "gegenkonto": str(aufgabe.get("gegenkonto") or debitor)[:8] or debitor,
            "datum": belegdatum_ddmm(aufgabe.get("frist"), jetzt),
            "beleg": sanitize_datev_text(aufgabe.get("beleg") or f"AU{i+1:03d}", 12),
            "text": sanitize_datev_text(aufgabe.get("beschreibung") or "Aufgabe", 30),
        })

    return buchungen


def buchung_to_row(b: Mapping[str, Any]) -> List[str]:
    row = [
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
    if len(row) != DATEV_NCOL:
        raise ValueError(f"Interne Spaltenanzahl {len(row)} != {DATEV_NCOL}")
    return row


def _parse_extf_csv(text: str) -> List[List[str]]:
    return list(csv.reader(io.StringIO(text), delimiter=";", quotechar='"'))


def validate_datev_buchungsstapel_csv(csv_bytes: bytes, *, strict: bool = True) -> Dict[str, Any]:
    """Prüft EXTF-Struktur; strict=True wirft bei harten Fehlern."""
    try:
        text = csv_bytes.decode(DATEV_ENCODING)
    except UnicodeDecodeError as e:
        raise ValueError(f"DATEV-Datei Encoding ungültig: {e}") from e

    rows = _parse_extf_csv(text)
    non_empty = [r for r in rows if any(str(c).strip() for c in r)]
    if len(non_empty) < 2:
        raise ValueError("DATEV-Datei zu kurz (EXTF-Header fehlt)")

    first_cell = (non_empty[0][0] if non_empty[0] else "").upper().replace('"', "").strip()
    if "EXTF" not in first_cell:
        raise ValueError("Kein gültiger EXTF-Header in Zeile 1")

    if len(non_empty[1]) < 10:
        raise ValueError("Spaltenheader (Zeile 2) unvollständig")

    data_rows = non_empty[2:]
    warnings: List[str] = []
    errors: List[str] = []

    if not data_rows:
        warnings.append(
            "Keine Buchungszeilen — nur Header. Stammdaten zuerst importieren; "
            "Buchungen in DATEV manuell ergänzen oder Umsatz/Aufgaben-Beträge pflegen."
        )

    for idx, row in enumerate(data_rows, start=3):
        if len(row) != DATEV_NCOL:
            errors.append(
                f"Zeile {idx}: {len(row)} Spalten statt {DATEV_NCOL} — DATEV-Import würde scheitern."
            )
            continue
        betrag_raw = (row[0] or "").strip()
        sh = (row[1] or "").strip().upper()
        if sh and sh not in ("S", "H"):
            errors.append(f"Zeile {idx}: Soll/Haben '{sh}' ungültig (nur S oder H).")
        if betrag_raw:
            if not re.match(r"^\d+,\d{2}$", betrag_raw):
                errors.append(f"Zeile {idx}: Betrag '{betrag_raw}' ungültig (Format 0,00).")

    if errors and strict:
        raise ValueError("; ".join(errors[:5]))

    return {
        "ok": len(errors) == 0,
        "zeilen": len(non_empty),
        "buchungen": len(data_rows),
        "warnings": warnings,
        "errors": errors,
        "format": f"EXTF v{DATEV_VERSION}",
    }

# ============================================================
# KANZLEI AI — BANK PARSER v1.0
# Datei: core/bank_parser.py
#
# Automatischer Import von Kontoauszügen
# Formate: CAMT.053 XML (Deutsche Standard) + MT940 (SWIFT)
#
# Was passiert nach dem Import:
#   1. Buchungen werden Mandanten zugeordnet (Name-Matching)
#   2. Verdächtige/offene Posten werden markiert
#   3. Fällige Aufgaben werden automatisch als erledigt markiert
#   4. Alles wird im Audit-Log festgehalten
# ============================================================

import xml.etree.ElementTree as ET
import re
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any

log = logging.getLogger("kanzlei_bank")

# CAMT.053 Namespaces
CAMT_NS = {
    "camt": "urn:iso:std:iso:20022:tech:xsd:camt.053.001.02",
    "camt3": "urn:iso:std:iso:20022:tech:xsd:camt.053.001.03",
    "camt6": "urn:iso:std:iso:20022:tech:xsd:camt.053.001.06",
    "camt8": "urn:iso:std:iso:20022:tech:xsd:camt.053.001.08",
}


# ============================================================
# DATENKLASSE: BUCHUNG
# ============================================================

class Buchung:
    """Repräsentiert eine einzelne Bank-Buchung."""

    def __init__(self):
        self.datum:          str   = ""
        self.wert_datum:     str   = ""
        self.betrag:         float = 0.0
        self.waehrung:       str   = "EUR"
        self.soll_haben:     str   = ""    # D = Debit (Ausgabe), C = Credit (Einnahme)
        self.verwendungszweck: str = ""
        self.auftraggeber:   str   = ""
        self.empfaenger:     str   = ""
        self.iban_auftraggeber: str = ""
        self.iban_empfaenger:   str = ""
        self.referenz:       str   = ""
        self.buchungstyp:    str   = ""
        self.end_to_end_id:  str   = ""
        self.mandant:        Optional[str] = None  # Automatisch zugeordnet

    def to_dict(self) -> Dict:
        return {
            "datum":             self.datum,
            "wert_datum":        self.wert_datum,
            "betrag":            self.betrag,
            "waehrung":          self.waehrung,
            "soll_haben":        self.soll_haben,
            "typ":               "Einnahme" if self.soll_haben == "C" else "Ausgabe",
            "verwendungszweck":  self.verwendungszweck,
            "auftraggeber":      self.auftraggeber,
            "empfaenger":        self.empfaenger,
            "iban_auftraggeber": self.iban_auftraggeber,
            "iban_empfaenger":   self.iban_empfaenger,
            "referenz":          self.referenz,
            "buchungstyp":       self.buchungstyp,
            "mandant":           self.mandant,
        }


# ============================================================
# CAMT.053 PARSER
# ============================================================

def parse_camt053(xml_inhalt: bytes) -> Dict[str, Any]:
    """
    Parst CAMT.053 XML (ISO 20022) Kontoauszug.
    Standard der deutschen Banken für elektronische Kontoauszüge.

    Returns:
        Dict mit iban, kontoinhaber, buchungen, saldo, zeitraum
    """
    try:
        root = ET.fromstring(xml_inhalt)
    except ET.ParseError as e:
        raise ValueError(f"Ungültiges XML: {e}")

    # Namespace automatisch erkennen
    ns_uri = ""
    if "}" in root.tag:
        ns_uri = root.tag.split("}")[0] + "}"

    def find(element, path):
        """Namespace-agnostisches Suchen."""
        if not element:
            return None
        # Versuche mit Namespace
        for ns in list(CAMT_NS.values()) + [""]:
            prefix = f"{{{ns}}}" if ns else ""
            parts  = path.split("/")
            el     = element
            for part in parts:
                tag  = prefix + part
                found = el.find(f"./{tag}")
                if found is None:
                    # Ohne Namespace versuchen
                    found = el.find(f"./{part}")
                if found is None:
                    el = None
                    break
                el = found
            if el is not None and el is not element:
                return el
        return None

    def findall(element, path):
        """Namespace-agnostisches Suchen (mehrere)."""
        results = []
        parts   = path.split("/")

        def _suche(el, remaining):
            if not remaining:
                results.append(el)
                return
            tag = remaining[0]
            for child in el:
                child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if child_tag == tag:
                    _suche(child, remaining[1:])

        _suche(element, parts)
        return results

    def text(element, path, default=""):
        el = find(element, path)
        return el.text.strip() if el is not None and el.text else default

    # ── Stammdaten ────────────────────────────────────────────
    iban         = ""
    kontoinhaber = ""
    waehrung     = "EUR"

    # Statement-Infos suchen
    for bk_to_cst in root.iter():
        tag = bk_to_cst.tag.split("}")[-1] if "}" in bk_to_cst.tag else bk_to_cst.tag
        if tag == "IBAN":
            if not iban:
                iban = bk_to_cst.text or ""
        if tag == "Nm" and not kontoinhaber:
            kontoinhaber = bk_to_cst.text or ""

    # Zeitraum
    fr_dt_tm = ""
    to_dt_tm = ""
    for el in root.iter():
        tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if tag == "FrDtTm" and not fr_dt_tm:
            fr_dt_tm = el.text or ""
        if tag == "ToDtTm" and not to_dt_tm:
            to_dt_tm = el.text or ""

    # Saldo
    saldo_betrag = 0.0
    saldo_typ    = ""
    for el in root.iter():
        tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if tag == "Bal":
            for child in el:
                child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if child_tag == "Amt":
                    try:
                        saldo_betrag = float(child.text or 0)
                    except Exception:
                        pass
                if child_tag == "CdtDbtInd":
                    saldo_typ = child.text or ""

    # ── Buchungen ─────────────────────────────────────────────
    buchungen = []

    for ntry in root.iter():
        tag = ntry.tag.split("}")[-1] if "}" in ntry.tag else ntry.tag
        if tag != "Ntry":
            continue

        buchung = Buchung()

        for child in ntry.iter():
            child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

            if child_tag == "Amt":
                try:
                    buchung.betrag = float(child.text or 0)
                    buchung.waehrung = child.attrib.get("Ccy", "EUR")
                except Exception:
                    pass

            elif child_tag == "CdtDbtInd":
                buchung.soll_haben = "C" if child.text == "CRDT" else "D"

            elif child_tag == "BookgDt" or child_tag == "ValDt":
                for date_child in child:
                    dt_tag = date_child.tag.split("}")[-1] if "}" in date_child.tag else date_child.tag
                    if dt_tag in ("Dt", "DtTm"):
                        dt_str = date_child.text or ""
                        if child_tag == "BookgDt":
                            buchung.datum = dt_str[:10]
                        else:
                            buchung.wert_datum = dt_str[:10]

            elif child_tag == "AddtlNtryInf":
                if child.text:
                    buchung.verwendungszweck = child.text.strip()

            elif child_tag == "EndToEndId":
                buchung.end_to_end_id = child.text or ""

            elif child_tag == "RltdPties":
                for rp_child in child.iter():
                    rp_tag = rp_child.tag.split("}")[-1] if "}" in rp_child.tag else rp_child.tag
                    if rp_tag == "Nm" and not buchung.auftraggeber:
                        buchung.auftraggeber = rp_child.text or ""
                    if rp_tag == "IBAN" and not buchung.iban_auftraggeber:
                        buchung.iban_auftraggeber = rp_child.text or ""

            elif child_tag == "RmtInf":
                for ri_child in child.iter():
                    ri_tag = ri_child.tag.split("}")[-1] if "}" in ri_child.tag else ri_child.tag
                    if ri_tag == "Ustrd" and ri_child.text:
                        if not buchung.verwendungszweck:
                            buchung.verwendungszweck = ri_child.text.strip()

        if buchung.betrag > 0 and buchung.datum:
            buchungen.append(buchung)

    log.info(f"CAMT.053 geparst: {len(buchungen)} Buchungen, IBAN: {iban}")

    return {
        "format":       "CAMT.053",
        "iban":         iban,
        "kontoinhaber": kontoinhaber,
        "waehrung":     waehrung,
        "zeitraum_von": fr_dt_tm[:10] if fr_dt_tm else "",
        "zeitraum_bis": to_dt_tm[:10] if to_dt_tm else "",
        "saldo":        saldo_betrag,
        "saldo_typ":    saldo_typ,
        "buchungen":    buchungen,
        "anzahl":       len(buchungen),
    }


# ============================================================
# MT940 PARSER (SWIFT)
# ============================================================

def parse_mt940(inhalt: str) -> Dict[str, Any]:
    """
    Parst MT940 (SWIFT) Kontoauszug.
    Älteres Format, wird von vielen Banken noch unterstützt.
    """
    lines    = inhalt.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    buchungen = []
    iban      = ""
    kontoinhaber = ""
    waehrung  = "EUR"
    saldo     = 0.0

    buchung_aktiv = None

    for line in lines:
        line = line.strip()

        # Kontonummer / IBAN
        if line.startswith(":25:"):
            iban_raw = line[4:].strip()
            # IBAN extrahieren wenn vorhanden
            iban_match = re.search(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", iban_raw)
            iban = iban_match.group(0) if iban_match else iban_raw

        # Anfangssaldo
        elif line.startswith(":60F:") or line.startswith(":60M:"):
            try:
                content  = line[5:]
                waehrung = content[1:4]
                betrag_str = content[10:].replace(",", ".")
                saldo    = float(betrag_str) if content[0] == "C" else -float(betrag_str)
            except Exception:
                pass

        # Buchung
        elif line.startswith(":61:"):
            if buchung_aktiv:
                buchungen.append(buchung_aktiv)

            buchung_aktiv = Buchung()
            try:
                content = line[4:]
                # Datum (YYMMDD)
                datum_raw = content[:6]
                buchung_aktiv.datum = f"20{datum_raw[:2]}-{datum_raw[2:4]}-{datum_raw[4:6]}"

                # Valuta-Datum (optional, MMDD)
                pos = 6
                if content[6:10].isdigit() and len(content) > 10:
                    vd = content[6:10]
                    buchung_aktiv.wert_datum = f"20{datum_raw[:2]}-{vd[:2]}-{vd[2:4]}"
                    pos = 10

                # Soll/Haben + Betrag
                sh_char = content[pos]
                buchung_aktiv.soll_haben = "C" if sh_char == "C" else "D"
                pos += 1
                # Manche MT940 haben 'RD' oder 'RC' etc.
                if content[pos] in "DR":
                    pos += 1

                # Waehrung (3 Zeichen) und Betrag
                betrag_match = re.search(r"(\d+,\d+)", content[pos:])
                if betrag_match:
                    buchung_aktiv.betrag = float(betrag_match.group(1).replace(",", "."))

                # Buchungsschlüssel
                rest = content[content.index(betrag_match.group(1)) + len(betrag_match.group(1)):]
                buchung_aktiv.buchungstyp = rest[:4].strip() if rest else ""

            except Exception as e:
                log.debug(f"MT940 Buchung Parse-Fehler: {e} | Zeile: {line}")
                buchung_aktiv = None

        # Verwendungszweck
        elif line.startswith(":86:") and buchung_aktiv:
            buchung_aktiv.verwendungszweck = line[4:].strip()

        elif line.startswith("?20") and buchung_aktiv:
            buchung_aktiv.verwendungszweck += " " + line[3:]

        elif line.startswith("?30") and buchung_aktiv:
            buchung_aktiv.auftraggeber = line[3:].strip()

        elif line.startswith("?31") and buchung_aktiv:
            buchung_aktiv.iban_auftraggeber = line[3:].strip()

        elif line.startswith("?32") and buchung_aktiv:
            if not buchung_aktiv.auftraggeber:
                buchung_aktiv.auftraggeber = line[3:].strip()

    # Letzte Buchung
    if buchung_aktiv and buchung_aktiv.betrag > 0:
        buchungen.append(buchung_aktiv)

    log.info(f"MT940 geparst: {len(buchungen)} Buchungen")

    return {
        "format":       "MT940",
        "iban":         iban,
        "kontoinhaber": kontoinhaber,
        "waehrung":     waehrung,
        "saldo":        saldo,
        "buchungen":    buchungen,
        "anzahl":       len(buchungen),
    }


# ============================================================
# MANDANTEN-ZUORDNUNG
# ============================================================

def ordne_mandanten_zu(
    buchungen: List[Buchung],
    mandanten: Dict[str, Dict],
) -> List[Buchung]:
    """
    Versucht automatisch, Buchungen Mandanten zuzuordnen.

    Matching-Strategien (in Reihenfolge):
    1. IBAN-Match (präzise)
    2. Name im Verwendungszweck (fuzzy)
    3. Name als Auftraggeber (fuzzy)
    """
    # IBAN-Index aufbauen
    iban_index: Dict[str, str] = {}
    name_index: Dict[str, str] = {}

    for mandant_name, m in mandanten.items():
        iban = m.get("iban", "").replace(" ", "").upper()
        if iban:
            iban_index[iban] = mandant_name

        # Normalisierter Name für Fuzzy-Match
        name_norm = mandant_name.lower().strip()
        name_index[name_norm] = mandant_name

        # Auch Teile des Namens (Nachname, Firmenname)
        teile = name_norm.split()
        for teil in teile:
            if len(teil) > 3:  # Kurze Wörter ignorieren
                if teil not in name_index:
                    name_index[teil] = mandant_name

    for buchung in buchungen:
        if buchung.mandant:
            continue  # Bereits zugeordnet

        # 1. IBAN-Match
        iban_check = buchung.iban_auftraggeber.replace(" ", "").upper()
        if iban_check and iban_check in iban_index:
            buchung.mandant = iban_index[iban_check]
            continue

        # 2. Name im Verwendungszweck
        zweck_lower = buchung.verwendungszweck.lower()
        best_match  = None
        best_len    = 0

        for name_norm, mandant_name in name_index.items():
            if name_norm in zweck_lower and len(name_norm) > best_len:
                best_match = mandant_name
                best_len   = len(name_norm)

        if best_match:
            buchung.mandant = best_match
            continue

        # 3. Auftraggeber-Name
        auftr_lower = buchung.auftraggeber.lower()
        for name_norm, mandant_name in name_index.items():
            if name_norm in auftr_lower and len(name_norm) > best_len:
                best_match = mandant_name
                best_len   = len(name_norm)

        if best_match:
            buchung.mandant = best_match

    zugeordnet = sum(1 for b in buchungen if b.mandant)
    log.info(f"Mandanten-Zuordnung: {zugeordnet}/{len(buchungen)} Buchungen zugeordnet")

    return buchungen


# ============================================================
# ANALYSE: OFFENE POSTEN ERKENNEN
# ============================================================

def erkenne_offene_posten(
    buchungen: List[Buchung],
    mandanten: Dict[str, Dict],
) -> List[Dict]:
    """
    Erkennt offene Posten und Zahlungsausfälle.
    Vergleicht erwartete Honorare mit tatsächlichen Eingängen.
    """
    offene_posten = []

    for mandant_name, m in mandanten.items():
        erwarteter_umsatz = m.get("umsatz", 0)
        if erwarteter_umsatz <= 0:
            continue

        # Einnahmen von diesem Mandanten diese Periode
        eingaenge = [
            b for b in buchungen
            if b.mandant == mandant_name and b.soll_haben == "C"
        ]
        eingegangen = sum(b.betrag for b in eingaenge)
        erwarteter_monat = round(erwarteter_umsatz / 12, 2)

        # Wenn deutlich weniger als erwartet
        if eingaenge and eingegangen < erwarteter_monat * 0.5:
            offene_posten.append({
                "mandant":         mandant_name,
                "erwartet":        erwarteter_monat,
                "eingegangen":     eingegangen,
                "differenz":       round(erwarteter_monat - eingegangen, 2),
                "typ":             "unterzahlung",
                "buchungen":       [b.to_dict() for b in eingaenge],
            })
        elif not eingaenge and erwarteter_monat > 500:
            offene_posten.append({
                "mandant":     mandant_name,
                "erwartet":    erwarteter_monat,
                "eingegangen": 0,
                "differenz":   erwarteter_monat,
                "typ":         "kein_eingang",
                "buchungen":   [],
            })

    return sorted(offene_posten, key=lambda x: x["differenz"], reverse=True)


# ============================================================
# HAUPTFUNKTION: KONTOAUSZUG IMPORTIEREN
# ============================================================

def importiere_kontoauszug(
    inhalt: bytes,
    dateiname: str,
    mandanten: Dict[str, Dict],
    ds=None,  # DatenSpeicher optional
) -> Dict[str, Any]:
    """
    Vollständiger Kontoauszug-Import.

    1. Format erkennen (CAMT.053 oder MT940)
    2. Buchungen parsen
    3. Mandanten automatisch zuordnen
    4. Offene Posten erkennen
    5. Im System speichern

    Returns:
        Vollständiges Import-Ergebnis mit Statistiken
    """
    # Format erkennen
    if dateiname.lower().endswith(".xml") or b"<Document" in inhalt[:500]:
        try:
            ergebnis = parse_camt053(inhalt)
        except Exception as e:
            raise ValueError(f"CAMT.053 Parse-Fehler: {e}")
    else:
        # MT940 (Text-Format)
        try:
            text    = inhalt.decode("utf-8", errors="replace")
            ergebnis = parse_mt940(text)
        except Exception as e:
            raise ValueError(f"MT940 Parse-Fehler: {e}")

    buchungen = ergebnis.pop("buchungen", [])

    # Mandanten zuordnen
    buchungen = ordne_mandanten_zu(buchungen, mandanten)

    # Buchungen als Dicts
    buchungen_dicts = [b.to_dict() for b in buchungen]

    # Offene Posten
    offene_posten = erkenne_offene_posten(buchungen, mandanten)

    # Statistiken
    einnahmen = sum(b.betrag for b in buchungen if b.soll_haben == "C")
    ausgaben  = sum(b.betrag for b in buchungen if b.soll_haben == "D")
    zugeordnet = sum(1 for b in buchungen if b.mandant)

    # Im System speichern (wenn DatenSpeicher vorhanden)
    if ds:
        import_id = f"bank_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        ds.log_eintrag(
            f"BANK_IMPORT | {dateiname} | {len(buchungen)} Buchungen | "
            f"€{einnahmen:.2f} Einnahmen | {zugeordnet} zugeordnet"
        )

        # Kommunikations-Einträge für zugeordnete Buchungen
        for b in buchungen:
            if b.mandant:
                try:
                    ds.kommunikation_hinzufuegen(b.mandant, {
                        "typ":     "bank_buchung",
                        "text":    f"{'Einnahme' if b.soll_haben == 'C' else 'Ausgabe'}: €{b.betrag:.2f} — {b.verwendungszweck[:80]}",
                        "betrag":  b.betrag,
                        "datum":   b.datum,
                        "timestamp": datetime.now().isoformat(),
                    })
                except Exception:
                    pass

    result = {
        **ergebnis,
        "dateiname":      dateiname,
        "import_zeitpunkt": datetime.now().isoformat(),
        "buchungen":      buchungen_dicts,
        "statistiken": {
            "gesamt":        len(buchungen),
            "zugeordnet":    zugeordnet,
            "nicht_zugeordnet": len(buchungen) - zugeordnet,
            "einnahmen":     round(einnahmen, 2),
            "ausgaben":      round(ausgaben, 2),
            "saldo_bewegung": round(einnahmen - ausgaben, 2),
        },
        "offene_posten":  offene_posten,
    }

    log.info(f"Import abgeschlossen: {len(buchungen)} Buchungen, €{einnahmen:.2f} Einnahmen")
    return result
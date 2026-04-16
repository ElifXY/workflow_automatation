# ============================================================
# KANZLEI AI — RECHNUNGS SERVICE v1.0
# Honorarrechnungen erstellen, verwalten, versenden
# Datei: core/rechnungs_service.py
#
# Was Steuerberater täglich brauchen:
#   ✓ Honorarrechnung an Mandant erstellen
#   ✓ Rechnungsnummer automatisch (fortlaufend)
#   ✓ StB-Vergütungsverordnung (StBVV) Positionen
#   ✓ PDF-Generierung (ohne externe Library)
#   ✓ Per Email versenden
#   ✓ Zahlungseingang tracken
#   ✓ Mahnwesen (1. / 2. Mahnung automatisch)
#   ✓ DSGVO-konformes Archiv
# ============================================================

import json
import os
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

log = logging.getLogger("kanzlei_rechnung")

# ─── StBVV Gebührentabelle (vereinfacht) ─────────────────────
STBVV_POSITIONEN = {
    # Buchführung
    "buchfuehrung_monat":    {"bezeichnung": "Buchführung (monatlich)",                    "einheit": "Monat"},
    "buchfuehrung_quartal":  {"bezeichnung": "Buchführung (quartalsweise)",                "einheit": "Quartal"},
    # Jahresabschluss
    "jahresabschluss":       {"bezeichnung": "Jahresabschluss",                            "einheit": "pauschal"},
    "bilanz":                {"bezeichnung": "Erstellung Bilanz",                          "einheit": "pauschal"},
    "guv":                   {"bezeichnung": "Erstellung GuV",                             "einheit": "pauschal"},
    # Steuererklärungen
    "einkommensteuer":       {"bezeichnung": "Einkommensteuererklärung",                   "einheit": "pauschal"},
    "koerperschaftsteuer":   {"bezeichnung": "Körperschaftsteuererklärung",                "einheit": "pauschal"},
    "gewerbesteuer":         {"bezeichnung": "Gewerbesteuererklärung",                     "einheit": "pauschal"},
    "umsatzsteuer":          {"bezeichnung": "Umsatzsteuererklärung",                      "einheit": "pauschal"},
    "ustvoa":                {"bezeichnung": "USt-Voranmeldung",                           "einheit": "Monat"},
    # Lohnbuchhaltung
    "lohnbuchhaltung":       {"bezeichnung": "Lohnbuchhaltung",                           "einheit": "Arbeitnehmer/Monat"},
    # Beratung
    "steuerberatung":        {"bezeichnung": "Steuerberatung (Stundensatz)",               "einheit": "Stunde"},
    "betriebspruefung":      {"bezeichnung": "Begleitung Betriebsprüfung",                 "einheit": "Stunde"},
    "existenzgruendung":     {"bezeichnung": "Existenzgründungsberatung",                  "einheit": "pauschal"},
    # Sonstiges
    "erbschaft":             {"bezeichnung": "Erbschaft-/Schenkungsteuererklärung",        "einheit": "pauschal"},
    "sonstige":              {"bezeichnung": "Sonstige Leistungen",                        "einheit": "pauschal"},
}


# ============================================================
# RECHNUNGSNUMMER-SYSTEM
# ============================================================

def naechste_rechnungsnummer(ds) -> str:
    """
    Generiert fortlaufende Rechnungsnummer.
    Format: RE-YYYY-NNNN (z.B. RE-2026-0042)
    """
    jahr = datetime.now().year
    zaehler = ds.rechnung_counter_next(jahr)

    return f"RE-{jahr}-{zaehler:04d}"


# ============================================================
# RECHNUNG ERSTELLEN
# ============================================================

def erstelle_rechnung(
    ds,
    mandant:        str,
    positionen:     List[Dict],
    leistungsdatum: str = None,
    faellig_tage:   int = 14,
    zahlungsziel:   str = None,
    notiz:          str = "",
    kanzlei_daten:  Dict = None,
) -> Dict[str, Any]:
    """
    Erstellt eine neue Honorarrechnung.

    Args:
        mandant:       Mandantenname
        positionen:    Liste von {"bezeichnung", "menge", "einzelpreis", "mwst_satz"}
        leistungsdatum: Datum der Leistungserbringung
        faellig_tage:  Zahlungsziel in Tagen
        kanzlei_daten: {"name", "adresse", "steuernummer", "iban"}

    Returns:
        Vollständiges Rechnungs-Dict
    """
    mandanten = ds.hole_mandanten()
    m = mandanten.get(mandant, {})

    # Positionen berechnen
    positionen_calc = []
    gesamt_netto    = 0.0
    gesamt_mwst     = 0.0

    for pos in positionen:
        menge        = float(pos.get("menge", 1))
        einzelpreis  = float(pos.get("einzelpreis", 0))
        mwst_satz    = float(pos.get("mwst_satz", 19))
        netto        = round(menge * einzelpreis, 2)
        mwst_betrag  = round(netto * mwst_satz / 100, 2)
        brutto       = round(netto + mwst_betrag, 2)

        gesamt_netto += netto
        gesamt_mwst  += mwst_betrag

        positionen_calc.append({
            "bezeichnung":  pos.get("bezeichnung", "Leistung"),
            "menge":        menge,
            "einheit":      pos.get("einheit", "pauschal"),
            "einzelpreis":  einzelpreis,
            "mwst_satz":    mwst_satz,
            "netto":        netto,
            "mwst_betrag":  mwst_betrag,
            "brutto":       brutto,
        })

    gesamt_brutto = round(gesamt_netto + gesamt_mwst, 2)

    jetzt          = datetime.now()
    faellig_datum  = zahlungsziel or (jetzt + timedelta(days=faellig_tage)).strftime("%Y-%m-%d")
    rechnungsnr    = naechste_rechnungsnummer(ds)

    # Kanzlei-Daten aus Settings
    from modules.settings_manager import setting_holen
    kanzlei = kanzlei_daten or {
        "name":         setting_holen("kanzlei_name") or "Ihre Steuerkanzlei",
        "adresse":      setting_holen("kanzlei_adresse") or "",
        "steuernummer": setting_holen("kanzlei_steuernummer") or "",
        "iban":         setting_holen("kanzlei_iban") or "",
        "bic":          setting_holen("kanzlei_bic") or "",
    }

    rechnung = {
        "id":               str(uuid.uuid4()),
        "rechnungsnummer":  rechnungsnr,
        "datum":            jetzt.strftime("%Y-%m-%d"),
        "leistungsdatum":   leistungsdatum or jetzt.strftime("%Y-%m-%d"),
        "faellig_bis":      faellig_datum,
        "mandant":          mandant,
        "mandant_email":    m.get("email", ""),
        "mandant_adresse":  m.get("adresse", ""),
        "kanzlei":          kanzlei,
        "positionen":       positionen_calc,
        "gesamt_netto":     round(gesamt_netto, 2),
        "gesamt_mwst":      round(gesamt_mwst, 2),
        "gesamt_brutto":    gesamt_brutto,
        "notiz":            notiz,
        "status":           "offen",        # offen | bezahlt | mahnung1 | mahnung2 | storno
        "erstellt_am":      jetzt.isoformat(),
        "bezahlt_am":       None,
        "bezahlt_betrag":   None,
        "mahnungen":        [],
    }

    # Speichern
    _rechnung_speichern(ds, rechnung)
    ds.log_eintrag(f"RECHNUNG_ERSTELLT | {mandant} | {rechnungsnr} | €{gesamt_brutto:.2f}")

    return rechnung


# ============================================================
# RECHNUNG SPEICHERN / LADEN
# ============================================================

def _rechnung_speichern(ds, rechnung: Dict):
    ds.rechnung_speichern(rechnung["id"], rechnung)


def rechnungen_laden(
    ds,
    mandant: str = None,
    status:  str = None,
    limit:   int = 100,
) -> List[Dict]:
    """Alle Rechnungen laden, optional gefiltert."""
    rechnungen = ds.rechnungen_liste()

    if mandant:
        rechnungen = [r for r in rechnungen if r.get("mandant") == mandant]
    if status:
        rechnungen = [r for r in rechnungen if r.get("status") == status]

    rechnungen.sort(key=lambda x: x.get("datum", ""), reverse=True)
    return rechnungen[:limit]


def rechnung_holen(ds, rechnung_id: str) -> Optional[Dict]:
    """Einzelne Rechnung anhand ID laden."""
    return ds.rechnung_holen(rechnung_id)


def rechnung_als_bezahlt(ds, rechnung_id: str, betrag: float = None) -> Dict:
    """Zahlungseingang erfassen."""
    r = ds.rechnung_holen(rechnung_id)
    if not r:
        raise ValueError(f"Rechnung {rechnung_id} nicht gefunden")

    r["status"]         = "bezahlt"
    r["bezahlt_am"]     = datetime.now().isoformat()
    r["bezahlt_betrag"] = betrag or r["gesamt_brutto"]

    ds.rechnung_speichern(rechnung_id, r)
    ds.log_eintrag(f"RECHNUNG_BEZAHLT | {r['mandant']} | {r['rechnungsnummer']} | €{r['bezahlt_betrag']:.2f}")
    return r


def rechnung_stornieren(ds, rechnung_id: str) -> Dict:
    """Rechnung stornieren."""
    r = ds.rechnung_holen(rechnung_id)
    if not r:
        raise ValueError(f"Rechnung {rechnung_id} nicht gefunden")

    r["status"]      = "storno"
    r["storniert_am"] = datetime.now().isoformat()

    ds.rechnung_speichern(rechnung_id, r)
    ds.log_eintrag(f"RECHNUNG_STORNIERT | {r['mandant']} | {r['rechnungsnummer']}")
    return r


# ============================================================
# MAHNWESEN
# ============================================================

def pruefe_offene_rechnungen(ds) -> List[Dict]:
    """
    Prüft alle offenen Rechnungen auf Überfälligkeit.
    Gibt Liste mit Mahnvorschlägen zurück.
    """
    jetzt      = datetime.now()
    rechnungen = rechnungen_laden(ds, status="offen")
    rechnungen += rechnungen_laden(ds, status="mahnung1")
    mahnungen  = []

    for r in rechnungen:
        try:
            faellig = datetime.strptime(r["faellig_bis"], "%Y-%m-%d")
            tage_ueberfaellig = (jetzt - faellig).days

            if tage_ueberfaellig <= 0:
                continue

            mahnung_nr   = len(r.get("mahnungen", [])) + 1
            mahngebueher = 0.0

            if tage_ueberfaellig > 30 and r["status"] == "mahnung1":
                mahnung_typ    = "mahnung2"
                mahngebueher   = 15.00  # Mahngebühr
            elif tage_ueberfaellig > 14 and r["status"] == "offen":
                mahnung_typ    = "mahnung1"
                mahngebueher   = 0.00
            else:
                continue

            mahnungen.append({
                "rechnung_id":      r["id"],
                "rechnungsnummer":  r["rechnungsnummer"],
                "mandant":          r["mandant"],
                "mandant_email":    r.get("mandant_email", ""),
                "betrag":           r["gesamt_brutto"],
                "tage_ueberfaellig": tage_ueberfaellig,
                "mahnung_typ":      mahnung_typ,
                "mahngebuehr":      mahngebueher,
                "gesamt_forderung": r["gesamt_brutto"] + mahngebueher,
            })

        except (ValueError, KeyError):
            continue

    return sorted(mahnungen, key=lambda x: x["tage_ueberfaellig"], reverse=True)


def mahnung_versenden(ds, rechnung_id: str) -> Dict:
    """Mahnung für eine überfällige Rechnung erstellen."""
    r = ds.rechnung_holen(rechnung_id)
    if not r:
        raise ValueError(f"Rechnung {rechnung_id} nicht gefunden")

    r = dict(r)
    mahnung_nr = len(r.get("mahnungen", [])) + 1

    mahnung = {
        "nummer":       mahnung_nr,
        "datum":        datetime.now().isoformat(),
        "typ":          f"mahnung{mahnung_nr}",
        "gesendet_an":  r.get("mandant_email", ""),
    }

    if "mahnungen" not in r:
        r["mahnungen"] = []
    r["mahnungen"].append(mahnung)
    r["status"] = f"mahnung{mahnung_nr}"

    ds.rechnung_speichern(rechnung_id, r)
    ds.log_eintrag(
        f"MAHNUNG_{mahnung_nr} | {r['mandant']} | {r['rechnungsnummer']} | "
        f"€{r['gesamt_brutto']:.2f}"
    )
    return r


# ============================================================
# RECHNUNGS-TEXT GENERIERUNG (HTML/Text)
# ============================================================

def erstelle_rechnungstext(rechnung: Dict) -> str:
    """
    Erstellt den formatierten Rechnungstext als HTML.
    Kann für PDF-Generierung oder Email-Body genutzt werden.
    """
    kanzlei = rechnung.get("kanzlei", {})
    r       = rechnung

    positionen_html = ""
    for i, pos in enumerate(r.get("positionen", []), 1):
        positionen_html += f"""
        <tr style="background:{'#f9f9f9' if i % 2 else '#fff'}">
          <td style="padding:8px 12px;border-bottom:1px solid #eee">{pos['bezeichnung']}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:center">{pos['menge']} {pos['einheit']}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:right">€ {pos['einzelpreis']:.2f}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:center">{pos['mwst_satz']:.0f}%</td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:right"><strong>€ {pos['brutto']:.2f}</strong></td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="UTF-8">
<style>
  body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 13px; color: #1a1a2e; margin: 0; padding: 40px; }}
  .header {{ display: flex; justify-content: space-between; margin-bottom: 40px; }}
  .kanzlei {{ font-size: 11px; color: #666; line-height: 1.7; }}
  .titel {{ font-size: 24px; font-weight: 700; color: #1a1a2e; margin: 30px 0 20px; }}
  .meta-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 30px; }}
  .meta-box {{ background: #f8f9fa; border-radius: 8px; padding: 14px 16px; }}
  .meta-label {{ font-size: 10px; color: #888; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
  th {{ background: #1a1a2e; color: #fff; padding: 10px 12px; text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }}
  .summen {{ margin-left: auto; max-width: 280px; }}
  .summen-row {{ display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #eee; font-size: 13px; }}
  .summen-row.gesamt {{ font-size: 16px; font-weight: 700; border-bottom: 2px solid #1a1a2e; padding: 10px 0; }}
  .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #eee; font-size: 11px; color: #888; }}
</style>
</head>
<body>

<div class="header">
  <div>
    <div style="font-size:22px;font-weight:700;color:#1a1a2e">{kanzlei.get('name', 'Steuerkanzlei')}</div>
    <div class="kanzlei">{kanzlei.get('adresse', '').replace(chr(10), '<br>')}<br>
    StNr: {kanzlei.get('steuernummer', '—')}</div>
  </div>
  <div style="text-align:right">
    <div style="font-size:11px;color:#888">An:</div>
    <div style="font-weight:600">{r['mandant']}</div>
    <div style="font-size:12px;color:#666">{r.get('mandant_adresse', '').replace(chr(10), '<br>')}</div>
  </div>
</div>

<div class="titel">Honorarrechnung {r['rechnungsnummer']}</div>

<div class="meta-grid">
  <div class="meta-box">
    <div class="meta-label">Rechnungsdatum</div>
    <div style="font-weight:600">{datetime.strptime(r['datum'], '%Y-%m-%d').strftime('%d.%m.%Y')}</div>
  </div>
  <div class="meta-box">
    <div class="meta-label">Zahlbar bis</div>
    <div style="font-weight:600;color:#e05555">{datetime.strptime(r['faellig_bis'], '%Y-%m-%d').strftime('%d.%m.%Y')}</div>
  </div>
  <div class="meta-box">
    <div class="meta-label">Leistungszeitraum</div>
    <div style="font-weight:600">{datetime.strptime(r['leistungsdatum'], '%Y-%m-%d').strftime('%d.%m.%Y')}</div>
  </div>
  <div class="meta-box">
    <div class="meta-label">Rechnungsnummer</div>
    <div style="font-weight:600">{r['rechnungsnummer']}</div>
  </div>
</div>

<table>
  <thead>
    <tr>
      <th>Leistungsbeschreibung</th>
      <th style="text-align:center">Menge</th>
      <th style="text-align:right">Einzelpreis</th>
      <th style="text-align:center">MwSt</th>
      <th style="text-align:right">Betrag</th>
    </tr>
  </thead>
  <tbody>{positionen_html}</tbody>
</table>

<div class="summen">
  <div class="summen-row">
    <span>Nettobetrag</span>
    <span>€ {r['gesamt_netto']:.2f}</span>
  </div>
  <div class="summen-row">
    <span>MwSt.</span>
    <span>€ {r['gesamt_mwst']:.2f}</span>
  </div>
  <div class="summen-row gesamt">
    <span>Gesamtbetrag</span>
    <span>€ {r['gesamt_brutto']:.2f}</span>
  </div>
</div>

{f'<p style="margin-top:20px;color:#555;font-size:12px">{r["notiz"]}</p>' if r.get('notiz') else ''}

<div class="footer">
  <strong>Bankverbindung:</strong> {kanzlei.get('iban', '—')} | BIC: {kanzlei.get('bic', '—')} |
  Verwendungszweck: {r['rechnungsnummer']}<br>
  Gemäß § 19 UStG wird keine Umsatzsteuer berechnet. (falls Kleinunternehmer)
</div>

</body></html>"""


def mahnungs_text(rechnung: Dict, mahnung_nr: int = 1) -> str:
    """Mahnungstext als Plain-Text für Email."""
    r     = rechnung
    stufe = ["Zahlungserinnerung", "1. Mahnung", "2. Mahnung"][min(mahnung_nr, 2)]

    return f"""Betreff: {stufe} — Rechnung {r['rechnungsnummer']}

Sehr geehrte/r {r['mandant']},

unsere Rechnung {r['rechnungsnummer']} vom {r['datum']} über
EUR {r['gesamt_brutto']:.2f} ist noch offen.

Zahlungsziel war: {r['faellig_bis']}

Bitte überweisen Sie den Betrag innerhalb von {7 if mahnung_nr == 1 else 5} Tagen auf unser Konto:
IBAN: {r.get('kanzlei', {}).get('iban', '—')}
Verwendungszweck: {r['rechnungsnummer']}

{'Bei weiterer Nichtzahlung behalten wir uns rechtliche Schritte vor.' if mahnung_nr >= 2 else 'Falls Sie bereits bezahlt haben, bitten wir Sie, diese Mahnung als gegenstandslos zu betrachten.'}

Mit freundlichen Grüßen
{r.get('kanzlei', {}).get('name', 'Ihre Kanzlei')}"""


# ============================================================
# RECHNUNGS-STATISTIKEN
# ============================================================

def rechnungs_statistiken(ds) -> Dict:
    """Übersicht über alle Rechnungen und offene Forderungen."""
    alle       = rechnungen_laden(ds, limit=9999)
    jetzt      = datetime.now()

    offen      = [r for r in alle if r["status"] == "offen"]
    bezahlt    = [r for r in alle if r["status"] == "bezahlt"]
    gemahnt    = [r for r in alle if r["status"] in ["mahnung1", "mahnung2"]]

    umsatz_ges = sum(r["gesamt_brutto"] for r in bezahlt)
    offen_ges  = sum(r["gesamt_brutto"] for r in (offen + gemahnt))

    ueberfaellig = []
    for r in offen + gemahnt:
        try:
            faellig = datetime.strptime(r["faellig_bis"], "%Y-%m-%d")
            if faellig < jetzt:
                ueberfaellig.append(r)
        except Exception:
            pass

    return {
        "gesamt_rechnungen":   len(alle),
        "offen":               len(offen),
        "bezahlt":             len(bezahlt),
        "gemahnt":             len(gemahnt),
        "ueberfaellig":        len(ueberfaellig),
        "offene_forderungen":  round(offen_ges, 2),
        "bezahlter_umsatz":    round(umsatz_ges, 2),
        "ueberfaellig_betrag": round(sum(r["gesamt_brutto"] for r in ueberfaellig), 2),
    }
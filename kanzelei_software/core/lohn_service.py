# ============================================================
# KANZLEI AI — LOHN SERVICE v1.0
# Datei: core/lohn_service.py
#
# Vollautomatische Lohnabrechnung:
#   ✓ Krankmeldungen, Urlaub, Überstunden einlesen
#   ✓ Lohnabrechnung berechnen (Brutto → Netto)
#   ✓ Lohnsteuer, SV-Beiträge, KV, RV, AV, PV
#   ✓ PDF-Lohnzettel erstellen
#   ✓ Direkt an Mitarbeiter versenden
#   ✓ ELSTER-Meldung vorbereiten (DEÜV)
#   ✓ Import aus Zeiterfassungs-Apps (CSV/JSON)
# ============================================================

import uuid
import logging
import json
import csv
import io
from datetime import datetime, date
from typing import Dict, List, Optional, Any

log = logging.getLogger("kanzlei_lohn")

# ─── Steuer-/SV-Sätze 2026 (Deutschland, vereinfacht) ────────
LOHNSTEUER_KLASSEN = {
    1: {"grundfreibetrag": 11784, "faktor": 0.14},  # Lohnsteuerklasse I
    2: {"grundfreibetrag": 11784, "faktor": 0.14},
    3: {"grundfreibetrag": 23568, "faktor": 0.14},
    4: {"grundfreibetrag": 11784, "faktor": 0.14},
    5: {"grundfreibetrag": 0,     "faktor": 0.25},
    6: {"grundfreibetrag": 0,     "faktor": 0.30},
}

SV_SAETZE = {
    "krankenversicherung_an":    0.0730,   # Arbeitnehmeranteil
    "krankenversicherung_ag":    0.0730,   # Arbeitgeberanteil
    "pflegeversicherung_an":     0.0170,
    "pflegeversicherung_ag":     0.0170,
    "rentenversicherung_an":     0.0930,
    "rentenversicherung_ag":     0.0930,
    "arbeitslosenversicherung_an": 0.0130,
    "arbeitslosenversicherung_ag": 0.0130,
    "beitragsbemessungsgrenze_kv": 62100 / 12,  # Monatlich
    "beitragsbemessungsgrenze_rv": 90600 / 12,
}

URLAUBSTAGE_STANDARD = 20  # Gesetzliches Minimum
FEIERTAGE_2026       = 11  # Bayern/NRW als Beispiel


class LohnService:

    def __init__(self, ds):
        self.ds = ds

    def _lohn_daten(self) -> Dict:
        return {"lohnabrechnung": self.ds.lohnabrechnung_holen()}

    # ============================================================
    # MITARBEITER VERWALTEN
    # ============================================================

    @staticmethod
    def _mandanten_liste(mandant: str, mandanten: Optional[List[str]] = None) -> List[str]:
        extra = [m.strip() for m in (mandanten or []) if m and str(m).strip()]
        primary = (mandant or "").strip()
        out: List[str] = []
        for m in [primary, *extra]:
            if m and m not in out:
                out.append(m)
        return out or ([primary] if primary else [])

    def mitarbeiter_anlegen(
        self,
        mandant:       str,
        name:          str,
        brutto_monat:  float,
        steuer_klasse: int = 1,
        sozialversicherung: bool = True,
        urlaubstage:   int = 20,
        wochenstunden: float = 40.0,
        steuer_id:     str = "",
        sv_nr:         str = "",
        iban:          str = "",
        eintritt:      str = None,
        mandanten:     Optional[List[str]] = None,
    ) -> Dict:
        """Neuen Mitarbeiter für Lohnabrechnung anlegen."""
        data = self._lohn_daten()
        ma_id = str(uuid.uuid4())
        mandanten_liste = self._mandanten_liste(mandant, mandanten)
        haupt_mandant = mandanten_liste[0] if mandanten_liste else mandant

        mitarbeiter = {
            "id":             ma_id,
            "mandant":        haupt_mandant,
            "mandanten":      mandanten_liste,
            "name":           name,
            "brutto_monat":   brutto_monat,
            "steuer_klasse":  steuer_klasse,
            "sozialversicherung": sozialversicherung,
            "urlaubstage":    urlaubstage,
            "wochenstunden":  wochenstunden,
            "steuer_id":      steuer_id,
            "sv_nr":          sv_nr,
            "iban":           iban,
            "eintritt":       eintritt or datetime.now().strftime("%Y-%m-%d"),
            "aktiv":          True,
            "erstellt_am":    datetime.now().isoformat(),
        }

        data["lohnabrechnung"]["mitarbeiter"][ma_id] = mitarbeiter
        self.ds.lohnabrechnung_speichern(data["lohnabrechnung"])
        self.ds.log_eintrag(f"LOHN_MITARBEITER | {mandant} | {name} | €{brutto_monat}")
        return mitarbeiter

    def _ma_hat_mandant(self, ma: Dict, mandant: str) -> bool:
        if not mandant:
            return True
        liste = ma.get("mandanten") or []
        if not liste and ma.get("mandant"):
            liste = [ma["mandant"]]
        return mandant in liste

    def mitarbeiter_holen(self, ma_id: str) -> Dict:
        data = self._lohn_daten()
        ma = data["lohnabrechnung"]["mitarbeiter"].get(ma_id)
        if not ma:
            raise ValueError(f"Mitarbeiter {ma_id} nicht gefunden")
        return dict(ma)

    def mitarbeiter_aktualisieren(
        self,
        ma_id: str,
        *,
        mandant: Optional[str] = None,
        mandanten: Optional[List[str]] = None,
        name: Optional[str] = None,
        brutto_monat: Optional[float] = None,
        steuer_klasse: Optional[int] = None,
        sozialversicherung: Optional[bool] = None,
        urlaubstage: Optional[int] = None,
        wochenstunden: Optional[float] = None,
        steuer_id: Optional[str] = None,
        sv_nr: Optional[str] = None,
        iban: Optional[str] = None,
        eintritt: Optional[str] = None,
        aktiv: Optional[bool] = None,
    ) -> Dict:
        """Bestehenden Mitarbeiter bearbeiten."""
        data = self._lohn_daten()
        ma = data["lohnabrechnung"]["mitarbeiter"].get(ma_id)
        if not ma:
            raise ValueError(f"Mitarbeiter {ma_id} nicht gefunden")
        ma = dict(ma)

        if mandant is not None or mandanten is not None:
            basis = (mandant or ma.get("mandant") or "").strip()
            mandanten_liste = self._mandanten_liste(basis, mandanten)
            if not mandanten_liste:
                raise ValueError("Mindestens ein Mandant erforderlich")
            ma["mandant"] = mandanten_liste[0]
            ma["mandanten"] = mandanten_liste

        if name is not None:
            n = (name or "").strip()
            if not n:
                raise ValueError("Name erforderlich")
            ma["name"] = n
        if brutto_monat is not None:
            if float(brutto_monat) < 0:
                raise ValueError("Bruttogehalt ungültig")
            ma["brutto_monat"] = float(brutto_monat)
        if steuer_klasse is not None:
            sk = int(steuer_klasse)
            if sk not in LOHNSTEUER_KLASSEN:
                raise ValueError("Steuerklasse muss 1–6 sein")
            ma["steuer_klasse"] = sk
        if sozialversicherung is not None:
            ma["sozialversicherung"] = bool(sozialversicherung)
        if urlaubstage is not None:
            ma["urlaubstage"] = int(urlaubstage)
        if wochenstunden is not None:
            ma["wochenstunden"] = float(wochenstunden)
        if steuer_id is not None:
            ma["steuer_id"] = steuer_id.strip()
        if sv_nr is not None:
            ma["sv_nr"] = sv_nr.strip()
        if iban is not None:
            ma["iban"] = iban.strip()
        if eintritt is not None:
            ma["eintritt"] = eintritt
        if aktiv is not None:
            ma["aktiv"] = bool(aktiv)

        ma["geaendert_am"] = datetime.now().isoformat()
        data["lohnabrechnung"]["mitarbeiter"][ma_id] = ma
        self.ds.lohnabrechnung_speichern(data["lohnabrechnung"])
        self.ds.log_eintrag(f"LOHN_MITARBEITER_UPDATE | {ma.get('mandant')} | {ma.get('name')}")
        return ma

    def mitarbeiter_liste(self, mandant: str = None) -> List[Dict]:
        data = self._lohn_daten()
        ma   = [m for m in data["lohnabrechnung"]["mitarbeiter"].values() if m.get("aktiv", True)]
        if mandant:
            ma = [m for m in ma if self._ma_hat_mandant(m, mandant)]
        return ma

    # ============================================================
    # ZEITDATEN IMPORTIEREN (aus Apps oder CSV)
    # ============================================================

    def zeitdaten_importieren(
        self,
        ma_id:  str,
        monat:  str,  # "2026-01"
        daten:  Dict,
    ) -> Dict:
        """
        Zeitdaten für einen Mitarbeiter importieren.
        Unterstützt manuell, CSV-Import oder App-Webhooks.
        """
        data = self._lohn_daten()

        key = f"{ma_id}_{monat}"
        zeitdaten = {
            "id":           key,
            "ma_id":        ma_id,
            "monat":        monat,
            "arbeitstage":  daten.get("arbeitstage", 21),
            "krankheitstage": daten.get("krankheitstage", 0),
            "urlaubstage":  daten.get("urlaubstage", 0),
            "ueberstunden": daten.get("ueberstunden", 0.0),
            "fehlstunden":  daten.get("fehlstunden", 0.0),
            "zuschlaege":   daten.get("zuschlaege", 0.0),  # Nacht, Wochenende, etc.
            "abzuege":      daten.get("abzuege", 0.0),
            "notiz":        daten.get("notiz", ""),
            "importiert_am":datetime.now().isoformat(),
            "quelle":       daten.get("quelle", "manuell"),
        }

        data["lohnabrechnung"]["zeitdaten"][key] = zeitdaten
        self.ds.lohnabrechnung_speichern(data["lohnabrechnung"])
        return zeitdaten

    def zeitdaten_csv_importieren(self, csv_inhalt: str, mandant: str, monat: str) -> Dict:
        """
        CSV-Import aus Zeiterfassungs-Apps (Personio, Factorial, etc.).
        Erwartet Spalten: Name, Arbeitstage, Krankheit, Urlaub, Überstunden
        """
        reader    = csv.DictReader(io.StringIO(csv_inhalt), delimiter=";")
        importiert = 0
        fehler    = []

        data         = self._lohn_daten()
        alle_ma      = {m["name"].lower(): m for m in self.mitarbeiter_liste(mandant)}

        for zeile in reader:
            try:
                name = zeile.get("Name","").strip()
                if not name:
                    continue

                # Mitarbeiter finden
                ma = alle_ma.get(name.lower())
                if not ma:
                    fehler.append(f"Mitarbeiter '{name}' nicht gefunden")
                    continue

                self.zeitdaten_importieren(ma["id"], monat, {
                    "arbeitstage":   int(zeile.get("Arbeitstage",   21)),
                    "krankheitstage":int(zeile.get("Krankheitstage", 0)),
                    "urlaubstage":   int(zeile.get("Urlaubstage",    0)),
                    "ueberstunden":  float(zeile.get("Überstunden",  0.0).replace(",",".")),
                    "quelle":        "csv_import",
                })
                importiert += 1
            except Exception as e:
                fehler.append(f"Zeile '{zeile}': {e}")

        return {"importiert": importiert, "fehler": fehler}

    # ============================================================
    # LOHNABRECHNUNG BERECHNEN
    # ============================================================

    def berechne_abrechnung(
        self,
        ma_id: str,
        monat: str,
    ) -> Dict:
        """
        Berechnet die komplette Lohnabrechnung für einen Mitarbeiter.
        Brutto → Netto mit allen Abzügen.
        """
        data = self._lohn_daten()
        ma   = data["lohnabrechnung"]["mitarbeiter"].get(ma_id)
        if not ma:
            raise ValueError(f"Mitarbeiter {ma_id} nicht gefunden")

        # Zeitdaten (wenn vorhanden)
        zeitdaten = data["lohnabrechnung"]["zeitdaten"].get(f"{ma_id}_{monat}", {})

        brutto_monat  = ma["brutto_monat"]
        arbeitstage   = zeitdaten.get("arbeitstage", 21)
        krank_tage    = zeitdaten.get("krankheitstage", 0)
        urlaub_tage   = zeitdaten.get("urlaubstage", 0)
        überstunden   = zeitdaten.get("ueberstunden", 0.0)
        zuschlaege    = zeitdaten.get("zuschlaege", 0.0)
        abzuege_extra = zeitdaten.get("abzuege", 0.0)

        # ── Brutto angepasst ──────────────────────────────────
        wochenstunden = float(ma.get("wochenstunden") or 40.0)
        if wochenstunden <= 0:
            wochenstunden = 40.0
        std_arbeitstage = max(arbeitstage, 1)
        std_stundensatz = brutto_monat / (wochenstunden * 4.33) if wochenstunden > 0 else 0.0

        # Krankheitstage: Lohnfortzahlung 6 Wochen (EFZ)
        krank_abzug = 0.0  # Arbeitgeber zahlt voll bis 6 Wochen → kein Abzug für MA

        # Überstunden-Vergütung
        überstunden_brutto = round(überstunden * std_stundensatz * 1.25, 2)  # 25% Zuschlag

        brutto_gesamt = round(brutto_monat + überstunden_brutto + zuschlaege, 2)

        # ── Lohnsteuer ────────────────────────────────────────
        klasse        = LOHNSTEUER_KLASSEN.get(ma["steuer_klasse"], LOHNSTEUER_KLASSEN[1])
        jahresbrutto  = brutto_gesamt * 12
        zvE_jahr      = max(0, jahresbrutto - klasse["grundfreibetrag"])

        # Progressive Besteuerung (vereinfacht)
        if zvE_jahr <= 0:
            lohnsteuer_jahr = 0.0
        elif zvE_jahr <= 17005:
            lohnsteuer_jahr = 0.0
        elif zvE_jahr <= 66760:
            y = (zvE_jahr - 17005) / 10000
            lohnsteuer_jahr = max(0.0, (939.68 * y + 1400) * y)
        elif zvE_jahr <= 277826:
            z = (zvE_jahr - 66760) / 10000
            lohnsteuer_jahr = max(0.0, (206.43 * z + 2397) * z + 9972)
        else:
            lohnsteuer_jahr = max(0.0, 0.45 * zvE_jahr - 18307)

        lohnsteuer_monat = round(max(0.0, lohnsteuer_jahr / 12), 2)
        soli_monat       = round(max(0, lohnsteuer_monat * 0.055), 2)

        # ── Sozialversicherung ────────────────────────────────
        sv = SV_SAETZE
        if ma.get("sozialversicherung", True):
            bemessungsgrundlage_kv = min(brutto_gesamt, sv["beitragsbemessungsgrenze_kv"])
            bemessungsgrundlage_rv = min(brutto_gesamt, sv["beitragsbemessungsgrenze_rv"])
            kv_an = round(bemessungsgrundlage_kv * sv["krankenversicherung_an"], 2)
            kv_ag = round(bemessungsgrundlage_kv * sv["krankenversicherung_ag"], 2)
            pv_an = round(bemessungsgrundlage_kv * sv["pflegeversicherung_an"], 2)
            pv_ag = round(bemessungsgrundlage_kv * sv["pflegeversicherung_ag"], 2)
            rv_an = round(bemessungsgrundlage_rv * sv["rentenversicherung_an"], 2)
            rv_ag = round(bemessungsgrundlage_rv * sv["rentenversicherung_ag"], 2)
            av_an = round(bemessungsgrundlage_rv * sv["arbeitslosenversicherung_an"], 2)
            av_ag = round(bemessungsgrundlage_rv * sv["arbeitslosenversicherung_ag"], 2)
            sv_gesamt_an = kv_an + pv_an + rv_an + av_an
            sv_gesamt_ag = kv_ag + pv_ag + rv_ag + av_ag
        else:
            kv_an = kv_ag = pv_an = pv_ag = rv_an = rv_ag = av_an = av_ag = 0.0
            sv_gesamt_an = sv_gesamt_ag = 0.0

        # ── Netto ─────────────────────────────────────────────
        gesamt_abzuege = lohnsteuer_monat + soli_monat + sv_gesamt_an + abzuege_extra
        netto          = round(brutto_gesamt - gesamt_abzuege, 2)

        # Arbeitgeberkosten
        ag_kosten_gesamt = round(brutto_gesamt + sv_gesamt_ag, 2)

        # ── Urlaubsübersicht ──────────────────────────────────
        urlaub_genommen = urlaub_tage  # Diesen Monat
        urlaub_anspruch = ma.get("urlaubstage", URLAUBSTAGE_STANDARD)

        abrechnung_id = str(uuid.uuid4())
        abrechnung = {
            "id":               abrechnung_id,
            "ma_id":            ma_id,
            "mitarbeiter_name": ma["name"],
            "mandant":          ma["mandant"],
            "monat":            monat,
            "brutto_grund":     brutto_monat,
            "überstunden_std":  überstunden,
            "überstunden_brutto": überstunden_brutto,
            "zuschlaege":       zuschlaege,
            "brutto_gesamt":    brutto_gesamt,
            "lohnsteuer":       lohnsteuer_monat,
            "solidaritaetszuschlag": soli_monat,
            "kv_an": kv_an, "kv_ag": kv_ag,
            "pv_an": pv_an, "pv_ag": pv_ag,
            "rv_an": rv_an, "rv_ag": rv_ag,
            "av_an": av_an, "av_ag": av_ag,
            "sv_gesamt_an":    sv_gesamt_an,
            "sv_gesamt_ag":    sv_gesamt_ag,
            "gesamt_abzuege":  gesamt_abzuege,
            "netto":           netto,
            "ag_kosten_gesamt":ag_kosten_gesamt,
            "krankheitstage":  krank_tage,
            "urlaubstage":     urlaub_genommen,
            "urlaub_anspruch": urlaub_anspruch,
            "iban":            ma.get("iban",""),
            "berechnet_am":    datetime.now().isoformat(),
            "status":          "berechnet",
        }

        # Speichern
        data["lohnabrechnung"]["abrechnungen"][abrechnung_id] = abrechnung
        self.ds.lohnabrechnung_speichern(data["lohnabrechnung"])
        self.ds.log_eintrag(
            f"LOHNABRECHNUNG | {ma['mandant']} | {ma['name']} | {monat} | "
            f"€{brutto_gesamt} brutto → €{netto} netto"
        )

        return abrechnung

    def batch_abrechnung(self, mandant: str, monat: str) -> List[Dict]:
        """Alle Mitarbeiter eines Mandanten auf einmal abrechnen."""
        mitarbeiter  = self.mitarbeiter_liste(mandant)
        abrechnungen = []
        for ma in mitarbeiter:
            try:
                a = self.berechne_abrechnung(ma["id"], monat)
                abrechnungen.append(a)
            except Exception as e:
                log.warning(f"Abrechnung für {ma['name']}: {e}")
        return abrechnungen

    def lohnzettel_html(self, abrechnung_id: str) -> str:
        """Lohnzettel als HTML (für PDF-Druck)."""
        data = self._lohn_daten()
        a    = data["lohnabrechnung"]["abrechnungen"].get(abrechnung_id)
        if not a:
            raise ValueError("Abrechnung nicht gefunden")

        monat_label = datetime.strptime(a["monat"], "%Y-%m").strftime("%B %Y")
        f = lambda v: f"€ {v:,.2f}".replace(",","X").replace(".",",").replace("X",".")

        return f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="UTF-8">
<style>
body{{font-family:Helvetica,Arial,sans-serif;font-size:12px;color:#1a1a2e;margin:0;padding:32px}}
h1{{font-size:20px;margin-bottom:4px;color:#1a1a2e}}
.sub{{color:#666;font-size:12px;margin-bottom:24px}}
table{{width:100%;border-collapse:collapse;margin-bottom:16px}}
th{{background:#1a1a2e;color:#fff;padding:8px 10px;text-align:left;font-size:11px}}
td{{padding:7px 10px;border-bottom:1px solid #eee}}
.right{{text-align:right}} .bold{{font-weight:700}}
.total{{background:#f8f9fa;font-weight:700;font-size:13px}}
.green{{color:#2d8a47}} .red{{color:#c0392b}}
</style></head><body>
<h1>Lohnabrechnung {monat_label}</h1>
<div class="sub">Mitarbeiter: <strong>{a['mitarbeiter_name']}</strong> | IBAN: {a.get('iban','—')}</div>

<table>
<tr><th>Bezüge</th><th class="right">Betrag</th></tr>
<tr><td>Grundgehalt</td><td class="right">{f(a['brutto_grund'])}</td></tr>
{"<tr><td>Überstunden ("+str(a['überstunden_std'])+" Std.)</td><td class='right'>"+f(a['überstunden_brutto'])+"</td></tr>" if a['überstunden_std'] else ""}
{"<tr><td>Zuschläge</td><td class='right'>"+f(a['zuschlaege'])+"</td></tr>" if a['zuschlaege'] else ""}
<tr class="total"><td>Brutto gesamt</td><td class="right">{f(a['brutto_gesamt'])}</td></tr>
</table>

<table>
<tr><th>Abzüge Arbeitnehmer</th><th class="right">Betrag</th></tr>
<tr><td>Lohnsteuer (Kl. {self._lohn_daten()["lohnabrechnung"]["mitarbeiter"].get(a["ma_id"],{}).get("steuer_klasse",1)})</td><td class="right red">{f(a['lohnsteuer'])}</td></tr>
<tr><td>Solidaritätszuschlag</td><td class="right red">{f(a['solidaritaetszuschlag'])}</td></tr>
<tr><td>Krankenversicherung AN</td><td class="right red">{f(a['kv_an'])}</td></tr>
<tr><td>Pflegeversicherung AN</td><td class="right red">{f(a['pv_an'])}</td></tr>
<tr><td>Rentenversicherung AN</td><td class="right red">{f(a['rv_an'])}</td></tr>
<tr><td>Arbeitslosenversicherung AN</td><td class="right red">{f(a['av_an'])}</td></tr>
<tr class="total"><td class="red">Abzüge gesamt</td><td class="right red">{f(a['gesamt_abzuege'])}</td></tr>
<tr class="total" style="font-size:15px"><td class="green">Auszahlungsbetrag (Netto)</td><td class="right green">{f(a['netto'])}</td></tr>
</table>

<table>
<tr><th>Arbeitgeberkosten</th><th class="right">Betrag</th></tr>
<tr><td>Brutto + AG-Anteile SV</td><td class="right">{f(a['ag_kosten_gesamt'])}</td></tr>
</table>

<table>
<tr><th>Urlaub / Fehlzeiten</th><th class="right">Tage</th></tr>
<tr><td>Krankheitstage</td><td class="right">{a['krankheitstage']}</td></tr>
<tr><td>Urlaubstage (diesen Monat)</td><td class="right">{a['urlaubstage']}</td></tr>
<tr><td>Jahresurlaub gesamt</td><td class="right">{a['urlaub_anspruch']}</td></tr>
</table>

<div style="margin-top:20px;font-size:10px;color:#888">
Erstellt: {datetime.now().strftime('%d.%m.%Y %H:%M')} | Kanzlei AI v2.0 | Steuerjahr 2026
</div></body></html>"""

    def abrechnungen_laden(self, mandant: str = None, monat: str = None) -> List[Dict]:
        data = self._lohn_daten()
        alle = list(data["lohnabrechnung"]["abrechnungen"].values())
        if mandant: alle = [a for a in alle if a.get("mandant") == mandant]
        if monat:   alle = [a for a in alle if a.get("monat") == monat]
        return sorted(alle, key=lambda x: x.get("berechnet_am",""), reverse=True)
# ============================================================
# KANZLEI AI — AUTONOMER STEUERFALL AUTOPILOT v1.1
# Datei: core/autonomer_steuerfall.py
#
# Fixes v1.1:
#   - export_elster_xml mit Named-Parametern aufgerufen
#   - base64 Import an Datei-Top-Level
#   - Robusteres Error-Handling bei ELSTER-Export
# ============================================================

import uuid
import json
import logging
import os
import base64
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

log = logging.getLogger("kanzlei_steuer_autopilot")

KONFIDENZ_AUTO_FREIGABE = 92.0
KONFIDENZ_REVIEW_NÖTIG  = 75.0

STEUER_SYSTEM_PROMPT = """Du bist ein hochspezialisierter KI-Steuerberater für Deutschland.
Analysiere alle Mandantendaten und erstelle eine vollständige Steuerberechnung.
Antworte NUR mit validem JSON ohne Markdown-Backticks:

{
  "steuerart": "ESt|USt|GewSt|KSt",
  "veranlagungsjahr": 2025,
  "einkommen": {
    "einnahmen_gesamt": 0.0,
    "betriebsausgaben_gesamt": 0.0,
    "gewinn_verlust": 0.0,
    "sonderausgaben": 0.0,
    "zvE": 0.0
  },
  "steuerberechnung": {
    "einkommensteuer": 0.0,
    "solidaritaetszuschlag": 0.0,
    "kirchensteuer": 0.0,
    "gewerbesteuer": 0.0,
    "umsatzsteuer_zahllast": 0.0,
    "vorauszahlungen_geleistet": 0.0,
    "nachzahlung_oder_erstattung": 0.0,
    "ist_nachzahlung": true
  },
  "abzugsposten": [
    {"bezeichnung": "Beispiel", "betrag": 0.0, "paragraph": "§ 4 EStG"}
  ],
  "optimierungen": [
    {"titel": "Mögliche Steuerersparnis", "betrag": 0.0, "beschreibung": "...", "risiko": "niedrig"}
  ],
  "konfidenz_score": 85.5,
  "konfidenz_begruendung": "Alle Belege vorhanden, keine Auffälligkeiten",
  "offene_fragen": [],
  "rechtliche_hinweise": [],
  "naechste_schritte": ["Schritt 1"],
  "elster_felder": {"kz_21": 0.0}
}"""


class AutononerSteuerfall:

    def __init__(self, ds):
        self.ds = ds

    def _steuerfaelle_daten(self) -> Dict:
        return {"steuerfaelle": self.ds.steuerfaelle_liste()}

    # ── Mandantendaten vollständig sammeln ────────────────────
    def sammle_mandanten_daten(self, mandant: str, jahr: int) -> Dict[str, Any]:
        """Alle verfügbaren Daten für einen Steuerfall aggregieren."""
        m        = self.ds.hole_mandanten().get(mandant, {})
        aufgaben = [a for a in self.ds.hole_fristen().values() if a.get("mandant") == mandant]
        belege_alle = self.ds.belege_liste()
        rechnungen_alle = self.ds.rechnungen_liste()
        lohn_alle = self.ds.lohnabrechnung_holen().get("abrechnungen", {})

        belege = [
            b for b in belege_alle
            if b.get("mandant") == mandant and str(jahr) in b.get("datum", "")
        ]
        rechnungen = [
            r for r in rechnungen_alle
            if r.get("mandant") == mandant and str(jahr) in r.get("datum", "")
        ]
        lohndaten = [
            a for a in lohn_alle.values()
            if a.get("mandant") == mandant and str(jahr) in a.get("monat", "")
        ]

        ausgaben_gesamt = sum(
            b.get("betrag_brutto", 0) for b in belege
            if b.get("typ") == "ausgabe" and b.get("status") == "bestaetigt"
        )
        einnahmen_gesamt = sum(
            r.get("gesamt_netto", 0) for r in rechnungen if r.get("status") == "bezahlt"
        )
        if einnahmen_gesamt == 0:
            einnahmen_gesamt = m.get("umsatz", 0)

        vorsteuer = sum(
            b.get("mwst_betrag", 0) for b in belege
            if b.get("vorsteuer_abzugsfaehig") and b.get("status") == "bestaetigt"
        )

        vollstaendigkeit = {
            "hat_einnahmen":         einnahmen_gesamt > 0,
            "hat_ausgaben":          ausgaben_gesamt > 0,
            "hat_belege":            len(belege) > 0,
            "hat_steuer_id":         bool(m.get("steuer_id")),
            "hat_keine_offene_docs": len(m.get("fehlende_dokumente_liste", [])) == 0,
            "hat_lohndaten":         len(lohndaten) > 0 if lohndaten else True,
        }
        vollstaendigkeits_score = sum(vollstaendigkeit.values()) / len(vollstaendigkeit) * 100

        return {
            "mandant":               mandant,
            "jahr":                  jahr,
            "stammdaten":            {
                "umsatz":    m.get("umsatz", 0),
                "branche":   m.get("branche", ""),
                "steuer_id": m.get("steuer_id", ""),
            },
            "einnahmen":             einnahmen_gesamt,
            "ausgaben":              ausgaben_gesamt,
            "vorsteuer":             vorsteuer,
            "belege_anzahl":         len(belege),
            "belege_bestätigt":      sum(1 for b in belege if b.get("status") == "bestaetigt"),
            "rechnungen_anzahl":     len(rechnungen),
            "lohn_monate":           len(lohndaten),
            "fehlende_dokumente":    m.get("fehlende_dokumente_liste", []),
            "vollstaendigkeit":      vollstaendigkeit,
            "vollstaendigkeits_score": vollstaendigkeits_score,
            "kategorien_ausgaben":   self._kategorisiere_ausgaben(belege),
        }

    def _kategorisiere_ausgaben(self, belege: List[Dict]) -> Dict[str, float]:
        kategorien: Dict[str, float] = {}
        for b in belege:
            if b.get("typ") == "ausgabe" and b.get("status") == "bestaetigt":
                kat = b.get("kategorie_name", b.get("kategorie", "Sonstiges"))
                kategorien[kat] = kategorien.get(kat, 0) + b.get("betrag_netto", 0)
        return dict(sorted(kategorien.items(), key=lambda x: x[1], reverse=True))

    # ── Vollautomatische Steuerfall-Verarbeitung ──────────────
    async def verarbeite_steuerfall(
        self,
        mandant:     str,
        jahr:        int,
        steuerart:   str = "ESt",
        api_key:     str = None,
        auto_elster: bool = False,
    ) -> Dict[str, Any]:
        """
        Vollautomatische Verarbeitung eines Steuerfalls:
        1. Daten sammeln
        2. KI-Analyse + Berechnung
        3. ELSTER XML vorbereiten
        4. Konfidenz bewerten
        5. Empfehlung ausgeben
        """
        import httpx

        key   = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY fehlt in .env")

        fall_id = str(uuid.uuid4())
        jetzt   = datetime.now()

        # Schritt 1: Daten sammeln
        log.info(f"Steuerfall {fall_id[:8]}: Daten sammeln für {mandant} {jahr}")
        mandant_daten = self.sammle_mandanten_daten(mandant, jahr)

        # Schritt 2: KI-Analyse
        user_prompt = (
            f"Analysiere diesen Steuerfall:\n"
            f"MANDANT: {mandant}\nSTEUERART: {steuerart}\nJAHR: {jahr}\n\n"
            f"DATEN:\n"
            f"- Einnahmen: €{mandant_daten['einnahmen']:,.2f}\n"
            f"- Ausgaben: €{mandant_daten['ausgaben']:,.2f}\n"
            f"- Vorsteuer: €{mandant_daten['vorsteuer']:,.2f}\n"
            f"- Branche: {mandant_daten['stammdaten']['branche']}\n"
            f"- Belege bestätigt: {mandant_daten['belege_bestätigt']}/{mandant_daten['belege_anzahl']}\n"
            f"- Fehlende Dokumente: {mandant_daten['fehlende_dokumente'] or 'keine'}\n"
            f"- Vollständigkeit: {mandant_daten['vollstaendigkeits_score']:.0f}%\n\n"
            f"AUSGABEN NACH KATEGORIE:\n"
            f"{json.dumps(mandant_daten['kategorien_ausgaben'], indent=2, ensure_ascii=False)}\n\n"
            f"Erstelle die vollständige Steuerberechnung mit Optimierungen."
        )

        ki_analyse = None
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key":         key,
                        "anthropic-version": "2023-06-01",
                        "content-type":      "application/json",
                    },
                    json={
                        "model":      "claude-opus-4-5",
                        "max_tokens": 2048,
                        "system":     STEUER_SYSTEM_PROMPT,
                        "messages":   [{"role": "user", "content": user_prompt}],
                    },
                )

            if response.status_code == 200:
                raw_text = response.json()["content"][0]["text"].strip()
                if "```" in raw_text:
                    import re
                    match    = re.search(r"\{.*\}", raw_text, re.DOTALL)
                    raw_text = match.group(0) if match else "{}"
                ki_analyse = json.loads(raw_text)

        except Exception as e:
            log.warning(f"KI-Analyse fehlgeschlagen: {e} — Fallback")

        if not ki_analyse:
            ki_analyse = self._fallback_berechnung(mandant_daten, steuerart, jahr)

        # Schritt 3: Konfidenz berechnen
        ki_konfidenz        = float(ki_analyse.get("konfidenz_score", 70))
        daten_konfidenz     = mandant_daten["vollstaendigkeits_score"]
        gesamt_konfidenz    = round(ki_konfidenz * 0.6 + daten_konfidenz * 0.4, 1)

        # Abzüge bei Problemen
        fehlende = mandant_daten.get("fehlende_dokumente", [])
        if fehlende:
            gesamt_konfidenz -= len(fehlende) * 3
        if mandant_daten["belege_anzahl"] == 0:
            gesamt_konfidenz -= 20
        gesamt_konfidenz = max(10.0, min(98.0, gesamt_konfidenz))

        # Schritt 4: Empfehlung
        if gesamt_konfidenz >= KONFIDENZ_AUTO_FREIGABE:
            empfehlung      = "auto_freigabe"
            empfehlung_text = "✓ Hohe Konfidenz — automatische Freigabe möglich"
        elif gesamt_konfidenz >= KONFIDENZ_REVIEW_NÖTIG:
            empfehlung      = "kurzer_review"
            empfehlung_text = "Kurzer Review empfohlen (ca. 15 Min)"
        else:
            empfehlung      = "manueller_check"
            empfehlung_text = "Unvollständige Daten — manueller Check erforderlich"

        # Schritt 5: ELSTER XML  ← BUG FIX: Named-Parameter
        elster_b64 = None
        try:
            from core.export_service import export_elster_xml
            m          = self.ds.hole_mandanten().get(mandant, {})
            elster_xml = export_elster_xml(
                mandant=mandant,
                mandant_daten=m,
                steuerart=steuerart,
                zeitraum_jahr=jahr,
            )
            elster_b64 = base64.standard_b64encode(elster_xml).decode()
        except Exception as e:
            log.warning(f"ELSTER XML Fehler (nicht kritisch): {e}")

        # Steuerfall zusammenstellen
        nachzahlung     = ki_analyse.get("steuerberechnung", {}).get("nachzahlung_oder_erstattung", 0)
        ist_nachzahlung = ki_analyse.get("steuerberechnung", {}).get("ist_nachzahlung", True)

        fall = {
            "id":                 fall_id,
            "mandant":            mandant,
            "jahr":               jahr,
            "steuerart":          steuerart,
            "status":             "berechnet",
            "konfidenz_score":    gesamt_konfidenz,
            "empfehlung":         empfehlung,
            "empfehlung_text":    empfehlung_text,
            "ki_analyse":         ki_analyse,
            "mandant_daten":      mandant_daten,
            "nachzahlung":        nachzahlung,
            "ist_nachzahlung":    ist_nachzahlung,
            "elster_xml_b64":     elster_b64,
            "erstellt_am":        jetzt.isoformat(),
            "freigegeben_am":     None,
            "freigegeben_von":    None,
            "elster_versendet_am": None,
        }

        # Speichern
        self.ds.steuerfall_speichern(fall_id, fall)
        self.ds.log_eintrag(
            f"STEUERFALL | {mandant} | {steuerart} {jahr} | "
            f"Konfidenz: {gesamt_konfidenz}% | {empfehlung}"
        )

        # Nachzahlung → Finanzierungsangebot automatisch triggern
        if ist_nachzahlung and nachzahlung > 500:
            try:
                from core.finanzierung_service import FinanzierungService
                fs      = FinanzierungService(self.ds)
                angebot = fs.erstelle_angebot(mandant, nachzahlung, "steuernachzahlung",
                                               steuerart=steuerart, jahr=jahr)
                fall["finanzierungsangebot"] = angebot
            except Exception as e:
                log.warning(f"Finanzierungsangebot konnte nicht erstellt werden: {e}")

        return fall

    def _fallback_berechnung(self, daten: Dict, steuerart: str, jahr: int) -> Dict:
        """Vereinfachte Berechnung wenn KI-API nicht verfügbar."""
        einnahmen = daten["einnahmen"]
        ausgaben  = daten["ausgaben"]
        gewinn    = max(0.0, einnahmen - ausgaben)

        if steuerart in ("ESt", "KSt"):
            steuer      = round(gewinn * 0.30, 2)
            soli        = round(steuer * 0.055, 2)
            nachzahlung = round(steuer + soli, 2)
        elif steuerart == "USt":
            ust_schuld  = round(einnahmen * 0.19, 2)
            vorsteuer   = daten.get("vorsteuer", 0)
            nachzahlung = round(ust_schuld - vorsteuer, 2)
        else:  # GewSt
            nachzahlung = round(gewinn * 0.035, 2)

        return {
            "steuerart":        steuerart,
            "einkommen":        {
                "einnahmen_gesamt":       einnahmen,
                "betriebsausgaben_gesamt": ausgaben,
                "zvE":                    gewinn,
            },
            "steuerberechnung": {
                "nachzahlung_oder_erstattung": nachzahlung,
                "ist_nachzahlung":             nachzahlung > 0,
                "einkommensteuer":             round(gewinn * 0.30, 2) if steuerart == "ESt" else 0,
                "solidaritaetszuschlag":       round(gewinn * 0.30 * 0.055, 2) if steuerart == "ESt" else 0,
            },
            "optimierungen":         [],
            "konfidenz_score":       60.0,
            "konfidenz_begruendung": "Fallback-Berechnung (KI-API nicht verfügbar) — 30% Pauschalsatz",
            "offene_fragen":         ["KI-Analyse erneut starten für präzise Berechnung"],
            "naechste_schritte":     ["API-Key prüfen", "Belege vervollständigen", "Erneut verarbeiten"],
        }

    # ── Fall-Verwaltung ───────────────────────────────────────
    def fall_freigeben(self, fall_id: str, freigegeben_von: str) -> Dict:
        """Steuerfall nach Review durch Steuerberater freigeben."""
        fall = self.ds.steuerfall_holen(fall_id)
        if not fall:
            raise ValueError(f"Steuerfall '{fall_id}' nicht gefunden")

        fall["status"]         = "freigegeben"
        fall["freigegeben_am"] = datetime.now().isoformat()
        fall["freigegeben_von"]= freigegeben_von
        self.ds.steuerfall_speichern(fall_id, fall)
        self.ds.log_eintrag(
            f"STEUERFALL_FREIGABE | {fall['mandant']} | {fall_id[:8]} | {freigegeben_von}"
        )
        return fall

    def faelle_laden(self, mandant: str = None, status: str = None) -> List[Dict]:
        """Alle Steuerfälle laden — ohne große Daten (KI-Analyse, ELSTER)."""
        data   = self._steuerfaelle_daten()
        faelle = list(data.get("steuerfaelle", {}).values())
        if mandant:
            faelle = [f for f in faelle if f.get("mandant") == mandant]
        if status:
            faelle = [f for f in faelle if f.get("status") == status]
        # Große Felder für Listings weglassen
        return [
            {k: v for k, v in f.items() if k not in ("ki_analyse", "elster_xml_b64", "mandant_daten")}
            for f in sorted(faelle, key=lambda x: x.get("erstellt_am", ""), reverse=True)
        ]

    def statistiken(self) -> Dict:
        """Autopilot-Gesamtstatistiken."""
        data            = self._steuerfaelle_daten()
        faelle          = list(data.get("steuerfaelle", {}).values())
        konfidenz_werte = [f["konfidenz_score"] for f in faelle if f.get("konfidenz_score")]

        return {
            "faelle_gesamt":                  len(faelle),
            "faelle_freigegeben":             sum(1 for f in faelle if f.get("status") == "freigegeben"),
            "auto_freigabe":                  sum(1 for f in faelle if f.get("empfehlung") == "auto_freigabe"),
            "durchschnitt_konfidenz":         round(sum(konfidenz_werte) / len(konfidenz_werte), 1) if konfidenz_werte else 0,
            "nachzahlungen":                  sum(1 for f in faelle if f.get("ist_nachzahlung")),
            "erstattungen":                   sum(1 for f in faelle if not f.get("ist_nachzahlung")),
            "gespar_stunden_schätzung":       len(faelle) * 8,
        }
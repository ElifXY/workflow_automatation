# ============================================================
# KANZLEI AI — NO-CODE WORKFLOW BAUKASTEN v1.1
# Datei: core/workflow_builder.py
#
# Fixes v1.1:
#   - ai_email Import mit try/except und Fallback-Text
#   - generiere_email_text Signatur korrekt aufgerufen
#   - Robusteres Error-Handling in allen Aktions-Typen
# ============================================================

import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

log = logging.getLogger("kanzlei_workflow_builder")

# ─── Verfügbare Trigger ───────────────────────────────────────
TRIGGER_TYPEN = {
    "keine_antwort_tage":    {"label": "Keine Antwort seit X Tagen",      "parameter": "tage"},
    "frist_in_tagen":        {"label": "Frist fällig in X Tagen",          "parameter": "tage"},
    "frist_ueberfaellig":    {"label": "Aufgabe überfällig",               "parameter": None},
    "beleg_erkannt":         {"label": "Beleg von bestimmtem Typ erkannt", "parameter": "beleg_typ"},
    "umsatz_unter":          {"label": "Umsatz unter X €",                 "parameter": "betrag"},
    "umsatz_über":           {"label": "Umsatz über X €",                  "parameter": "betrag"},
    "neue_rechnung":         {"label": "Neue Rechnung erstellt",            "parameter": None},
    "rechnung_ueberfaellig": {"label": "Rechnung überfällig",              "parameter": "tage"},
    "dokument_hochgeladen":  {"label": "Mandant hat Dokument hochgeladen", "parameter": None},
    "unterschrift_erledigt": {"label": "Dokument wurde unterzeichnet",     "parameter": None},
    "neuer_mandant":         {"label": "Neuer Mandant angelegt",           "parameter": None},
    "manuell":               {"label": "Manuell gestartet",                "parameter": None},
    "taeglich":              {"label": "Täglich (Cron)",                   "parameter": "uhrzeit"},
    "monatlich":             {"label": "Monatlich am X. Tag",              "parameter": "tag"},
}

# ─── Verfügbare Aktionen ──────────────────────────────────────
AKTION_TYPEN = {
    "email_senden":          {"label": "Email an Mandant senden",         "parameter": ["vorlage"]},
    "aufgabe_anlegen":       {"label": "Aufgabe anlegen",                  "parameter": ["beschreibung", "frist_tage", "prioritaet"]},
    "bot_frage_stellen":     {"label": "Bot-Frage im Portal stellen",     "parameter": ["frage_text", "antwort_optionen"]},
    "unterschrift_anfragen": {"label": "Dokument zur Unterschrift senden","parameter": ["dokumentname"]},
    "freigabe_anfragen":     {"label": "Freigabe anfordern",              "parameter": ["titel"]},
    "dokument_anfordern":    {"label": "Dokument anfordern",              "parameter": ["dokument_name"]},
    "workflow_starten":      {"label": "Anderen Workflow starten",        "parameter": ["workflow_id"]},
    "benachrichtigung":      {"label": "Interne Benachrichtigung",        "parameter": ["text"]},
    "honorar_anpassen":      {"label": "Honoraranpassung vorschlagen",    "parameter": []},
    "monatsabschluss":       {"label": "Monatsabschluss starten",         "parameter": []},
    "datev_export":          {"label": "DATEV-Export erstellen",          "parameter": []},
    "lohnabrechnung":        {"label": "Lohnabrechnung erstellen",        "parameter": []},
}


class WorkflowBaukasten:

    def __init__(self, ds, bot=None, profit_monitor=None):
        self.ds             = ds
        self.bot            = bot
        self.profit_monitor = profit_monitor

    def _daten(self) -> Dict:
        return {
            "workflow_regeln": self.ds.workflow_regeln_liste(),
            "workflow_runs": {},
        }

    # ── Regel erstellen / verwalten ──────────────────────────
    def regel_erstellen(
        self,
        name:             str,
        beschreibung:     str,
        trigger:          Dict,
        bedingungen:      List[Dict],
        aktionen:         List[Dict],
        aktiv:            bool = True,
        mandanten_filter: Optional[List[str]] = None,
    ) -> Dict:
        if trigger["typ"] not in TRIGGER_TYPEN:
            raise ValueError(f"Unbekannter Trigger: {trigger['typ']}")
        for a in aktionen:
            if a["typ"] not in AKTION_TYPEN:
                raise ValueError(f"Unbekannte Aktion: {a['typ']}")

        regel_id = str(uuid.uuid4())
        regel    = {
            "id":               regel_id,
            "name":             name,
            "beschreibung":     beschreibung,
            "trigger":          trigger,
            "bedingungen":      bedingungen,
            "aktionen":         aktionen,
            "aktiv":            aktiv,
            "mandanten_filter": mandanten_filter,
            "erstellt_am":      datetime.now().isoformat(),
            "letzte_ausfuehrung": None,
            "ausfuehrungen":    0,
            "aktionen_gesamt":  0,
        }

        data = self._daten()
        data["workflow_regeln"][regel_id] = regel
        self.ds.workflow_regel_speichern(regel_id, regel)
        self.ds.log_eintrag(f"WORKFLOW_REGEL | {name} | Trigger: {trigger['typ']}")
        return regel

    def regel_liste(self, nur_aktive: bool = False) -> List[Dict]:
        data   = self._daten()
        regeln = list(data.get("workflow_regeln", {}).values())
        if nur_aktive:
            regeln = [r for r in regeln if r.get("aktiv")]
        return sorted(regeln, key=lambda x: x.get("erstellt_am", ""), reverse=True)

    def regel_aktivieren(self, regel_id: str, aktiv: bool) -> Dict:
        data   = self._daten()
        regeln = data.get("workflow_regeln", {})
        if regel_id not in regeln:
            raise ValueError("Regel nicht gefunden")
        regeln[regel_id]["aktiv"] = aktiv
        self.ds.workflow_regel_speichern(regel_id, regeln[regel_id])
        return regeln[regel_id]

    def regel_loeschen(self, regel_id: str):
        self.ds.workflow_regel_loeschen(regel_id)

    # ── Workflow ausführen ────────────────────────────────────
    def fuehre_alle_aus(self) -> Dict:
        """Alle aktiven Regeln ausführen — ideal als Cron-Job."""
        regeln    = self.regel_liste(nur_aktive=True)
        mandanten = self.ds.hole_mandanten()
        alle_runs = []

        for regel in regeln:
            try:
                runs = self._fuehre_regel_aus(regel, mandanten)
                alle_runs.extend(runs)
            except Exception as e:
                log.error(f"Workflow '{regel['name']}' Fehler: {e}")

        gesamt_aktionen = sum(r.get("aktionen_ausgefuehrt", 0) for r in alle_runs)
        self.ds.log_eintrag(
            f"WORKFLOW_BATCH | {len(regeln)} Regeln | {len(alle_runs)} Runs | "
            f"{gesamt_aktionen} Aktionen"
        )
        return {
            "regeln_geprueft": len(regeln),
            "runs":            len(alle_runs),
            "aktionen":        gesamt_aktionen,
            "details":         alle_runs,
        }

    def _fuehre_regel_aus(self, regel: Dict, mandanten: Dict) -> List[Dict]:
        trigger = regel["trigger"]
        runs    = []

        ziel_mandanten = list(mandanten.keys())
        if regel.get("mandanten_filter"):
            ziel_mandanten = [m for m in ziel_mandanten if m in regel["mandanten_filter"]]

        for mandant_name in ziel_mandanten:
            m = mandanten[mandant_name]
            try:
                if not self._prüfe_trigger(trigger, mandant_name, m):
                    continue
                if not self._prüfe_bedingungen(regel["bedingungen"], mandant_name, m):
                    continue
                count = self._fuehre_aktionen_aus(regel["aktionen"], mandant_name, m, regel)
                runs.append({
                    "regel_id":             regel["id"],
                    "regel_name":           regel["name"],
                    "mandant":              mandant_name,
                    "aktionen_ausgefuehrt": count,
                    "zeitpunkt":            datetime.now().isoformat(),
                })
            except Exception as e:
                log.warning(f"Regel '{regel['name']}' für {mandant_name}: {e}")

        if runs:
            r = self.ds.workflow_regel_holen(regel["id"])
            if r:
                r["letzte_ausfuehrung"] = datetime.now().isoformat()
                r["ausfuehrungen"]      = r.get("ausfuehrungen", 0) + len(runs)
                r["aktionen_gesamt"]    = r.get("aktionen_gesamt", 0) + sum(
                    x["aktionen_ausgefuehrt"] for x in runs
                )
                self.ds.workflow_regel_speichern(regel["id"], r)

        return runs

    def _prüfe_trigger(self, trigger: Dict, mandant: str, m: Dict) -> bool:
        typ = trigger.get("typ")
        p   = trigger.get("parameter")

        if typ == "keine_antwort_tage":
            return self.ds.berechne_tage_ohne_antwort(mandant) >= int(p or 7)

        elif typ == "frist_in_tagen":
            aufgaben = self.ds.hole_fristen()
            jetzt    = datetime.now()
            for a in aufgaben.values():
                if a.get("mandant") != mandant or a.get("erledigt"):
                    continue
                try:
                    if (datetime.strptime(a["frist"], "%Y-%m-%d") - jetzt).days == int(p or 14):
                        return True
                except Exception:
                    pass
            return False

        elif typ == "frist_ueberfaellig":
            aufgaben = self.ds.hole_fristen()
            heute    = datetime.now().strftime("%Y-%m-%d")
            return any(
                a.get("mandant") == mandant and not a.get("erledigt")
                and a.get("frist", "9999") < heute
                for a in aufgaben.values()
            )

        elif typ == "rechnung_ueberfaellig":
            rechnungen = self.ds.rechnungen_liste()
            jetzt = datetime.now()
            for r in rechnungen:
                if r.get("mandant") != mandant or r.get("status") not in ("offen",):
                    continue
                try:
                    if (jetzt - datetime.strptime(r["faellig_bis"], "%Y-%m-%d")).days >= int(p or 14):
                        return True
                except Exception:
                    pass
            return False

        elif typ == "umsatz_unter":
            return m.get("umsatz", 0) < float(p or 0)

        elif typ == "umsatz_über":
            return m.get("umsatz", 0) > float(p or 0)

        elif typ == "taeglich":
            # Optional: nur ab konfigurierter Uhrzeit (HH:MM)
            if p and isinstance(p, str) and ":" in p:
                return datetime.now().strftime("%H:%M") >= p[:5]
            return True

        elif typ == "monatlich":
            try:
                ziel_tag = int(p if p is not None else 1)
            except (TypeError, ValueError):
                ziel_tag = 1
            return datetime.now().day == max(1, min(28, ziel_tag))

        elif typ == "manuell":
            return True

        elif typ == "dokument_hochgeladen":
            uploads = self.ds.portal_liste("upload") or []
            return any(u.get("mandant") == mandant for u in uploads)

        elif typ == "unterschrift_erledigt":
            sigs = self.ds.portal_liste("unterschrift") or []
            return any(
                u.get("mandant") == mandant and u.get("status") == "erledigt"
                for u in sigs
            )

        return False

    def _prüfe_bedingungen(self, bedingungen: List[Dict], mandant: str, m: Dict) -> bool:
        for bed in bedingungen:
            feld     = bed.get("feld", "")
            operator = bed.get("operator", "==")
            wert     = bed.get("wert")

            if feld == "umsatz":
                ist_wert = m.get("umsatz", 0)
            elif feld == "tage_ohne_antwort":
                ist_wert = self.ds.berechne_tage_ohne_antwort(mandant)
            elif feld == "fehlende_dokumente_anzahl":
                ist_wert = len(m.get("fehlende_dokumente_liste", []))
            elif feld == "branche":
                ist_wert = m.get("branche", "")
            else:
                continue

            try:
                ok = (
                    (operator == "==" and ist_wert == wert) or
                    (operator == "!=" and ist_wert != wert) or
                    (operator == ">"  and float(ist_wert) > float(wert or 0)) or
                    (operator == ">=" and float(ist_wert) >= float(wert or 0)) or
                    (operator == "<"  and float(ist_wert) < float(wert or 0)) or
                    (operator == "<=" and float(ist_wert) <= float(wert or 0)) or
                    (operator == "contains" and str(wert or "").lower() in str(ist_wert).lower())
                )
                if not ok:
                    return False
            except (TypeError, ValueError):
                return False

        return True

    def _fuehre_aktionen_aus(
        self, aktionen: List[Dict], mandant: str, m: Dict, regel: Dict
    ) -> int:
        count = 0
        for aktion in aktionen:
            try:
                self._fuehre_aktion_aus(aktion, mandant, m, regel)
                count += 1
            except Exception as e:
                log.warning(f"Aktion '{aktion['typ']}' für {mandant} fehlgeschlagen: {e}")
        return count

    def _fuehre_aktion_aus(self, aktion: Dict, mandant: str, m: Dict, regel: Dict):
        """Eine einzelne Aktion ausführen."""
        typ    = aktion["typ"]
        params = aktion.get("parameter", {})

        if typ == "email_senden":
            # BUG FIX: try/except mit Fallback-Text falls ai_email Import fehlschlägt
            text = params.get("text", "")
            if not text:
                try:
                    from core.ai_email import generiere_email_text
                    text = generiere_email_text(
                        mandant=mandant,
                        grund=params.get("grund", "KEINE_ANTWORT"),
                    )
                except Exception:
                    text = (
                        f"Sehr geehrte/r {mandant},\n\n"
                        f"bitte melden Sie sich bei unserer Kanzlei.\n\n"
                        f"Mit freundlichen Grüßen\nIhre Kanzlei"
                    )

            self.ds.kommunikation_hinzufuegen(mandant, {
                "typ":       "workflow_email",
                "text":      text[:150],
                "timestamp": datetime.now().isoformat(),
                "workflow":  regel["name"],
            })
            to_addr = (params.get("empfaenger") or m.get("email") or "").strip()
            if to_addr and "@" in to_addr:
                try:
                    from core.daten_speicher import email_outbox_enqueue

                    kid = str(getattr(self.ds, "kanzlei_id", None) or "default")
                    idem = f"wf-email|{regel['id']}|{mandant}|{datetime.now().strftime('%Y-%m-%d')}"
                    email_outbox_enqueue(
                        kanzlei_id=kid,
                        mandant=mandant,
                        to_email=to_addr,
                        subject=params.get("betreff") or f"Mitteilung — {mandant}",
                        body_text=text,
                        body_html="",
                        idempotency_key=idem,
                    )
                except Exception as e:
                    log.warning("Workflow E-Mail Outbox %s: %s", mandant, e)
            self.ds.log_eintrag(f"WORKFLOW_EMAIL | {mandant} | {regel['name']}")

        elif typ == "aufgabe_anlegen":
            frist_tage   = int(params.get("frist_tage", 7))
            frist        = (datetime.now() + timedelta(days=frist_tage)).strftime("%Y-%m-%d")
            aufgabe_id   = str(uuid.uuid4())
            self.ds.aufgabe_speichern(aufgabe_id, {
                "id":           aufgabe_id,
                "mandant":      mandant,
                "beschreibung": params.get("beschreibung", f"Workflow: {regel['name']}"),
                "frist":        frist,
                "prioritaet":   params.get("prioritaet", "normal"),
                "kategorie":    "workflow_automatisch",
                "erledigt":     False,
                "erstellt_am":  datetime.now().isoformat(),
                "workflow":     regel["name"],
            })

        elif typ == "bot_frage_stellen" and self.bot:
            self.bot.frage_stellen(
                mandant          = mandant,
                frage_text       = params.get("frage_text", "Bitte kurz bestätigen."),
                frage_typ        = params.get("frage_typ", "sonstiges"),
                antwort_optionen = params.get("antwort_optionen"),
            )

        elif typ == "dokument_anfordern":
            dok_name = params.get("dokument_name", "Unterlage")
            mm       = self.ds.hole_mandanten().get(mandant, {})
            fehlende = mm.get("fehlende_dokumente_liste", [])
            if dok_name not in fehlende:
                fehlende.append(dok_name)
                mm["fehlende_dokumente_liste"] = fehlende
                self.ds.mandant_speichern(mandant, mm)

        elif typ == "unterschrift_anfragen":
            try:
                from portal_api import erstelle_unterschrift_anfrage

                erstelle_unterschrift_anfrage(
                    self.ds,
                    mandant,
                    params.get("dokumentname", "Dokument").strip() or "Dokument",
                    params.get("dokument_b64"),
                    params.get("dokumenttyp", "pdf"),
                    params.get("betreff", f"Unterschrift — {params.get('dokumentname', 'Dokument')}"),
                    params.get("hinweis", ""),
                    int(params.get("gueltig_tage", 14) or 14),
                    portal_sichtbar=True,
                )
            except Exception as e:
                log.warning("unterschrift_anfragen %s: %s", mandant, e)
                raise

        elif typ == "freigabe_anfragen":
            aufgabe_id = str(uuid.uuid4())
            self.ds.aufgabe_speichern(aufgabe_id, {
                "id":           aufgabe_id,
                "mandant":      mandant,
                "beschreibung": params.get("titel", f"Freigabe: {regel['name']}"),
                "frist":        (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d"),
                "prioritaet":   "hoch",
                "kategorie":    "workflow_freigabe",
                "erledigt":     False,
                "erstellt_am":  datetime.now().isoformat(),
                "workflow":     regel["name"],
            })

        elif typ == "benachrichtigung":
            self.ds.log_eintrag(
                f"WORKFLOW_NOTIZ | {mandant} | {params.get('text', '')[:80]}"
            )

        elif typ == "lohnabrechnung":
            try:
                from core.lohn_service import LohnService
                ls    = LohnService(self.ds)
                monat = datetime.now().strftime("%Y-%m")
                ls.batch_abrechnung(mandant, monat)
            except Exception as e:
                log.warning(f"Lohnabrechnung-Aktion für {mandant}: {e}")

        # Weitere Aktionen (honorar_anpassen, datev_export etc.) werden
        # als Aufgaben angelegt, nicht direkt ausgeführt
        elif typ == "workflow_starten":
            ziel_id = params.get("workflow_id") or params.get("regel_id")
            if ziel_id:
                ziel = self.ds.workflow_regel_holen(str(ziel_id))
                if ziel and ziel.get("aktiv"):
                    self._fuehre_regel_aus(ziel, self.ds.hole_mandanten())

        elif typ in ("honorar_anpassen", "datev_export", "monatsabschluss"):
            aufgabe_id = str(uuid.uuid4())
            self.ds.aufgabe_speichern(aufgabe_id, {
                "id":           aufgabe_id,
                "mandant":      mandant,
                "beschreibung": f"Workflow '{regel['name']}': {AKTION_TYPEN.get(typ,{}).get('label',typ)}",
                "frist":        (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d"),
                "prioritaet":   "normal",
                "kategorie":    "workflow_automatisch",
                "erledigt":     False,
                "erstellt_am":  datetime.now().isoformat(),
                "workflow":     regel["name"],
            })

    # ── Template-Workflows ────────────────────────────────────
    def erstelle_standard_workflows(self) -> List[Dict]:
        """Sinnvolle Standard-Workflows für neue Kanzlei."""
        standard = [
            {
                "name":         "Kein Kontakt seit 7 Tagen",
                "beschreibung": "Bot-Frage senden wenn Mandant seit 7 Tagen keine Antwort",
                "trigger":      {"typ": "keine_antwort_tage", "parameter": 7},
                "bedingungen":  [{"feld": "umsatz", "operator": ">", "wert": 500}],
                "aktionen":     [
                    {"typ": "bot_frage_stellen", "parameter": {
                        "frage_text":       "Wir haben einige Zeit nichts von Ihnen gehört. Alles in Ordnung?",
                        "frage_typ":        "sonstiges",
                        "antwort_optionen": ["Ja, alles gut", "Bitte anrufen", "Ich melde mich bald"],
                    }},
                ],
            },
            {
                "name":         "Rechnung 14 Tage überfällig",
                "beschreibung": "Mahnungs-Aufgabe anlegen wenn Rechnung 14+ Tage überfällig",
                "trigger":      {"typ": "rechnung_ueberfaellig", "parameter": 14},
                "bedingungen":  [],
                "aktionen":     [
                    {"typ": "aufgabe_anlegen", "parameter": {
                        "beschreibung": "Mahnung versenden — Rechnung überfällig",
                        "frist_tage":   2,
                        "prioritaet":   "hoch",
                    }},
                ],
            },
            {
                "name":         "Monatliche Lohnabrechnung",
                "beschreibung": "Lohnabrechnung am 1. jeden Monats automatisch erstellen",
                "trigger":      {"typ": "monatlich", "parameter": 1},
                "bedingungen":  [],
                "aktionen":     [
                    {"typ": "lohnabrechnung",  "parameter": {}},
                    {"typ": "benachrichtigung","parameter": {"text": "Lohnabrechnung automatisch erstellt"}},
                ],
            },
        ]

        erstellt = []
        for w in standard:
            try:
                r = self.regel_erstellen(**w)
                erstellt.append(r)
            except Exception as e:
                log.warning(f"Standard-Workflow '{w['name']}': {e}")
        return erstellt

    def statistiken(self) -> Dict:
        data   = self._daten()
        regeln = list(data.get("workflow_regeln", {}).values())
        return {
            "regeln_gesamt":   len(regeln),
            "regeln_aktiv":    sum(1 for r in regeln if r.get("aktiv")),
            "ausfuehrungen":   sum(r.get("ausfuehrungen", 0) for r in regeln),
            "aktionen_gesamt": sum(r.get("aktionen_gesamt", 0) for r in regeln),
            "top_regeln":      sorted(
                regeln, key=lambda x: x.get("ausfuehrungen", 0), reverse=True
            )[:5],
        }
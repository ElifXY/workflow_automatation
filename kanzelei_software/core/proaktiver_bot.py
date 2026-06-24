# ============================================================
# KANZLEI AI — PROAKTIVER MANDANTEN-BOT v1.0
# Datei: core/proaktiver_bot.py
# ============================================================

import uuid
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple

from core.aufgabe_erledigt import aufgabe_ist_erledigt

log = logging.getLogger("kanzlei_bot")

# Schwellen (Analyse-Regeln)
MIN_FEHLENDE_BELEGE = 2
MIN_TAGE_OHNE_ANTWORT = 14
MIN_UEBERFAELLIGE_FRISTEN = 1
UMSATZ_ANOMALIE_FAKTOR = 0.6

FRAGE_TYPEN = {
    "buchung_bestaetigung":   {"icon": "💳", "prioritaet": "hoch"},
    "fahrtenbuch":            {"icon": "🚗", "prioritaet": "mittel"},
    "fehlende_einnahme":      {"icon": "📉", "prioritaet": "hoch"},
    "kassenbestand":          {"icon": "💰", "prioritaet": "mittel"},
    "beleg_fehlend":          {"icon": "🧾", "prioritaet": "mittel"},
    "umsatz_anomalie":        {"icon": "📊", "prioritaet": "hoch"},
    "konto_ungewoehnlich":    {"icon": "🏦", "prioritaet": "hoch"},
    "personal_aenderung":     {"icon": "👤", "prioritaet": "mittel"},
    "frist_erinnerung":       {"icon": "⏰", "prioritaet": "kritisch"},
    "kontakt_erinnerung":     {"icon": "📬", "prioritaet": "mittel"},
    "investition_geplant":    {"icon": "📈", "prioritaet": "niedrig"},
    "sonstiges":              {"icon": "❓", "prioritaet": "niedrig"},
}


def _safe_float(value: Any, default: Optional[float] = 0.0) -> float:
    if value is None:
        return default if default is not None else 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return default if default is not None else 0.0


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_str_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        if s.startswith("["):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return [str(x).strip() for x in parsed if str(x).strip()]
            except json.JSONDecodeError:
                pass
        return [s]
    return []


def _parse_iso_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        s = str(value).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt
    except (TypeError, ValueError):
        return None


def _fehlende_docs_aus_mandant(m: Dict) -> List[str]:
    docs = _as_str_list(m.get("fehlende_dokumente_liste"))
    if not docs:
        docs = _as_str_list(m.get("fehlende_dokumente"))
    return docs


class ProaktiverBot:
    """Analysiert Mandantendaten und erzeugt Fragen im Mandantenportal."""

    def __init__(self, ds):
        self.ds = ds

    def _min_tage_ohne_antwort(self) -> int:
        from core.tenant_settings import tenant_int
        return tenant_int(self.ds, "eskalation_stufe_1_tage", MIN_TAGE_OHNE_ANTWORT)

    def _stundensatz(self) -> float:
        from core.tenant_settings import tenant_float
        return tenant_float(self.ds, "stundensatz", 150.0)

    def _portal_daten(self) -> Dict:
        fragen = self.ds.bot_fragen_liste()
        return {"bot_fragen": fragen if isinstance(fragen, dict) else {}}

    def _frage_persistieren(self, frage: Dict) -> None:
        fid = frage.get("id")
        if not fid:
            raise ValueError("Frage ohne ID")
        if not self.ds.bot_frage_speichern(fid, frage):
            raise RuntimeError("Bot-Frage konnte nicht gespeichert werden")

    def frage_stellen(
        self,
        mandant:     str,
        frage_text:  str,
        frage_typ:   str = "sonstiges",
        kontext:     str = "",
        betrag:      Optional[float] = None,
        antwort_optionen: Optional[List[str]] = None,
        aufgabe_wenn_nein: Optional[str] = None,
    ) -> Dict:
        mandanten = self.ds.hole_mandanten() or {}
        if mandant not in mandanten:
            raise ValueError(f"Mandant '{mandant}' nicht gefunden")

        typ_info = FRAGE_TYPEN.get(frage_typ, FRAGE_TYPEN["sonstiges"])
        frage_id = str(uuid.uuid4())
        jetzt    = datetime.now()

        frage = {
            "id":               frage_id,
            "mandant":          mandant,
            "text":             frage_text,
            "kontext":          kontext,
            "typ":              frage_typ,
            "icon":             typ_info["icon"],
            "prioritaet":       typ_info["prioritaet"],
            "betrag":           betrag,
            "antwort_optionen": antwort_optionen or [
                "Ja, korrekt",
                "Nein, bitte korrigieren",
                "Ich melde mich",
            ],
            "aufgabe_wenn_nein": aufgabe_wenn_nein,
            "status":           "offen",
            "erstellt_am":      jetzt.isoformat(),
            "ablaeuft_am":      (jetzt + timedelta(days=14)).isoformat(),
            "antwort":          None,
            "antwort_zeitpunkt": None,
            "antwort_notiz":    None,
        }

        self._frage_persistieren(frage)
        self.ds.log_eintrag(f"BOT_FRAGE | {mandant} | {frage_typ} | {frage_text[:60]}")
        try:
            from core.bot_notifications import notify_mandant_new_bot_frage

            notify_mandant_new_bot_frage(self.ds, mandant, frage)
        except Exception as e:
            log.warning("Bot-Mail an Mandant %s: %s", mandant, e)
        return frage

    def antwort_erfassen(
        self,
        frage_id:  str,
        antwort:   str,
        notiz:     str = "",
        mandant:   str = "",
    ) -> Dict:
        data   = self._portal_daten()
        fragen = data.get("bot_fragen", {})

        if frage_id not in fragen:
            raise ValueError("Frage nicht gefunden")

        frage = dict(fragen[frage_id])
        if mandant and frage.get("mandant") != mandant:
            raise PermissionError("Kein Zugriff")

        frage["status"]            = "beantwortet"
        frage["antwort"]           = antwort
        frage["antwort_zeitpunkt"] = datetime.now().isoformat()
        frage["antwort_notiz"]     = notiz

        negativ_antworten = ["nein", "falsch", "korrigieren", "fehler"]
        ist_negativ = any(w in (antwort or "").lower() for w in negativ_antworten)

        aufgabe_id = None
        if ist_negativ and frage.get("aufgabe_wenn_nein"):
            aufgabe_id = str(uuid.uuid4())
            frist = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
            try:
                self.ds.aufgabe_speichern(aufgabe_id, {
                    "id":           aufgabe_id,
                    "mandant":      frage["mandant"],
                    "beschreibung": frage["aufgabe_wenn_nein"],
                    "frist":        frist,
                    "prioritaet":   "hoch",
                    "kategorie":    "bot_followup",
                    "erledigt":     False,
                    "erstellt_am":  datetime.now().isoformat(),
                    "bot_frage_id": frage_id,
                })
            except Exception as e:
                log.warning("Bot-Follow-up-Aufgabe konnte nicht angelegt werden: %s", e)

        self._frage_persistieren(frage)
        self.ds.log_eintrag(
            f"BOT_ANTWORT | {frage.get('mandant')} | {frage.get('typ')} | {(antwort or '')[:30]}"
        )

        return {
            **frage,
            "aufgabe_angelegt": aufgabe_id is not None,
            "aufgabe_id":       aufgabe_id,
        }

    def fragen_fuer_mandant(self, mandant: str, nur_offen: bool = True) -> List[Dict]:
        data   = self._portal_daten()
        fragen = [
            f for f in data.get("bot_fragen", {}).values()
            if f.get("mandant") == mandant
        ]
        if nur_offen:
            jetzt = datetime.now()
            offen = []
            for f in fragen:
                if f.get("status") != "offen":
                    continue
                ablauf = _parse_iso_dt(f.get("ablaeuft_am"))
                if ablauf is None or ablauf > jetzt:
                    offen.append(f)
            fragen = offen
        return sorted(fragen, key=lambda x: x.get("erstellt_am") or "", reverse=True)

    def alle_fragen(self, status_filter: str = None) -> List[Dict]:
        data   = self._portal_daten()
        fragen = list(data.get("bot_fragen", {}).values())
        if status_filter:
            fragen = [f for f in fragen if f.get("status") == status_filter]
        return sorted(fragen, key=lambda x: x.get("erstellt_am") or "", reverse=True)

    def _tage_ohne_antwort(self, name: str) -> int:
        try:
            return _safe_int(self.ds.berechne_tage_ohne_antwort(name), 999)
        except Exception as e:
            log.warning("tage_ohne_antwort für %s: %s", name, e)
            return 999

    def _diagnose_mandant(
        self, name: str, m: Dict, alle_aufgaben: Dict, bestehende: set
    ) -> Dict[str, Any]:
        """Welche Regeln würden greifen (ohne zu speichern)?"""
        umsatz = _safe_float(m.get("umsatz"), 0.0)
        monats_raw = _optional_float(m.get("letzter_monatsumsatz"))
        fehlende_docs = _fehlende_docs_aus_mandant(m)
        tage = self._tage_ohne_antwort(name)
        heute = datetime.now().strftime("%Y-%m-%d")
        ueberfaellige = [
            a for a in alle_aufgaben.values()
            if isinstance(a, dict)
            and a.get("mandant") == name
            and not aufgabe_ist_erledigt(a)
            and str(a.get("frist") or "9999") < heute
        ]
        kfz = any(
            isinstance(a, dict)
            and a.get("mandant") == name
            and not aufgabe_ist_erledigt(a)
            and any(
                w in str(a.get("beschreibung", "")).lower()
                for w in ("fahrt", "kfz", "auto", "benzin", "kraftstoff")
            )
            for a in alle_aufgaben.values()
        )
        erwarteter_monat = umsatz / 12.0 if umsatz > 0 else 0.0
        umsatz_ok = (
            monats_raw is not None
            and monats_raw > 0
            and erwarteter_monat > 0
            and monats_raw < erwarteter_monat * UMSATZ_ANOMALIE_FAKTOR
        )
        return {
            "mandant": name,
            "umsatz_anomalie": umsatz_ok and "umsatz_anomalie" not in bestehende,
            "beleg_fehlend": len(fehlende_docs) >= MIN_FEHLENDE_BELEGE and "beleg_fehlend" not in bestehende,
            "kontakt_erinnerung": tage >= self._min_tage_ohne_antwort() and "kontakt_erinnerung" not in bestehende,
            "fahrtenbuch": kfz and "fahrtenbuch" not in bestehende,
            "frist_erinnerung": len(ueberfaellige) >= MIN_UEBERFAELLIGE_FRISTEN and "frist_erinnerung" not in bestehende,
            "fehlende_docs_anzahl": len(fehlende_docs),
            "tage_ohne_antwort": tage,
            "ueberfaellige_aufgaben": len(ueberfaellige),
            "offene_frage_typen": sorted(bestehende),
        }

    def analysiere_alle_mandanten(self) -> Tuple[List[Dict], List[Dict]]:
        """
        Returns:
            (neue_fragen, pruefung_pro_mandant)
        """
        mandanten = self.ds.hole_mandanten() or {}
        if not isinstance(mandanten, dict):
            mandanten = {}
        try:
            aufgaben = self.ds.hole_fristen() or {}
        except Exception as e:
            log.error("Bot-Analyse: Aufgaben konnten nicht geladen werden: %s", e)
            raise RuntimeError(f"Aufgaben konnten nicht geladen werden: {e}") from e
        if not isinstance(aufgaben, dict):
            aufgaben = {}

        neue_fragen: List[Dict] = []
        pruefung: List[Dict] = []
        for name, m in mandanten.items():
            if not name or not isinstance(m, dict):
                continue
            bestehende = {f.get("typ") for f in self.fragen_fuer_mandant(name, nur_offen=True)}
            diag = self._diagnose_mandant(name, m, aufgaben, bestehende)
            try:
                fragen = self._analysiere_mandant(name, m, aufgaben, bestehende)
                neue_fragen.extend(fragen)
                diag["neu_angelegt"] = [f.get("typ") for f in fragen]
            except Exception as e:
                log.warning("Bot-Analyse Fehler für %s: %s", name, e, exc_info=True)
                diag["fehler"] = str(e)
                diag["neu_angelegt"] = []
            pruefung.append(diag)

        log.info(
            "Bot-Analyse: %s neue Fragen für %s Mandanten",
            len(neue_fragen),
            len(mandanten),
        )
        return neue_fragen, pruefung

    def _analysiere_mandant(
        self,
        name: str,
        m: Dict,
        alle_aufgaben: Dict,
        bestehende: Optional[set] = None,
    ) -> List[Dict]:
        neue_fragen: List[Dict] = []
        if bestehende is None:
            bestehende = {f.get("typ") for f in self.fragen_fuer_mandant(name, nur_offen=True)}
        heute = datetime.now().strftime("%Y-%m-%d")

        umsatz = _safe_float(m.get("umsatz"), 0.0)
        monats_raw = _optional_float(m.get("letzter_monatsumsatz"))
        if umsatz > 0 and monats_raw is not None:
            erwarteter_monat = umsatz / 12.0
            if (
                monats_raw > 0
                and erwarteter_monat > 0
                and monats_raw < erwarteter_monat * UMSATZ_ANOMALIE_FAKTOR
                and "umsatz_anomalie" not in bestehende
            ):
                differenz = round(erwarteter_monat - monats_raw, 2)
                f = self.frage_stellen(
                    mandant=name,
                    frage_text=(
                        f"Ihre Einnahmen waren diesen Monat €{monats_raw:,.2f} — "
                        f"das ist €{differenz:,.2f} weniger als erwartet. "
                        f"Gibt es einen besonderen Grund dafür?"
                    ),
                    frage_typ="umsatz_anomalie",
                    kontext=f"Erwartet: €{erwarteter_monat:,.2f}/Monat",
                    betrag=differenz,
                    antwort_optionen=[
                        "Saisonbedingt — alles normal",
                        "Ausfall eines Kunden",
                        "Urlaub / Krankheit",
                        "Bitte kontaktieren Sie mich",
                    ],
                    aufgabe_wenn_nein=f"Umsatzrückgang {name} klären",
                )
                neue_fragen.append(f)

        fehlende_docs = _fehlende_docs_aus_mandant(m)
        if len(fehlende_docs) >= MIN_FEHLENDE_BELEGE and "beleg_fehlend" not in bestehende:
            docs_str = ", ".join(fehlende_docs[:3])
            f = self.frage_stellen(
                mandant=name,
                frage_text=(
                    f"Wir warten noch auf {len(fehlende_docs)} Dokument(e): "
                    f"{docs_str}{'...' if len(fehlende_docs) > 3 else ''}. "
                    f"Wann können Sie diese einreichen?"
                ),
                frage_typ="beleg_fehlend",
                kontext=f"Alle fehlenden Dokumente: {', '.join(fehlende_docs)}",
                antwort_optionen=[
                    "Diese Woche",
                    "Nächste Woche",
                    "Habe ich gerade hochgeladen",
                    "Bitte rufen Sie mich an",
                ],
                aufgabe_wenn_nein=f"Dokumente bei {name} anfordern — 2. Erinnerung",
            )
            neue_fragen.append(f)

        tage_ohne_antwort = self._tage_ohne_antwort(name)
        if tage_ohne_antwort >= self._min_tage_ohne_antwort() and "kontakt_erinnerung" not in bestehende:
            f = self.frage_stellen(
                mandant=name,
                frage_text=(
                    f"Wir haben seit {tage_ohne_antwort} Tagen nichts von Ihnen gehört. "
                    f"Läuft bei Ihnen alles gut?"
                ),
                frage_typ="kontakt_erinnerung",
                antwort_optionen=[
                    "Ja, alles in Ordnung",
                    "Ich wollte mich melden — bitte kurz anrufen",
                    "Es gibt etwas zu besprechen",
                ],
            )
            neue_fragen.append(f)

        kfz_aufgaben = [
            a for a in alle_aufgaben.values()
            if isinstance(a, dict)
            and a.get("mandant") == name
            and not aufgabe_ist_erledigt(a)
            and any(
                w in str(a.get("beschreibung", "")).lower()
                for w in ("fahrt", "kfz", "auto", "benzin", "kraftstoff")
            )
        ]
        if kfz_aufgaben and "fahrtenbuch" not in bestehende:
            f = self.frage_stellen(
                mandant=name,
                frage_text=(
                    "Für Ihre Fahrzeugkosten benötigen wir ein aktuelles Fahrtenbuch. "
                    "Ist Ihr Fahrtenbuch auf dem neuesten Stand?"
                ),
                frage_typ="fahrtenbuch",
                antwort_optionen=[
                    "Ja, Fahrtenbuch ist aktuell",
                    "Nein, ich habe keins geführt",
                    "Ich nutze die 1%-Regel",
                    "Bitte erklären Sie mir das",
                ],
                aufgabe_wenn_nein=f"Fahrtenbuch-Regelung für {name} besprechen",
            )
            neue_fragen.append(f)

        ueberfaellige = [
            a for a in alle_aufgaben.values()
            if isinstance(a, dict)
            and a.get("mandant") == name
            and not aufgabe_ist_erledigt(a)
            and str(a.get("frist") or "9999") < heute
        ]
        if len(ueberfaellige) >= MIN_UEBERFAELLIGE_FRISTEN and "frist_erinnerung" not in bestehende:
            erste = ueberfaellige[0].get("beschreibung", "") or "Aufgabe"
            f = self.frage_stellen(
                mandant=name,
                frage_text=(
                    f"Sie haben {len(ueberfaellige)} überfällige Aufgabe(n) in unserer Kanzlei. "
                    f"Die dringendste: '{erste}'. Wie möchten Sie vorgehen?"
                ),
                frage_typ="frist_erinnerung",
                antwort_optionen=[
                    "Ich sende die Unterlagen diese Woche",
                    "Bitte vereinbaren Sie einen Termin",
                    "Ich benötige eine Fristverlängerung",
                ],
                aufgabe_wenn_nein=f"Dringend: Fristen für {name} klären",
            )
            neue_fragen.append(f)

        return neue_fragen

    def statistiken(self) -> Dict:
        data   = self._portal_daten()
        fragen = list(data.get("bot_fragen", {}).values())

        gesamt      = len(fragen)
        beantwortet = sum(1 for f in fragen if f.get("status") == "beantwortet")
        offen       = sum(1 for f in fragen if f.get("status") == "offen")
        antwortquote = round(beantwortet / gesamt * 100, 1) if gesamt else 0

        gesparte_telefonate = beantwortet
        gesparte_minuten    = gesparte_telefonate * 8
        gesparte_stunden    = round(gesparte_minuten / 60, 1)

        stundensatz = self._stundensatz()
        return {
            "fragen_gesamt":         gesamt,
            "fragen_offen":          offen,
            "fragen_beantwortet":    beantwortet,
            "antwortquote_prozent":  antwortquote,
            "gesparte_telefonate":   gesparte_telefonate,
            "gesparte_stunden":      gesparte_stunden,
            "zeitersparnis_euro":    round(gesparte_stunden * stundensatz, 2),
            "stundensatz":           stundensatz,
        }

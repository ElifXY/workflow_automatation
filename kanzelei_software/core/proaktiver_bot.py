# ============================================================
# KANZLEI AI — PROAKTIVER MANDANTEN-BOT v1.0
# Datei: core/proaktiver_bot.py
# ============================================================

import uuid
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from core.aufgabe_erledigt import aufgabe_ist_erledigt

log = logging.getLogger("kanzlei_bot")

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
    "investition_geplant":    {"icon": "📈", "prioritaet": "niedrig"},
    "sonstiges":              {"icon": "❓", "prioritaet": "niedrig"},
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


class ProaktiverBot:
    """Analysiert Mandantendaten und erzeugt Fragen im Mandantenportal."""

    def __init__(self, ds):
        self.ds = ds

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

    def analysiere_alle_mandanten(self) -> List[Dict]:
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
        for name, m in mandanten.items():
            if not name or not isinstance(m, dict):
                continue
            try:
                fragen = self._analysiere_mandant(name, m, aufgaben)
                neue_fragen.extend(fragen)
            except Exception as e:
                log.warning("Bot-Analyse Fehler für %s: %s", name, e, exc_info=True)

        log.info(
            "Bot-Analyse: %s neue Fragen für %s Mandanten",
            len(neue_fragen),
            len(mandanten),
        )
        return neue_fragen

    def _analysiere_mandant(
        self, name: str, m: Dict, alle_aufgaben: Dict
    ) -> List[Dict]:
        neue_fragen: List[Dict] = []
        bestehende = {f.get("typ") for f in self.fragen_fuer_mandant(name, nur_offen=True)}
        jetzt = datetime.now()
        heute = jetzt.strftime("%Y-%m-%d")

        umsatz = _safe_float(m.get("umsatz"), 0.0)
        if umsatz > 0:
            letzter_monatsumsatz = _safe_float(m.get("letzter_monatsumsatz"), umsatz / 12.0)
            erwarteter_monat = umsatz / 12.0

            if (
                letzter_monatsumsatz > 0
                and letzter_monatsumsatz < erwarteter_monat * 0.6
                and "umsatz_anomalie" not in bestehende
            ):
                differenz = round(erwarteter_monat - letzter_monatsumsatz, 2)
                f = self.frage_stellen(
                    mandant=name,
                    frage_text=(
                        f"Ihre Einnahmen waren diesen Monat €{letzter_monatsumsatz:,.2f} — "
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

        fehlende_docs = _as_str_list(m.get("fehlende_dokumente_liste"))
        if len(fehlende_docs) >= 3 and "beleg_fehlend" not in bestehende:
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

        try:
            tage_ohne_antwort = _safe_int(self.ds.berechne_tage_ohne_antwort(name), 0)
        except Exception as e:
            log.warning("tage_ohne_antwort für %s: %s", name, e)
            tage_ohne_antwort = 0

        if tage_ohne_antwort >= 14 and "sonstiges" not in bestehende:
            f = self.frage_stellen(
                mandant=name,
                frage_text=(
                    f"Wir haben seit {tage_ohne_antwort} Tagen nichts von Ihnen gehört. "
                    f"Läuft bei Ihnen alles gut?"
                ),
                frage_typ="sonstiges",
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
        if len(ueberfaellige) >= 2 and "frist_erinnerung" not in bestehende:
            erste = ueberfaellige[0].get("beschreibung", "") or "Aufgabe"
            f = self.frage_stellen(
                mandant=name,
                frage_text=(
                    f"Sie haben {len(ueberfaellige)} überfällige Aufgaben in unserer Kanzlei. "
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

        return {
            "fragen_gesamt":         gesamt,
            "fragen_offen":          offen,
            "fragen_beantwortet":    beantwortet,
            "antwortquote_prozent":  antwortquote,
            "gesparte_telefonate":   gesparte_telefonate,
            "gesparte_stunden":      gesparte_stunden,
            "zeitersparnis_euro":    round(gesparte_stunden * 150, 2),
        }

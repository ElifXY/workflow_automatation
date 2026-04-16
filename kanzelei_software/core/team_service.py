# ============================================================
# KANZLEI AI — TEAM & ZEITERFASSUNG v1.1
# Datei: core/team_service.py
#
# Fixes v1.1:
#   - 'stundesatz' Tippfehler → 'stundensatz'
#   - 'import os' aus Funktions-Body → Datei-Top-Level
#   - Stundensatz-Fallback robuster
# ============================================================

import os
import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

log = logging.getLogger("kanzlei_team")


# ============================================================
# AUFGABEN-ZUWEISUNG
# ============================================================

def aufgabe_zuweisen(
    ds,
    aufgabe_id: str,
    mitarbeiter: str,
    zugewiesen_von: str = "system",
) -> Dict:
    """Aufgabe einem Mitarbeiter zuweisen."""
    aufgaben = ds.hole_fristen()
    if aufgabe_id not in aufgaben:
        raise ValueError(f"Aufgabe {aufgabe_id} nicht gefunden")

    a = aufgaben[aufgabe_id]
    a["zugewiesen_an"]  = mitarbeiter
    a["zugewiesen_von"] = zugewiesen_von
    a["zugewiesen_am"]  = datetime.now().isoformat()

    ds.aufgabe_speichern(aufgabe_id, a)
    ds.log_eintrag(f"AUFGABE_ZUGEWIESEN | {a.get('mandant')} | {aufgabe_id[:8]} | → {mitarbeiter}")
    return a


def aufgaben_fuer_mitarbeiter(ds, mitarbeiter: str) -> List[Dict]:
    """Alle offenen Aufgaben eines Mitarbeiters, nach Frist sortiert."""
    aufgaben = ds.hole_fristen()
    result = [
        a for a in aufgaben.values()
        if a.get("zugewiesen_an") == mitarbeiter and not a.get("erledigt")
    ]
    jetzt = datetime.now()
    for a in result:
        try:
            frist = datetime.strptime(a["frist"], "%Y-%m-%d")
            a["tage_bis_frist"] = (frist - jetzt).days
        except Exception:
            a["tage_bis_frist"] = None
    return sorted(result, key=lambda x: (x.get("tage_bis_frist") is None, x.get("tage_bis_frist") or 9999))


def team_auslastung(ds) -> List[Dict]:
    """Auslastung aller Mitarbeiter basierend auf offenen Aufgaben."""
    aufgaben = ds.hole_fristen()
    auslastung: Dict[str, Dict] = {}

    for a in aufgaben.values():
        ma = a.get("zugewiesen_an")
        if not ma or a.get("erledigt"):
            continue

        if ma not in auslastung:
            auslastung[ma] = {
                "mitarbeiter":       ma,
                "aufgaben_offen":    0,
                "aufgaben_kritisch": 0,
                "mandanten":         set(),
            }

        auslastung[ma]["aufgaben_offen"] += 1
        auslastung[ma]["mandanten"].add(a.get("mandant", "?"))

        try:
            frist = datetime.strptime(a["frist"], "%Y-%m-%d")
            if (frist - datetime.now()).days <= 2:
                auslastung[ma]["aufgaben_kritisch"] += 1
        except Exception:
            pass

    result = []
    for ma, daten in auslastung.items():
        daten["mandanten"]         = list(daten["mandanten"])
        daten["mandanten_anzahl"]  = len(daten["mandanten"])
        result.append(daten)

    return sorted(result, key=lambda x: x["aufgaben_offen"], reverse=True)


# ============================================================
# ZEITERFASSUNG
# ============================================================

def _hole_stundensatz() -> float:
    """Stundensatz aus Umgebungsvariable oder Settings holen."""
    try:
        from modules.settings_manager import setting_holen
        wert = setting_holen("stundensatz")
        if wert:
            return float(wert)
    except Exception:
        pass
    return float(os.getenv("STUNDENSATZ", "150"))


def zeit_starten(
    ds,
    mitarbeiter: str,
    mandant:     str,
    taetigkeit:  str,
    aufgabe_id:  Optional[str] = None,
) -> Dict:
    """
    Zeiterfassung für einen Mitarbeiter starten.
    Laufende Timer werden automatisch gestoppt.
    """
    zeiterfassung = ds.zeiterfassung_holen()
    if "eintraege" not in zeiterfassung:
        zeiterfassung["eintraege"] = {}
    if "laufend" not in zeiterfassung:
        zeiterfassung["laufend"] = {}

    # Bereits laufenden Timer stoppen
    laufend = zeiterfassung["laufend"]
    if mitarbeiter in laufend:
        _zeit_auto_stopp(zeiterfassung, mitarbeiter)

    stundensatz = _hole_stundensatz()
    zeit_id     = str(uuid.uuid4())

    eintrag = {
        "id":          zeit_id,
        "mitarbeiter": mitarbeiter,
        "mandant":     mandant,
        "taetigkeit":  taetigkeit,
        "aufgabe_id":  aufgabe_id,
        "start":       datetime.now().isoformat(),
        "ende":        None,
        "dauer_min":   None,
        "abrechenbar": True,
        "stundensatz": stundensatz,   # KORREKTUR: war 'stundesatz'
    }

    zeiterfassung["laufend"][mitarbeiter] = zeit_id
    zeiterfassung["eintraege"][zeit_id] = eintrag
    ds.zeiterfassung_speichern(zeiterfassung)

    ds.log_eintrag(f"ZEIT_GESTARTET | {mitarbeiter} | {mandant} | {taetigkeit}")
    return eintrag


def _zeit_auto_stopp(zeiterfassung: Dict, mitarbeiter: str):
    """Laufenden Timer eines Mitarbeiters automatisch beenden."""
    laufend = zeiterfassung["laufend"]
    if mitarbeiter not in laufend:
        return

    zeit_id = laufend[mitarbeiter]
    eintrag = zeiterfassung["eintraege"].get(zeit_id)
    if eintrag and not eintrag.get("ende"):
        ende      = datetime.now()
        start     = datetime.fromisoformat(eintrag["start"])
        dauer_min = round((ende - start).total_seconds() / 60, 1)
        eintrag["ende"]      = ende.isoformat()
        eintrag["dauer_min"] = dauer_min
        eintrag["betrag"]    = round(dauer_min / 60 * eintrag.get("stundensatz", 150), 2)

    del laufend[mitarbeiter]


def zeit_stoppen(ds, mitarbeiter: str, notiz: str = "") -> Dict:
    """Laufenden Timer stoppen und Betrag berechnen."""
    zeiterfassung = ds.zeiterfassung_holen()
    if "laufend" not in zeiterfassung or "eintraege" not in zeiterfassung:
        raise ValueError("Keine Zeiterfassung gestartet")

    laufend = zeiterfassung["laufend"]
    if mitarbeiter not in laufend:
        raise ValueError(f"Kein laufender Timer für '{mitarbeiter}'")

    zeit_id = laufend[mitarbeiter]
    eintrag = zeiterfassung["eintraege"][zeit_id]

    ende      = datetime.now()
    start     = datetime.fromisoformat(eintrag["start"])
    dauer_min = round((ende - start).total_seconds() / 60, 1)

    eintrag["ende"]      = ende.isoformat()
    eintrag["dauer_min"] = dauer_min
    eintrag["notiz"]     = notiz
    eintrag["betrag"]    = round(dauer_min / 60 * eintrag.get("stundensatz", 150), 2)

    del laufend[mitarbeiter]
    ds.zeiterfassung_speichern(zeiterfassung)

    ds.log_eintrag(
        f"ZEIT_GESTOPPT | {mitarbeiter} | {eintrag['mandant']} | "
        f"{dauer_min:.0f}min | €{eintrag.get('betrag', 0):.2f}"
    )
    return eintrag


def laufende_zeiten(ds) -> List[Dict]:
    """Alle gerade aktiven Timer mit bisheriger Laufzeit."""
    zeiterfassung = ds.zeiterfassung_holen()
    laufend = zeiterfassung.get("laufend", {})
    eintraege = zeiterfassung.get("eintraege", {})
    result    = []

    for ma, zeit_id in laufend.items():
        eintrag = eintraege.get(zeit_id, {})
        if eintrag:
            try:
                start    = datetime.fromisoformat(eintrag["start"])
                laufzeit = round((datetime.now() - start).total_seconds() / 60, 0)
                result.append({**eintrag, "laufzeit_min": laufzeit})
            except Exception:
                pass

    return result


def zeit_eintraege(
    ds,
    mitarbeiter: Optional[str] = None,
    mandant:     Optional[str] = None,
    von_datum:   Optional[str] = None,
    bis_datum:   Optional[str] = None,
) -> List[Dict]:
    """Abgeschlossene Zeiteinträge laden, gefiltert."""
    zeiterfassung = ds.zeiterfassung_holen()
    eintraege = list(zeiterfassung.get("eintraege", {}).values())

    # Nur abgeschlossene
    eintraege = [e for e in eintraege if e.get("ende")]

    if mitarbeiter:
        eintraege = [e for e in eintraege if e.get("mitarbeiter") == mitarbeiter]
    if mandant:
        eintraege = [e for e in eintraege if e.get("mandant") == mandant]
    if von_datum:
        eintraege = [e for e in eintraege if e.get("start", "") >= von_datum]
    if bis_datum:
        eintraege = [e for e in eintraege if e.get("start", "") <= bis_datum + "T23:59:59"]

    return sorted(eintraege, key=lambda x: x.get("start", ""), reverse=True)


def zeit_statistiken(ds, mandant: Optional[str] = None) -> Dict:
    """Zeiterfassungs-Statistiken — Stunden, Umsatz, Aufschlüsselung."""
    eintraege     = zeit_eintraege(ds, mandant=mandant)

    gesamt_min    = sum(e.get("dauer_min", 0) for e in eintraege)
    gesamt_betrag = sum(e.get("betrag", 0) for e in eintraege)

    pro_mandant: Dict[str, float] = {}
    for e in eintraege:
        m = e.get("mandant", "?")
        pro_mandant[m] = pro_mandant.get(m, 0) + e.get("dauer_min", 0)

    pro_mitarbeiter: Dict[str, float] = {}
    for e in eintraege:
        ma = e.get("mitarbeiter", "?")
        pro_mitarbeiter[ma] = pro_mitarbeiter.get(ma, 0) + e.get("dauer_min", 0)

    return {
        "gesamt_stunden":          round(gesamt_min / 60, 2),
        "gesamt_betrag":           round(gesamt_betrag, 2),
        "eintraege_anzahl":        len(eintraege),
        "pro_mandant_stunden":     {
            k: round(v / 60, 2)
            for k, v in sorted(pro_mandant.items(), key=lambda x: x[1], reverse=True)
        },
        "pro_mitarbeiter_stunden": {
            k: round(v / 60, 2)
            for k, v in sorted(pro_mitarbeiter.items(), key=lambda x: x[1], reverse=True)
        },
    }
# Historie / TTL für erledigte Aufgaben und Steuerfälle (pro Kanzlei)
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Tuple

from core.aufgabe_erledigt import aufgabe_ist_erledigt

try:
    from modules.settings_manager import DEFAULT_SETTINGS, SETTINGS_KEY
except Exception:  # pragma: no cover
    SETTINGS_KEY = "__settings_manager_v1"
    DEFAULT_SETTINGS = {}


def _merged_settings_dict(store) -> Dict[str, Any]:
    base = DEFAULT_SETTINGS.copy() if DEFAULT_SETTINGS else {}
    raw = store.setting_holen(SETTINGS_KEY, None)
    if isinstance(raw, dict):
        base.update(raw)
    return base


def historie_erledigte_aufgaben_tage(store) -> int:
    v = _merged_settings_dict(store).get("historie_erledigte_aufgaben_tage", 30)
    try:
        return max(1, min(3650, int(v)))
    except (TypeError, ValueError):
        return 30


def historie_steuerfaelle_tage(store) -> int:
    v = _merged_settings_dict(store).get("historie_steuerfaelle_tage", 30)
    try:
        return max(1, min(3650, int(v)))
    except (TypeError, ValueError):
        return 30


def _parse_iso_dt(s: Any) -> datetime | None:
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if not s:
        return None
    core = s.replace("Z", "").split("+")[0].strip()
    try:
        if "T" in core:
            return datetime.fromisoformat(core[:26])
    except ValueError:
        pass
    for fmt, ln in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d", 10)):
        try:
            return datetime.strptime(core[:ln], fmt)
        except ValueError:
            continue
    return None


def purge_abgelaufene_erledigte_aufgaben(store) -> int:
    """Löscht erledigte Aufgaben dauerhaft, deren Historie-TTL überschritten ist."""
    ttl = historie_erledigte_aufgaben_tage(store)
    jetzt = datetime.now()
    removed = 0
    for aid, a in list(store.hole_fristen().items()):
        if not aufgabe_ist_erledigt(a):
            continue
        ref = a.get("erledigt_am") or a.get("erstellt_am")
        ts = _parse_iso_dt(ref)
        if ts is None:
            continue
        if (jetzt - ts).days > ttl:
            if store.aufgabe_loeschen(aid):
                removed += 1
    return removed


def aufgaben_historie_nach_purge(store, mandant: str) -> Tuple[List[Dict], int]:
    """
    Entfernt abgelaufene erledigte Aufgaben, liefert verbleibende Historie-Einträge
    für einen Mandanten mit Metadatum historie_verbleibend_tage.
    """
    purge_abgelaufene_erledigte_aufgaben(store)
    ttl = historie_erledigte_aufgaben_tage(store)
    jetzt = datetime.now()
    out: List[Dict] = []
    for a in store.hole_aufgaben_fuer_mandant(mandant):
        if not aufgabe_ist_erledigt(a):
            continue
        ref = a.get("erledigt_am") or a.get("erstellt_am")
        ts = _parse_iso_dt(ref)
        if ts is None:
            rest = ttl
        else:
            age = (jetzt - ts).days
            rest = max(0, ttl - age)
        row = dict(a)
        row["historie_verbleibend_tage"] = rest
        out.append(row)
    out.sort(key=lambda x: (x.get("erledigt_am") or x.get("erstellt_am") or ""), reverse=True)
    return out, ttl


def steuerfall_historie_eintritt_am(fall: Dict) -> str | None:
    """Ankerdatum für TTL (Freigabe oder manuelles Ablegen)."""
    return fall.get("historie_eintritt_am") or fall.get("freigegeben_am")


def steuerfall_ist_in_historie(fall: Dict) -> bool:
    if fall.get("historie_eintritt_am"):
        return True
    if fall.get("freigegeben_am"):
        return True
    if str(fall.get("status") or "").lower() == "freigegeben":
        return True
    return False


def purge_abgelaufene_steuerfaelle(store) -> int:
    ttl = historie_steuerfaelle_tage(store)
    jetzt = datetime.now()
    faelle: Dict[str, Dict] = dict(store.steuerfaelle_liste())
    removed = 0
    for fid, f in list(faelle.items()):
        ref = steuerfall_historie_eintritt_am(f)
        if not ref:
            continue
        ts = _parse_iso_dt(ref)
        if ts is None:
            continue
        if (jetzt - ts).days > ttl:
            if store.steuerfall_loeschen(fid):
                removed += 1
    return removed


def steuerfaelle_historie_liste(store, mandant: str | None = None) -> Tuple[List[Dict], int]:
    """Fälle mit Historie-Zeitstempel (Freigabe oder manuell), nach Purge."""
    purge_abgelaufene_steuerfaelle(store)
    ttl = historie_steuerfaelle_tage(store)
    jetzt = datetime.now()
    raw = list(store.steuerfaelle_liste().values())
    hist: List[Dict] = []
    for f in raw:
        if not steuerfall_ist_in_historie(f):
            continue
        if mandant and f.get("mandant") != mandant:
            continue
        ref = steuerfall_historie_eintritt_am(f)
        ts = _parse_iso_dt(ref)
        if ts is None:
            rest = ttl
        else:
            rest = max(0, ttl - (jetzt - ts).days)
        slim = {k: v for k, v in f.items() if k not in ("ki_analyse", "elster_xml_b64", "mandant_daten")}
        slim["historie_verbleibend_tage"] = rest
        hist.append(slim)
    hist.sort(key=lambda x: x.get("erstellt_am", ""), reverse=True)
    return hist, ttl

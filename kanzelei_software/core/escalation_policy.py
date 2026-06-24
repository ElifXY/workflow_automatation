# Automatische Eskalations-Stufen (Tag 0 → 30)

from __future__ import annotations



from typing import Any, Dict, List



from modules.settings_manager import load_settings_for_store





DEFAULT_STUFEN = [

    {"tag": 0, "aktion": "dokument_angefordert", "label": "Dokument angefordert"},

    {"tag": 3, "aktion": "erinnerung_1", "label": "Erste Erinnerung"},

    {"tag": 7, "aktion": "erinnerung_2", "label": "Zweite Erinnerung"},

    {"tag": 14, "aktion": "erinnerung_deutlich", "label": "Deutlicher Hinweis"},

    {"tag": 21, "aktion": "eskalation_intern", "label": "Interne Eskalation"},

    {"tag": 30, "aktion": "mandant_rot", "label": "Mandant rot markiert"},

]





def eskalations_stufen_aus_settings(store) -> List[Dict[str, Any]]:

    cfg = load_settings_for_store(store)

    s1 = int(cfg.get("eskalation_stufe_1_tage") or 7)

    s2 = int(cfg.get("eskalation_stufe_2_tage") or 14)

    return [

        {"tag": 0, "aktion": "dokument_angefordert", "label": "Dokument angefordert"},

        {"tag": 3, "aktion": "erinnerung_1", "label": "Erste Erinnerung (Portal/E-Mail)"},

        {"tag": min(7, s1), "aktion": "erinnerung_2", "label": "Zweite Erinnerung"},

        {"tag": s1, "aktion": "erinnerung_deutlich", "label": "Deutlicher Hinweis"},

        {"tag": s2, "aktion": "eskalation_intern", "label": "Interne Eskalation an Kanzlei"},

        {"tag": max(s2 + 7, 30), "aktion": "mandant_rot", "label": "Mandant rot markiert"},

    ]





def aktuelle_eskalations_stufe(tage_ohne_antwort: int, store) -> Dict[str, Any]:

    """Welche Stufe gilt für Mandant ohne Antwort seit N Tagen."""

    stufen = eskalations_stufen_aus_settings(store)

    tage = max(0, int(tage_ohne_antwort or 0))

    current = stufen[0]

    naechste = None

    for i, st in enumerate(stufen):

        if tage >= st["tag"]:

            current = st

            if i + 1 < len(stufen):

                naechste = stufen[i + 1]

    tage_bis_naechste = None

    if naechste:

        tage_bis_naechste = max(0, naechste["tag"] - tage)

    return {

        "tage_ohne_antwort": tage,

        "stufe": current,

        "naechste_stufe": naechste,

        "tage_bis_naechste": tage_bis_naechste,

        "stufen_plan": stufen,

    }





def mandant_eskalation_timeline(name: str, m: Dict[str, Any], store) -> Dict[str, Any]:

    """Eskalationsplan für einen Mandanten — für Akte und Dashboard."""

    cfg = load_settings_for_store(store)

    try:

        tage = int(store.berechne_tage_ohne_antwort(name) or 0)

    except Exception:

        tage = 0

    info = aktuelle_eskalations_stufe(tage, store)

    stufen = info.get("stufen_plan") or eskalations_stufen_aus_settings(store)

    last_aktion = (m.get("eskalation_letzte_aktion") or "").strip()

    last_am = m.get("eskalation_letzte_am") or ""



    timeline: List[Dict[str, Any]] = []

    current_aktion = (info.get("stufe") or {}).get("aktion", "")

    for st in stufen:

        aktion = st.get("aktion", "")

        executed = last_aktion == aktion

        timeline.append({

            "tag": st.get("tag"),

            "aktion": aktion,

            "label": st.get("label"),

            "erreicht": tage >= int(st.get("tag") or 0),

            "aktuell": aktion == current_aktion,

            "ausgefuehrt": executed,

            "ausgefuehrt_am": last_am if executed else None,

        })



    fehlende = m.get("fehlende_dokumente_liste") or []

    fehl_n = len(fehlende) if isinstance(fehlende, list) else 0



    return {

        "mandant": name,

        "tage_ohne_antwort": tage,

        "fehlende_dokumente": fehl_n,

        "aktuelle_stufe": info.get("stufe"),

        "naechste_stufe": info.get("naechste_stufe"),

        "tage_bis_naechste": info.get("tage_bis_naechste"),

        "timeline": timeline,

        "auto_eskalation_aktiv": bool(cfg.get("auto_eskalation_aktiv", True)),

    }



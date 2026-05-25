# Dashboard „Heute“ — operative Kennzahlen auf einen Blick
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from core.aufgabe_erledigt import aufgabe_ist_erledigt
from core.frist_utils import parse_frist, tage_bis_frist


def heute_operations(store) -> Dict[str, Any]:
    """Bot offen, fehlende Belege, überfällige/heute fällige Aufgaben."""
    jetzt = datetime.now()
    heute_datum = jetzt.date()

    mandanten = store.hole_mandanten() or {}
    aufgaben = store.hole_fristen() or {}

    bot_offen = 0
    bot_pro_mandant: List[Dict[str, Any]] = []
    try:
        from core.proaktiver_bot import ProaktiverBot

        bot = ProaktiverBot(store)
        for name in mandanten:
            if not name:
                continue
            n = len(bot.fragen_fuer_mandant(name, nur_offen=True))
            if n:
                bot_offen += n
                bot_pro_mandant.append({"mandant": name, "anzahl": n})
        bot_pro_mandant.sort(key=lambda x: -x["anzahl"])
    except Exception:
        pass

    ueberfaellig = 0
    faellig_heute = 0
    ueberfaellig_liste: List[Dict[str, Any]] = []

    for a in aufgaben.values():
        if not isinstance(a, dict) or aufgabe_ist_erledigt(a):
            continue
        frist_raw = a.get("frist")
        tage = tage_bis_frist(frist_raw, heute=heute_datum)
        if tage is None:
            continue
        frist_iso = parse_frist(frist_raw)
        frist_str = frist_iso.isoformat() if frist_iso else str(frist_raw or "")
        if tage < 0:
            ueberfaellig += 1
            if len(ueberfaellig_liste) < 8:
                ueberfaellig_liste.append({
                    "mandant": a.get("mandant", ""),
                    "beschreibung": (a.get("beschreibung") or "")[:80],
                    "frist": frist_str,
                })
        elif tage == 0:
            faellig_heute += 1

    fehlende_docs = 0
    mandanten_mit_docs: List[Dict[str, Any]] = []
    for name, m in mandanten.items():
        if not isinstance(m, dict):
            continue
        docs = m.get("fehlende_dokumente_liste") or []
        if isinstance(docs, str):
            docs = [docs] if docs.strip() else []
        n = len(docs)
        if n:
            fehlende_docs += n
            mandanten_mit_docs.append({"mandant": name, "anzahl": n})
    mandanten_mit_docs.sort(key=lambda x: -x["anzahl"])

    zeile = (
        f"{bot_offen} Bot-Fragen · {fehlende_docs} fehlende Belege · "
        f"{ueberfaellig} überfällig · {faellig_heute} heute fällig"
    )

    return {
        "zeile": zeile,
        "bot_fragen_offen": bot_offen,
        "fehlende_belege": fehlende_docs,
        "aufgaben_ueberfaellig": ueberfaellig,
        "aufgaben_heute": faellig_heute,
        "bot_top_mandanten": bot_pro_mandant[:5],
        "docs_top_mandanten": mandanten_mit_docs[:5],
        "ueberfaellig_preview": ueberfaellig_liste,
        "referenz_datum": heute_datum.isoformat(),
        "timestamp": jetzt.isoformat(),
    }


def pilot_scorecard(store) -> Dict[str, Any]:
    """Pilot-Kennzahlen inkl. optionaler Baseline aus Einstellungen."""
    from core.proaktiver_bot import ProaktiverBot

    bot = ProaktiverBot(store)
    stats = bot.statistiken()
    baseline = store.setting_holen("pilot_baseline", {}) or {}
    if not isinstance(baseline, dict):
        baseline = {}

    b_gestellt = int(baseline.get("fragen_gesamt") or 0)
    b_beantwortet = int(baseline.get("fragen_beantwortet") or 0)
    b_stunden = float(baseline.get("gesparte_stunden") or 0)

    gestellt = int(stats.get("fragen_gesamt") or 0)
    beantwortet = int(stats.get("fragen_beantwortet") or 0)
    stunden = float(stats.get("gesparte_stunden") or 0)

    pilot_start = baseline.get("gestartet_am")
    if not pilot_start:
        pilot_start = datetime.now().isoformat()
        try:
            store.setting_setzen(
                "pilot_baseline",
                {
                    "gestartet_am": pilot_start,
                    "fragen_gesamt": 0,
                    "fragen_beantwortet": 0,
                    "gesparte_stunden": 0,
                    "notiz": "Automatisch beim ersten Abruf gesetzt",
                },
            )
        except Exception:
            pass

    try:
        start_dt = datetime.fromisoformat(str(pilot_start).replace("Z", "+00:00"))
        if start_dt.tzinfo:
            start_dt = start_dt.replace(tzinfo=None)
        tage = max(1, (datetime.now() - start_dt).days + 1)
        woche = min(4, max(1, (tage + 6) // 7))
    except Exception:
        tage = 1
        woche = 1

    return {
        "pilot_woche": woche,
        "pilot_tage": tage,
        "gestartet_am": pilot_start,
        "aktuell": stats,
        "delta": {
            "fragen_gestellt": gestellt - b_gestellt,
            "fragen_beantwortet": beantwortet - b_beantwortet,
            "gesparte_stunden": round(stunden - b_stunden, 1),
        },
        "baseline": baseline,
        "hinweis": (
            "Geschätzte Zeitersparnis: 8 Min. pro beantworteter Bot-Frage. "
            "Baseline unter Einstellungen zurücksetzbar."
        ),
    }

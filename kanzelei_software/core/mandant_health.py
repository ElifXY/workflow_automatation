# Mandanten-Gesundheit: Score 0–100, Ampel, Blockierungsgründe
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from core.decision_engine import _berechne_risiko_daten


def health_from_risiko(risiko: Dict[str, Any]) -> Dict[str, Any]:
    """0–100 Gesundheit (100 = best), Ampel gruen/gelb/rot, Begründungen."""
    risiko_pct = int(risiko.get("risiko_prozent") or 0)
    score = max(0, min(100, 100 - risiko_pct))
    if score >= 70:
        ampel = "gruen"
        label = "Grün"
    elif score >= 40:
        ampel = "gelb"
        label = "Gelb"
    else:
        ampel = "rot"
        label = "Rot"

    gruende: List[str] = []
    for item in risiko.get("score_items") or []:
        txt = (item.get("text") or "").strip()
        if txt:
            gruende.append(txt)
    tage = int(risiko.get("tage_ohne_antwort") or 0)
    if tage >= 7 and not any("Antwort" in g or "Rückmeldung" in g for g in gruende):
        gruende.append(f"{tage} Tage ohne Antwort")
    fehl = int(risiko.get("fehlende_dokumente") or 0)
    if fehl and not any("Dokument" in g for g in gruende):
        gruende.append(f"{fehl} fehlende Unterlage(n)")
    ueber = int(risiko.get("aufgaben_ueberfaellig") or 0)
    if ueber and not any("Überfällig" in g or "überfällig" in g.lower() for g in gruende):
        gruende.append(f"{ueber} überfällige Aufgabe(n)")

    return {
        "health_score": score,
        "health_ampel": ampel,
        "health_label": label,
        "health_gruende": gruende[:6],
        "nervfaktor_score": risiko_pct,
    }


def mandant_health(name: str, m: Dict, store) -> Dict[str, Any]:
    risiko = _berechne_risiko_daten(name, m, store)
    h = health_from_risiko(risiko)
    return {
        "mandant": name,
        **risiko,
        **h,
    }


def blockierungs_eintraege(store, limit: int = 50) -> List[Dict[str, Any]]:
    """Sortierte Liste: was die Kanzlei blockiert."""
    mandanten = store.hole_mandanten() or {}
    rows: List[Dict[str, Any]] = []

    for name, m in mandanten.items():
        if not name or not isinstance(m, dict):
            continue
        risiko = _berechne_risiko_daten(name, m, store)
        h = health_from_risiko(risiko)
        if h["health_ampel"] == "gruen" and not risiko.get("fehlende_dokumente"):
            continue

        prio = int(h["nervfaktor_score"] or 0)
        if risiko.get("aufgaben_ueberfaellig"):
            prio += 20
        if int(risiko.get("tage_ohne_antwort") or 0) >= 14:
            prio += 15

        fehlende = m.get("fehlende_dokumente_liste") or []
        if isinstance(fehlende, list):
            for doc in fehlende[:3]:
                rows.append({
                    "mandant": name,
                    "typ": "fehlendes_dokument",
                    "titel": f"Dokument fehlt: {doc}",
                    "detail": f"{len(fehlende)} offen insgesamt",
                    "prioritaet": prio + 10,
                    "health_ampel": h["health_ampel"],
                    "health_score": h["health_score"],
                    "gruende": h["health_gruende"],
                })

        if int(risiko.get("tage_ohne_antwort") or 0) >= 7:
            rows.append({
                "mandant": name,
                "typ": "keine_antwort",
                "titel": f"Keine Antwort seit {risiko['tage_ohne_antwort']} Tagen",
                "detail": " · ".join(h["health_gruende"][:2]) or "Nachfassen empfohlen",
                "prioritaet": prio + 5,
                "health_ampel": h["health_ampel"],
                "health_score": h["health_score"],
                "gruende": h["health_gruende"],
            })

        for desc in (risiko.get("ueberfaellig_liste") or [])[:2]:
            rows.append({
                "mandant": name,
                "typ": "frist_kritisch",
                "titel": f"Frist blockiert: {desc}",
                "detail": "Überfällige Aufgabe",
                "prioritaet": prio + 25,
                "health_ampel": h["health_ampel"],
                "health_score": h["health_score"],
                "gruende": h["health_gruende"],
            })

    rows.sort(key=lambda x: (-x["prioritaet"], x["mandant"]))
    return rows[:limit]


def top_nervfaktoren(store, top_n: int = 5) -> Dict[str, Any]:
    """Top-N Mandanten nach Nervfaktor + Anteil an Gesamt-Blockierung."""
    mandanten = store.hole_mandanten() or {}
    scored: List[Dict[str, Any]] = []
    total_weight = 0

    for name, m in mandanten.items():
        if not name or not isinstance(m, dict):
            continue
        risiko = _berechne_risiko_daten(name, m, store)
        h = health_from_risiko(risiko)
        w = max(1, int(h["nervfaktor_score"] or 0))
        if h["health_ampel"] != "gruen":
            total_weight += w
        scored.append({
            "mandant": name,
            "gewicht": w,
            **h,
            "tage_ohne_antwort": risiko.get("tage_ohne_antwort"),
            "fehlende_dokumente": risiko.get("fehlende_dokumente"),
            "aufgaben_ueberfaellig": risiko.get("aufgaben_ueberfaellig"),
        })

    scored.sort(key=lambda x: -x["gewicht"])
    top = scored[:top_n]
    top_weight = sum(x["gewicht"] for x in top)
    anteil_pct = int(round(100 * top_weight / total_weight)) if total_weight else 0

    return {
        "top": top,
        "anzahl": len(top),
        "anteil_blockierung_pct": min(100, anteil_pct),
        "headline": (
            f"Diese {len(top)} Mandanten blockieren ca. {min(100, anteil_pct)} % Ihrer Arbeit."
            if top else "Keine kritischen Blockierungen."
        ),
    }

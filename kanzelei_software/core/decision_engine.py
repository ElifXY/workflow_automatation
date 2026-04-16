# ============================================================
# KANZLEI AI — DECISION ENGINE v5.0
# Echte AI-Analyse via OpenAI GPT-4o mini
#
# Vorher: 15 if-else Regeln = statisch, kein Mehrwert
# Jetzt:  OpenAI analysiert jeden Mandanten individuell
#         → versteht Kontext, nicht nur Schwellenwerte
#         → gibt strukturierte, erklärte Empfehlungen
#         → lernt implizit aus dem Prompt-Kontext
#
# Fallback: Schnelle Regel-Engine wenn OpenAI nicht verfügbar
# ============================================================

import os
import json
import logging
import httpx
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

log = logging.getLogger("kanzlei_decision")

RISIKO_SCHWELLEN = {"KRITISCH": 8000, "WICHTIG": 4000, "NORMAL": 1000, "OK": 0}
PRIO_MAP = {"kritisch": 2.5, "hoch": 1.8, "normal": 1.0, "niedrig": 0.5}


def _safe(d: Any, *keys, default=None) -> Any:
    try:
        r = d
        for k in keys:
            if r is None: return default
            r = r.get(k) if isinstance(r, dict) else default
        return r if r is not None else default
    except Exception:
        return default


# ═══════════════════════════════════════════════════════════
# ECHTE AI-ANALYSE via OpenAI
# ═══════════════════════════════════════════════════════════

AI_SYSTEM_PROMPT = """Du bist ein Experte für Steuerberater-Kanzleien.
Analysiere Mandanten-Daten und gib strukturierte Handlungsempfehlungen.

DEINE AUFGABE:
Bewerte jeden Mandanten nach: Absprung-Risiko (0-100) und Priorität der Handlung.

ANTWORTE NUR MIT VALIDEM JSON (kein Text davor/danach):
{
  "risiko_score": 0-100,
  "status": "KRITISCH|WICHTIG|NORMAL|OK",
  "empfehlung": {
    "prioritaet": "kritisch|hoch|mittel|ok",
    "farbe": "#hex",
    "icon": "emoji",
    "titel": "Kurzer Titel max 60 Zeichen",
    "text": "Erklärung max 120 Zeichen",
    "aktion": "sofort_anrufen|email_now|followup|vip_kontakt|document|nichts",
    "aktion_text": "Anzeige-Text"
  },
  "begruendung": "1-2 Sätze warum diese Empfehlung"
}

FARBEN: kritisch=#e05555, hoch=#e08c45, mittel=#5b8de8, ok=#5cb87a
ICONS: 🔴 kritisch, ⚠️ hoch, 📞 followup, ⭐ vip, 📄 dokumente, ✅ ok"""


async def analysiere_mandant_ai(
    name: str, m: Dict, risiko_daten: Dict
) -> Optional[Dict]:
    """
    OpenAI analysiert einen Mandanten individuell.
    Versteht Kontext — nicht nur stupide Schwellenwerte.
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return None

    umsatz       = float(_safe(m, "umsatz", default=0))
    tage         = risiko_daten.get("tage_ohne_antwort", 0)
    ueberfaellig = risiko_daten.get("aufgaben_ueberfaellig", 0)
    fehlende     = risiko_daten.get("fehlende_dokumente", 0)
    offen        = risiko_daten.get("aufgaben_offen", 0)
    branche      = _safe(m, "branche", default="Unbekannt")

    # Kontext für OpenAI aufbauen
    kontext = (
        f"Mandant: {name} | Branche: {branche} | Jahresumsatz: €{umsatz:,.0f}\n"
        f"Tage ohne Antwort: {tage} | Aufgaben offen: {offen} | "
        f"Davon überfällig: {ueberfaellig} | Dokumente fehlend: {fehlende}\n"
        f"Überfällige Aufgaben: {', '.join(risiko_daten.get('ueberfaellig_liste', []))}\n"
        f"Hat E-Mail: {'Ja' if _safe(m, 'email') else 'Nein'}"
    )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}",
                         "Content-Type": "application/json"},
                json={
                    "model":       "gpt-4o-mini",
                    "max_tokens":  300,
                    "temperature": 0.1,
                    "messages": [
                        {"role": "system", "content": AI_SYSTEM_PROMPT},
                        {"role": "user",   "content": kontext},
                    ],
                },
            )
        if r.status_code != 200:
            return None
        text = r.json()["choices"][0]["message"]["content"].strip()
        # JSON extrahieren
        if "```" in text:
            import re
            m_json = re.search(r"\{.*\}", text, re.DOTALL)
            text = m_json.group(0) if m_json else text
        return json.loads(text)
    except Exception as e:
        log.debug(f"AI-Analyse für {name} fehlgeschlagen: {e}")
        return None


# ═══════════════════════════════════════════════════════════
# SCHNELLE REGEL-ENGINE (Fallback + synchrone Nutzung)
# ═══════════════════════════════════════════════════════════

def _berechne_risiko_daten(name: str, m: Dict, ds) -> Dict:
    """Berechnet rohe Risiko-Metriken für einen Mandanten."""
    raw_score    = 0
    score_items  = []
    ueberfaellig = []
    bald         = []

    fehlende = _safe(m, "fehlende_dokumente_liste", default=[])
    fehlende = fehlende if isinstance(fehlende, list) else []

    try:
        tage = ds.berechne_tage_ohne_antwort(name)
    except Exception:
        tage = 0

    try:
        meine = [
            a for a in ds.hole_fristen().values()
            if _safe(a, "mandant") == name and not _safe(a, "erledigt", default=False)
        ]
    except Exception:
        meine = []

    heute = datetime.now().strftime("%Y-%m-%d")

    for a in meine:
        frist = _safe(a, "frist", default="9999-99-99")
        prio  = _safe(a, "prioritaet", default="normal")
        mult  = PRIO_MAP.get(prio, 1.0)
        try:
            diff = (datetime.now() - datetime.strptime(frist, "%Y-%m-%d")).days
        except Exception:
            diff = 0

        if frist < heute:
            punkte = int(3000 * mult * min(max(diff, 1) / 7, 3))
            raw_score += punkte
            ueberfaellig.append(_safe(a, "beschreibung", default="Aufgabe")[:40])
            score_items.append({"text": f"Überfällig: {ueberfaellig[-1]}", "punkte": punkte})
        elif diff > -3:
            punkte = int(1500 * mult)
            raw_score += punkte
            bald.append(_safe(a, "beschreibung", default="Aufgabe")[:40])

    if tage >= 21:
        p = min(tage * 150, 4500); raw_score += p
        score_items.append({"text": f"{tage} Tage ohne Antwort — kritisch", "punkte": p})
    elif tage >= 14:
        p = min(tage * 120, 3600); raw_score += p
        score_items.append({"text": f"{tage} Tage ohne Rückmeldung", "punkte": p})
    elif tage >= 7:
        p = tage * 60; raw_score += p

    if fehlende:
        p = len(fehlende) * 800; raw_score += p
        score_items.append({"text": f"{len(fehlende)} Dokument(e) fehlen", "punkte": p})

    umsatz = float(_safe(m, "umsatz", default=0))
    if umsatz >= 500000: raw_score = int(raw_score * 1.4)
    elif umsatz >= 100000: raw_score = int(raw_score * 1.2)

    status = "OK"
    for s, schwelle in RISIKO_SCHWELLEN.items():
        if raw_score >= schwelle:
            status = s
            break

    return {
        "raw_score":             raw_score,
        "risiko_prozent":        min(100, int(raw_score / RISIKO_SCHWELLEN["KRITISCH"] * 100)),
        "status":                status,
        "score_items":           score_items,
        "tage_ohne_antwort":     tage,
        "aufgaben_offen":        len(meine),
        "aufgaben_ueberfaellig": len(ueberfaellig),
        "fehlende_dokumente":    len(fehlende),
        "ueberfaellig_liste":    ueberfaellig[:3],
        "bald_faellig_liste":    bald[:3],
    }


def _fallback_empfehlung(name: str, m: Dict, risiko: Dict) -> Dict:
    """Schnelle Regel-Empfehlung wenn OpenAI nicht verfügbar."""
    umsatz     = float(_safe(m, "umsatz", default=0))
    hat_email  = bool(_safe(m, "email"))
    tage       = risiko["tage_ohne_antwort"]
    ueberfaellig = risiko["aufgaben_ueberfaellig"]
    ist_vip    = umsatz >= 500000
    ist_high   = umsatz >= 100000

    if ist_vip and (ueberfaellig > 0 or tage >= 14):
        return {"prioritaet":"kritisch","farbe":"#e05555","icon":"🔴",
                "titel":"SOFORT HANDELN — VIP-Mandant in Gefahr",
                "text":f"€{umsatz:,.0f} · {tage}d kein Kontakt · {ueberfaellig} überfällig",
                "aktion":"sofort_anrufen","aktion_text":"🔴 Sofort anrufen"}

    if ueberfaellig >= 2 or (ueberfaellig > 0 and ist_high):
        return {"prioritaet":"kritisch","farbe":"#e05555","icon":"🚨",
                "titel":f"{ueberfaellig} Aufgabe(n) überfällig",
                "text":" · ".join(risiko["ueberfaellig_liste"][:2]) or "Sofortiger Handlungsbedarf",
                "aktion":"email_now","aktion_text":"📧 Email jetzt"}

    if tage >= 14:
        return {"prioritaet":"hoch","farbe":"#e08c45","icon":"⚠️",
                "titel":f"{tage} Tage ohne Antwort",
                "text":"Mandant könnte abwandern — jetzt kontaktieren",
                "aktion":"followup","aktion_text":"📞 Nachfassen"}

    if ist_vip and tage >= 7:
        return {"prioritaet":"hoch","farbe":"#c8a96e","icon":"⭐",
                "titel":"VIP — regelmäßiger Kontakt empfohlen",
                "text":f"€{umsatz:,.0f} · {tage}d kein Kontakt",
                "aktion":"vip_kontakt","aktion_text":"⭐ VIP-Kontakt"}

    if risiko["fehlende_dokumente"] > 0:
        return {"prioritaet":"mittel","farbe":"#5b8de8","icon":"📄",
                "titel":f"{risiko['fehlende_dokumente']} Dokument(e) fehlen",
                "text":"Unterlagen für Abschluss ausstehend",
                "aktion":"document","aktion_text":"📄 Anfordern"}

    return {"prioritaet":"ok","farbe":"#5cb87a","icon":"✅",
            "titel":"Alles in Ordnung","text":"Kein akuter Handlungsbedarf",
            "aktion":"nichts","aktion_text":"✅ OK"}


def _umsatz_score(umsatz: float) -> Dict:
    u = float(umsatz or 0)
    if u >= 500000:   return {"score":100,"kategorie":"VIP","ist_vip":True,"ist_high":True}
    if u >= 100000:   return {"score":60+int((u-100000)/400000*40),"kategorie":"HIGH","ist_vip":False,"ist_high":True}
    if u >= 30000:    return {"score":20+int((u-30000)/70000*40),"kategorie":"MEDIUM","ist_vip":False,"ist_high":False}
    return {"score":max(0,int(u/30000*20)),"kategorie":"LOW","ist_vip":False,"ist_high":False}


# ═══════════════════════════════════════════════════════════
# HAUPT-ANALYSE — synchron (für /kpis Endpoint)
# ═══════════════════════════════════════════════════════════

def analysiere_alle_mandanten(ds) -> List[Dict]:
    """
    Analysiert alle Mandanten synchron mit Regel-Engine.
    AI-Analyse läuft asynchron (separat via /ki/analyse Endpoint).
    """
    try:
        mandanten = ds.hole_mandanten()
    except Exception as e:
        log.error(f"analysiere_alle_mandanten: {e}")
        return []

    ergebnisse = []

    for name, m in mandanten.items():
        if not isinstance(m, dict):
            continue
        try:
            risiko        = _berechne_risiko_daten(name, m, ds)
            umsatz_s      = _umsatz_score(_safe(m, "umsatz", default=0))
            empfehlung    = _fallback_empfehlung(name, m, risiko)

            ergebnisse.append({
                "mandant":               name,
                "email":                 _safe(m, "email", default=""),
                "umsatz":                umsatz_s["score"] and float(_safe(m,"umsatz",default=0)),
                "score":                 risiko["raw_score"],
                "risiko_score":          risiko["risiko_prozent"],
                "status":                risiko["status"],
                "score_details":         [{"grund":i["text"],"punkte":i["punkte"],"typ":"info"} for i in risiko["score_items"]],
                "tage_ohne_antwort":     risiko["tage_ohne_antwort"],
                "aufgaben_offen":        risiko["aufgaben_offen"],
                "aufgaben_ueberfaellig": risiko["aufgaben_ueberfaellig"],
                "fehlende_dokumente":    risiko["fehlende_dokumente"],
                "umsatz_score":          umsatz_s["score"],
                "umsatz_kategorie":      umsatz_s["kategorie"],
                "ist_vip":               umsatz_s["ist_vip"],
                "empfehlung":            empfehlung,
                "empfehlungen":          [{"typ":"kritisch" if i["punkte"]>2000 else "wichtig",
                                           "text":i["text"],"aktion":"email_now","prio":i["punkte"]}
                                          for i in risiko["score_items"][:4]],
                "ai_analyse":            None,  # Wird async befüllt
            })

        except Exception as e:
            log.warning(f"Analyse '{name}' Fehler: {e}")
            ergebnisse.append({
                "mandant":name,"email":_safe(m,"email",default=""),
                "umsatz":float(_safe(m,"umsatz",default=0)),
                "score":0,"risiko_score":0,"status":"OK","score_details":[],
                "tage_ohne_antwort":0,"aufgaben_offen":0,"aufgaben_ueberfaellig":0,
                "fehlende_dokumente":0,"umsatz_score":0,"umsatz_kategorie":"LOW",
                "ist_vip":False,
                "empfehlung":{"prioritaet":"ok","farbe":"#5cb87a","icon":"✅",
                              "titel":"Analyse fehlgeschlagen","text":"Neu laden",
                              "aktion":"review","aktion_text":"Prüfen"},
                "empfehlungen":[],"ai_analyse":None,
            })

    ergebnisse.sort(key=lambda x: (
        0 if x["status"]=="KRITISCH" else 1 if x["status"]=="WICHTIG" else
        2 if x["status"]=="NORMAL" else 3,
        -x.get("umsatz",0), -x.get("score",0),
    ))
    return ergebnisse


# ═══════════════════════════════════════════════════════════
# ASYNC AI-ANALYSE (für /ki/mandant-analyse Endpoint)
# ═══════════════════════════════════════════════════════════

async def analysiere_mandant_komplett(name: str, m: Dict, ds) -> Dict:
    """
    Vollständige Analyse mit echter OpenAI-Empfehlung.
    Wird aufgerufen wenn User einen Mandanten öffnet oder
    der Agent eine tiefere Analyse braucht.
    """
    risiko     = _berechne_risiko_daten(name, m, ds)
    umsatz_s   = _umsatz_score(_safe(m, "umsatz", default=0))

    # OpenAI-Analyse versuchen
    ai_result  = await analysiere_mandant_ai(name, m, risiko)

    if ai_result:
        empfehlung = ai_result.get("empfehlung", _fallback_empfehlung(name, m, risiko))
        status     = ai_result.get("status", risiko["status"])
        risiko_score = ai_result.get("risiko_score", risiko["risiko_prozent"])
        ai_begruendung = ai_result.get("begruendung", "")
    else:
        empfehlung    = _fallback_empfehlung(name, m, risiko)
        status        = risiko["status"]
        risiko_score  = risiko["risiko_prozent"]
        ai_begruendung = "Regel-basierte Analyse (OpenAI nicht verfügbar)"

    return {
        "mandant":          name,
        "risiko_score":     risiko_score,
        "status":           status,
        "empfehlung":       empfehlung,
        "ai_begruendung":   ai_begruendung,
        "ai_genutzt":       ai_result is not None,
        "umsatz_kategorie": umsatz_s["kategorie"],
        "ist_vip":          umsatz_s["ist_vip"],
        "metriken":         risiko,
    }


# ═══════════════════════════════════════════════════════════
# KOMPATIBILITÄT MIT BESTEHENDEM CODE
# ═══════════════════════════════════════════════════════════

def berechne_mandant_score(name: str, m: Dict, ds) -> Dict:
    risiko = _berechne_risiko_daten(name, m, ds)
    return {
        "score":                risiko["raw_score"],
        "status":               risiko["status"],
        "score_details":        risiko["score_items"],
        "umsatz":               float(_safe(m, "umsatz", default=0)),
        "tage_ohne_antwort":    risiko["tage_ohne_antwort"],
        "aufgaben_offen":       risiko["aufgaben_offen"],
        "aufgaben_ueberfaellig":risiko["aufgaben_ueberfaellig"],
        "fehlende_dokumente":   risiko["fehlende_dokumente"],
    }


def berechne_steuerfristen(mandant: str = None) -> List[Dict]:
    jahr  = datetime.now().year
    monat = datetime.now().month
    fristen = []
    for m in range(monat, min(monat + 3, 13)):
        naechster = m + 1 if m < 12 else 1
        nj = jahr if m < 12 else jahr + 1
        try:
            f = datetime(nj, naechster, 10)
            fristen.append({"typ":"UStVA","beschreibung":f"USt-Voranmeldung {m:02d}/{jahr}",
                            "faellig":f.strftime("%Y-%m-%d"),
                            "tage_verbleibend":(f-datetime.now()).days,"mandant":mandant or "alle"})
        except Exception:
            pass
    for typ, mo, tag, titel in [("ESt",7,31,f"Einkommensteuer {jahr-1}"),
                                  ("GewSt",7,31,f"Gewerbesteuer {jahr-1}")]:
        try:
            f = datetime(jahr, mo, tag)
            fristen.append({"typ":typ,"beschreibung":titel,"faellig":f.strftime("%Y-%m-%d"),
                            "tage_verbleibend":(f-datetime.now()).days,"mandant":mandant or "alle"})
        except Exception:
            pass
    return sorted(fristen, key=lambda x: x["faellig"])


def pruefe_mandant_plausibilitaet(name: str, m: Dict) -> List[str]:
    w = []
    if not isinstance(m, dict): return ["Ungültige Daten"]
    if not _safe(m,"email"):    w.append("Keine E-Mail hinterlegt")
    if float(_safe(m,"umsatz",default=0)) <= 0: w.append("Kein Umsatz hinterlegt")
    if not _safe(m,"branche"):  w.append("Keine Branche hinterlegt")
    return w


def pruefe_aufgabe_plausibilitaet(a: Dict) -> List[str]:
    w = []
    if not isinstance(a, dict): return ["Ungültige Daten"]
    if not _safe(a,"beschreibung"): w.append("Keine Beschreibung")
    try:
        frist = _safe(a,"frist",default="")
        if frist: datetime.strptime(frist, "%Y-%m-%d")
    except ValueError:
        w.append(f"Ungültiges Datum: {_safe(a,'frist')}")
    return w

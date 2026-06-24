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
        "m365": _m365_heute_snapshot(store),
        "m365_mail": _m365_mail_snapshot(store),
    }


def _m365_mail_snapshot(store) -> Dict[str, Any]:
    try:
        from core.m365_integration import m365_mail_heute_block

        return m365_mail_heute_block(store)
    except Exception:
        return {"aktiv": False, "verbunden": False}


def _m365_heute_snapshot(store) -> Dict[str, Any]:
    try:
        from core.m365_integration import m365_heute_block

        return m365_heute_block(store)
    except Exception:
        return {"aktiv": False, "verbunden": False}


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


def _heute_iso() -> str:
    return datetime.now().date().isoformat()


def _events_in_range(store, von_datum: str, bis_datum: str, metric_prefix: str = "") -> int:
    from core.usage_events import count_events_in_range

    return count_events_in_range(store, von_datum, bis_datum, metric_prefix)


def _workflow_aktionen_heute(store) -> int:
    """Workflow-Aktionen nur vom heutigen Lauf (nicht Lifetime)."""
    heute = _heute_iso()
    return _events_in_range(store, heute, heute, "workflow")


def _events_heute(store, metric_prefix: str = "") -> int:
    return _events_in_range(store, _heute_iso(), _heute_iso(), metric_prefix)


def autopilot_stats(store) -> Dict[str, Any]:
    """Autopilot-Center: automatisch erledigte Arbeit (heute / Woche)."""
    from core.workflow_builder import WorkflowBaukasten

    jetzt = datetime.now()
    heute = jetzt.date()

    try:
        from core.daten_speicher import email_outbox_recent

        mails = email_outbox_recent(store.kanzlei_id, limit=200)
        mails_heute = sum(
            1 for r in mails
            if str(r.get("sent_at") or r.get("updated_at") or "")[:10] == heute.isoformat()
            and r.get("status") == "sent"
        )
    except Exception:
        mails_heute = 0

    uploads_heute = 0
    try:
        for row in store.portal_liste("upload"):
            ts = str(row.get("hochgeladen_am") or "")[:10]
            if ts == heute.isoformat():
                uploads_heute += 1
    except Exception:
        pass

    wb = WorkflowBaukasten(store)
    wf = wb.statistiken()
    ausfuehrungen = int(wf.get("ausfuehrungen") or 0)
    aktionen = int(wf.get("aktionen_gesamt") or 0)

    try:
        from core.proaktiver_bot import ProaktiverBot

        bot = ProaktiverBot(store).statistiken()
        bot_fragen = int(bot.get("fragen_gestellt_heute") or bot.get("fragen_gesamt") or 0)
    except Exception:
        bot_fragen = 0

    erinnerungen_heute = mails_heute + bot_fragen
    docs_eingesammelt = uploads_heute
    eskalationen = _events_heute(store, "eskalation")
    auto_aufgaben = _events_heute(store, "auto_")
    wf_aktionen_heute = _workflow_aktionen_heute(store)

    from core.tenant_settings import tenant_float

    min_pro_aktion = 8.0
    min_pro_doc = 12.0
    min_pro_wf = 3.0
    stundensatz = tenant_float(store, "stundensatz", 150.0)

    geschaetzte_minuten = (
        erinnerungen_heute * min_pro_aktion
        + docs_eingesammelt * min_pro_doc
        + wf_aktionen_heute * min_pro_wf
    )
    stunden_gespart = round(geschaetzte_minuten / 60.0, 1)
    euro_gespart = round(stunden_gespart * stundensatz, 2)

    return {
        "referenz_datum": heute.isoformat(),
        "heute": {
            "erinnerungen_gesendet": erinnerungen_heute,
            "dokumente_eingesammelt": docs_eingesammelt,
            "eskalationen": eskalationen,
            "automationen_ausgefuehrt": ausfuehrungen,
            "aktionen_gesamt": wf_aktionen_heute,
            "emails_versendet": mails_heute,
            "geschaetzte_stunden_gespart": stunden_gespart,
            "geschaetzte_euro_gespart": euro_gespart,
        },
        "woche": {
            "automationen_ausgefuehrt": _events_in_range(
                store,
                (jetzt.date() - __import__("datetime").timedelta(days=6)).isoformat(),
                heute.isoformat(),
                "workflow",
            ),
            "aktionen_gesamt": _events_in_range(
                store,
                (jetzt.date() - __import__("datetime").timedelta(days=6)).isoformat(),
                heute.isoformat(),
                "workflow",
            ),
        },
        "headline": (
            f"Heute: {erinnerungen_heute} Erinnerungen, "
            f"{docs_eingesammelt} Dokumente eingesammelt"
        ),
        "roi_hinweis": (
            f"Geschätzt {stunden_gespart} Std. ({euro_gespart:.0f} €) Arbeit heute "
            "durch Automationen unterstützt (8/12/3 Min. pro Aktion, Stundensatz aus Einstellungen)."
        ),
    }


def roi_monatsbericht(store) -> Dict[str, Any]:
    """ROI-Center — monatliche Zusammenfassung (Events im laufenden Monat)."""
    jetzt = datetime.now()
    monat_start = jetzt.replace(day=1).date().isoformat()
    heute = jetzt.date().isoformat()

    erinnerungen = _events_in_range(store, monat_start, heute, "email")
    erinnerungen += _events_in_range(store, monat_start, heute, "bot")
    dokumente = _events_in_range(store, monat_start, heute, "upload")
    if dokumente == 0:
        try:
            for row in store.portal_liste("upload"):
                ts = str(row.get("hochgeladen_am") or "")[:10]
                if monat_start <= ts <= heute:
                    dokumente += 1
        except Exception:
            pass
    automationen = _events_in_range(store, monat_start, heute, "workflow")
    eskalationen = _events_in_range(store, monat_start, heute, "eskalation")

    from core.tenant_settings import tenant_float

    stundensatz = tenant_float(store, "stundensatz", 150.0)
    geschaetzte_minuten = (
        erinnerungen * 8 + dokumente * 12 + automationen * 3 + eskalationen * 5
    )
    stunden = round(geschaetzte_minuten / 60.0, 1)
    euro = round(stunden * stundensatz, 2)

    return {
        "monat": jetzt.strftime("%Y-%m"),
        "erinnerungen": erinnerungen,
        "dokumente_eingesammelt": dokumente,
        "automationen": automationen,
        "eskalationen": eskalationen,
        "geschaetzte_stunden_gespart": stunden,
        "geschaetzte_euro_gespart": euro,
        "text": (
            f"Monat {jetzt.strftime('%m/%Y')} (Stand {heute}): ca. {stunden} Stunden "
            f"({euro:.0f} €) durch Automationen unterstützt."
        ),
        "hinweis": "Schätzung aus Monats-Events; Stundensatz aus Einstellungen.",
    }


def blockierungszentrum(store, limit: int = 30) -> Dict[str, Any]:
    from core.mandant_health import blockierungs_eintraege, top_nervfaktoren

    eintraege = blockierungs_eintraege(store, limit=limit)
    nerv = top_nervfaktoren(store, top_n=5)
    return {
        "eintraege": eintraege,
        "anzahl": len(eintraege),
        "nervfaktoren": nerv,
        "headline": nerv.get("headline") or "Keine Blockierungen.",
        "timestamp": datetime.now().isoformat(),
    }

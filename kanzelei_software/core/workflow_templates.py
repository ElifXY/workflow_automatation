# Vorinstallierte Automations-Vorlagen (Marktplatz)
from __future__ import annotations

from typing import Any, Dict, List

MARKETPLACE_TEMPLATES: List[Dict[str, Any]] = [
    {
        "id": "fehlende_unterlagen",
        "name": "Fehlende Unterlagen",
        "beschreibung": "Erinnert Mandanten automatisch an fehlende Belege und Dokumente.",
        "kategorie": "dokumente",
        "icon": "📄",
        "regel": {
            "name": "Fehlende Unterlagen — Nachfassen",
            "beschreibung": "Bot-Frage wenn Dokumente fehlen und keine Antwort seit 5 Tagen",
        "trigger": {"typ": "keine_antwort_tage", "parameter": 5},
            "bedingungen": [{"feld": "fehlende_dokumente_anzahl", "operator": ">", "wert": 0}],
            "aktionen": [
                {"typ": "bot_frage_stellen", "parameter": {
                    "frage_text": "Für Ihre steuerliche Bearbeitung fehlen noch Unterlagen. Bitte laden Sie diese im Portal hoch.",
                    "frage_typ": "dokument_anfrage",
                }},
                {"typ": "email_senden", "parameter": {"vorlage": "fehlende_dokumente"}},
            ],
        },
    },
    {
        "id": "jahresabschluss",
        "name": "Jahresabschluss",
        "beschreibung": "Checkliste und Erinnerungen für Jahresabschluss-Unterlagen.",
        "kategorie": "fristen",
        "icon": "📊",
        "regel": {
            "name": "Jahresabschluss — Unterlagen anfordern",
            "beschreibung": "Monatlich prüfen ob JA-Unterlagen vollständig",
            "trigger": {"typ": "monatlich", "parameter": 15},
            "bedingungen": [],
            "aktionen": [
                {"typ": "aufgabe_anlegen", "parameter": {
                    "beschreibung": "Jahresabschluss-Unterlagen prüfen",
                    "frist_tage": 14,
                    "prioritaet": "hoch",
                }},
            ],
        },
    },
    {
        "id": "lohn_monatlich",
        "name": "Lohnabrechnung",
        "beschreibung": "Monatliche Lohn-Unterlagen und Fristen.",
        "kategorie": "lohn",
        "icon": "💼",
        "regel": {
            "name": "Lohn — monatliche Erinnerung",
            "beschreibung": "Am 20. jeden Monats Lohnunterlagen anfordern",
            "trigger": {"typ": "monatlich", "parameter": 20},
            "bedingungen": [],
            "aktionen": [
                {"typ": "bot_frage_stellen", "parameter": {
                    "frage_text": "Bitte reichen Sie die Lohnunterlagen für den laufenden Monat ein.",
                    "frage_typ": "dokument_anfrage",
                }},
            ],
        },
    },
    {
        "id": "einkommensteuer",
        "name": "Einkommensteuer",
        "beschreibung": "EST-Unterlagen und Fristen-Nachverfolgung.",
        "kategorie": "steuer",
        "icon": "📋",
        "regel": {
            "name": "Einkommensteuer — fehlende Belege",
            "beschreibung": "Nachfassen bei fehlenden EST-Unterlagen",
            "trigger": {"typ": "keine_antwort_tage", "parameter": 7},
            "bedingungen": [{"feld": "fehlende_dokumente_anzahl", "operator": ">", "wert": 0}],
            "aktionen": [
                {"typ": "email_senden", "parameter": {"vorlage": "fehlende_dokumente"}},
            ],
        },
    },
    {
        "id": "kein_kontakt_7",
        "name": "Kein Kontakt 7 Tage",
        "beschreibung": "Bot-Frage wenn Mandant 7 Tage nicht antwortet.",
        "kategorie": "kommunikation",
        "icon": "📞",
        "regel": {
            "name": "Kein Kontakt seit 7 Tagen",
            "beschreibung": "Automatische Nachfrage",
            "trigger": {"typ": "keine_antwort_tage", "parameter": 7},
            "bedingungen": [],
            "aktionen": [
                {"typ": "bot_frage_stellen", "parameter": {
                    "frage_text": "Wir haben einige Zeit nichts von Ihnen gehört. Gibt es offene Fragen?",
                    "frage_typ": "sonstiges",
                }},
            ],
        },
    },
    {
        "id": "m365_frist_abgleich",
        "name": "M365 Termin-Abgleich",
        "beschreibung": "Prüft Outlook-Kalender und legt interne Aufgabe bei anstehenden Terminen an.",
        "kategorie": "integration",
        "icon": "📅",
        "regel": {
            "name": "M365 — Kalender & Mandanten-Fristen",
            "beschreibung": "Monatlich Kalender gegen offene Mandanten-Fälle abgleichen",
            "trigger": {"typ": "monatlich", "parameter": 1},
            "bedingungen": [{"feld": "fehlende_dokumente_anzahl", "operator": ">", "wert": 0}],
            "aktionen": [
                {"typ": "m365_kalender_pruefen", "parameter": {
                    "text": "Outlook-Termine mit offenen Mandanten-Unterlagen abgleichen",
                    "aufgabe_bei_termine": True,
                    "frist_tage": 1,
                    "prioritaet": "hoch",
                }},
            ],
        },
    },
    {
        "id": "m365_postfach_abgleich",
        "name": "M365 Postfach-Abgleich",
        "beschreibung": "Liest eingehende Mails und ordnet sie Mandanten zu (read-only Pilot).",
        "kategorie": "integration",
        "icon": "📧",
        "regel": {
            "name": "M365 — Postfach & Mandanten",
            "beschreibung": "Täglich Posteingang auf Mandanten-Mails prüfen",
            "trigger": {"typ": "taeglich", "parameter": "08:00"},
            "bedingungen": [],
            "aktionen": [
                {"typ": "m365_postfach_pruefen", "parameter": {
                    "text": "Eingehende Mails mit Mandanten-Stammdaten abgleichen",
                    "aufgabe_bei_mail": True,
                    "timeline_sync": True,
                    "limit": 10,
                    "frist_tage": 1,
                    "prioritaet": "normal",
                }},
            ],
        },
    },
    {
        "id": "m365_timeline_taeglich",
        "name": "M365 Timeline-Import",
        "beschreibung": "Importiert neue Outlook-Mails täglich in die Mandanten-Kommunikation.",
        "kategorie": "integration",
        "icon": "🗂️",
        "regel": {
            "name": "M365 — Timeline-Import (täglich)",
            "beschreibung": "Neue M365-Mails in die Kommunikations-Timeline übernehmen",
            "trigger": {"typ": "taeglich", "parameter": "07:30"},
            "bedingungen": [],
            "aktionen": [
                {"typ": "m365_timeline_import", "parameter": {"limit": 10}},
            ],
        },
    },
]


def liste_vorlagen() -> List[Dict[str, Any]]:
    return [
        {k: v for k, v in t.items() if k != "regel"}
        for t in MARKETPLACE_TEMPLATES
    ]


def vorlage_by_id(template_id: str) -> Dict[str, Any] | None:
    tid = (template_id or "").strip().lower()
    for t in MARKETPLACE_TEMPLATES:
        if t["id"] == tid:
            return t
    return None


def zaehle_betroffene_mandanten(store, regel_def: Dict[str, Any]) -> int:
    """Vorschau: wie viele Mandanten würde diese Regel betreffen (heuristisch)."""
    from core.workflow_builder import WorkflowBaukasten

    wb = WorkflowBaukasten(store)
    mandanten = store.hole_mandanten() or {}
    trigger = regel_def.get("trigger") or {}
    bedingungen = regel_def.get("bedingungen") or []
    n = 0
    for name, m in mandanten.items():
        if not name:
            continue
        try:
            if not wb._prüfe_trigger(trigger, name, m):
                continue
            if bedingungen and not wb._prüfe_bedingungen(bedingungen, name, m):
                continue
            n += 1
        except Exception:
            pass
    return n


def aktiviere_vorlage(store, template_id: str) -> Dict[str, Any]:
    tpl = vorlage_by_id(template_id)
    if not tpl:
        raise ValueError(f"Unbekannte Vorlage: {template_id}")
    from core.workflow_builder import WorkflowBaukasten

    wb = WorkflowBaukasten(store)
    r = tpl["regel"]
    created = wb.regel_erstellen(
        name=r["name"],
        beschreibung=r.get("beschreibung", ""),
        trigger=r["trigger"],
        bedingungen=r.get("bedingungen") or [],
        aktionen=r.get("aktionen") or [],
    )
    wb.regel_aktivieren(created["id"], True)
    store.log_eintrag(f"VORLAGE_AKTIVIERT | {template_id} | {created.get('id', '')[:8]}")
    return {"status": "ok", "vorlage": template_id, "regel": created}

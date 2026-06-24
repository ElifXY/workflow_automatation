# Audit-Trail für Automationen (Workflow, Eskalation, Scheduler, Bot)
from __future__ import annotations

from typing import Any, Dict, List

AUTOMATION_KEYWORDS = (
    "WORKFLOW",
    "ESKALATION",
    "SCHEDULER_",
    "VORLAGE",
    "BOT_MAIL",
    "BOT_ANALYSE",
    "ENGINE",
    "EMAIL_ENQUEUED",
    "EMAIL_GESENDET",
    "EMAIL_MANUELL",
    "DOKUMENT_ANGEFORDERT",
    "ONBOARDING",
)


def _ist_automation_log(aktion: str, details: str) -> bool:
    blob = f"{aktion} {details}".upper()
    return any(k in blob for k in AUTOMATION_KEYWORDS)


def automation_audit(store, limit: int = 50) -> Dict[str, Any]:
    """Letzte Automation-relevante Log-Einträge für die UI."""
    raw = store.hole_logs(limit=max(limit * 4, 200)) or []
    eintraege: List[Dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        aktion = str(row.get("aktion") or "")
        details = str(row.get("details") or "")
        if not _ist_automation_log(aktion, details):
            continue
        text = aktion if not details else f"{aktion} | {details}"
        eintraege.append({
            "zeit": row.get("zeitpunkt") or row.get("zeit"),
            "text": text.strip(" |"),
            "benutzer": row.get("benutzer") or "system",
            "kategorie": _kategorie_aus_text(text),
        })
    eintraege.sort(key=lambda x: str(x.get("zeit") or ""), reverse=True)
    eintraege = eintraege[:limit]
    return {
        "eintraege": eintraege,
        "anzahl": len(eintraege),
        "timestamp": __import__("datetime").datetime.now().isoformat(),
    }


def _kategorie_aus_text(text: str) -> str:
    u = text.upper()
    if "ESKALATION" in u:
        return "eskalation"
    if "VORLAGE" in u or "WORKFLOW" in u:
        return "workflow"
    if "EMAIL" in u or "BOT_MAIL" in u:
        return "email"
    if "SCHEDULER" in u or "ENGINE" in u:
        return "scheduler"
    if "BOT" in u:
        return "bot"
    return "automation"

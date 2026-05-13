"""
Append-only Audit-Log fuer sicherheitsrelevante Ereignisse.

Persistenz:
- Wir nutzen die bestehende ``DatenSpeicher.log_eintrag``-Pipeline (Postgres
  bevorzugt, sonst lokales Logfile pro Tenant). Die Pipeline ist append-only.
- Jeder Eintrag bekommt zusaetzlich ein strukturierts JSON-Objekt
  (``event``, ``status``, ``target``, ``actor`` …) als Suffix angehangen, damit
  Tooling spaeter zuverlaessig parsen kann.

Designziele:
- **Niemals Exceptions in den Aufrufer eskalieren lassen.** Audit darf den
  Geschaeftspfad nicht brechen.
- **Tenant-scoped**: jeder Eintrag traegt ``kanzlei_id``.
- **Kanonische Event-Namen** (``UPPER_SNAKE_CASE``). Beispiele:
  ``LOGIN_OK``, ``LOGIN_FAIL``, ``ROLE_CHANGE``, ``USER_CREATE``,
  ``USER_DEACTIVATE``, ``PERMISSION_DENIED``, ``SETTINGS_UPDATE``.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Mapping, Optional

log = logging.getLogger(__name__)


def _coerce_actor(actor: Any) -> Mapping[str, Any]:
    """Akzeptiert ``dict`` (current_user) oder freie Strings/None."""
    if isinstance(actor, Mapping):
        return actor
    if actor is None:
        return {}
    return {"benutzername": str(actor)}


def _tenant_id(actor: Mapping[str, Any], explicit: Optional[str]) -> str:
    if explicit:
        return str(explicit).strip() or "default"
    return (
        str(
            actor.get("tenant_id")
            or actor.get("kanzlei_id")
            or "default"
        ).strip()
        or "default"
    )


def audit_event(
    actor: Any,
    event: str,
    *,
    kanzlei_id: Optional[str] = None,
    status: str = "ok",
    target: Optional[str] = None,
    ip: Optional[str] = None,
    details: Optional[Mapping[str, Any]] = None,
) -> None:
    """
    Schreibt einen Audit-Eintrag. Niemals raisen.

    Beispiel::

        audit_event(current_user, "ROLE_CHANGE", target="user:42",
                    details={"old": "mitarbeiter", "new": "admin"})
    """
    actor_map = _coerce_actor(actor)
    kid = _tenant_id(actor_map, kanzlei_id)

    payload = {
        "event": (event or "UNKNOWN").strip().upper(),
        "status": (status or "ok").strip().lower(),
        "actor": str(
            actor_map.get("benutzername")
            or actor_map.get("email")
            or actor_map.get("user_id")
            or ""
        ),
        "actor_role": str(actor_map.get("role") or actor_map.get("rolle") or ""),
        "target": str(target) if target else "",
        "ip": str(ip) if ip else "",
    }
    if details:
        try:
            payload["details"] = dict(details)
        except Exception:
            payload["details"] = {"_raw": str(details)}

    try:
        from core.daten_speicher import DatenSpeicher

        ds = DatenSpeicher(kanzlei_id=kid)
        text = f"AUDIT | {payload['event']} | {json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
        try:
            ds.log_eintrag(text, benutzer=payload["actor"], ip=payload["ip"])
        except TypeError:
            # Aeltere Signatur ohne kwargs
            ds.log_eintrag(text)
    except Exception as exc:
        log.warning("audit_event sink failed: %s | payload=%s", exc, payload)


def permission_denied(
    actor: Any,
    permission: str,
    *,
    path: Optional[str] = None,
    method: Optional[str] = None,
    ip: Optional[str] = None,
) -> None:
    """Convenience-Wrapper fuer 403er."""
    audit_event(
        actor,
        "PERMISSION_DENIED",
        status="deny",
        target=permission,
        ip=ip,
        details={"path": path, "method": method},
    )

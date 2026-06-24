"""
Microsoft 365 / Outlook — Graph-Integrationsstatus (Pass 8).

Login via OAuth ist vorhanden; Kalender- und Postfach-Sync nutzen tenantweise gespeicherte Graph-Tokens.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

M365_TOKEN_KEY = "m365_graph_tokens"
M365_TIMELINE_SYNC_KEY = "m365_kommunikation_sync_ids"
M365_GRAPH_SCOPES = "openid offline_access Calendars.Read Mail.Read"


def _now_iso() -> str:
    return datetime.now().isoformat()


def load_m365_tokens(store) -> Dict[str, Any]:
    if store is None:
        return {}
    try:
        raw = store.setting_holen(M365_TOKEN_KEY, {})
        if isinstance(raw, str):
            raw = json.loads(raw) if raw.strip() else {}
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def save_m365_tokens(store, token_data: Dict[str, Any], *, email: str = "") -> None:
    if store is None:
        return
    expires_in = int(token_data.get("expires_in") or 3600)
    payload = {
        "access_token": str(token_data.get("access_token") or ""),
        "refresh_token": str(token_data.get("refresh_token") or ""),
        "token_type": str(token_data.get("token_type") or "Bearer"),
        "scope": str(token_data.get("scope") or M365_GRAPH_SCOPES),
        "expires_at": (datetime.now() + timedelta(seconds=max(60, expires_in - 60))).isoformat(),
        "connected_at": _now_iso(),
        "connected_email": (email or "").strip().lower(),
    }
    store.setting_setzen(M365_TOKEN_KEY, payload)
    store.log_eintrag("M365_GRAPH_VERBUNDEN")


def clear_m365_tokens(store) -> None:
    if store is None:
        return
    store.setting_setzen(M365_TOKEN_KEY, {})
    store.log_eintrag("M365_GRAPH_GETRENNT")


def graph_connected(store) -> bool:
    tok = load_m365_tokens(store)
    return bool(str(tok.get("access_token") or "").strip() or str(tok.get("refresh_token") or "").strip())


def _oauth_env(key: str) -> str:
    return (os.getenv(f"OAUTH_MICROSOFT_{key}") or "").strip()


def _oauth_redirect_uri() -> str:
    explicit = _oauth_env("REDIRECT_URI")
    if explicit:
        return explicit
    base = (os.getenv("PUBLIC_APP_URL") or os.getenv("PORTAL_BASE_URL") or "").strip().rstrip("/")
    if not base:
        base = "https://kanzlei-automation.com"
    return f"{base}/api/auth/oauth/microsoft/callback"


def build_m365_connect_auth_url(state: str, nonce: str) -> Optional[str]:
    client_id = _oauth_env("CLIENT_ID")
    if not client_id:
        return None
    params = {
        "client_id": client_id,
        "redirect_uri": _oauth_redirect_uri(),
        "response_type": "code",
        "scope": M365_GRAPH_SCOPES,
        "state": state,
        "nonce": nonce,
        "prompt": "consent",
    }
    return f"https://login.microsoftonline.com/common/oauth2/v2.0/authorize?{urlencode(params)}"


def _http_form_post(url: str, data: Dict[str, str]) -> Dict[str, Any]:
    body = urlencode(data).encode("utf-8")
    req = Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else {}


def _http_get_json(url: str, access_token: str) -> Dict[str, Any]:
    req = Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {access_token}")
    req.add_header("Accept", "application/json")
    with urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else {}


def refresh_m365_access_token(store) -> str:
    tok = load_m365_tokens(store)
    access = str(tok.get("access_token") or "").strip()
    expires_at = str(tok.get("expires_at") or "")
    if access and expires_at:
        try:
            if datetime.now() < datetime.fromisoformat(expires_at):
                return access
        except Exception:
            pass

    refresh = str(tok.get("refresh_token") or "").strip()
    if not refresh:
        return access

    client_id = _oauth_env("CLIENT_ID")
    client_secret = _oauth_env("CLIENT_SECRET")
    if not client_id or not client_secret:
        return access

    try:
        token_data = _http_form_post(
            "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            {
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh,
                "scope": M365_GRAPH_SCOPES,
            },
        )
    except (HTTPError, URLError, json.JSONDecodeError, TimeoutError):
        return access

    if not token_data.get("access_token"):
        return access

    email = str(tok.get("connected_email") or "")
    save_m365_tokens(store, token_data, email=email)
    return str(token_data.get("access_token") or "")


def fetch_calendar_preview(store, *, limit: int = 5) -> Dict[str, Any]:
    if not graph_connected(store):
        return {
            "connected": False,
            "events": [],
            "hinweis": "Microsoft 365 ist noch nicht verbunden.",
        }

    access = refresh_m365_access_token(store)
    if not access:
        return {
            "connected": False,
            "events": [],
            "hinweis": "Graph-Zugriff abgelaufen — bitte erneut verbinden.",
        }

    start = datetime.now().strftime("%Y-%m-%dT00:00:00Z")
    end = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%dT23:59:59Z")
    url = (
        "https://graph.microsoft.com/v1.0/me/calendarview"
        f"?startDateTime={start}&endDateTime={end}"
        f"&$top={max(1, min(limit, 20))}&$orderby=start/dateTime"
        "&$select=subject,start,end,location,isAllDay"
    )
    try:
        data = _http_get_json(url, access)
    except HTTPError as exc:
        return {
            "connected": True,
            "events": [],
            "hinweis": f"Graph-Kalender nicht lesbar (HTTP {exc.code}).",
        }
    except (URLError, json.JSONDecodeError, TimeoutError):
        return {
            "connected": True,
            "events": [],
            "hinweis": "Graph-Kalender vorübergehend nicht erreichbar.",
        }

    events: List[Dict[str, Any]] = []
    for item in data.get("value") or []:
        if not isinstance(item, dict):
            continue
        start_obj = item.get("start") if isinstance(item.get("start"), dict) else {}
        events.append(
            {
                "subject": str(item.get("subject") or "(Ohne Titel)"),
                "start": str(start_obj.get("dateTime") or start_obj.get("date") or ""),
                "end": str((item.get("end") or {}).get("dateTime") or ""),
                "location": str((item.get("location") or {}).get("displayName") or ""),
                "all_day": bool(item.get("isAllDay")),
            }
        )

    tok = load_m365_tokens(store)
    return {
        "connected": True,
        "connected_email": str(tok.get("connected_email") or ""),
        "connected_at": str(tok.get("connected_at") or ""),
        "events": events,
        "hinweis": f"{len(events)} Termin(e) in den nächsten 14 Tagen (Pilot-Vorschau).",
    }


def _parse_event_date(start_raw: str):
    raw = (start_raw or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        return datetime.fromisoformat(raw[:19]).date()
    except Exception:
        return None


def m365_heute_block(store) -> Dict[str, Any]:
    """Kalender-Snapshot für Dashboard — nur wenn Graph verbunden und Sync aktiv."""
    if store is None:
        return {"aktiv": False, "verbunden": False}
    try:
        kalender_aktiv = bool(store.setting_holen("m365_kalender_sync_aktiv"))
    except Exception:
        kalender_aktiv = False
    if not graph_connected(store):
        return {"aktiv": False, "verbunden": False, "sync_aktiv": kalender_aktiv}
    if not kalender_aktiv:
        return {"aktiv": False, "verbunden": True, "sync_aktiv": False}

    preview = fetch_calendar_preview(store, limit=12)
    events = preview.get("events") or []
    heute = datetime.now().date()
    heute_events: List[Dict[str, Any]] = []
    for ev in events:
        d = _parse_event_date(str(ev.get("start") or ""))
        if d == heute:
            heute_events.append(ev)

    return {
        "aktiv": True,
        "verbunden": True,
        "sync_aktiv": True,
        "termine_heute": len(heute_events),
        "termine_14t": len(events),
        "preview_heute": heute_events[:5],
        "connected_email": preview.get("connected_email") or "",
        "hinweis": preview.get("hinweis") or "",
    }


def run_m365_kalender_workflow_action(store, mandant: str, params: Dict[str, Any]) -> str:
    """Workflow-Aktion: Kalender prüfen und internen Hinweis erzeugen."""
    if not graph_connected(store):
        return "M365 nicht verbunden — übersprungen"
    try:
        if not store.setting_holen("m365_kalender_sync_aktiv"):
            return "Kalender-Sync deaktiviert — übersprungen"
    except Exception:
        return "Kalender-Sync nicht lesbar"

    preview = fetch_calendar_preview(store, limit=10)
    events = preview.get("events") or []
    n = len(events)
    text = str(params.get("text") or "").strip()
    if not text:
        text = f"M365-Kalender: {n} Termin(e) in 14 Tagen — Abgleich mit Mandant {mandant}"
    store.log_eintrag(f"WORKFLOW_M365 | {mandant} | {text[:120]}")

    if params.get("aufgabe_bei_termine") and n:
        from datetime import timedelta
        import uuid

        aufgabe_id = str(uuid.uuid4())
        store.aufgabe_speichern(
            aufgabe_id,
            {
                "id": aufgabe_id,
                "mandant": mandant,
                "beschreibung": text[:500],
                "frist": (datetime.now() + timedelta(days=int(params.get("frist_tage") or 2))).strftime("%Y-%m-%d"),
                "prioritaet": str(params.get("prioritaet") or "normal"),
                "kategorie": "m365_kalender",
                "erledigt": False,
                "erstellt_am": datetime.now().isoformat(),
                "workflow": "m365_kalender_pruefen",
            },
        )
    return text


def _sender_email(msg: Dict[str, Any]) -> str:
    frm = msg.get("from") or {}
    if isinstance(frm, dict):
        ea = frm.get("emailAddress") or {}
        if isinstance(ea, dict):
            return str(ea.get("address") or "").strip().lower()
    return ""


def _build_mandant_email_index(store) -> Dict[str, str]:
    index: Dict[str, str] = {}
    try:
        mandanten = store.hole_mandanten() or {}
    except Exception:
        return index
    for name, m in mandanten.items():
        if not name or not isinstance(m, dict):
            continue
        em = str(m.get("email") or "").strip().lower()
        if em and "@" in em:
            index[em] = str(name)
    return index


def fetch_mail_preview(store, *, limit: int = 10) -> Dict[str, Any]:
    if not graph_connected(store):
        return {"connected": False, "messages": [], "hinweis": "Microsoft 365 ist noch nicht verbunden."}
    try:
        if not store.setting_holen("m365_postfach_readonly_aktiv"):
            return {
                "connected": True,
                "sync_aktiv": False,
                "messages": [],
                "hinweis": "Postfach-Sync ist deaktiviert — unter Integrationen aktivieren.",
            }
    except Exception:
        pass

    access = refresh_m365_access_token(store)
    if not access:
        return {
            "connected": False,
            "messages": [],
            "hinweis": "Graph-Zugriff abgelaufen — bitte erneut verbinden.",
        }

    top = max(1, min(limit, 25))
    url = (
        "https://graph.microsoft.com/v1.0/me/messages"
        f"?$top={top}&$orderby=receivedDateTime desc"
        "&$select=subject,from,receivedDateTime,isRead,bodyPreview"
    )
    try:
        data = _http_get_json(url, access)
    except HTTPError as exc:
        return {
            "connected": True,
            "messages": [],
            "hinweis": f"Graph-Postfach nicht lesbar (HTTP {exc.code}).",
        }
    except (URLError, json.JSONDecodeError, TimeoutError):
        return {
            "connected": True,
            "messages": [],
            "hinweis": "Graph-Postfach vorübergehend nicht erreichbar.",
        }

    email_index = _build_mandant_email_index(store)
    messages: List[Dict[str, Any]] = []
    matched = 0
    for item in data.get("value") or []:
        if not isinstance(item, dict):
            continue
        sender = _sender_email(item)
        mandant = email_index.get(sender, "")
        if mandant:
            matched += 1
        messages.append(
            {
                "subject": str(item.get("subject") or "(Ohne Betreff)"),
                "from": sender,
                "received": str(item.get("receivedDateTime") or ""),
                "is_read": bool(item.get("isRead")),
                "preview": str(item.get("bodyPreview") or "")[:160],
                "mandant_vorschlag": mandant,
            }
        )

    return {
        "connected": True,
        "sync_aktiv": True,
        "messages": messages,
        "mandanten_treffer": matched,
        "hinweis": (
            f"{len(messages)} E-Mail(s), {matched} Mandanten-Zuordnung(en) — read-only Pilot."
            if messages
            else "Postfach leer oder keine Berechtigung."
        ),
    }


def m365_mail_heute_block(store) -> Dict[str, Any]:
    if store is None:
        return {"aktiv": False, "verbunden": False}
    if not graph_connected(store):
        return {"aktiv": False, "verbunden": False}
    try:
        mail_aktiv = bool(store.setting_holen("m365_postfach_readonly_aktiv"))
    except Exception:
        mail_aktiv = False
    if not mail_aktiv:
        return {"aktiv": False, "verbunden": True, "sync_aktiv": False}

    preview = fetch_mail_preview(store, limit=8)
    unread = sum(1 for m in preview.get("messages") or [] if not m.get("is_read"))
    matched = int(preview.get("mandanten_treffer") or 0)
    return {
        "aktiv": True,
        "verbunden": True,
        "sync_aktiv": True,
        "ungelesen": unread,
        "mandanten_treffer": matched,
        "preview": (preview.get("messages") or [])[:5],
        "hinweis": preview.get("hinweis") or "",
    }


def run_m365_postfach_workflow_action(store, mandant: str, params: Dict[str, Any]) -> str:
    if not graph_connected(store):
        return "M365 nicht verbunden — übersprungen"
    try:
        if not store.setting_holen("m365_postfach_readonly_aktiv"):
            return "Postfach-Sync deaktiviert — übersprungen"
    except Exception:
        return "Postfach-Sync nicht lesbar"

    preview = fetch_mail_preview(store, limit=15)
    messages = preview.get("messages") or []
    mandant_email = ""
    try:
        mm = store.hole_mandant(mandant) or {}
        mandant_email = str(mm.get("email") or "").strip().lower()
    except Exception:
        pass

    hits = [m for m in messages if m.get("mandant_vorschlag") == mandant]
    if mandant_email and not hits:
        hits = [m for m in messages if m.get("from") == mandant_email]

    n = len(hits)
    text = str(params.get("text") or "").strip()
    if not text:
        text = f"M365-Postfach: {n} relevante Mail(s) für Mandant {mandant}"
    store.log_eintrag(f"WORKFLOW_M365_MAIL | {mandant} | {text[:120]}")

    if params.get("aufgabe_bei_mail") and n:
        import uuid

        aufgabe_id = str(uuid.uuid4())
        store.aufgabe_speichern(
            aufgabe_id,
            {
                "id": aufgabe_id,
                "mandant": mandant,
                "beschreibung": text[:500],
                "frist": (datetime.now() + timedelta(days=int(params.get("frist_tage") or 1))).strftime("%Y-%m-%d"),
                "prioritaet": str(params.get("prioritaet") or "normal"),
                "kategorie": "m365_postfach",
                "erledigt": False,
                "erstellt_am": datetime.now().isoformat(),
                "workflow": "m365_postfach_pruefen",
            },
        )

    if params.get("timeline_sync"):
        sync = sync_m365_mails_to_timeline(
            store,
            mandant,
            limit=int(params.get("limit") or 10),
        )
        sync_hint = str(sync.get("hinweis") or "").strip()
        if sync_hint:
            text = f"{text} | Timeline: {sync_hint}" if text else sync_hint
    return text


def run_m365_timeline_workflow_action(store, mandant: str, params: Dict[str, Any]) -> str:
    """Workflow-Aktion: M365-Mails idempotent in die Mandanten-Timeline importieren."""
    limit = max(1, min(int(params.get("limit") or 10), 20))
    result = sync_m365_mails_to_timeline(store, mandant, limit=limit)
    imported = int(result.get("imported") or 0)
    hinweis = str(result.get("hinweis") or "").strip()
    store.log_eintrag(f"WORKFLOW_M365_TIMELINE | {mandant} | {imported} importiert")
    return hinweis or f"{imported} Mail(s) in Timeline importiert"


def fetch_mails_for_mandant(store, mandant_name: str, *, limit: int = 8) -> Dict[str, Any]:
    """Postfach-Mails gefiltert auf einen Mandanten (Pilot read-only)."""
    name = (mandant_name or "").strip()
    if not name:
        return {"connected": False, "messages": [], "hinweis": "Mandant fehlt"}

    mandant_email = ""
    try:
        mm = store.hole_mandant(name) or {}
        mandant_email = str(mm.get("email") or "").strip().lower()
    except Exception:
        pass

    preview = fetch_mail_preview(store, limit=max(limit, 15))
    if not preview.get("connected"):
        return {**preview, "mandant": name, "mandant_email": mandant_email, "count": 0}

    all_msgs = preview.get("messages") or []
    filtered = [msg for msg in all_msgs if msg.get("mandant_vorschlag") == name]
    if mandant_email:
        for msg in all_msgs:
            if msg.get("from") == mandant_email and msg not in filtered:
                filtered.append(msg)

    filtered = filtered[: max(1, min(limit, 20))]
    return {
        "connected": preview.get("connected", False),
        "sync_aktiv": preview.get("sync_aktiv", False),
        "mandant": name,
        "mandant_email": mandant_email,
        "messages": filtered,
        "count": len(filtered),
        "hinweis": (
            f"{len(filtered)} E-Mail(s) für {name} in der Vorschau."
            if filtered
            else "Keine passenden Mails im verbundenen Postfach (Pilot)."
        ),
    }


def _mail_timeline_key(mandant_name: str, msg: Dict[str, Any]) -> str:
    raw = "|".join([
        mandant_name,
        str(msg.get("from") or ""),
        str(msg.get("received") or ""),
        str(msg.get("subject") or ""),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _load_timeline_sync_ids(store) -> set:
    try:
        raw = store.setting_holen(M365_TIMELINE_SYNC_KEY, [])
        if isinstance(raw, str):
            raw = json.loads(raw) if raw.strip() else []
        if not isinstance(raw, list):
            return set()
        return {str(x) for x in raw if str(x).strip()}
    except Exception:
        return set()


def _save_timeline_sync_ids(store, ids: set) -> None:
    store.setting_setzen(M365_TIMELINE_SYNC_KEY, list(ids)[-2000:])


def sync_m365_mails_to_timeline(store, mandant_name: str, *, limit: int = 10) -> Dict[str, Any]:
    """Importiert M365-Mails idempotent in die Mandanten-Kommunikations-Timeline."""
    preview = fetch_mails_for_mandant(store, mandant_name, limit=limit)
    if not preview.get("connected"):
        return {"imported": 0, "skipped": 0, "hinweis": preview.get("hinweis") or "M365 nicht verbunden"}
    if preview.get("sync_aktiv") is False:
        return {"imported": 0, "skipped": 0, "hinweis": "Postfach-Sync deaktiviert"}

    synced = _load_timeline_sync_ids(store)
    imported = 0
    skipped = 0
    for msg in preview.get("messages") or []:
        key = _mail_timeline_key(mandant_name, msg)
        if key in synced:
            skipped += 1
            continue
        subject = str(msg.get("subject") or "(Ohne Betreff)")
        preview_txt = str(msg.get("preview") or "")[:220]
        text = f"📧 {subject}"
        if preview_txt:
            text = f"{text}\n{preview_txt}"
        ts = str(msg.get("received") or _now_iso())
        ok = store.kommunikation_hinzufuegen(
            mandant_name,
            {
                "typ": "m365_email",
                "text": text,
                "richtung": "eingehend",
                "timestamp": ts,
            },
        )
        if ok:
            synced.add(key)
            imported += 1

    if imported:
        _save_timeline_sync_ids(store, synced)
        store.log_eintrag(f"M365_TIMELINE | {mandant_name} | {imported} importiert")

    return {
        "imported": imported,
        "skipped": skipped,
        "mandant": mandant_name,
        "hinweis": (
            f"{imported} Mail(s) in Timeline übernommen, {skipped} bereits vorhanden."
            if imported or skipped
            else "Keine neuen Mails zum Import."
        ),
    }


def m365_status(store=None, user: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    oauth_id = _oauth_env("CLIENT_ID")
    oauth_secret = _oauth_env("CLIENT_SECRET")
    login_ready = bool(oauth_id and oauth_secret)

    kalender_aktiv = False
    mail_aktiv = False
    graph_tokens = {}
    if store is not None:
        try:
            kalender_aktiv = bool(store.setting_holen("m365_kalender_sync_aktiv"))
            mail_aktiv = bool(store.setting_holen("m365_postfach_readonly_aktiv"))
            graph_tokens = load_m365_tokens(store)
        except Exception:
            pass

    user_provider = ""
    if user:
        user_provider = str(user.get("oauth_provider") or user.get("auth_provider") or "").lower()

    connected = graph_connected(store)
    connected_email = str(graph_tokens.get("connected_email") or "")
    connected_at = str(graph_tokens.get("connected_at") or "")

    if connected:
        kalender_status = "verbunden" if kalender_aktiv else "verbunden_inaktiv"
        postfach_status = "verbunden" if mail_aktiv else "verbunden_inaktiv"
        naechster = "Kalender- und Postfach-Vorschau testen oder Sync in Workflows aktivieren"
    elif login_ready:
        kalender_status = "vorbereitet" if not kalender_aktiv else "wartet_auf_verbindung"
        postfach_status = "vorbereitet" if not mail_aktiv else "wartet_auf_verbindung"
        naechster = "Microsoft 365 verbinden (Graph: Calendars.Read, Mail.Read)"
    else:
        kalender_status = "vorbereitet"
        postfach_status = "vorbereitet"
        naechster = "OAUTH_MICROSOFT_CLIENT_ID und SECRET in .env setzen"

    return {
        "oauth_login_verfuegbar": login_ready,
        "microsoft_login_genutzt": user_provider == "microsoft",
        "graph_verbunden": connected,
        "graph_connected_email": connected_email,
        "graph_connected_at": connected_at,
        "kalender_sync_status": kalender_status,
        "postfach_status": postfach_status,
        "kalender_sync_aktiv": kalender_aktiv,
        "postfach_readonly_aktiv": mail_aktiv,
        "naechster_schritt": naechster,
        "hinweis": (
            "Microsoft Graph ist verbunden — Kalender-Vorschau und Sync-Pilot bereit."
            if connected
            else "Anmeldung mit Microsoft ist möglich. Für Kalender/E-Mail: tenantweise verbinden."
        ),
    }

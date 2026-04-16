# ============================================================
# KANZLEI AI — PRODUCTION API v3.0
# Fixes: Thread-safe DB, Rate-Limiting, Auth auf allen Endpoints,
#        Standardisierte Responses, Globales Error-Handling
# ============================================================

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, status, Depends, Header, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from datetime import datetime, timedelta
from pathlib import Path
import uuid
import asyncio
import os
import json
import logging
import time
import smtplib
import hmac
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import httpx
import secrets

from dotenv import load_dotenv

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.daten_speicher import (
    DatenSpeicher,
    email_outbox_enqueue,
    email_outbox_due,
    email_outbox_claim,
    email_outbox_mark_sent,
    email_outbox_mark_failed,
    email_outbox_recent,
    agent_action_record,
    agent_action_update,
    usage_get,
    usage_increment,
    api_key_create,
    api_key_verify,
    api_key_list,
    api_key_deactivate,
    api_key_rotate,
    webhook_endpoint_create,
    webhook_endpoint_list,
    webhook_endpoints_for_event,
    webhook_endpoint_delete,
    webhook_enqueue,
    webhook_due,
    webhook_mark_sent,
    webhook_mark_failed,
)
from core.rbac import has_permission
from core.decision_engine import analysiere_alle_mandanten, berechne_steuerfristen, berechne_mandant_score
from core.ai_email import generate_ai_email
from backend.services.mandanten_service import MandantenService
from backend.services.aufgaben_service import AufgabenService
from backend.services.settings_service import SettingsService

load_dotenv()

# ── Logging ──────────────────────────────────────────────────
os.makedirs("data", exist_ok=True)

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("data/api.log", encoding="utf-8"),
    ]
)
log = logging.getLogger("kanzlei_api")

# ── App ───────────────────────────────────────────────────────
app = FastAPI(
    title="Kanzlei AI — API v3.0",
    description="Vollautomatisches Kanzlei-Management",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(GZipMiddleware, minimum_size=1000)
_origins_env = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:80,http://127.0.0.1:80",
)
_cors_origins = [o.strip() for o in _origins_env.split(",") if o.strip()]
# Wildcard + credentials ist im Browser ungültig — dann Credentials aus
_cors_creds = "*" not in _cors_origins and not (
    len(_cors_origins) == 1 and _cors_origins[0] == "*"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins if _cors_origins else ["http://localhost:3000"],
    allow_credentials=_cors_creds,
    allow_methods=["*"],
    allow_headers=["*"],
)

ds = DatenSpeicher()   # Fallback für Startup + nicht-User-spezifische Calls

def get_ds(user: dict = None) -> DatenSpeicher:
    """
    Gibt DatenSpeicher für die Kanzlei des eingeloggten Users zurück.
    Kern des Multi-Kanzlei-Systems: jeder User sieht nur seine Daten.
    """
    kanzlei_id = (user or {}).get("kanzlei_id", "default")
    if kanzlei_id == "default":
        return ds
    return DatenSpeicher(kanzlei_id=kanzlei_id)

# ── Rate-Limiting (In-Memory) ─────────────────────────────────
_rate_store: Dict[str, List[float]] = {}
RATE_LIMIT   = int(os.getenv("API_RATE_LIMIT", "60"))   # Requests/Minute
RATE_WINDOW  = 60  # Sekunden

def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Auth-Endpoints strenger limitieren
    is_auth = request.url.path.startswith("/auth/login")
    limit   = 10 if is_auth else RATE_LIMIT
    ip      = _get_client_ip(request)
    key     = f"{ip}:{request.url.path if is_auth else ip}"

    now = time.time()
    _rate_store[key] = [t for t in _rate_store.get(key, []) if now - t < RATE_WINDOW]

    if len(_rate_store[key]) >= limit:
        return JSONResponse(
            status_code=429,
            content={
                "ok":     False,
                "error":  "Zu viele Anfragen — bitte warten",
                "code":   429,
                "retry_after": RATE_WINDOW,
            }
        )
    _rate_store[key].append(now)
    return await call_next(request)


PLAN_USAGE_LIMITS = {
    "starter": {"ai_requests_day": 200, "exports_day": 30},
    "professional": {"ai_requests_day": 2000, "exports_day": 300},
    "enterprise": {"ai_requests_day": 100000, "exports_day": 10000},
}


def _usage_metric_for_path(path: str) -> Optional[str]:
    if path.startswith("/export/") or path.startswith("/system/export"):
        return "exports_day"
    ai_prefixes = (
        "/ki/",
        "/ml/",
        "/belege/analysieren",
        "/dokumente/analysieren",
        "/engine/analyse",
        "/prognose/",
    )
    if path.startswith(ai_prefixes):
        return "ai_requests_day"
    return None


def _plan_for_user(user: dict) -> str:
    try:
        from core.auth import hole_kanzlei

        kid = user.get("kanzlei_id", "default")
        row = hole_kanzlei(kid) or {}
        return (row.get("plan") or "starter").strip().lower()
    except Exception:
        return "starter"


@app.middleware("http")
async def usage_quota_middleware(request: Request, call_next):
    metric = _usage_metric_for_path(request.url.path)
    if not metric:
        return await call_next(request)

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return await call_next(request)
    from core.auth import verifiziere_session

    session = verifiziere_session(auth.removeprefix("Bearer ").strip())
    if not session:
        return await call_next(request)

    plan = _plan_for_user(session)
    limit = PLAN_USAGE_LIMITS.get(plan, PLAN_USAGE_LIMITS["starter"]).get(metric, 0)
    kid = session.get("kanzlei_id", "default")
    current = usage_get(kid, metric)
    if limit and current >= limit:
        return JSONResponse(
            status_code=402,
            content={
                "ok": False,
                "error": f"Plan-Limit erreicht ({metric}: {current}/{limit})",
                "code": 402,
                "metric": metric,
                "plan": plan,
            },
        )

    response = await call_next(request)
    if response.status_code < 400:
        usage_increment(kid, metric, 1)
    return response


@app.middleware("http")
async def https_enforce_middleware(request: Request, call_next):
    """
    Optionaler HTTPS-Only Modus für Produktion hinter Proxy.
    Aktiv via FORCE_HTTPS=1.
    """
    environment = (os.getenv("ENVIRONMENT") or os.getenv("APP_ENV") or "development").lower()
    force_https = (
        environment == "production"
        or (os.getenv("FORCE_HTTPS", "") or "").strip().lower() in ("1", "true", "yes", "on")
    )
    if not force_https:
        return await call_next(request)
    host = (request.headers.get("host") or "").split(":")[0].lower()
    if host in {"localhost", "127.0.0.1"}:
        return await call_next(request)
    proto = request.headers.get("x-forwarded-proto", "").lower()
    if request.url.scheme == "https" or proto == "https":
        return await call_next(request)
    return JSONResponse(
        status_code=426,
        content={"ok": False, "error": "HTTPS erforderlich", "code": 426},
    )

# ── Globale Exception Handler ─────────────────────────────────

@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    errors = []
    for err in exc.errors():
        field = " → ".join(str(e) for e in err.get("loc", []))
        errors.append(f"{field}: {err.get('msg', 'Ungültiger Wert')}")
    log.warning(f"Validation Error {request.url.path}: {errors}")
    return JSONResponse(
        status_code=422,
        content={
            "ok":     False,
            "error":  "Validierungsfehler",
            "details": errors,
            "code":   422,
        }
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    log.warning(f"HTTP {exc.status_code} {request.url.path}: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "ok":    False,
            "error": exc.detail,
            "code":  exc.status_code,
        }
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error(f"Unhandled Error {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "ok":    False,
            "error": "Interner Serverfehler — bitte erneut versuchen",
            "code":  500,
        }
    )

# ── Standardisierte Response-Helpers ─────────────────────────

def ok(data: Any = None, message: str = None, **kwargs) -> Dict:
    """Erfolgreiche Response — immer gleiches Format."""
    result = {"ok": True}
    if data is not None:
        result["data"] = data
    if message:
        result["message"] = message
    result.update(kwargs)
    return result

def ok_compat(payload: Dict[str, Any], message: Optional[str] = None, **kwargs) -> Dict:
    """
    Einheitliches Format ohne Breaking Changes:
    - behält bestehende Top-Level-Felder
    - ergänzt zusätzlich ok/data/message
    """
    result = {"ok": True, "data": payload}
    result.update(payload)
    if message:
        result["message"] = message
    result.update(kwargs)
    return result

def err(message: str, code: int = 400) -> HTTPException:
    """Fehler-Response — wirft HTTPException."""
    return HTTPException(status_code=code, detail=message)


# ============================================================
# PYDANTIC MODELS
# ============================================================

class MandantCreate(BaseModel):
    name:      str   = Field(..., min_length=2, max_length=100)
    umsatz:    float = Field(0.0, ge=0)
    email:     Optional[str]  = None
    telefon:   Optional[str]  = None
    branche:   Optional[str]  = None
    steuer_id: Optional[str]  = None
    notizen:   Optional[str]  = None
    adresse:   Optional[str]  = None

class MandantUpdate(BaseModel):
    umsatz:    Optional[float] = Field(None, ge=0)
    email:     Optional[str]  = None
    telefon:   Optional[str]  = None
    branche:   Optional[str]  = None
    notizen:   Optional[str]  = None
    steuer_id: Optional[str]  = None
    adresse:   Optional[str]  = None

class AufgabeCreate(BaseModel):
    beschreibung: str          = Field(..., min_length=1, max_length=500)
    frist:        str          = Field(..., example="2026-06-30")
    prioritaet:   Optional[str] = Field("normal")
    kategorie:    Optional[str] = None
    notiz:        Optional[str] = None

class DokumentAnforderung(BaseModel):
    dokument_name: str          = Field(..., min_length=2)
    beschreibung:  Optional[str] = None
    frist:         Optional[str] = None

class SimulationRequest(BaseModel):
    investition:       Optional[float] = Field(0.0, ge=0)
    zusatz_einnahmen:  Optional[float] = Field(0.0, ge=0)
    abschreibungen:    Optional[float] = Field(0.0, ge=0)
    sonderausgaben:    Optional[float] = Field(0.0, ge=0)

class BulkAufgabeCreate(BaseModel):
    aufgaben: List[AufgabeCreate]


LEGAL_REQUIRED_FILES = [
    "legal/IMPRESSUM_TEMPLATE.md",
    "legal/PRIVACY_POLICY_TEMPLATE.md",
    "legal/AVV_TEMPLATE.md",
    "legal/COMPLIANCE_CHECKLIST.md",
]


def _compliance_status() -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []
    present = 0
    for rel_path in LEGAL_REQUIRED_FILES:
        exists = Path(rel_path).exists()
        checks.append({"file": rel_path, "exists": exists})
        if exists:
            present += 1
    total = len(LEGAL_REQUIRED_FILES)
    percent = int(round((present / max(1, total)) * 100))
    return {
        "present": present,
        "required": total,
        "percent": percent,
        "missing_files": [c["file"] for c in checks if not c["exists"]],
        "checks": checks,
        "status": "ok" if present == total else "incomplete",
    }


# ============================================================
# HILFSFUNKTIONEN
# ============================================================

def get_mandant_or_404(name: str, ds_instance=None) -> Dict:
    store = ds_instance or ds
    m = store.hole_mandant(name)
    if not m:
        raise HTTPException(
            status_code=404,
            detail=f"Mandant '{name}' nicht gefunden"
        )
    return m


def _kv_get(store: DatenSpeicher, key: str, default):
    value = store.setting_holen(key, default)
    return value if value is not None else default


def _kv_set(store: DatenSpeicher, key: str, value) -> None:
    store.setting_setzen(key, value)

def darf_email_senden(name: str, mindest_abstand_stunden: int = 24, store: Optional[DatenSpeicher] = None) -> bool:
    st = store or ds
    m = st.hole_mandant(name) if hasattr(st, "hole_mandant") else st.hole_mandanten().get(name, {})
    if not m:
        return False
    letzte = m.get("letzte_email")
    if not letzte:
        return True
    try:
        delta = datetime.now() - datetime.fromisoformat(letzte)
        return delta.total_seconds() > (mindest_abstand_stunden * 3600)
    except Exception:
        return True


def send_email_smtp(to_email: str, subject: str, body: str, html_body: str = None) -> bool:
    """
    Sendet Email via SMTP.
    FIX: Sendet HTML wenn html_body angegeben — nicht mehr als Plain Text.
    Fallback: Plain Text wenn kein HTML.
    """
    sender   = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASS")
    smtp_host = os.getenv("EMAIL_HOST", os.getenv("SMTP_HOST", "smtp.gmail.com"))
    smtp_port = int(os.getenv("EMAIL_PORT", os.getenv("SMTP_PORT", "587")))

    if not sender or not password:
        log.warning("EMAIL_USER / EMAIL_PASS fehlen in .env — Email nicht gesendet")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["From"]    = os.getenv("EMAIL_FROM", sender)
        msg["To"]      = to_email
        msg["Subject"] = subject

        # Immer Plain Text anhängen (Fallback)
        msg.attach(MIMEText(body or "", "plain", "utf-8"))

        # HTML als bevorzugte Version (wird von modernen Clients genutzt)
        if html_body:
            msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(sender, password)
            server.send_message(msg)

        log.info(f"Email gesendet → {to_email} | Betreff: {subject[:40]}")
        return True

    except smtplib.SMTPAuthenticationError:
        log.error("SMTP Auth-Fehler — EMAIL_USER / EMAIL_PASS in .env prüfen")
        return False
    except smtplib.SMTPException as e:
        log.error(f"SMTP Fehler: {e}")
        return False
    except Exception as e:
        log.error(f"Email-Fehler: {e}")
        return False


def _email_fuer_mandant_senden(name: str, store: Optional[DatenSpeicher] = None) -> bool:
    """
    Legt eine professionelle HTML-Email in die Outbox.
    Versand erfolgt über Worker mit Retry/Backoff.
    """
    st = store or ds
    mandanten = st.hole_mandanten()
    if name not in mandanten:
        return False

    m = mandanten[name]
    empfaenger = m.get("email")
    if not empfaenger:
        log.warning(f"Mandant '{name}' hat keine Email-Adresse")
        return False

    aufgaben = st.hole_fristen()

    # HTML + Betreff aus neuem System
    from core.ai_email import erstelle_email_vorschau
    try:
        vorschau = erstelle_email_vorschau(name, m, aufgaben, st)
        html_body  = vorschau["email_html"]
        plain_body = vorschau["email_text"]
        subject    = vorschau["betreff"]
    except Exception as e:
        log.warning(f"Email-Vorschau Fehler für {name}: {e}")
        from core.ai_email import generate_ai_email
        plain_body = generate_ai_email(name, m, aufgaben, st)
        html_body  = None
        subject    = f"Kanzlei Mitteilung — {name} — {datetime.now().strftime('%d.%m.%Y')}"

    idk_src = f"{st.kanzlei_id}|{name}|auto|{datetime.now().strftime('%Y-%m-%d')}|{subject}|{plain_body[:120]}"
    idk = hashlib.sha256(idk_src.encode("utf-8")).hexdigest()
    enq = email_outbox_enqueue(
        kanzlei_id=st.kanzlei_id,
        mandant=name,
        to_email=empfaenger,
        subject=subject,
        body_text=plain_body or "",
        body_html=html_body or "",
        idempotency_key=idk,
        max_attempts=5,
    )
    if enq.get("created"):
        st.log_eintrag(f"EMAIL_ENQUEUED | {name} | {empfaenger} | outbox_id={enq.get('id')}")
        return True
    return enq.get("status") in ("pending", "sending", "sent")


def _process_email_outbox_once(limit: int = 10) -> Dict[str, int]:
    due = email_outbox_due(limit=limit)
    sent = 0
    failed = 0
    skipped = 0

    for row in due:
        oid = row.get("id")
        if not oid or not email_outbox_claim(int(oid)):
            skipped += 1
            continue
        try:
            ok_send = send_email_smtp(
                row.get("to_email", ""),
                row.get("subject", ""),
                row.get("body_text", ""),
                row.get("body_html") or None,
            )
            if not ok_send:
                raise RuntimeError("SMTP send fehlgeschlagen")
            email_outbox_mark_sent(int(oid))
            sent += 1
            kid = row.get("kanzlei_id", "default")
            name = row.get("mandant", "")
            if name:
                st = DatenSpeicher(kanzlei_id=kid)
                m = st.hole_mandant(name)
                if m:
                    m["letzte_email"] = datetime.now().isoformat()
                    st.mandant_speichern(name, m)
                    st.log_eintrag(f"EMAIL_GESENDET | {name} | {row.get('to_email','')} | OUTBOX")
                _emit_webhook_event(
                    kid,
                    "email.sent",
                    {
                        "mandant": name,
                        "to": row.get("to_email", ""),
                        "subject": row.get("subject", ""),
                        "outbox_id": oid,
                    },
                )
        except Exception as e:
            failed += 1
            email_outbox_mark_failed(int(oid), str(e))

    return {"sent": sent, "failed": failed, "skipped": skipped, "checked": len(due)}


async def email_outbox_worker():
    await asyncio.sleep(8)
    while True:
        try:
            res = _process_email_outbox_once(limit=20)
            if res.get("sent") or res.get("failed"):
                log.info(f"Email-Outbox Worker: {res}")
        except Exception as e:
            log.warning(f"Email-Outbox Worker Fehler: {e}")
        await asyncio.sleep(20)


def _emit_webhook_event(kanzlei_id: str, event_type: str, payload: Dict[str, Any]) -> None:
    try:
        webhook_enqueue(kanzlei_id, event_type, payload)
    except Exception as e:
        log.debug(f"Webhook enqueue fehlgeschlagen ({event_type}): {e}")


async def webhook_delivery_worker():
    await asyncio.sleep(10)
    while True:
        try:
            due = webhook_due(limit=25)
            for ev in due:
                qid = int(ev.get("id"))
                kid = ev.get("kanzlei_id", "default")
                et = ev.get("event_type", "")
                try:
                    payload = json.loads(ev.get("payload_json") or "{}")
                except Exception:
                    payload = {}
                targets = webhook_endpoints_for_event(kid, et)
                if not targets:
                    webhook_mark_sent(qid)
                    continue
                delivered = 0
                for t in targets:
                    try:
                        body = json.dumps(
                            {"event": et, "payload": payload, "timestamp": datetime.now().isoformat()},
                            ensure_ascii=False,
                        )
                        sig = hmac.new(
                            (t.get("secret") or "").encode("utf-8"),
                            body.encode("utf-8"),
                            hashlib.sha256,
                        ).hexdigest()
                        async with httpx.AsyncClient(timeout=8) as client:
                            res = await client.post(
                                t["url"],
                                content=body.encode("utf-8"),
                                headers={
                                    "X-Kanzlei-Event": et,
                                    "X-Kanzlei-Signature": f"sha256={sig}",
                                    "X-Kanzlei-Webhook-Id": str(t.get("id", "")),
                                    "Content-Type": "application/json",
                                },
                            )
                        if 200 <= res.status_code < 300:
                            delivered += 1
                    except Exception:
                        continue
                if delivered > 0:
                    webhook_mark_sent(qid)
                else:
                    webhook_mark_failed(qid, "Keine Endpoint-Zustellung erfolgreich")
        except Exception as e:
            log.warning(f"Webhook Worker Fehler: {e}")
        await asyncio.sleep(20)


def berechne_steuersimulation(mandant_data: dict, sim: SimulationRequest) -> dict:
    umsatz = mandant_data.get("umsatz", 0)
    basis_gewinn = umsatz - mandant_data.get("betriebsausgaben", 0)
    neuer_gewinn = (
        basis_gewinn
        + sim.zusatz_einnahmen
        - sim.investition
        - sim.abschreibungen
        - sim.sonderausgaben
    )

    steuer_alt = round(max(0, basis_gewinn * 0.30), 2)
    steuer_neu = round(max(0, neuer_gewinn * 0.30), 2)
    ersparnis = round(steuer_alt - steuer_neu, 2)

    return {
        "basis_gewinn": round(basis_gewinn, 2),
        "simulierter_gewinn": round(neuer_gewinn, 2),
        "steuerlast_aktuell": steuer_alt,
        "steuerlast_simuliert": steuer_neu,
        "steuerersparnis": ersparnis,
        "hinweis": "Schätzung auf Basis 30% Steuersatz. Nur zur Planung — kein Steuerrat."
    }


def _track_action_for_suggestions(store: DatenSpeicher, action: str) -> None:
    """
    Speichert einfache Nutzungsereignisse zur späteren Settings-Empfehlung.
    Leichtgewichtig in Settings (rolling 14 Tage).
    """
    try:
        key = "__usage_events_v1"
        events = store.setting_holen(key, []) or []
        now = datetime.now()
        ts = now.isoformat()
        events.append({"a": action, "t": ts})
        cutoff = now - timedelta(days=14)
        compact = []
        for e in events[-2000:]:
            try:
                if datetime.fromisoformat(e.get("t", "")) >= cutoff:
                    compact.append(e)
            except Exception:
                continue
        store.setting_setzen(key, compact)
    except Exception:
        pass


def _extract_tenant_ids(payload: Any) -> set[str]:
    """Collect tenant ids from nested JSON payloads."""
    ids: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in {"organization_id", "kanzlei_id"} and value:
                ids.add(str(value))
            ids.update(_extract_tenant_ids(value))
    elif isinstance(payload, list):
        for item in payload:
            ids.update(_extract_tenant_ids(item))
    return ids


def _settings_suggestions(store: DatenSpeicher) -> List[Dict[str, Any]]:
    events = store.setting_holen("__usage_events_v1", []) or []
    counts: Dict[str, int] = {}
    now = datetime.now()
    cutoff = now - timedelta(days=7)
    for e in events:
        try:
            if datetime.fromisoformat(e.get("t", "")) < cutoff:
                continue
        except Exception:
            continue
        a = e.get("a")
        if not a:
            continue
        counts[a] = counts.get(a, 0) + 1

    suggestions: List[Dict[str, Any]] = []
    if counts.get("workflow_monatsabschluss", 0) >= 6:
        signal = counts.get("workflow_monatsabschluss", 0)
        suggestions.append({
            "id": "workflow_auto_monat",
            "titel": "Monatsabschluss automatisieren",
            "grund": "Sie starten Monatsabschluss sehr häufig.",
            "empfehlung": {"key": "workflow_auto_monatsabschluss", "wert": True},
            "impact": "Zeitersparnis bei wiederkehrenden Abschluss-Aufgaben",
            "confidence": min(0.99, 0.55 + signal * 0.04),
            "signal_count": signal,
        })
    if counts.get("email_send_manual", 0) + counts.get("email_bulk", 0) >= 12:
        signal = counts.get("email_send_manual", 0) + counts.get("email_bulk", 0)
        suggestions.append({
            "id": "email_followup_auto",
            "titel": "Follow-up Mails automatisieren",
            "grund": "Sie versenden sehr häufig manuelle oder Bulk-Emails.",
            "empfehlung": {"key": "workflow_auto_followup_email", "wert": True},
            "impact": "Weniger manuelle Kommunikation und weniger Vergessen",
            "confidence": min(0.99, 0.5 + signal * 0.03),
            "signal_count": signal,
        })
    if counts.get("engine_run_manual", 0) >= 10:
        signal = counts.get("engine_run_manual", 0)
        suggestions.append({
            "id": "engine_autonomie_hoch",
            "titel": "Engine-Autonomie erhöhen",
            "grund": "Sie triggern die Engine oft manuell.",
            "empfehlung": {"key": "ki_autonomie_grad", "wert": 85},
            "impact": "Mehr automatische Entscheidungen im Tagesbetrieb",
            "confidence": min(0.99, 0.45 + signal * 0.035),
            "signal_count": signal,
        })
    if counts.get("settings_change", 0) >= 8:
        signal = counts.get("settings_change", 0)
        suggestions.append({
            "id": "settings_export_backup",
            "titel": "Regelmäßige Settings-Backups aktivieren",
            "grund": "Sie ändern häufig Einstellungen.",
            "empfehlung": {"key": "workflow_settings_backup_taeglich", "wert": True},
            "impact": "Schnelle Wiederherstellung bei Fehlkonfigurationen",
            "confidence": min(0.99, 0.5 + signal * 0.03),
            "signal_count": signal,
        })
    return suggestions[:6]


# ============================================================
# STARTUP / SHUTDOWN
# ============================================================

@app.on_event("startup")
async def startup_event():
    log.info("=" * 60)
    log.info("Kanzlei AI API v3.0 — Start")
    log.info("=" * 60)

    os.makedirs("data", exist_ok=True)

    # ── Konfiguration validieren ──────────────────────────────
    checks = {
        "OPENAI_API_KEY":  os.getenv("OPENAI_API_KEY"),
        "PORTAL_SECRET":   os.getenv("PORTAL_SECRET"),
        "JWT_SECRET":      os.getenv("JWT_SECRET"),
    }
    optionale = {
        "EMAIL_USER":      os.getenv("EMAIL_USER"),
        "EMAIL_PASS":      os.getenv("EMAIL_PASS"),
    }

    alle_ok = True
    for key, val in checks.items():
        if not val:
            log.error(f"❌ PFLICHT-KEY fehlt: {key} — bitte in .env eintragen!")
            alle_ok = False
        else:
            log.info(f"✓ {key} gesetzt")

    for key, val in optionale.items():
        if not val:
            log.warning(f"⚠ Optional fehlt: {key} — automatische Emails deaktiviert")
        else:
            log.info(f"✓ {key} gesetzt")

    if alle_ok:
        log.info("✓ Alle Pflicht-Keys vorhanden — System startet vollständig")
    else:
        log.error("⚠ System startet mit eingeschränkter Funktion — Keys in .env prüfen!")

    environment = (os.getenv("ENVIRONMENT") or os.getenv("APP_ENV") or "development").lower()
    if environment == "production":
        database_url = (os.getenv("DATABASE_URL") or "").strip()
        if not database_url:
            raise RuntimeError("DATABASE_URL fehlt: Production benötigt Postgres-Verbindung.")
        if not database_url.lower().startswith("postgresql://"):
            raise RuntimeError("Production verlangt PostgreSQL: DATABASE_URL muss mit postgresql:// beginnen.")
        json_runtime = [
            str(p) for p in Path("data").rglob("*.json")
            if p.is_file()
        ] if Path("data").exists() else []
        if json_runtime:
            raise RuntimeError(f"Production blockiert: JSON-Runtime-Dateien gefunden: {json_runtime}")

    # ── Daten-Verzeichnisse anlegen ───────────────────────────
    for d in ["data/uploads"]:
        os.makedirs(d, exist_ok=True)

    if environment == "production":
        sqlite_files = [str(p) for p in Path("data").glob("*.db")]
        if sqlite_files:
            raise RuntimeError(f"Production blockiert: SQLite-Dateien gefunden: {sqlite_files}")

    # ── Auto-Agent starten ────────────────────────────────────
    asyncio.create_task(auto_agent_worker())
    asyncio.create_task(email_outbox_worker())
    asyncio.create_task(webhook_delivery_worker())
    log.info("✓ Auto-Agent gestartet")
    log.info("✓ Email-Outbox Worker gestartet")
    log.info("✓ Webhook Delivery Worker gestartet")
    log.info("=" * 60)


@app.on_event("shutdown")
async def shutdown_event():
    log.info("API wird beendet")


# ============================================================
# ROOT & HEALTH
# ============================================================

@app.get("/", tags=["System"])
def root():
    """Öffentlicher Status — keine Mandanten- oder Aufgaben-Zahlen (Datenschutz)."""
    return {
        "name": "Kanzlei AI API",
        "version": "3.0.0",
        "status": "running",
        "docs": "/docs",
        "intro": "/api/v1/introduction",
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/health", tags=["System"])
def health():
    try:
        ds.hole_mandanten()
        return {"status": "healthy", "timestamp": datetime.now().isoformat()}
    except Exception as e:
        raise HTTPException(503, f"Datenspeicher nicht erreichbar: {e}")


@app.get("/api/v1/meta", tags=["System"])
def api_v1_meta():
    return ok({
        "version": "v1",
        "contract": {
            "success": {"ok": True, "data": {}},
            "error": {"ok": False, "error": "message", "code": 400},
        },
        "timestamp": datetime.now().isoformat(),
    })


@app.get("/api/v1/health", tags=["System"])
def api_v1_health():
    return ok({"status": "healthy", "timestamp": datetime.now().isoformat()})


# Early auth helper so dependencies below resolve at import time.
def get_current_user(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    request: Request = None,
) -> dict:
    if x_api_key:
        api_key = api_key_verify(x_api_key.strip())
        if not api_key:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Ungültiger API-Key")
        return {
            "benutzername": f"api_key:{api_key['name']}",
            "rolle": "admin",
            "kanzlei_id": api_key["kanzlei_id"],
            "api_key_id": api_key["id"],
            "api_permissions": api_key.get("permissions", []),
        }
    from core.auth import verifiziere_session
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Login erforderlich",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.removeprefix("Bearer ").strip()
    session = verifiziere_session(token)
    if not session:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Session abgelaufen — bitte neu anmelden",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return session


@app.get("/api/v1/dashboard", tags=["System"])
def api_v1_dashboard(_user: dict = Depends(get_current_user)):
    return get_dashboard(_user)


@app.get("/api/v1/kpis", tags=["System"])
def api_v1_kpis(_user: dict = Depends(get_current_user)):
    return get_kpis(_user)


@app.get("/api/v1/settings/suggestions", tags=["System"])
def api_v1_settings_suggestions(_user: dict = Depends(get_current_user)):
    return settings_suggestions(_user)


@app.get("/api/v1/billing/usage", tags=["System"])
def api_v1_billing_usage(_user: dict = Depends(get_current_user)):
    return billing_usage(_user)


@app.get("/api/v1/compliance/status", tags=["System"])
def api_v1_compliance_status(_user: dict = Depends(get_current_user)):
    return ok(_compliance_status())


@app.get("/api/v1/webhooks/verify-example", tags=["System"])
def api_v1_webhook_verify_example():
    snippet = {
        "python": (
            "import hmac, hashlib\n"
            "def verify(sig_header, secret, raw_body_bytes):\n"
            "    # sig_header format: sha256=<hex>\n"
            "    got = (sig_header or '').split('=',1)[-1]\n"
            "    exp = hmac.new(secret.encode('utf-8'), raw_body_bytes, hashlib.sha256).hexdigest()\n"
            "    return hmac.compare_digest(got, exp)\n"
        ),
        "headers": {
            "X-Kanzlei-Event": "event type",
            "X-Kanzlei-Signature": "sha256=<hmac_hex>",
            "X-Kanzlei-Webhook-Id": "endpoint id",
        },
        "important": "Signatur immer gegen den RAW-Request-Body prüfen, nicht gegen re-serialisiertes JSON.",
    }
    return ok(snippet)


@app.get("/api/v1/endpoints", tags=["System"])
def api_v1_endpoints_catalog():
    return ok({
        "core": [
            "/api/v1/health",
            "/api/v1/meta",
            "/api/v1/dashboard",
            "/api/v1/kpis",
            "/api/v1/settings/suggestions",
            "/api/v1/billing/usage",
            "/api/v1/compliance/status",
            "/api/v1/ai/usecases",
            "/api/v1/webhooks/verify-example",
        ],
        "saas_admin": [
            "/saas/apikeys",
            "/saas/apikeys/{key_id}",
            "/saas/apikeys/{key_id}/rotate",
            "/saas/webhooks",
            "/saas/webhooks/{webhook_id}",
            "/saas/webhooks/{webhook_id}/test",
        ],
    })


@app.get("/api/v1/introduction", tags=["System"])
def api_v1_introduction():
    return ok({
        "produkt": "Kanzlei AI",
        "kurzbeschreibung": "Multi-Tenant Steuerkanzlei-SaaS mit Automatisierung, Decision Engine und Self-Service APIs.",
        "wie_es_funktioniert": [
            "1) Auth: Benutzer oder API-Key identifiziert eine Kanzlei (tenant).",
            "2) Datenebene: Jeder Request wird tenant-spezifisch über kanzlei_id isoliert.",
            "3) Automatisierung: Engine/Agent priorisiert Fälle, Email-Outbox versendet robust mit Retry.",
            "4) SaaS Controls: Billing-Limits, RBAC, Usage-Metering und Audit-Policies schützen Betrieb und Umsatz.",
            "5) Integrationen: Tenant-Webhooks und API-Keys für externe Systeme.",
        ],
        "empfohlener_start": [
            "/api/v1/meta",
            "/api/v1/health",
            "/api/v1/endpoints",
            "/api/v1/billing/usage",
        ],
    })


@app.get("/api/v1/ai/usecases", tags=["System"])
def api_v1_ai_usecases(_user: dict = Depends(get_current_user)):
    return ok({
        "usecases": [
            {"id": "auto_reply", "name": "Automatische Antworten", "value_metric": "Antwortzeit sinkt"},
            {"id": "doc_processing", "name": "Dokumentenverarbeitung", "value_metric": "Durchsatz steigt"},
            {"id": "deadline_detection", "name": "Fristen-Erkennung", "value_metric": "Fristversäumnisse sinken"},
        ],
        "recommended_start": ["/dokumente/analysieren", "/prognose/fristen", "/bot/analyse"],
    })


# ============================================================
# AUTH — Login, Sessions, Team-Management (moved before usage)
# ============================================================

def get_current_user(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    request: Request = None,
) -> dict:
    """
    Auth-Dependency. Gibt Session-Dict mit kanzlei_id zurück.
    kanzlei_id bestimmt welche Daten der User sieht — Kern des Multi-Kanzlei-Systems.
    """
    if x_api_key:
        api_key = api_key_verify(x_api_key.strip())
        if not api_key:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Ungültiger API-Key")
        return {
            "benutzername": f"api_key:{api_key['name']}",
            "rolle": "admin",
            "kanzlei_id": api_key["kanzlei_id"],
            "api_key_id": api_key["id"],
            "api_permissions": api_key.get("permissions", []),
        }
    from core.auth import verifiziere_session
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Login erforderlich",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token   = authorization.removeprefix("Bearer ").strip()
    session = verifiziere_session(token)
    if not session:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Session abgelaufen — bitte neu anmelden",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return session


def require_permission(permission: str):
    def _dep(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user.get("api_key_id"):
            perms = current_user.get("api_permissions") or []
            if "*" in perms or permission in perms:
                return current_user
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"API-Key ohne Berechtigung: {permission}",
            )
        role = current_user.get("rolle", "")
        if not has_permission(role, permission):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Fehlende Berechtigung: {permission}",
            )
        return current_user
    return _dep


def require_saas_master(
    x_saas_master_key: Optional[str] = Header(None, alias="X-Saas-Master-Key"),
) -> bool:
    """Schützt Multi-Tenant-SaaS-Verwaltungs-Endpunkte."""
    expected = (os.getenv("SAAS_MASTER_KEY") or "").strip()
    if not expected:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "SAAS_MASTER_KEY ist nicht gesetzt — SaaS-Admin deaktiviert",
        )
    if not x_saas_master_key or not secrets.compare_digest(x_saas_master_key, expected):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ungültiger SaaS Master-Key")
    return True


_AUTH_EXEMPT_PREFIXES = (
    "/health",
    "/ready",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/auth/login",
    "/auth/registrieren",
    "/auth/setup-status",
    "/billing/stripe/webhook",
    "/api/v1/health",
    "/api/v1/meta",
    "/api/v1/introduction",
    "/api/v1/webhooks/verify-example",
)


@app.middleware("http")
async def auth_guard_middleware(request: Request, call_next):
    path = request.url.path or "/"
    if request.method == "OPTIONS":
        return await call_next(request)
    if path == "/" or path.startswith(_AUTH_EXEMPT_PREFIXES):
        return await call_next(request)

    try:
        current_user = get_current_user(
            authorization=request.headers.get("Authorization"),
            x_api_key=request.headers.get("X-API-Key"),
            request=request,
        )
    except HTTPException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"ok": False, "error": exc.detail, "code": exc.status_code},
        )

    current_kid = str(current_user.get("kanzlei_id", ""))

    # Header tenant guard (strong, explicit)
    header_org = request.headers.get("X-Organization-Id") or request.headers.get("X-Kanzlei-Id")
    if header_org and str(header_org) != current_kid:
        return JSONResponse(
            status_code=403,
            content={"ok": False, "error": "Cross-tenant Header blockiert", "code": 403},
        )

    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        try:
            content_type = (request.headers.get("content-type") or "").lower()
            if "application/json" in content_type:
                raw = await request.body()
                if raw:
                    payload = json.loads(raw.decode("utf-8"))
                    found_tenant_ids = _extract_tenant_ids(payload)
                    if any(kid != current_kid for kid in found_tenant_ids):
                        return JSONResponse(
                            status_code=403,
                            content={
                                "ok": False,
                                "error": "Cross-tenant Payload blockiert",
                                "code": 403,
                            },
                        )
        except Exception:
            pass

    # Query param tenant guard (read/write)
    query_org = request.query_params.get("organization_id") or request.query_params.get("kanzlei_id")
    if query_org and str(query_org) != current_kid:
        return JSONResponse(
            status_code=403,
            content={
                "ok": False,
                "error": "Cross-tenant Query blockiert",
                "code": 403,
            },
        )

    return await call_next(request)


# ============================================================
# MANDANTEN — CRUD
# ============================================================

@app.get("/mandanten", tags=["Mandanten"])
def get_mandanten(
    suche:      Optional[str]   = Query(None),
    branche:    Optional[str]   = Query(None),
    min_umsatz: Optional[float] = Query(None, ge=0),
    sortierung: Optional[str]   = Query("name"),
    _user: dict = Depends(get_current_user),
):
    from core.decision_engine import berechne_mandant_score
    store = get_ds(_user)
    svc = MandantenService(store)
    daten = svc.list_mandanten(suche=suche, branche=branche, min_umsatz=min_umsatz)
    result = []

    for row in daten:
        name = row.get("name", "")
        m = row
        try:
            sd = berechne_mandant_score(name, m, store)
        except Exception:
            sd = {"score":0,"status":"OK","aufgaben_offen":0,"aufgaben_ueberfaellig":0,"tage_ohne_antwort":0}

        result.append({
            "name":                  name,
            "email":                 m.get("email",""),
            "telefon":               m.get("telefon",""),
            "branche":               m.get("branche",""),
            "umsatz":                float(m.get("umsatz",0)),
            "notizen":               m.get("notizen",""),
            "steuer_id":             m.get("steuer_id",""),
            "score":                 sd.get("score",0),
            "status":                sd.get("status","OK"),
            "aufgaben_offen":        sd.get("aufgaben_offen",0),
            "aufgaben_ueberfaellig": sd.get("aufgaben_ueberfaellig",0),
            "tage_ohne_antwort":     sd.get("tage_ohne_antwort",0),
        })

    if   sortierung == "umsatz": result.sort(key=lambda x: x["umsatz"], reverse=True)
    elif sortierung == "score":  result.sort(key=lambda x: x["score"],  reverse=True)
    else:                        result.sort(key=lambda x: x["name"].lower())

    return ok(result, count=len(result))


@app.get("/mandanten/{name}", tags=["Mandanten"])
def get_mandant(name: str, _user: dict = Depends(get_current_user)):
    from core.decision_engine import berechne_mandant_score
    store    = get_ds(_user)
    m        = get_mandant_or_404(name, store)
    aufgaben = store.hole_aufgaben_fuer_mandant(name)

    try:
        sd = berechne_mandant_score(name, m, store)
    except Exception:
        sd = {}

    return ok({
        **m,
        "score_details":     sd.get("score_details", []),
        "aufgaben":          aufgaben,
        "aufgaben_gesamt":   len(aufgaben),
        "aufgaben_offen":    sum(1 for a in aufgaben if not a.get("erledigt")),
        "aufgaben_erledigt": sum(1 for a in aufgaben if a.get("erledigt")),
    })


@app.post("/mandanten", tags=["Mandanten"], status_code=201)
def create_mandant(data: MandantCreate, _user: dict = Depends(get_current_user)):
    svc = MandantenService(get_ds(_user))
    try:
        payload = svc.create_mandant(data)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    log.info(f"Mandant erstellt: {data.name}")
    return ok_compat(payload, "Mandant erstellt")


@app.put("/mandanten/{name}", tags=["Mandanten"])
def update_mandant(name: str, data: MandantUpdate, _user: dict = Depends(get_current_user)):
    update_felder = data.dict(exclude_none=True)
    svc = MandantenService(get_ds(_user))
    try:
        payload = svc.update_mandant(name, update_felder)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return ok_compat(
        payload,
        "Mandant aktualisiert",
    )


@app.delete("/mandanten/{name}", tags=["Mandanten"])
def delete_mandant(name: str, _user: dict = Depends(get_current_user)):
    svc = MandantenService(get_ds(_user))
    try:
        payload = svc.delete_mandant(name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return ok_compat(payload, "Mandant gelöscht")


@app.post("/mandanten/{name}/antwort", tags=["Mandanten"])
def mandant_antwort_empfangen(name: str, _user: dict = Depends(get_current_user)):
    svc = MandantenService(get_ds(_user))
    try:
        payload = svc.mark_antwort(name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return ok_compat(payload, "Antwort gespeichert")


# ============================================================
# AUFGABEN — CRUD
# ============================================================

@app.get("/mandanten/{name}/aufgaben", tags=["Aufgaben"])
def get_aufgaben(
    name: str,
    nur_offen: bool = Query(False),
    prioritaet: Optional[str] = Query(None),
    _user: dict = Depends(get_current_user),
):
    store = get_ds(_user)
    get_mandant_or_404(name, store)
    svc = AufgabenService(store)
    return ok_compat(svc.list_for_mandant(name, nur_offen=nur_offen, prioritaet=prioritaet))


@app.post("/mandanten/{name}/aufgaben", tags=["Aufgaben"], status_code=status.HTTP_201_CREATED)
def create_aufgabe(name: str, data: AufgabeCreate,
    _user: dict = Depends(get_current_user)):
    store = get_ds(_user)
    get_mandant_or_404(name, store)
    svc = AufgabenService(store)
    return ok_compat(svc.create(name, data), "Aufgabe erstellt")


@app.post("/mandanten/{name}/aufgaben/bulk", tags=["Aufgaben"])
def create_aufgaben_bulk(name: str, data: BulkAufgabeCreate,
    _user: dict = Depends(get_current_user)):
    store = get_ds(_user)
    get_mandant_or_404(name, store)
    svc = AufgabenService(store)
    payload = svc.create_bulk(name, data.aufgaben)
    return ok_compat(
        payload,
        "Bulk-Aufgaben erstellt",
    )


@app.post("/aufgaben/{aufgabe_id}/erledigen", tags=["Aufgaben"])
def toggle_aufgabe(aufgabe_id: str,
    _user: dict = Depends(get_current_user)):
    svc = AufgabenService(get_ds(_user))
    try:
        payload = svc.toggle(aufgabe_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return ok_compat(payload, "Aufgabe aktualisiert")


@app.delete("/aufgaben/{aufgabe_id}", tags=["Aufgaben"])
def delete_aufgabe(aufgabe_id: str,
    _user: dict = Depends(get_current_user)):
    svc = AufgabenService(get_ds(_user))
    try:
        payload = svc.delete(aufgabe_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return ok_compat(payload, "Aufgabe gelöscht")


# ============================================================
# DOKUMENTE
# ============================================================

@app.get("/mandanten/{name}/dokumente", tags=["Dokumente"])
def get_dokumente(name: str, _user: dict = Depends(get_current_user)):
    store = get_ds(_user)
    m = get_mandant_or_404(name, store)
    return ok_compat({
        "name": name,
        "fehlende_dokumente": m.get("fehlende_dokumente_liste", []),
        "anzahl_fehlend": len(m.get("fehlende_dokumente_liste", []))
    })


@app.post("/mandanten/{name}/dokumente/anfordern", tags=["Dokumente"])
def dokument_anfordern(name: str, data: DokumentAnforderung, background_tasks: BackgroundTasks,
    _user: dict = Depends(get_current_user)):
    store = get_ds(_user)
    m = get_mandant_or_404(name)
    fehlende = m.get("fehlende_dokumente_liste", [])
    if data.dokument_name not in fehlende:
        fehlende.append(data.dokument_name)
    m["fehlende_dokumente_liste"] = fehlende
    store.mandant_speichern(name, m)
    store.log_eintrag(f"DOKUMENT_ANGEFORDERT | {name} | {data.dokument_name}")
    if m.get("email") and darf_email_senden(name, store=store):
        background_tasks.add_task(_email_fuer_mandant_senden, name, store)
    return ok_compat({"status": "ok", "dokument": data.dokument_name}, "Dokument angefordert")


@app.post("/mandanten/{name}/dokumente/erhalten", tags=["Dokumente"])
def dokument_erhalten(name: str, dokument_name: str = Query(...),
    _user: dict = Depends(get_current_user)):
    store = get_ds(_user)
    m = get_mandant_or_404(name)
    fehlende = m.get("fehlende_dokumente_liste", [])
    if dokument_name in fehlende:
        fehlende.remove(dokument_name)
    m["fehlende_dokumente_liste"] = fehlende
    m["letzte_antwort"] = datetime.now().isoformat()
    store.mandant_speichern(name, m)
    store.log_eintrag(f"DOKUMENT_ERHALTEN | {name} | {dokument_name}")
    return ok_compat({"status": "ok", "verbleibend": fehlende}, "Dokument als erhalten markiert")


# ============================================================
# EMAIL-SYSTEM
# ============================================================

class EmailSendRequest(BaseModel):
    betreff:    Optional[str] = None
    email_text: Optional[str] = None   # Wenn gesetzt: benutzerdefinierten Text senden
    force:      bool          = True   # BUGFIX: war False → jetzt True als Default (manuelle Sends immer erlaubt)

@app.get("/email/{name}/vorschau", tags=["Email"])
def email_vorschau(name: str, _user: dict = Depends(get_current_user)):
    store    = get_ds(_user)
    m        = get_mandant_or_404(name, store)
    aufgaben = store.hole_fristen()
    from core.ai_email import erstelle_email_vorschau
    vorschau = erstelle_email_vorschau(name, m, aufgaben, store)
    return {
        "mandant":       name,
        "empfaenger":    m.get("email", ""),
        "email_text":    vorschau["email_text"],
        "email_html":    vorschau["email_html"],
        "betreff":       vorschau["betreff"],
        "ton":           vorschau["ton"],
        "generiert_am":  datetime.now().isoformat(),
    }

@app.post("/email/{name}/senden", tags=["Email"])
def email_senden(name: str, background_tasks: BackgroundTasks,
                 data: Optional[EmailSendRequest] = None,
    _user: dict = Depends(get_current_user)):
    store = get_ds(_user)
    m = get_mandant_or_404(name, store)
    if not m.get("email"):
        raise HTTPException(400, f"Mandant '{name}' hat keine Email-Adresse")

    # BUGFIX: 24h-Sperre nur bei automatischen Sends, nicht bei manuellen
    force = data.force if data else True  # Manueller Send immer erlaubt
    if not force and not darf_email_senden(name, store=store):
        raise HTTPException(429, "Email bereits in den letzten 24h gesendet. Nutze force=true zum Überschreiben.")

    # Benutzerdefinierten Text verwenden wenn vorhanden
    custom_text = data.email_text if data and data.email_text else None

    if custom_text:
        subject = (data.betreff if data and data.betreff
                   else f"Nachricht von Ihrer Kanzlei — {datetime.now().strftime('%d.%m.%Y')}")
        idem_src = f"{store.kanzlei_id}|{name}|manual|{datetime.now().strftime('%Y-%m-%d-%H')}|{subject}|{custom_text[:160]}"
        idem = hashlib.sha256(idem_src.encode("utf-8")).hexdigest()
        enq = email_outbox_enqueue(
            kanzlei_id=store.kanzlei_id,
            mandant=name,
            to_email=m["email"],
            subject=subject,
            body_text=custom_text,
            body_html="",
            idempotency_key=idem,
            max_attempts=5,
        )
        store.log_eintrag(f"EMAIL_MANUELL_ENQUEUED | {name} | {m['email']} | outbox_id={enq.get('id')}")
        background_tasks.add_task(_process_email_outbox_once, 5)
        _track_action_for_suggestions(store, "email_send_manual")
    else:
        background_tasks.add_task(_email_fuer_mandant_senden, name, store)
        background_tasks.add_task(_process_email_outbox_once, 5)
        _track_action_for_suggestions(store, "email_send_auto")

    return ok_compat(
        {"status": "queued", "mandant": name, "empfaenger": m["email"]},
        "Email in Queue eingereiht",
    )


@app.post("/email/bulk", tags=["Email"])
def email_bulk(mandanten_namen: List[str], background_tasks: BackgroundTasks,
    _user: dict = Depends(get_current_user)):
    store = get_ds(_user)
    gesendet = []
    uebersprungen = []

    for name in mandanten_namen:
        try:
            m = store.hole_mandanten().get(name)
            if not m or not m.get("email"):
                uebersprungen.append({"name": name, "grund": "Keine Email-Adresse"})
                continue
            if not darf_email_senden(name, store=store):
                uebersprungen.append({"name": name, "grund": "Bereits heute gesendet"})
                continue
            background_tasks.add_task(_email_fuer_mandant_senden, name, store)
            background_tasks.add_task(_process_email_outbox_once, 10)
            gesendet.append(name)
        except Exception as e:
            uebersprungen.append({"name": name, "grund": str(e)})

    if gesendet:
        _track_action_for_suggestions(store, "email_bulk")
    return ok_compat({
        "gesendet": gesendet,
        "uebersprungen": uebersprungen,
        "gesamt": len(mandanten_namen),
    })


@app.get("/email/outbox", tags=["Email"], summary="Email-Queue Status (pro Kanzlei)")
def email_outbox_status(
    limit: int = Query(50, ge=1, le=300),
    _user: dict = Depends(require_permission("reports:read")),
):
    kid = _user.get("kanzlei_id", "default")
    rows = email_outbox_recent(kid, limit=limit)
    return {
        "kanzlei_id": kid,
        "eintraege": rows,
        "gesamt": len(rows),
        "pending": sum(1 for r in rows if r.get("status") in ("pending", "sending")),
        "failed": sum(1 for r in rows if r.get("status") in ("failed", "dead")),
        "sent": sum(1 for r in rows if r.get("status") == "sent"),
    }


@app.get("/billing/usage", tags=["Billing"], summary="Aktuelle Nutzung vs Plan-Limits")
def billing_usage(_user: dict = Depends(get_current_user)):
    kid = _user.get("kanzlei_id", "default")
    plan = _plan_for_user(_user)
    limits = PLAN_USAGE_LIMITS.get(plan, PLAN_USAGE_LIMITS["starter"])
    ai = usage_get(kid, "ai_requests_day")
    ex = usage_get(kid, "exports_day")
    return ok({
        "kanzlei_id": kid,
        "plan": plan,
        "limits": limits,
        "usage_today": {
            "ai_requests_day": ai,
            "exports_day": ex,
        },
    })


@app.post("/saas/apikeys", tags=["SaaS"], summary="API-Key erzeugen (einmal anzeigen)")
def saas_api_key_create(
    data: ApiKeyCreateRequest,
    _user: dict = Depends(require_permission("settings:write")),
):
    kid = _user.get("kanzlei_id", "default")
    created = api_key_create(kid, data.name, permissions=data.permissions or [])
    _emit_webhook_event(kid, "apikey.created", {"id": created["id"], "name": data.name})
    return ok({
        "id": created["id"],
        "api_key": created["key"],
        "hinweis": "Dieser Key wird nur einmal angezeigt.",
    })


@app.get("/saas/apikeys", tags=["SaaS"], summary="API-Keys der Kanzlei")
def saas_api_keys(_user: dict = Depends(require_permission("settings:read"))):
    kid = _user.get("kanzlei_id", "default")
    return ok({"eintraege": api_key_list(kid)})


@app.delete("/saas/apikeys/{key_id}", tags=["SaaS"], summary="API-Key deaktivieren")
def saas_api_key_delete(
    key_id: str,
    _user: dict = Depends(require_permission("settings:write")),
):
    kid = _user.get("kanzlei_id", "default")
    ok_del = api_key_deactivate(kid, key_id)
    if not ok_del:
        raise HTTPException(404, "API-Key nicht gefunden")
    _emit_webhook_event(kid, "apikey.revoked", {"id": key_id})
    return ok({"status": "deactivated", "id": key_id})


class ApiKeyRotateRequest(BaseModel):
    new_name: Optional[str] = Field(None, min_length=2, max_length=120)


@app.post("/saas/apikeys/{key_id}/rotate", tags=["SaaS"], summary="API-Key rotieren")
def saas_api_key_rotate(
    key_id: str,
    data: ApiKeyRotateRequest = Body(default=ApiKeyRotateRequest()),
    _user: dict = Depends(require_permission("settings:write")),
):
    kid = _user.get("kanzlei_id", "default")
    rotated = api_key_rotate(kid, key_id, new_name=data.new_name)
    if not rotated:
        raise HTTPException(404, "API-Key nicht gefunden oder bereits deaktiviert")
    _emit_webhook_event(kid, "apikey.rotated", {"old_id": rotated["old_id"], "new_id": rotated["new_id"]})
    return ok({
        "old_id": rotated["old_id"],
        "new_id": rotated["new_id"],
        "api_key": rotated["key"],
        "hinweis": "Neuer Key nur einmal sichtbar. Alten Key sofort ersetzen.",
    })


@app.post("/saas/webhooks", tags=["SaaS"], summary="Webhook Endpoint registrieren")
def saas_webhook_create(
    data: WebhookCreateRequest,
    _user: dict = Depends(require_permission("settings:write")),
):
    kid = _user.get("kanzlei_id", "default")
    if not (data.url.startswith("http://") or data.url.startswith("https://")):
        raise HTTPException(400, "Webhook URL muss mit http:// oder https:// starten")
    w = webhook_endpoint_create(kid, data.url, data.events, data.secret)
    return ok({"id": w["id"], "secret": w["secret"], "events": data.events, "url": data.url})


@app.get("/saas/webhooks", tags=["SaaS"], summary="Webhook Endpoints listen")
def saas_webhook_list(_user: dict = Depends(require_permission("settings:read"))):
    kid = _user.get("kanzlei_id", "default")
    return ok({"eintraege": webhook_endpoint_list(kid)})


@app.delete("/saas/webhooks/{webhook_id}", tags=["SaaS"], summary="Webhook Endpoint löschen")
def saas_webhook_delete(
    webhook_id: str,
    _user: dict = Depends(require_permission("settings:write")),
):
    kid = _user.get("kanzlei_id", "default")
    ok_del = webhook_endpoint_delete(kid, webhook_id)
    if not ok_del:
        raise HTTPException(404, "Webhook nicht gefunden")
    return ok({"status": "deleted", "id": webhook_id})


@app.post("/saas/webhooks/{webhook_id}/test", tags=["SaaS"], summary="Testevent enqueuen")
def saas_webhook_test(
    webhook_id: str,
    _user: dict = Depends(require_permission("settings:write")),
):
    kid = _user.get("kanzlei_id", "default")
    exists = any(w["id"] == webhook_id for w in webhook_endpoint_list(kid))
    if not exists:
        raise HTTPException(404, "Webhook nicht gefunden")
    _emit_webhook_event(kid, "webhook.test", {"webhook_id": webhook_id, "by": _user.get("benutzername")})
    return ok({"queued": True, "webhook_id": webhook_id})


@app.get("/agent/actions", tags=["Engine"], summary="Auto-Agent Aktionen (idempotent)")
def agent_actions_status(
    limit: int = Query(100, ge=1, le=500),
    _user: dict = Depends(require_permission("engine:read")),
):
    store = get_ds(_user)
    rows = store._conn().execute(
        """
        SELECT action_key, mandant, aktion, status, details, created_at
        FROM agent_actions
        WHERE kanzlei_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (store.kanzlei_id, limit),
    ).fetchall()
    data = [dict(r) for r in rows]
    return {
        "kanzlei_id": store.kanzlei_id,
        "eintraege": data,
        "gesamt": len(data),
    }


# ============================================================
# DASHBOARD & ANALYTICS
# ============================================================

@app.get("/dashboard", tags=["Dashboard"])
def get_dashboard(_user: dict = Depends(get_current_user)):
    store = get_ds(_user)
    mandanten = store.hole_mandanten()
    aufgaben = store.hole_fristen()
    jetzt = datetime.now()

    total_umsatz = sum(m.get("umsatz", 0) for m in mandanten.values())
    total_aufgaben = len(aufgaben)
    offene_aufgaben = sum(1 for a in aufgaben.values() if not a.get("erledigt"))

    ueberfaellig = []
    faellig_heute = []
    faellig_diese_woche = []

    for a in aufgaben.values():
        if a.get("erledigt"):
            continue
        try:
            frist = datetime.strptime(a["frist"], "%Y-%m-%d")
            tage = (frist - jetzt).days
            eintrag = {**a, "tage_bis_frist": tage}
            if tage < 0:
                ueberfaellig.append(eintrag)
            elif tage == 0:
                faellig_heute.append(eintrag)
            elif tage <= 7:
                faellig_diese_woche.append(eintrag)
        except Exception:
            continue

    return ok_compat({
        "kpis": {
            "mandanten_gesamt": len(mandanten),
            "total_umsatz": round(total_umsatz, 2),
            "aufgaben_gesamt": total_aufgaben,
            "aufgaben_offen": offene_aufgaben,
            "aufgaben_erledigt": total_aufgaben - offene_aufgaben,
            "aufgaben_ueberfaellig": len(ueberfaellig),
            "completion_rate": round(
                (total_aufgaben - offene_aufgaben) / total_aufgaben * 100, 1
            ) if total_aufgaben > 0 else 100.0
        },
        "alerts": {
            "ueberfaellig": ueberfaellig[:10],
            "faellig_heute": faellig_heute,
            "faellig_diese_woche": faellig_diese_woche[:10]
        },
        "generiert_am": jetzt.isoformat()
    })


@app.get("/heute", tags=["Dashboard"])
def get_heute(_user: dict = Depends(get_current_user)):
    result = []
    jetzt = datetime.now()
    store = get_ds(_user)

    for a in store.hole_fristen().values():
        if a.get("erledigt"):
            continue
        try:
            frist = datetime.strptime(a["frist"], "%Y-%m-%d")
            tage = (frist - jetzt).days

            if tage < 0:
                prio = 10000 + abs(tage) * 100
                label = f"UEBERFAELLIG seit {abs(tage)} Tagen"
            elif tage == 0:
                prio = 9000
                label = "HEUTE faellig"
            elif tage <= 1:
                prio = 8000
                label = "MORGEN faellig"
            elif tage <= 3:
                prio = 6000
                label = f"in {tage} Tagen faellig"
            else:
                continue

            result.append({
                "text": f"{a.get('mandant', '?')} -> {a.get('beschreibung', '?')}",
                "label": label,
                "prioritaet": a.get("prioritaet", "normal"),
                "frist": a["frist"],
                "tage": tage,
                "sort_score": prio
            })

        except Exception:
            continue

    result.sort(key=lambda x: x["sort_score"], reverse=True)
    return ok_compat({"eintraege": result[:15], "anzahl": len(result[:15])})


@app.get("/kpis", tags=["Dashboard"],
         summary="Alle Mandanten mit Risiko-Score, Umsatz-Score und KI-Empfehlung")
def get_kpis(_user: dict = Depends(get_current_user)):
    """
    Mandanten-Risiko- & Umsatz-AI.
    Gibt priorisierten Report zurück — kritischste Mandanten zuerst.
    Wird direkt vom Risiko-Dashboard genutzt.
    """
    from core.decision_engine import analysiere_alle_mandanten
    data = analysiere_alle_mandanten(get_ds(_user))
    return ok_compat({"eintraege": data, "anzahl": len(data)})


@app.get("/decisions", tags=["Dashboard"])
def get_decisions(_user: dict = Depends(get_current_user)):
    from core.decision_engine import analysiere_alle_mandanten
    store = get_ds(_user)
    alle = analysiere_alle_mandanten(store)
    result = []
    for m in alle:
        result.append({
            "mandant": m.get("mandant"),
            "status": m.get("status", "OK"),
            "score": m.get("score", 0),
            "risiko_score": m.get("risiko_score", 0),
            "aufgaben_offen": m.get("aufgaben_offen", 0),
            "aufgaben_ueberfaellig": m.get("aufgaben_ueberfaellig", 0),
            "entscheidungen": m.get("empfehlungen", []),
            "empfehlung": m.get("empfehlung", {}),
        })
    return result


@app.get("/empfehlungen", tags=["Dashboard"],
         summary="KI-Empfehlungen für alle Mandanten (priorisiert)")
def get_empfehlungen(_user: dict = Depends(get_current_user)):
    """Nutzt die neue Decision Engine — Risiko + Umsatz kombiniert."""
    from core.decision_engine import analysiere_alle_mandanten
    alle = analysiere_alle_mandanten(get_ds(_user))
    # Nur Mandanten mit Handlungsbedarf zurückgeben
    data = [
        m for m in alle
        if m.get("status") in ("KRITISCH","WICHTIG","NORMAL") or
           m.get("empfehlungen") or
           (m.get("tage_ohne_antwort",0) >= 7)
    ]
    return ok_compat({"eintraege": data, "anzahl": len(data)})


# ============================================================
# SIMULATION & BENCHMARKING
# ============================================================

@app.post("/mandanten/{name}/simulation", tags=["Analyse"])
def steuersimulation(name: str, data: SimulationRequest,
    _user: dict = Depends(get_current_user)):
    store = get_ds(_user)
    m = get_mandant_or_404(name, store)
    ergebnis = berechne_steuersimulation(m, data)
    store.log_eintrag(f"SIMULATION | {name} | Ersparnis: {ergebnis['steuerersparnis']}EUR")
    return {"mandant": name, "simulation": ergebnis, "eingaben": data.dict()}


@app.get("/benchmarking", tags=["Analyse"])
def benchmarking(branche: Optional[str] = Query(None), _user: dict = Depends(get_current_user)):
    store = get_ds(_user)
    mandanten = store.hole_mandanten()
    daten = []

    for name, m in mandanten.items():
        if branche and m.get("branche", "").lower() != branche.lower():
            continue
        daten.append({
            "name": name,
            "umsatz": m.get("umsatz", 0),
            "branche": m.get("branche", "Unbekannt")
        })

    if not daten:
        return {"hinweis": "Keine Daten fuer diese Branche", "daten": []}

    umsaetze = [d["umsatz"] for d in daten]
    durchschnitt = round(sum(umsaetze) / len(umsaetze), 2)

    for d in daten:
        abweichung = round(d["umsatz"] - durchschnitt, 2)
        d["abweichung_vom_durchschnitt"] = abweichung
        d["bewertung"] = "ueberdurchschnittlich" if abweichung > 0 else "unterdurchschnittlich"

    daten.sort(key=lambda x: x["umsatz"], reverse=True)

    return {
        "anzahl": len(daten),
        "durchschnittsumsatz": durchschnitt,
        "max_umsatz": max(umsaetze),
        "min_umsatz": min(umsaetze),
        "branche": branche or "alle",
        "mandanten": daten
    }


# ============================================================
# REPORTING
# ============================================================

@app.get("/mandanten/{name}/report", tags=["Reporting"])
def mandant_report(name: str, _user: dict = Depends(get_current_user)):
    store = get_ds(_user)
    m = get_mandant_or_404(name, store)
    aufgaben_alle = [a for a in store.hole_fristen().values() if a.get("mandant") == name]
    aufgaben_offen = [a for a in aufgaben_alle if not a.get("erledigt")]
    aufgaben_erledigt = [a for a in aufgaben_alle if a.get("erledigt")]

    try:
        score_data = berechne_mandant_score(name, m, store)
    except Exception:
        score_data = {}

    try:
        # Generate recommendations based on mandant score and tasks
        decisions = {
            "entscheidungen": [
                f"Offene Aufgaben: {len(aufgaben_offen)}"
                if aufgaben_offen else "Alle Aufgaben erledigt"
            ]
        }
    except Exception:
        decisions = {"entscheidungen": []}

    return {
        "report": {
            "mandant": name,
            "erstellt_am": datetime.now().isoformat(),
            "stammdaten": m,
            "score": score_data,
            "aufgaben": {
                "gesamt": len(aufgaben_alle),
                "offen": len(aufgaben_offen),
                "erledigt": len(aufgaben_erledigt),
                "details_offen": aufgaben_offen,
                "details_erledigt": aufgaben_erledigt
            },
            "dokumente": {
                "fehlend": m.get("fehlende_dokumente_liste", []),
                "anzahl_fehlend": len(m.get("fehlende_dokumente_liste", []))
            },
            "empfehlungen": decisions.get("entscheidungen", []),
            "email_vorschau": generate_ai_email(name, m, store.hole_fristen(), store)
        }
    }


# ============================================================
# AUDIT & LOGS
# ============================================================

@app.get("/audit", tags=["System"])
def get_audit(
    limit: int = Query(50, ge=1, le=500),
    suche: Optional[str] = Query(None),
    _user: dict = Depends(get_current_user),
):
    store = get_ds(_user)
    logs = store.hole_logs(limit=max(limit * 3, 100))
    if suche:
        q = suche.lower()
        logs = [
            l for l in logs
            if q in str(l.get("aktion", "")).lower()
            or q in str(l.get("details", "")).lower()
            or q in str(l.get("benutzer", "")).lower()
        ]
    logs_sorted = sorted(logs, key=lambda x: x.get("zeitpunkt", ""), reverse=True)
    out = [
        {
            "zeit": l.get("zeitpunkt"),
            "text": f"{l.get('aktion','')} | {l.get('details','')}".strip(" |"),
            "benutzer": l.get("benutzer", "system"),
            "ip": l.get("ip_adresse", ""),
        }
        for l in logs_sorted[:limit]
    ]
    return ok_compat({
        "gesamt": len(logs),
        "angezeigt": len(out),
        "logs": out,
    })


@app.get("/audit/policies", tags=["System"], summary="Audit-Policy Alerts (regelbasiert)")
def audit_policies(_user: dict = Depends(require_permission("reports:read"))):
    store = get_ds(_user)
    kid = store.kanzlei_id
    alerts: List[Dict[str, Any]] = []
    conn = store._conn()

    dead_mail = conn.execute(
        "SELECT COUNT(*) AS n FROM email_outbox WHERE kanzlei_id = ? AND status = 'dead' AND created_at >= datetime('now','-24 hours')",
        (kid,),
    ).fetchone()["n"]
    if dead_mail >= 3:
        alerts.append({
            "severity": "high",
            "policy": "email_delivery",
            "title": "Mehrere Emails endgültig fehlgeschlagen",
            "details": f"{dead_mail} Dead-Letter in den letzten 24h",
        })

    failed_webhooks = conn.execute(
        "SELECT COUNT(*) AS n FROM webhook_queue WHERE kanzlei_id = ? AND status IN ('failed','dead') AND created_at >= datetime('now','-24 hours')",
        (kid,),
    ).fetchone()["n"]
    if failed_webhooks >= 5:
        alerts.append({
            "severity": "medium",
            "policy": "webhook_delivery",
            "title": "Webhook Zustellungen instabil",
            "details": f"{failed_webhooks} fehlgeschlagene Webhook-Events in 24h",
        })

    settings_changes = usage_get(kid, "settings_changes_day")
    if settings_changes >= 20:
        alerts.append({
            "severity": "low",
            "policy": "settings_churn",
            "title": "Viele Settings-Änderungen heute",
            "details": f"{settings_changes} Änderungen — mögliche Fehlkonfiguration prüfen",
        })

    return ok({"alerts": alerts, "count": len(alerts)})


@app.get("/ai/usecases", tags=["System"], summary="KI Use-Case Katalog")
def ai_usecases(_user: dict = Depends(require_permission("reports:read"))):
    return ok({
        "usecases": [
            {"id": "auto_reply", "name": "Automatische Antworten", "value_metric": "Antwortzeit sinkt"},
            {"id": "doc_processing", "name": "Dokumentenverarbeitung", "value_metric": "Durchsatz steigt"},
            {"id": "deadline_detection", "name": "Fristen-Erkennung", "value_metric": "Fristversäumnisse sinken"},
        ],
        "recommended_start": ["/dokumente/analysieren", "/prognose/fristen", "/bot/analyse"],
    })


@app.get("/compliance/status", tags=["System"], summary="Compliance-Dateien prüfen")
def compliance_status(_user: dict = Depends(require_permission("reports:read"))):
    return ok(_compliance_status())


@app.get("/saas/readiness", tags=["SaaS"], summary="SaaS Readiness Snapshot")
def saas_readiness(_user: dict = Depends(require_permission("reports:read"))):
    store = get_ds(_user)
    kid = store.kanzlei_id
    plan = _plan_for_user(_user)
    limits = PLAN_USAGE_LIMITS.get(plan, PLAN_USAGE_LIMITS["starter"])
    usage = {
        "ai_requests_day": usage_get(kid, "ai_requests_day"),
        "exports_day": usage_get(kid, "exports_day"),
        "settings_changes_day": usage_get(kid, "settings_changes_day"),
    }
    db = store._conn()
    outbox_dead = db.execute(
        "SELECT COUNT(*) AS n FROM email_outbox WHERE kanzlei_id = ? AND status = 'dead' AND created_at >= datetime('now','-24 hours')",
        (kid,),
    ).fetchone()["n"]
    webhooks_failed = db.execute(
        "SELECT COUNT(*) AS n FROM webhook_queue WHERE kanzlei_id = ? AND status IN ('failed','dead') AND created_at >= datetime('now','-24 hours')",
        (kid,),
    ).fetchone()["n"]
    api_keys = api_key_list(kid)
    webhooks = webhook_endpoint_list(kid)
    alerts = audit_policies(_user).get("data", {}).get("alerts", [])
    compliance = _compliance_status()

    score = 100
    if outbox_dead >= 3:
        score -= 20
    if webhooks_failed >= 5:
        score -= 20
    if len(api_keys) == 0:
        score -= 10
    if len(webhooks) == 0:
        score -= 10
    if compliance.get("percent", 0) < 100:
        score -= 10
    for metric, lim in limits.items():
        val = usage.get(metric, 0)
        if lim and val / max(1, lim) > 0.9:
            score -= 10
    score = max(0, min(100, score))

    return ok({
        "kanzlei_id": kid,
        "plan": plan,
        "readiness_score": score,
        "health": {
            "email_outbox_dead_24h": outbox_dead,
            "webhook_failures_24h": webhooks_failed,
            "api_keys_aktiv": len([k for k in api_keys if k.get("aktiv")]),
            "webhooks_aktiv": len([w for w in webhooks if w.get("aktiv")]),
        },
        "usage_today": usage,
        "limits": limits,
        "alerts": alerts,
        "compliance": compliance,
        "checked_at": datetime.now().isoformat(),
    })


# ============================================================
# AUTO-AGENT (HINTERGRUND-WORKER)
# ============================================================

_agent_running = False   # FIX: Double-Execution verhindern
_agent_owner = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"


def _try_acquire_agent_lock(ttl_seconds: int = 290) -> bool:
    """
    Prozessübergreifender Lock (SQLite), damit bei mehreren Workern
    nicht mehrere Auto-Agents parallel laufen.
    """
    from core.daten_speicher import get_connection

    now = int(time.time())
    exp = now + ttl_seconds
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_locks (
            name TEXT PRIMARY KEY,
            owner TEXT NOT NULL,
            expires_at INTEGER NOT NULL
        )
    """)
    conn.execute("""
        INSERT INTO agent_locks (name, owner, expires_at)
        VALUES ('auto_agent', ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            owner = excluded.owner,
            expires_at = excluded.expires_at
        WHERE agent_locks.expires_at < ? OR agent_locks.owner = ?
    """, (_agent_owner, exp, now, _agent_owner))
    row = conn.execute(
        "SELECT owner, expires_at FROM agent_locks WHERE name = 'auto_agent'"
    ).fetchone()
    return bool(row and row["owner"] == _agent_owner and int(row["expires_at"]) >= now)


def _release_agent_lock() -> None:
    from core.daten_speicher import get_connection

    conn = get_connection()
    conn.execute(
        "UPDATE agent_locks SET expires_at = 0 WHERE name = 'auto_agent' AND owner = ?",
        (_agent_owner,),
    )
    conn.commit()

async def auto_agent_worker():
    """
    Autonomer Hintergrund-Agent:
    - Läuft alle 5 Minuten
    - Nutzt neue Decision Engine (Risiko + Umsatz)
    - Sendet automatisch HTML-Emails bei kritischen Mandanten
    - FIX: Double-Execution verhindert
    - FIX: Logging für jede Aktion
    - FIX: Cooldown 24h pro Mandant (kein Spam)
    """
    global _agent_running

    await asyncio.sleep(15)  # Startup-Delay

    while True:
        if not _try_acquire_agent_lock():
            log.debug("Auto-Agent: Worker-Lock aktiv, Runde übersprungen")
            await asyncio.sleep(300)
            continue
        if _agent_running:
            log.warning("Auto-Agent: bereits läuft — überspringe Runde")
            await asyncio.sleep(300)
            continue

        _agent_running = True
        try:
            log.info("Auto-Agent: Analyse gestartet")
            from core.decision_engine import analysiere_alle_mandanten

            alle      = analysiere_alle_mandanten(ds)
            aktionen  = 0
            emails    = 0
            today     = datetime.now().strftime("%Y-%m-%d")

            for mandant_data in alle:
                name   = mandant_data.get("mandant", "")
                status = mandant_data.get("status", "OK")
                empf   = mandant_data.get("empfehlung", {})
                aktion = empf.get("aktion", "nichts")

                if not name:
                    continue

                try:
                    # Nur kritische + wichtige Mandanten automatisch kontaktieren
                    if status not in ("KRITISCH", "WICHTIG"):
                        continue

                    # Aktion muss Email sein
                    if aktion not in ("email_now", "sofort_anrufen", "followup"):
                        continue

                    action_key = hashlib.sha256(
                        f"{ds.kanzlei_id}|{name}|{aktion}|{today}".encode("utf-8")
                    ).hexdigest()
                    reserved = agent_action_record(
                        kanzlei_id=ds.kanzlei_id,
                        action_key=action_key,
                        mandant=name,
                        aktion=aktion,
                        status="planned",
                        details=f"status={status}",
                    )
                    if not reserved:
                        log.debug(f"Agent: {name} — Aktion bereits heute verarbeitet")
                        continue

                    # Cooldown: max. 1 Email pro 24h
                    if not darf_email_senden(name, 24):
                        agent_action_update(
                            ds.kanzlei_id,
                            action_key,
                            "skipped_cooldown",
                            "bereits innerhalb 24h versendet",
                        )
                        log.debug(f"Agent: {name} — Cooldown aktiv")
                        continue

                    # Email senden
                    success = _email_fuer_mandant_senden(name)
                    if success:
                        agent_action_update(
                            ds.kanzlei_id,
                            action_key,
                            "queued",
                            "email in outbox eingereiht",
                        )
                        emails   += 1
                        aktionen += 1
                        log.info(
                            f"Auto-Agent: Email → {name} | "
                            f"Status: {status} | Aktion: {aktion}"
                        )
                    else:
                        agent_action_update(
                            ds.kanzlei_id,
                            action_key,
                            "failed",
                            "enqueue fehlgeschlagen",
                        )
                        log.debug(f"Auto-Agent: Email nicht gesendet für {name} (kein Empfänger oder SMTP-Fehler)")

                except Exception as ex:
                    log.warning(f"Auto-Agent: Fehler für '{name}': {ex}")

            if aktionen:
                ds.log_eintrag(
                    f"AUTO_AGENT | {aktionen} Aktionen | {emails} Emails | {today}"
                )
            else:
                log.info("Auto-Agent: Keine Aktionen nötig")

        except Exception as e:
            log.error(f"Auto-Agent kritischer Fehler: {e}")
        finally:
            _agent_running = False
            _release_agent_lock()

        await asyncio.sleep(300)  # 5 Minuten


# ============================================================
# WORKFLOWS — One-Click Automatisierung
# ============================================================

@app.post("/workflow/monatsabschluss/{name}", tags=["Workflows"],
          summary="Monatsabschluss-Workflow starten")
def workflow_monatsabschluss(
    name: str,
    monat: int = Query(default=None, ge=1, le=12),
    jahr: int  = Query(default=None, ge=2020, le=2099),
    _user: dict = Depends(get_current_user),
):
    """
    Erstellt automatisch alle Standardaufgaben für einen Monatsabschluss.
    Spart 20-30 Minuten manuelle Aufgaben-Erstellung.
    """
    store = get_ds(_user)
    get_mandant_or_404(name, store)
    from core.engine import Engine

    jetzt = datetime.now()
    engine = Engine(store)
    result = engine.workflow_monatsabschluss(
        name,
        monat or jetzt.month,
        jahr  or jetzt.year
    )
    _track_action_for_suggestions(store, "workflow_monatsabschluss")
    return ok_compat(result)


@app.post("/workflow/jahresabschluss/{name}", tags=["Workflows"],
          summary="Jahresabschluss-Workflow starten")
def workflow_jahresabschluss(
    name: str,
    jahr: int = Query(default=None, ge=2020, le=2099),
    _user: dict = Depends(get_current_user),
):
    """
    Erstellt automatisch alle Standardaufgaben für einen Jahresabschluss.
    Inklusive Bilanz, GuV, Steuererklärung — komplett vorbereitet.
    """
    store = get_ds(_user)
    get_mandant_or_404(name, store)
    from core.engine import Engine

    engine = Engine(store)
    result = engine.workflow_jahresabschluss(name, jahr or datetime.now().year)
    _track_action_for_suggestions(store, "workflow_jahresabschluss")
    return ok_compat(result)


@app.post("/workflow/onboarding/{name}", tags=["Workflows"],
          summary="Onboarding-Workflow für neuen Mandanten")
def workflow_onboarding(name: str, _user: dict = Depends(get_current_user)):
    """
    Startet den Onboarding-Workflow für einen neuen Mandanten.
    Legt alle Erstaufgaben an + bereitet Willkommens-Email vor.
    """
    store = get_ds(_user)
    get_mandant_or_404(name, store)
    from core.engine import Engine

    engine = Engine(store)
    result = engine.workflow_neuer_mandant(name)
    _track_action_for_suggestions(store, "workflow_onboarding")
    return ok_compat(result)


# ============================================================
# ENGINE — Manuelle Steuerung & Trigger
# ============================================================

@app.post("/engine/run", tags=["Engine"], summary="Engine manuell triggern")
def engine_run(background_tasks: BackgroundTasks, _user: dict = Depends(get_current_user)):
    """
    Führt alle Daily Checks sofort aus (ohne auf den Auto-Agent zu warten).
    Nützlich nach Datenänderungen oder für manuelle Kontrolle.
    """
    from core.engine import Engine
    store = get_ds(_user)

    def run():
        engine = Engine(store)
        result = engine.run_daily_checks()
        log.info(f"Engine manuell getriggert | {result.get('mandanten_geprueft', 0)} Mandanten")

    background_tasks.add_task(run)
    _track_action_for_suggestions(store, "engine_run_manual")
    return ok_compat({
        "status":    "gestartet",
        "hinweis":   "Engine läuft im Hintergrund",
        "timestamp": datetime.now().isoformat()
    })


@app.get("/engine/analyse", tags=["Engine"], summary="Vollständige KI-Analyse aller Mandanten")
def engine_analyse(_user: dict = Depends(get_current_user)):
    """
    Analysiert alle Mandanten mit der Decision Engine.
    Gibt Scores, Status und Handlungsempfehlungen für alle zurück.
    """
    from core.engine import Engine
    store = get_ds(_user)

    engine = Engine(store)
    _track_action_for_suggestions(store, "engine_analyse")
    return ok_compat(engine.run_full_analysis())


@app.get("/engine/bericht", tags=["Engine"], summary="Automatischer Tagesbericht")
def engine_bericht(_user: dict = Depends(get_current_user)):
    """
    Generiert den automatischen Tagesbericht als Text.
    Zusammenfassung aller wichtigen Ereignisse für den Steuerberater.
    """
    from core.engine import Engine
    store = get_ds(_user)

    engine = Engine(store)
    bericht = engine.erstelle_tagesbericht()
    return ok_compat({
        "bericht":       bericht,
        "generiert_am":  datetime.now().isoformat()
    })


# ============================================================
# PREDICTIVE ANALYTICS
# ============================================================

@app.get("/prognose/fristen", tags=["Analyse"], summary="Fristen-Belastungsprognose")
def prognose_fristen(
    tage: int = Query(default=30, ge=1, le=365,
                      description="Vorschau-Zeitraum in Tagen"),
    _user: dict = Depends(get_current_user),
):
    """
    Berechnet die Fristen-Belastung für die nächsten N Tage.
    Hilft bei der Kapazitätsplanung: Wann wird es stressig?
    """
    from core.engine import Engine
    store = get_ds(_user)

    engine = Engine(store)
    return ok_compat(engine.predictive_fristenbelastung(tage))


@app.get("/prognose/umsatz", tags=["Analyse"], summary="Umsatz- & Risiko-Prognose")
def prognose_umsatz(_user: dict = Depends(get_current_user)):
    """
    Umsatz-Prognose + Risiko-Score basierend auf offenen Aufgaben.
    Basis für Cashflow-Planung und Ressourcen-Management.
    """
    from core.engine import Engine
    store = get_ds(_user)

    engine = Engine(store)
    return ok_compat(engine.predictive_umsatz_prognose())


@app.get("/prognose/steuerfristen", tags=["Analyse"],
         summary="Gesetzliche Steuerfristen (Deutschland)")
def prognose_steuerfristen(jahr: int = Query(default=None), _user: dict = Depends(get_current_user)):
    """
    Alle gesetzlichen Steuerfristen für ein Jahr.
    Compliance: Lohnsteuer, USt, Körperschaftsteuer, Gewerbesteuer, Jahresabschluss.
    """
    from core.engine import berechne_steuerfristen

    ziel_jahr = jahr or datetime.now().year
    fristen   = berechne_steuerfristen(ziel_jahr)
    jetzt     = datetime.now()

    # Dringlichkeit ergänzen
    for f in fristen:
        try:
            datum = datetime.strptime(f["datum"], "%Y-%m-%d")
            f["tage_bis_frist"] = (datum - jetzt).days
            f["dringend"]  = 0 <= f["tage_bis_frist"] <= 14
            f["ueberfaellig"] = f["tage_bis_frist"] < 0
        except ValueError:
            pass

    return ok_compat({
        "jahr":          ziel_jahr,
        "anzahl":        len(fristen),
        "fristen":       fristen,
        "generiert_am":  jetzt.isoformat()
    })


# ============================================================
# TIMELINE & KOMMUNIKATION
# ============================================================

@app.get("/timeline/{name}", tags=["Kommunikation"],
         summary="Kommunikations-Timeline eines Mandanten")
def get_timeline(name: str, limit: int = Query(50, ge=1, le=500),
    _user: dict = Depends(get_current_user)):
    """
    Vollständige Timeline aller Kontakte, Emails und Aktionen für einen Mandanten.
    Revisionssicher — jede Interaktion wird erfasst.
    """
    store = get_ds(_user)
    get_mandant_or_404(name, store)
    timeline = store.timeline_laden(name)
    sortiert = sorted(timeline, key=lambda x: x.get("timestamp", ""), reverse=True)
    return ok_compat({
        "mandant":  name,
        "anzahl":   len(sortiert),
        "timeline": sortiert[:limit]
    })


@app.get("/kommunikation/{name}", tags=["Kommunikation"],
         summary="Kommunikations-History eines Mandanten")
def get_kommunikation(name: str, limit: int = Query(50, ge=1, le=200),
    _user: dict = Depends(get_current_user)):
    """
    Alle Kommunikationseinträge (Emails, Notizen, Anrufe) für einen Mandanten.
    """
    store = get_ds(_user)
    get_mandant_or_404(name, store)
    komm     = store.hole_kommunikation(name)
    sortiert = sorted(komm, key=lambda x: x.get("timestamp", x.get("zeit", "")), reverse=True)
    return ok_compat({
        "mandant":        name,
        "anzahl":         len(sortiert),
        "kommunikation":  sortiert[:limit]
    })


@app.post("/kommunikation/{name}", tags=["Kommunikation"],
          summary="Kommunikationseintrag manuell hinzufügen")
def add_kommunikation(name: str, data: dict,
    _user: dict = Depends(get_current_user)):
    """
    Manuellen Kommunikationseintrag speichern (Anruf, Meeting, Notiz).
    """

    store = get_ds(_user)
    get_mandant_or_404(name, store)

    eintrag = {
        "typ":       data.get("typ", "manuell"),
        "text":      data.get("text", ""),
        "timestamp": datetime.now().isoformat(),
    }

    store.kommunikation_hinzufuegen(name, eintrag)

    # Letzte Antwort aktualisieren wenn Typ "antwort" oder "anruf"
    if eintrag["typ"] in ["antwort", "anruf", "meeting"]:
        m = store.hole_mandanten().get(name, {})
        m["letzte_antwort"] = datetime.now().isoformat()
        store.mandant_speichern(name, m)

    store.log_eintrag(f"KOMMUNIKATION | {name} | {eintrag['typ']}")
    return ok_compat({"status": "ok", "eintrag": eintrag})


# ============================================================
# SETTINGS
# ============================================================

@app.get("/settings", tags=["System"], summary="Alle Systemeinstellungen laden (alle 6 Kategorien)")
def get_settings(_user: dict = Depends(get_current_user)):
    """
    Alle Systemeinstellungen — 100+ Keys in 6 Kategorien.
    Festgeschriebene Werte (GoBD, Audit) sind klar markiert.
    """
    svc = SettingsService(get_ds(_user))
    return ok_compat(svc.get_all())


@app.put("/settings", tags=["System"], summary="Systemeinstellung ändern")
def update_setting(data: dict,
    _user: dict = Depends(require_permission("settings:write"))):
    """
    Systemeinstellung ändern — alle 100+ Keys aus DEFAULT_SETTINGS erlaubt.
    Festgeschriebene Werte (gobd_konform, audit_unveraenderbar) werden abgelehnt.
    Format: {"key": "ki_autonomie_grad", "wert": 85}
    """

    store = get_ds(_user)
    svc = SettingsService(store)

    key  = data.get("key")
    wert = data.get("wert")

    if not key:
        raise HTTPException(400, "Feld 'key' fehlt")
    if wert is None:
        raise HTTPException(400, "Feld 'wert' fehlt")

    try:
        payload = svc.update_one(key, wert)
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    usage_increment(store.kanzlei_id, "settings_changes_day", 1)
    _emit_webhook_event(store.kanzlei_id, "settings.changed", {"key": key, "wert": wert})
    _track_action_for_suggestions(store, "settings_change")
    return ok_compat(payload)


@app.put("/settings/batch", tags=["System"],
         summary="Mehrere Settings auf einmal speichern")
def update_settings_batch(updates: Dict[str, Any] = Body(...),
    _user: dict = Depends(require_permission("settings:write"))):
    """
    Mehrere Settings effizient auf einmal speichern.
    Format: {"ki_autonomie_grad": 85, "ki_lernen_kanzleiweit": true, ...}
    Festgeschriebene Werte werden übersprungen (kein Fehler).
    """

    store = get_ds(_user)
    svc = SettingsService(store)
    payload = svc.update_batch(updates)
    if payload.get("gespeichert", 0):
        usage_increment(store.kanzlei_id, "settings_changes_day", payload["gespeichert"])
        _emit_webhook_event(
            store.kanzlei_id,
            "settings.batch_changed",
            {"count": payload["gespeichert"], "keys": list(updates.keys())[:20]},
        )
        _track_action_for_suggestions(store, "settings_change")
    return ok_compat(payload)


@app.get("/settings/kategorien", tags=["System"],
         summary="Settings gruppiert nach Kategorie (für Frontend-Tabs)")
def get_settings_kategorien(_user: dict = Depends(get_current_user)):
    """
    Settings sortiert nach den 6 Profitabilitäts-Kategorien:
    ki, workflow, portal, billing, compliance, schnittstellen, kanzlei
    """
    svc = SettingsService(get_ds(_user))
    return ok_compat(svc.categories())


@app.get("/settings/festgeschrieben", tags=["System"],
         summary="Zeigt festgeschriebene Werte (nicht änderbar)")
def get_festgeschrieben(_user: dict = Depends(get_current_user)):
    """
    Zeigt welche Settings aus Compliance-Gründen festgeschrieben sind.
    GoBD-Konformität und Audit-Trail können nicht deaktiviert werden.
    """
    svc = SettingsService(get_ds(_user))
    return ok_compat(svc.fixed())


@app.post("/settings/reset", tags=["System"], summary="Settings zurücksetzen")
def reset_settings(key: Optional[str] = Query(None),
    _user: dict = Depends(require_permission("settings:write"))):
    """Settings auf Standardwerte zurücksetzen. Ohne key → alles zurücksetzen."""

    store = get_ds(_user)
    svc = SettingsService(store)
    payload = svc.reset(key)
    usage_increment(store.kanzlei_id, "settings_changes_day", 1)
    _emit_webhook_event(store.kanzlei_id, "settings.reset", {"key": key or "alle"})
    _track_action_for_suggestions(store, "settings_change")
    return ok_compat(payload)


@app.get("/settings/suggestions", tags=["System"], summary="Automatische Settings-Vorschläge")
def settings_suggestions(_user: dict = Depends(get_current_user)):
    """
    Analysiert wiederkehrende Aktionen (rolling 7 Tage) und gibt
    konkrete Setting-Vorschläge zurück.
    """
    store = get_ds(_user)
    sugs = _settings_suggestions(store)
    return ok_compat({
        "anzahl": len(sugs),
        "vorschlaege": sugs,
        "hinweis": "Vorschläge sind nicht automatisch aktiv — bewusst übernehmen.",
    })


@app.post("/settings/suggestions/{suggestion_id}/apply", tags=["System"], summary="Settings-Vorschlag anwenden")
def apply_settings_suggestion(
    suggestion_id: str,
    _user: dict = Depends(require_permission("settings:write")),
):
    store = get_ds(_user)
    from modules.settings_manager import setting_setzen, FESTGESCHRIEBEN

    sugs = _settings_suggestions(store)
    chosen = next((s for s in sugs if s.get("id") == suggestion_id), None)
    if not chosen:
        raise HTTPException(404, "Vorschlag nicht gefunden oder nicht mehr relevant")
    rec = chosen.get("empfehlung") or {}
    key = rec.get("key")
    wert = rec.get("wert")
    if not key:
        raise HTTPException(400, "Vorschlag ohne key ist ungültig")
    if key in FESTGESCHRIEBEN:
        raise HTTPException(403, f"'{key}' ist festgeschrieben und kann nicht geändert werden")
    ok_set = setting_setzen(key, wert)
    if not ok_set:
        raise HTTPException(400, f"Ungültige Empfehlung: {key}={wert}")
    store.log_eintrag(f"SETTING_SUGGESTION_APPLIED | {suggestion_id} | {key}={wert}")
    usage_increment(store.kanzlei_id, "settings_changes_day", 1)
    _emit_webhook_event(
        store.kanzlei_id,
        "settings.suggestion_applied",
        {"suggestion_id": suggestion_id, "key": key, "wert": wert},
    )
    _track_action_for_suggestions(store, "settings_change")
    return ok_compat({
        "applied": True,
        "suggestion_id": suggestion_id,
        "key": key,
        "wert": wert,
    }, "Vorschlag angewendet")


# ── Settings werden auch von beleg_service und anderen Modulen genutzt ────
def setting_holen_global(key: str):
    """Helper für andere Module — holt ein Setting aus dem zentralen Store."""
    from modules.settings_manager import setting_holen
    return setting_holen(key)


# ============================================================
# DATENBANK-INFO & EXPORT
# ============================================================

@app.get("/system/info", tags=["System"], summary="Datenbankstatus & System-Info")
def system_info(_user: dict = Depends(get_current_user)):
    """Datenbankgröße, Backup-Status, Statistiken."""
    store = get_ds(_user)
    return ok_compat(store.datenbank_info())


@app.get("/system/export", tags=["System"], summary="Vollständiger Datenexport (JSON)")
def system_export(_user: dict = Depends(require_permission("export:read"))):
    """
    Exportiert die gesamte Datenbank als JSON.
    Für Backup, Migration oder DATEV-Vorbereitung.
    """
    store = get_ds(_user)
    data = store.exportiere_json()
    store.log_eintrag("DATEN_EXPORT")
    _track_action_for_suggestions(store, "system_export")
    return ok_compat({
        "export_zeitpunkt": datetime.now().isoformat(),
        "daten":            data
    })


# ============================================================
# PLAUSIBILITÄTSPRÜFUNG
# ============================================================

@app.get("/plausibilitaet", tags=["Engine"],
         summary="Plausibilitätsprüfung aller Daten")
def plausibilitaetspruefung(_user: dict = Depends(get_current_user)):
    """
    Prüft alle Mandanten und Aufgaben auf Datenfehler.
    Findet: fehlende E-Mails, negative Umsätze, ungültige Daten,
            inaktive Mandanten, überfällige unerledigte Aufgaben.
    """
    from core.engine import pruefe_mandant_plausibilitaet, pruefe_aufgabe_plausibilitaet
    store = get_ds(_user)

    mandanten  = store.hole_mandanten()
    aufgaben   = store.hole_fristen()
    alle_fehler = []

    for name, m in mandanten.items():
        fehler = pruefe_mandant_plausibilitaet(name, m)
        alle_fehler.extend([{"mandant": name, **f} for f in fehler])

    for a in aufgaben.values():
        fehler = pruefe_aufgabe_plausibilitaet(a)
        alle_fehler.extend([{"mandant": a.get("mandant", "?"), **f} for f in fehler])

    # Nach Schwere sortieren
    schwere_order = {"hoch": 0, "mittel": 1, "niedrig": 2}
    alle_fehler.sort(key=lambda x: schwere_order.get(x.get("schwere", "niedrig"), 9))

    return ok_compat({
        "gesamt":        len(alle_fehler),
        "hoch":          sum(1 for f in alle_fehler if f.get("schwere") == "hoch"),
        "mittel":        sum(1 for f in alle_fehler if f.get("schwere") == "mittel"),
        "niedrig":       sum(1 for f in alle_fehler if f.get("schwere") == "niedrig"),
        "fehler":        alle_fehler,
        "geprueft_am":   datetime.now().isoformat()
    })


# ============================================================
# AUTH — Login, Sessions, Team-Management (Pydantic Models only)
# ============================================================

class LoginRequest(BaseModel):
    benutzername: str = Field(..., min_length=2)
    passwort:     str = Field(..., min_length=4)

class RegistrierRequest(BaseModel):
    benutzername: str  = Field(..., min_length=2, max_length=50)
    passwort:     str  = Field(..., min_length=8)
    anzeigename:  Optional[str] = None
    email:        Optional[str] = None
    rolle:        Optional[str] = Field("steuerberater")
    admin_key:    Optional[str] = None  # Für nicht-ersten Benutzer

class PasswortRequest(BaseModel):
    altes_passwort: str = Field(..., min_length=4)
    neues_passwort: str = Field(..., min_length=8)


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    permissions: Optional[List[str]] = None


class WebhookCreateRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=500)
    events: List[str] = Field(default_factory=lambda: ["email.sent", "settings.changed"])
    secret: Optional[str] = Field(None, min_length=8, max_length=120)


class ApiKeyRotateRequest(BaseModel):
    new_name: Optional[str] = Field(None, min_length=2, max_length=120)

@app.post("/auth/login", tags=["Auth"], summary="Login — Session-Token erhalten")
async def auth_login(data: LoginRequest, request: Request):
    """Login mit Rate-Limiting (max 10 Versuche/5min pro IP). Ohne vorherigen Bearer-Token."""

    from core.auth import login, setup_erstbenutzer, hat_irgendein_benutzer
    if not hat_irgendein_benutzer():
        setup_erstbenutzer()
    ip = _get_client_ip(request)
    try:
        result = login(data.benutzername, data.passwort, ip=ip)
        if not result:
            raise HTTPException(401, "Benutzername oder Passwort falsch")
        kid = result.get("kanzlei_id", "default")
        log_store = DatenSpeicher(kanzlei_id=kid)
        log_store.log_eintrag(f"LOGIN | {data.benutzername}", benutzer=data.benutzername, ip=ip)
        return ok(result, "Login erfolgreich")
    except ValueError as e:
        raise HTTPException(429, str(e))

@app.post("/auth/logout", tags=["Auth"], summary="Logout — Session beenden")
def auth_logout(authorization: Optional[str] = Header(None)):
    """Session-Token invalidieren."""
    from core.auth import logout
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
        logout(token)
    return {"status": "ok"}

@app.post("/auth/registrieren", tags=["Auth"], summary="Neuen Benutzer anlegen",
          status_code=status.HTTP_201_CREATED)
def auth_registrieren(data: RegistrierRequest):
    """
    Neuen Benutzer anlegen.
    Erster Benutzer wird automatisch Admin — kein Admin-Key nötig.
    Weitere Benutzer: Admin-Key aus .env (PORTAL_ADMIN_KEY) erforderlich.
    """

    from core.auth import erstelle_benutzer, hat_irgendein_benutzer
    import os
    if hat_irgendein_benutzer():
        expected = os.getenv("PORTAL_ADMIN_KEY", "kanzlei-admin-2024")
        import secrets as sc
        if not data.admin_key or not sc.compare_digest(data.admin_key, expected):
            raise HTTPException(403, "Admin-Key erforderlich für weitere Benutzer")
    kanzlei_id = "default"
    try:
        result = erstelle_benutzer(
            data.benutzername, data.passwort,
            rolle=data.rolle or "steuerberater",
            email=data.email or "",
            kanzlei_id=kanzlei_id,
        )
        log_store = DatenSpeicher(kanzlei_id=kanzlei_id)
        log_store.log_eintrag(f"BENUTZER_ERSTELLT | {data.benutzername} | {data.rolle}")
        return {"status": "created", **result}
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.get("/auth/me", tags=["Auth"], summary="Eigene Benutzer-Info")
def auth_me(current_user: dict = Depends(get_current_user)):
    """Gibt Info zum aktuell eingeloggten Benutzer zurück."""
    return current_user

@app.get("/auth/benutzer", tags=["Auth"], summary="Alle Benutzer (nur Admin)")
def auth_benutzer_liste(current_user: dict = Depends(require_permission("settings:write"))):
    """Alle Kanzlei-Mitarbeiter auflisten."""
    from core.auth import liste_benutzer
    if current_user.get("rolle") not in ["admin"]:
        raise HTTPException(403, "Nur für Admins")
    return liste_benutzer(current_user.get("kanzlei_id", "default"))

@app.put("/auth/passwort", tags=["Auth"], summary="Passwort ändern")
def auth_passwort(data: PasswortRequest, current_user: dict = Depends(get_current_user)):
    """Eigenes Passwort ändern."""

    store = get_ds(current_user)
    from core.auth import aendere_passwort
    kid = current_user.get("kanzlei_id", "default")
    try:
        ok = aendere_passwort(
            current_user["benutzername"], data.altes_passwort, data.neues_passwort,
            kanzlei_id=kid,
        )
        if not ok:
            raise HTTPException(400, "Altes Passwort falsch")
        store.log_eintrag(f"PASSWORT_GEAENDERT | {current_user['benutzername']}")
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.get("/auth/setup-status", tags=["Auth"], summary="Prüft ob System eingerichtet")
def auth_setup_status():
    """Prüft ob bereits Benutzer angelegt sind (für Ersteinrichtung)."""
    from core.auth import hat_irgendein_benutzer
    return {"eingerichtet": hat_irgendein_benutzer()}


# ============================================================
# BANK IMPORT — CAMT.053 / MT940
# ============================================================

@app.post("/bank/import", tags=["Bank"],
          summary="Kontoauszug importieren (CAMT.053 XML oder MT940)")
async def bank_import(
    datei: bytes = Body(..., media_type="application/octet-stream"),
    dateiname: str = Query("kontoauszug.xml", description="Dateiname inkl. Endung"),
    _user: dict = Depends(get_current_user),
):
    """
    Importiert einen Kontoauszug und ordnet Buchungen automatisch Mandanten zu.
    Unterstützt CAMT.053 XML (ISO 20022) und MT940 (SWIFT).
    Erkennt offene Posten und fehlende Zahlungen.
    """
    from core.bank_parser import importiere_kontoauszug
    store = get_ds(_user)
    try:
        mandanten = store.hole_mandanten()
        result    = importiere_kontoauszug(datei, dateiname, mandanten, store)
        return result
    except ValueError as e:
        raise HTTPException(400, f"Parse-Fehler: {e}")
    except Exception as e:
        raise HTTPException(500, f"Import-Fehler: {e}")

@app.post("/bank/import/multipart", tags=["Bank"],
          summary="Kontoauszug per Datei-Upload importieren")
async def bank_import_multipart(
    background_tasks: BackgroundTasks,
    _user: dict = Depends(get_current_user),
):
    """
    Alternativer Upload via multipart/form-data (für Browser-Formulare).
    Nutze /bank/import für direkte Binär-Uploads.
    """
    # Hinweis: Für echten File-Upload python-multipart installieren
    # und FastAPI File/UploadFile nutzen. Hier Platzhalter.
    return {"hinweis": "Für Datei-Upload: POST /bank/import mit raw bytes body"}

@app.get("/bank/buchungen", tags=["Bank"],
         summary="Importierte Buchungen abrufen")
def bank_buchungen(
    mandant: Optional[str] = Query(None),
    limit:   int           = Query(50, ge=1, le=500),
    _user: dict = Depends(get_current_user),
):
    """
    Alle importierten Bankbuchungen abrufen.
    Optional nach Mandant filtern.
    """
    store = get_ds(_user)
    # Buchungen aus Kommunikations-History lesen
    alle_buchungen = []
    if mandant:
        komm = store.hole_kommunikation(mandant)
        alle_buchungen = [k for k in komm if k.get("typ") == "bank_buchung"]
    else:
        mandanten = store.hole_mandanten()
        for name in mandanten:
            komm = store.hole_kommunikation(name)
            for k in komm:
                if k.get("typ") == "bank_buchung":
                    alle_buchungen.append({"mandant": name, **k})

    alle_buchungen.sort(
        key=lambda x: x.get("datum", x.get("timestamp", "")), reverse=True
    )
    return {
        "anzahl":    len(alle_buchungen),
        "buchungen": alle_buchungen[:limit],
    }


# ============================================================
# EXPORT ENDPUNKTE (aus export_endpoints.py integriert)
# ============================================================

@app.get("/export/{name}/excel", tags=["Export"],
         summary="Excel-Report für einen Mandanten")
def export_excel(name: str,
    _user: dict = Depends(get_current_user)):
    """Formatierter Excel-Report: Stammdaten, Aufgaben, Kommunikation."""

    store = get_ds(_user)
    from fastapi.responses import StreamingResponse
    from core.export_service import export_excel_report
    import io
    m             = get_mandant_or_404(name, store)
    aufgaben      = [a for a in store.hole_fristen().values() if a.get("mandant") == name]
    kommunikation = store.hole_kommunikation(name)
    try:
        excel_bytes = export_excel_report(name, m, aufgaben, kommunikation)
        datum       = datetime.now().strftime("%Y%m%d")
        filename    = f"{datum}_{name.replace(' ', '_')}_Report.xlsx"
        store.log_eintrag(f"EXPORT_EXCEL | {name}")
        return StreamingResponse(
            io.BytesIO(excel_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except ImportError:
        raise HTTPException(500, "openpyxl nicht installiert: pip install openpyxl")
    except Exception as e:
        raise HTTPException(500, f"Excel-Export Fehler: {e}")

@app.get("/export/{name}/datev", tags=["Export"],
         summary="DATEV Buchungsstapel CSV (EXTF v700)")
def export_datev(
    name:         str,
    berater_nr:   str = Query("1234"),
    mandanten_nr: str = Query("00000"),
    jahr:         int = Query(None),
    _user: dict = Depends(get_current_user),
):
    """DATEV EXTF v700 Buchungsstapel — direkt in DATEV importierbar."""
    from fastapi.responses import StreamingResponse
    from core.export_service import export_datev_buchungsstapel
    import io
    store = get_ds(_user)
    m        = get_mandant_or_404(name, store)
    aufgaben = [a for a in store.hole_fristen().values() if a.get("mandant") == name]
    try:
        csv_bytes = export_datev_buchungsstapel(name, m, aufgaben, berater_nr, mandanten_nr, jahr)
        datum     = datetime.now().strftime("%Y%m%d")
        filename  = f"EXTF_{datum}_{name.replace(' ', '_')}_Buchungsstapel.csv"
        store.log_eintrag(f"EXPORT_DATEV | {name}")
        return StreamingResponse(
            io.BytesIO(csv_bytes),
            media_type="text/csv; charset=windows-1252",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        raise HTTPException(500, f"DATEV Export Fehler: {e}")

@app.get("/export/datev/stammdaten", tags=["Export"],
         summary="DATEV Stammdaten aller Mandanten als Debitoren")
def export_datev_stammdaten_ep(berater_nr: str = Query("1234"),
    _user: dict = Depends(get_current_user)):
    """Alle Mandanten als DATEV-Debitorenstammdaten exportieren."""

    store = get_ds(_user)
    from fastapi.responses import StreamingResponse
    from core.export_service import export_datev_stammdaten
    import io
    mandanten = store.hole_mandanten()
    if not mandanten:
        raise HTTPException(404, "Keine Mandanten vorhanden")
    try:
        csv_bytes = export_datev_stammdaten(mandanten, berater_nr)
        datum     = datetime.now().strftime("%Y%m%d")
        store.log_eintrag("EXPORT_DATEV_STAMMDATEN")
        return StreamingResponse(
            io.BytesIO(csv_bytes),
            media_type="text/csv; charset=windows-1252",
            headers={"Content-Disposition": f'attachment; filename="EXTF_{datum}_Stammdaten.csv"'}
        )
    except Exception as e:
        raise HTTPException(500, f"Stammdaten Export Fehler: {e}")

@app.get("/export/{name}/elster", tags=["Export"],
         summary="ELSTER-kompatibles XML (UStVA / GewSt)")
def export_elster(
    name:      str,
    steuerart: str = Query("UStVA", description="UStVA | GewSt"),
    jahr:      int = Query(None),
    quartal:   int = Query(None, ge=1, le=4),
    _user: dict = Depends(get_current_user),
):
    """ELSTER ERiC Transfer-XML — für UStVA und Gewerbesteuer."""
    from fastapi.responses import StreamingResponse
    from core.export_service import export_elster_xml
    import io
    store = get_ds(_user)
    m = get_mandant_or_404(name, store)
    try:
        xml_bytes = export_elster_xml(name, m, steuerart, jahr, quartal)
        datum     = datetime.now().strftime("%Y%m%d")
        filename  = f"{datum}_{name.replace(' ', '_')}_{steuerart}.xml"
        store.log_eintrag(f"EXPORT_ELSTER | {name} | {steuerart}")
        return StreamingResponse(
            io.BytesIO(xml_bytes),
            media_type="application/xml",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        raise HTTPException(500, f"ELSTER Export Fehler: {e}")

@app.get("/export/csv/mandanten", tags=["Export"],
         summary="Alle Mandanten als CSV")
def export_csv_mandanten_ep(_user: dict = Depends(get_current_user)):
    """Alle Mandanten als UTF-8 CSV (Excel-kompatibel)."""
    from fastapi.responses import StreamingResponse
    from core.export_service import export_csv_mandanten
    import io
    store = get_ds(_user)
    csv_bytes = export_csv_mandanten(store.hole_mandanten())
    datum     = datetime.now().strftime("%Y%m%d")
    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{datum}_Mandanten.csv"'}
    )

@app.get("/export/csv/aufgaben", tags=["Export"],
         summary="Alle Aufgaben als CSV")
def export_csv_aufgaben_ep(_user: dict = Depends(get_current_user)):
    """Alle Aufgaben als UTF-8 CSV."""
    from fastapi.responses import StreamingResponse
    from core.export_service import export_csv_aufgaben
    import io
    store = get_ds(_user)
    csv_bytes = export_csv_aufgaben(store.hole_fristen())
    datum     = datetime.now().strftime("%Y%m%d")
    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{datum}_Aufgaben.csv"'}
    )

@app.get("/export/{name}/komplett", tags=["Export"],
         summary="Komplett-Paket ZIP (DATEV + ELSTER + Excel + CSV)")
def export_komplett(name: str, _user: dict = Depends(get_current_user)):
    """
    ZIP mit allem: DATEV Buchungsstapel + Stammdaten, ELSTER XML,
    Excel-Report, Mandanten-CSV, Aufgaben-CSV + README.
    Ein Klick — alles für DATEV/Finanzamt.
    """
    from fastapi.responses import StreamingResponse
    from core.export_service import export_komplettpaket
    import io
    store = get_ds(_user)
    m              = get_mandant_or_404(name, store)
    alle_mandanten = store.hole_mandanten()
    alle_aufgaben  = store.hole_fristen()
    aufgaben_list  = [a for a in alle_aufgaben.values() if a.get("mandant") == name]
    kommunikation  = store.hole_kommunikation(name)
    try:
        zip_bytes = export_komplettpaket(
            name, m, aufgaben_list, alle_mandanten, alle_aufgaben, kommunikation
        )
        datum    = datetime.now().strftime("%Y%m%d")
        filename = f"{datum}_{name.replace(' ', '_')}_KanzleiAI_Export.zip"
        store.log_eintrag(f"EXPORT_KOMPLETT | {name}")
        return StreamingResponse(
            io.BytesIO(zip_bytes),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        log.error(f"Komplett-Export Fehler: {e}")
        raise HTTPException(500, f"Export Fehler: {e}")


# ============================================================
# PORTAL ADMIN (in Haupt-API integriert)
# ============================================================

@app.post("/portal/admin/token/{mandant}", tags=["Portal"],
          summary="Zugangs-Link für Mandantenportal generieren")
def generiere_portal_token(
    mandant:   str,
    admin_key: str = Query(..., description="Admin-Key aus .env"),
    _user: dict = Depends(get_current_user),
):
    """
    Generiert einen sicheren Login-Link für das Mandantenportal.
    Link ist 7 Tage gültig und kann per Email an den Mandanten gesendet werden.
    """
    import os, secrets as sc
    expected = os.getenv("PORTAL_ADMIN_KEY", "kanzlei-admin-2024")
    if not sc.compare_digest(admin_key, expected):
        raise HTTPException(403, "Ungültiger Admin-Key")
    store = get_ds(_user)
    get_mandant_or_404(mandant, store)
    try:
        import sys
        sys.path.insert(0, ".")
        from portal_api import erstelle_token
        token    = erstelle_token(mandant)
        port     = os.getenv("PORTAL_PORT", "8001")
        base_url = os.getenv("PORTAL_BASE_URL", f"http://localhost:{port}")
        link     = f"{base_url}/portal?token={token}"
        store.log_eintrag(f"PORTAL_TOKEN_ERSTELLT | {mandant}")
        return {
            "mandant":     mandant,
            "token":       token,
            "link":        link,
            "gueltig_tage": 7,
            "hinweis":     "Link per Email an Mandanten senden",
        }
    except ImportError:
        raise HTTPException(500, "portal_api.py nicht gefunden — bitte neben api.py ablegen")


# ============================================================
# DOKUMENT SCANNER — KI-Analyse & Speichern
# ============================================================

class DokumentAnalyseRequest(BaseModel):
    dateiname:   str
    inhalt_b64:  str
    dateityp:    str = "application/pdf"

class DokumentSpeichernRequest(BaseModel):
    dateiname:   str
    doktyp:      str = "sonstiges"
    ordner:      str = "Sonstiges"
    mandant:     Optional[str] = ""
    datum:       Optional[str] = None
    absender:    Optional[str] = None
    betrag:      Optional[float] = None
    notiz:       Optional[str] = None
    aufgabe:     Optional[str] = None
    frist:       Optional[str] = None
    signatur:    Optional[str] = None  # Base64 PNG
    inhalt_b64:  Optional[str] = None

DOKUMENT_SYSTEM_PROMPT = """Du bist ein KI-Dokumentenanalyst für eine deutsche Steuerkanzlei.
Analysiere das Dokument und antworte NUR mit JSON:

{
  "doktyp": "rechnung|kontoauszug|steuerbescheid|jahresabschluss|vertrag|lohnabrechnung|mahnung|korrespondenz|sonstiges",
  "ordner": "Vorgeschlagener Ordnerpfad z.B. Rechnungen/Eingang",
  "datum": "YYYY-MM-DD oder leer",
  "absender": "Name des Absenders",
  "empfaenger": "Name des Empfängers",
  "betrag": 0.00,
  "mandant": "Mandantenname falls erkennbar, sonst leer",
  "aufgabe": "Empfohlene Aufgabe z.B. 'Bis 30.06. Steuerbescheid prüfen' oder leer",
  "frist": "YYYY-MM-DD Frist falls vorhanden",
  "ki_zusammenfassung": "2-3 Sätze: Was ist das, was muss getan werden?",
  "konfidenz": 0.85
}"""

@app.post("/dokumente/analysieren", tags=["Dokument-Scanner"],
          summary="Dokument mit KI analysieren — Typ, Ordner, Metadaten")
async def dokument_analysieren(data: DokumentAnalyseRequest,
    _user: dict = Depends(get_current_user)):
    """
    KI analysiert ein hochgeladenes Dokument:
    - Erkennt Dokumenttyp (Rechnung, Bescheid, Vertrag...)
    - Liest Metadaten (Datum, Betrag, Absender)
    - Schlägt Ziel-Ordner vor
    - Empfiehlt Aufgaben mit Fristen
    Alles editierbar bevor es gespeichert wird.
    """

    store = get_ds(_user)
    import base64
    import httpx

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        # Fallback ohne KI: intelligente Guess basierend auf Dateinamen
        name_lower = data.dateiname.lower()
        doktyp = "sonstiges"
        ordner = "Sonstiges"
        if any(x in name_lower for x in ["rechnung", "invoice", "re-"]):
            doktyp, ordner = "rechnung", "Rechnungen/Eingang"
        elif any(x in name_lower for x in ["konto", "auszug", "kontoauszug"]):
            doktyp, ordner = "kontoauszug", "Bank/Kontoauszüge"
        elif any(x in name_lower for x in ["bescheid", "finanzamt"]):
            doktyp, ordner = "steuerbescheid", "Steuerbescheide"
        elif any(x in name_lower for x in ["vertrag", "contract"]):
            doktyp, ordner = "vertrag", "Verträge"
        elif any(x in name_lower for x in ["lohn", "gehalt", "payslip"]):
            doktyp, ordner = "lohnabrechnung", "Lohnbuchhaltung"

        return {
            "doktyp": doktyp, "ordner": ordner,
            "datum": "", "absender": "", "empfaenger": "", "betrag": 0.0,
            "mandant": "", "aufgabe": "", "frist": "",
            "ki_zusammenfassung": f"KI nicht konfiguriert (OPENAI_API_KEY fehlt). Dateiname deutet auf '{doktyp}' hin. Bitte manuell prüfen.",
            "konfidenz": 0.3,
        }

    try:
        import base64 as b64lib
        bild_bytes = b64lib.b64decode(data.inhalt_b64)
        bild_b64   = b64lib.standard_b64encode(bild_bytes).decode()

        # Mime-Type bestimmen
        name_lower = data.dateiname.lower()
        if name_lower.endswith(".pdf"):
            media_type = "application/pdf"
        elif name_lower.endswith(".png"):
            media_type = "image/png"
        else:
            media_type = "image/jpeg"

        payload = {
            "model":      "gpt-4o",
            "max_tokens": 800,
            "messages": [
            {"role": "system", "content": DOKUMENT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{{media_type}};base64,{{bild_b64}}", "detail": "high"}},
                    {"type": "text", "text": f"Analysiere dieses Dokument: {data.dateiname}"},
                ]
            }]
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )

        if response.status_code != 200:
            raise RuntimeError(f"OpenAI Fehler {response.status_code}")

        raw_text = response.json().get("content", [{}])[0].get("text", "{}").strip()

        # JSON extrahieren
        import re as _re
        match = _re.search(r"\{.*\}", raw_text, _re.DOTALL)
        if match:
            raw_text = match.group(0)

        import json as _json
        result = _json.loads(raw_text)
        store.log_eintrag(f"DOKUMENT_ANALYSIERT | {data.dateiname} | {result.get('doktyp','?')}")
        return result

    except Exception as e:
        log.warning(f"Dokument-Analyse Fehler: {e}")
        return {
            "doktyp": "sonstiges", "ordner": "Sonstiges",
            "datum": "", "absender": "", "empfaenger": "", "betrag": 0.0,
            "mandant": "", "aufgabe": "", "frist": "",
            "ki_zusammenfassung": f"Automatische Analyse nicht möglich: {str(e)[:100]}. Bitte manuell zuordnen.",
            "konfidenz": 0.0,
        }


@app.post("/dokumente/speichern", tags=["Dokument-Scanner"],
          summary="Analysiertes Dokument in Ordner speichern")
def dokument_speichern_scanner(data: DokumentSpeichernRequest,
    _user: dict = Depends(get_current_user)):
    """
    Speichert ein geprüftes Dokument nach Bestätigung durch den Steuerberater.
    Legt Ordnerstruktur automatisch an. Verknüpft mit Mandant.
    """

    store = get_ds(_user)
    import base64

    # Ordner anlegen
    basis = os.path.join("data", "dokumente")
    if data.mandant:
        ziel_ordner = os.path.join(basis, data.mandant.replace(" ", "_"), data.ordner)
    else:
        ziel_ordner = os.path.join(basis, data.ordner)
    os.makedirs(ziel_ordner, exist_ok=True)

    # Datei speichern
    datei_pfad = os.path.join(ziel_ordner, data.dateiname)
    if data.inhalt_b64:
        try:
            bild_bytes = base64.b64decode(data.inhalt_b64)
            with open(datei_pfad, "wb") as f:
                f.write(bild_bytes)
        except Exception:
            pass

    # Signatur separat speichern
    if data.signatur and data.signatur.startswith("data:image"):
        try:
            sig_data = base64.b64decode(data.signatur.split(",")[1])
            sig_pfad = datei_pfad.replace(".", "_signiert.")
            with open(sig_pfad + ".png", "wb") as f:
                f.write(sig_data)
        except Exception:
            pass

    # In Datenbank vermerken
    dok_eintrag = {
        "dateiname":  data.dateiname,
        "doktyp":     data.doktyp,
        "ordner":     data.ordner,
        "mandant":    data.mandant,
        "datum":      data.datum,
        "absender":   data.absender,
        "betrag":     data.betrag,
        "notiz":      data.notiz,
        "pfad":       datei_pfad,
        "signiert":   bool(data.signatur),
        "gespeichert_am": datetime.now().isoformat(),
    }

    docs = _kv_get(store, "__gescannte_dokumente_v1", [])
    if not isinstance(docs, list):
        docs = []
    docs.append(dok_eintrag)
    _kv_set(store, "__gescannte_dokumente_v1", docs)

    # Kommunikations-Eintrag für Mandant
    if data.mandant and data.mandant in store.hole_mandanten():
        store.kommunikation_hinzufuegen(data.mandant, {
            "typ": "dokument_gespeichert",
            "text": f"Dokument gespeichert: {data.dateiname} → {data.ordner}",
            "timestamp": datetime.now().isoformat(),
        })

    store.log_eintrag(f"DOKUMENT_GESPEICHERT | {data.mandant} | {data.dateiname} | {data.ordner}")

    return {
        "status": "gespeichert",
        "pfad":   datei_pfad,
        "ordner": data.ordner,
    }


@app.get("/dokumente/liste", tags=["Dokument-Scanner"],
         summary="Alle gescannten Dokumente")
def gescannte_dokumente_liste(mandant: Optional[str] = Query(None),
    _user: dict = Depends(get_current_user)):
    """Alle gespeicherten Dokumente aus dem Scanner."""
    store = get_ds(_user)
    docs = _kv_get(store, "__gescannte_dokumente_v1", [])
    if not isinstance(docs, list):
        docs = []
    if mandant:
        docs = [d for d in docs if d.get("mandant") == mandant]
    return {"dokumente": docs, "anzahl": len(docs)}


# ============================================================
# BELEGE — KI-gestützte Belegverarbeitung
# ============================================================

class BelegAnalyseRequest(BaseModel):
    dateiname:   str            = Field(..., min_length=2)
    inhalt_b64:  str            = Field(..., description="Base64-kodierter Bildinhalt")
    mandant:     Optional[str]  = ""

class BelegKorrektur(BaseModel):
    betrag_brutto:            Optional[float] = None
    betrag_netto:             Optional[float] = None
    mwst_betrag:              Optional[float] = None
    mwst_satz:                Optional[int]   = None
    datum:                    Optional[str]   = None
    lieferant:                Optional[str]   = None
    kategorie:                Optional[str]   = None
    skr03_soll:               Optional[str]   = None
    skr03_haben:              Optional[str]   = None
    buchungstext:             Optional[str]   = None
    mandant:                  Optional[str]   = None
    vorsteuer_abzugsfaehig:   Optional[bool]  = None

@app.post("/belege/analysieren", tags=["Belege"],
          summary="Beleg mit KI analysieren (Claude Vision)")
async def beleg_analysieren(data: BelegAnalyseRequest, _user: dict = Depends(get_current_user)):
    """
    Analysiert einen Beleg mit Claude Vision API.
    Erkennt automatisch: Betrag, Datum, Kategorie, SKR03-Konto, MwSt-Satz.
    Spart 3-5 Minuten pro Beleg — bei 50 Belegen/Tag = 4h täglich.
    """
    import base64
    from core.beleg_service import analysiere_beleg, beleg_speichern
    store = get_ds(_user)

    api_key = os.getenv("OPENAI_API_KEY", "")
    try:
        bild_bytes = base64.b64decode(data.inhalt_b64)
    except Exception:
        raise HTTPException(400, "Ungültiger Base64-Inhalt")

    try:
        beleg = await analysiere_beleg(bild_bytes, data.dateiname, data.mandant, api_key)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        # Fallback: Manuelles Template
        log.warning(f"KI-Analyse fehlgeschlagen, Fallback: {e}")
        from core.beleg_service import beleg_ohne_ki_parsen
        beleg = beleg_ohne_ki_parsen(data.dateiname, {"mandant": data.mandant})

    beleg_id = beleg_speichern(store, beleg)
    store.log_eintrag(f"BELEG_ANALYSIERT | {data.mandant} | {data.dateiname}")
    return beleg

@app.get("/belege", tags=["Belege"], summary="Alle Belege laden")
def belege_alle(
    mandant: Optional[str] = Query(None),
    status:  Optional[str] = Query(None),
    limit:   int           = Query(100, ge=1, le=1000),
    _user: dict = Depends(get_current_user),
):
    """Alle verarbeiteten Belege, optional gefiltert."""
    from core.beleg_service import belege_laden
    store = get_ds(_user)
    belege = belege_laden(store, mandant, status)
    return {"belege": belege[:limit], "anzahl": len(belege)}

@app.post("/belege/{beleg_id}/bestaetigen", tags=["Belege"],
          summary="Buchungsvorschlag bestätigen")
def beleg_bestaetigen_ep(beleg_id: str, korrekturen: BelegKorrektur = None,
    _user: dict = Depends(get_current_user)):
    """Buchungsvorschlag bestätigen — mit optionalen Korrekturen."""
    from core.beleg_service import beleg_bestaetigen
    store = get_ds(_user)
    try:
        korr = korrekturen.dict(exclude_none=True) if korrekturen else {}
        return beleg_bestaetigen(store, beleg_id, korr)
    except ValueError as e:
        raise HTTPException(404, str(e))

@app.post("/belege/{beleg_id}/ablehnen", tags=["Belege"],
          summary="Buchungsvorschlag ablehnen")
def beleg_ablehnen(beleg_id: str,
    _user: dict = Depends(get_current_user)):
    """Buchungsvorschlag ablehnen und als 'abgelehnt' markieren."""
    from core.beleg_service import beleg_ablehnen as beleg_ablehnen_core
    store = get_ds(_user)
    try:
        return beleg_ablehnen_core(store, beleg_id)
    except ValueError as e:
        raise HTTPException(404, str(e))

@app.get("/belege/statistiken", tags=["Belege"],
         summary="Beleg-Statistiken (Kategorien, Vorsteuer)")
def beleg_statistiken_ep(mandant: Optional[str] = Query(None),
    _user: dict = Depends(get_current_user)):
    """Ausgaben, Einnahmen, Vorsteuer aufgeschlüsselt nach Kategorie."""
    from core.beleg_service import belege_statistiken
    store = get_ds(_user)
    return belege_statistiken(store, mandant)


# ============================================================
# RECHNUNGEN — Honorarrechnungen & Mahnwesen
# ============================================================

class RechnungCreate(BaseModel):
    mandant:        str
    positionen:     List[Dict]
    leistungsdatum: Optional[str] = None
    faellig_tage:   int           = 14
    notiz:          str           = ""

class ZahlungRequest(BaseModel):
    betrag: Optional[float] = None

@app.post("/rechnungen", tags=["Rechnungen"], status_code=status.HTTP_201_CREATED,
          summary="Neue Honorarrechnung erstellen")
def rechnung_erstellen(data: RechnungCreate, _user: dict = Depends(get_current_user)):
    """
    Erstellt eine neue Honorarrechnung mit automatischer Nummerierung (RE-YYYY-NNNN).
    Positionen aus StBVV-Gebührentabelle wählbar.
    """
    store = get_ds(_user)
    get_mandant_or_404(data.mandant, store)
    from core.rechnungs_service import erstelle_rechnung
    try:
        r = erstelle_rechnung(
            store, data.mandant, data.positionen,
            data.leistungsdatum, data.faellig_tage, notiz=data.notiz,
        )
        return r
    except Exception as e:
        raise HTTPException(500, f"Rechnung-Fehler: {e}")

@app.get("/rechnungen", tags=["Rechnungen"], summary="Alle Rechnungen")
def rechnungen_alle_ep(
    mandant: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(100),
    _user: dict = Depends(get_current_user),
):
    from core.rechnungs_service import rechnungen_laden
    store = get_ds(_user)
    r = rechnungen_laden(store, mandant, status_filter, limit)
    return {"rechnungen": r, "anzahl": len(r)}

@app.get("/rechnungen/statistiken", tags=["Rechnungen"],
         summary="Rechnungs-Statistiken & offene Forderungen")
def rechnungen_stats_ep(_user: dict = Depends(get_current_user)):
    from core.rechnungs_service import rechnungs_statistiken
    store = get_ds(_user)
    return rechnungs_statistiken(store)

@app.get("/rechnungen/mahnungen", tags=["Rechnungen"],
         summary="Überfällige Rechnungen — Mahnvorschläge")
def rechnungen_mahnungen_ep(_user: dict = Depends(get_current_user)):
    """Gibt alle überfälligen Rechnungen mit Mahnvorschlag zurück."""
    from core.rechnungs_service import pruefe_offene_rechnungen
    store = get_ds(_user)
    return {"mahnungen": pruefe_offene_rechnungen(store)}

@app.get("/rechnungen/{rechnung_id}", tags=["Rechnungen"], summary="Einzelne Rechnung")
def rechnung_detail(rechnung_id: str, _user: dict = Depends(get_current_user)):
    from core.rechnungs_service import rechnung_holen
    store = get_ds(_user)
    r = rechnung_holen(store, rechnung_id)
    if not r:
        raise HTTPException(404, "Rechnung nicht gefunden")
    return r

@app.post("/rechnungen/{rechnung_id}/bezahlt", tags=["Rechnungen"],
          summary="Zahlungseingang erfassen")
def rechnung_bezahlt_ep(rechnung_id: str, data: ZahlungRequest, _user: dict = Depends(get_current_user)):
    from core.rechnungs_service import rechnung_als_bezahlt
    store = get_ds(_user)
    try:
        return rechnung_als_bezahlt(store, rechnung_id, data.betrag)
    except ValueError as e:
        raise HTTPException(404, str(e))

@app.post("/rechnungen/{rechnung_id}/mahnung", tags=["Rechnungen"],
          summary="Mahnung erstellen + Email senden")
def rechnung_mahnung_ep(rechnung_id: str, background_tasks: BackgroundTasks,
    _user: dict = Depends(get_current_user)):
    from core.rechnungs_service import mahnung_versenden, mahnungs_text
    store = get_ds(_user)
    try:
        r = mahnung_versenden(store, rechnung_id)
        # Email im Hintergrund senden
        if r.get("mandant_email"):
            text = mahnungs_text(r, len(r.get("mahnungen", [])))
            subject = f"Mahnung — {r['rechnungsnummer']} — {r['mandant']}"
            background_tasks.add_task(
                send_email_smtp, r["mandant_email"], subject, text
            )
        return r
    except ValueError as e:
        raise HTTPException(404, str(e))

@app.post("/rechnungen/{rechnung_id}/email", tags=["Rechnungen"],
          summary="Rechnung per Email senden")
def rechnung_email_senden(rechnung_id: str, background_tasks: BackgroundTasks,
    _user: dict = Depends(get_current_user)):
    """Rechnung als HTML-Email an Mandant senden."""
    from core.rechnungs_service import erstelle_rechnungstext, rechnung_holen
    store = get_ds(_user)
    r = rechnung_holen(store, rechnung_id)
    if not r:
        raise HTTPException(404, "Rechnung nicht gefunden")
    if not r.get("mandant_email"):
        raise HTTPException(400, "Mandant hat keine Email-Adresse")
    html = erstelle_rechnungstext(r)
    background_tasks.add_task(
        send_email_smtp, r["mandant_email"],
        f"Honorarrechnung {r['rechnungsnummer']} — {r.get('kanzlei', {}).get('name', 'Kanzlei')}",
        html
    )
    return {"status": "gesendet", "empfaenger": r["mandant_email"]}

@app.delete("/rechnungen/{rechnung_id}", tags=["Rechnungen"],
            summary="Rechnung stornieren")
def rechnung_storno_ep(rechnung_id: str, _user: dict = Depends(get_current_user)):
    from core.rechnungs_service import rechnung_stornieren
    store = get_ds(_user)
    try:
        return rechnung_stornieren(store, rechnung_id)
    except ValueError as e:
        raise HTTPException(404, str(e))

@app.get("/rechnungen/{rechnung_id}/html", tags=["Rechnungen"],
         summary="Rechnung als HTML (für PDF-Druck)")
def rechnung_html(rechnung_id: str, _user: dict = Depends(get_current_user)):
    """HTML-Version der Rechnung zum Drucken / PDF-Export im Browser."""
    from fastapi.responses import HTMLResponse
    from core.rechnungs_service import erstelle_rechnungstext, rechnung_holen
    store = get_ds(_user)
    r = rechnung_holen(store, rechnung_id)
    if not r:
        raise HTTPException(404, "Rechnung nicht gefunden")
    return HTMLResponse(content=erstelle_rechnungstext(r))

@app.get("/stbvv", tags=["Rechnungen"], summary="StBVV Gebühren-Positionen")
def stbvv_liste(_user: dict = Depends(get_current_user)):
    """Vordefinierte Gebührenpositionen nach StBVV."""
    from core.rechnungs_service import STBVV_POSITIONEN
    return STBVV_POSITIONEN


# ============================================================
# TEAM — Aufgaben zuweisen, Auslastung
# ============================================================

@app.post("/aufgaben/{aufgabe_id}/zuweisen", tags=["Team"],
          summary="Aufgabe einem Mitarbeiter zuweisen")
def aufgabe_zuweisen_ep(
    aufgabe_id: str,
    mitarbeiter: str = Query(...),
    zugewiesen_von: str = Query("system"),
    _user: dict = Depends(get_current_user),
):
    from core.team_service import aufgabe_zuweisen
    store = get_ds(_user)
    try:
        return aufgabe_zuweisen(store, aufgabe_id, mitarbeiter, zugewiesen_von)
    except ValueError as e:
        raise HTTPException(404, str(e))

@app.get("/team/aufgaben/{mitarbeiter}", tags=["Team"],
         summary="Aufgaben eines Mitarbeiters")
def team_aufgaben_ep(mitarbeiter: str, _user: dict = Depends(get_current_user)):
    from core.team_service import aufgaben_fuer_mitarbeiter
    store = get_ds(_user)
    return {"aufgaben": aufgaben_fuer_mitarbeiter(store, mitarbeiter)}

@app.get("/team/auslastung", tags=["Team"],
         summary="Team-Auslastung aller Mitarbeiter")
def team_auslastung_ep(_user: dict = Depends(get_current_user)):
    from core.team_service import team_auslastung
    store = get_ds(_user)
    return {"auslastung": team_auslastung(store)}


# ============================================================
# ZEITERFASSUNG
# ============================================================

class ZeitStartRequest(BaseModel):
    mitarbeiter: str
    mandant:     str
    taetigkeit:  str
    aufgabe_id:  Optional[str] = None

@app.post("/zeit/starten", tags=["Zeiterfassung"],
          summary="Zeiterfassung starten")
def zeit_starten_ep(data: ZeitStartRequest, _user: dict = Depends(get_current_user)):
    from core.team_service import zeit_starten
    store = get_ds(_user)
    return zeit_starten(store, data.mitarbeiter, data.mandant, data.taetigkeit, data.aufgabe_id)

@app.post("/zeit/stoppen/{mitarbeiter}", tags=["Zeiterfassung"],
          summary="Laufende Zeiterfassung stoppen")
def zeit_stoppen_ep(mitarbeiter: str, notiz: str = Query(""),
    _user: dict = Depends(get_current_user)):
    from core.team_service import zeit_stoppen
    store = get_ds(_user)
    try:
        return zeit_stoppen(store, mitarbeiter, notiz)
    except ValueError as e:
        raise HTTPException(404, str(e))

@app.get("/zeit/laufend", tags=["Zeiterfassung"],
         summary="Alle gerade laufenden Timer")
def zeit_laufend_ep(_user: dict = Depends(get_current_user)):
    from core.team_service import laufende_zeiten
    store = get_ds(_user)
    return {"laufend": laufende_zeiten(store)}

@app.get("/zeit/eintraege", tags=["Zeiterfassung"],
         summary="Zeiteinträge laden")
def zeit_eintraege_ep(
    mitarbeiter: Optional[str] = Query(None),
    mandant:     Optional[str] = Query(None),
    von:         Optional[str] = Query(None),
    bis:         Optional[str] = Query(None),
    _user: dict = Depends(get_current_user),
):
    from core.team_service import zeit_eintraege
    store = get_ds(_user)
    return {"eintraege": zeit_eintraege(store, mitarbeiter, mandant, von, bis)}

@app.get("/zeit/statistiken", tags=["Zeiterfassung"],
         summary="Zeiterfassungs-Statistiken (Stunden, Umsatz)")
def zeit_statistiken_ep(mandant: Optional[str] = Query(None),
    _user: dict = Depends(get_current_user)):
    from core.team_service import zeit_statistiken
    store = get_ds(_user)
    return zeit_statistiken(store, mandant)


# ============================================================
# KI-ASSISTENT — Backend Proxy (verhindert CORS im Browser)
# ============================================================

class KIChatRequest(BaseModel):
    messages:    List[Dict]
    system:      Optional[str] = None
    max_tokens:  int           = 1500
    mandant:     Optional[str] = None

@app.post("/ki/chat", tags=["KI-Assistent"],
          summary="KI-Chat — Backend Proxy für OpenAI GPT-4o mini")
async def ki_chat(data: KIChatRequest, _user: dict = Depends(get_current_user)):
    """
    Backend-Proxy für OpenAI API.
    Modell: gpt-4o-mini (günstig, schnell, sehr gut für Steuerberatung)
    CORS-Problem gelöst: Browser → Backend → OpenAI (nicht direkt)
    Mandanten-Kontext wird automatisch angereichert.
    """
    import httpx

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise HTTPException(500,
            "OPENAI_API_KEY fehlt in .env — "
            "Key unter platform.openai.com/api-keys erstellen und in .env eintragen")

    # System-Prompt aufbauen
    system_text = data.system or ""

    # Mandanten-Kontext anreichern
    store = get_ds(_user)
    if data.mandant:
        try:
            m           = store.hole_mandanten().get(data.mandant, {})
            aufgaben    = [a for a in store.hole_fristen().values()
                           if a.get("mandant") == data.mandant]
            offen       = sum(1 for a in aufgaben if not a.get("erledigt"))
            ueberfaellig= sum(1 for a in aufgaben
                              if not a.get("erledigt") and
                              a.get("frist", "9999") < datetime.now().strftime("%Y-%m-%d"))
            system_text += (
                f"\n\nAKTUELLER MANDANT-KONTEXT:\n"
                f"- Name: {data.mandant}\n"
                f"- Jahresumsatz: €{m.get('umsatz', 0):,.0f}\n"
                f"- Branche: {m.get('branche', '—')}\n"
                f"- Aufgaben offen: {offen}\n"
                f"- Aufgaben überfällig: {ueberfaellig}\n"
                f"- Tage ohne Antwort: {store.berechne_tage_ohne_antwort(data.mandant)}"
            )
        except Exception:
            pass

    # OpenAI Format: system als erstes Element in messages
    openai_messages = []
    if system_text:
        openai_messages.append({"role": "system", "content": system_text})
    openai_messages.extend(data.messages)

    payload = {
        "model":      "gpt-4o-mini",
        "max_tokens": data.max_tokens,
        "messages":   openai_messages,
        "temperature": 0.3,   # Niedrig = präzise, sachlich (ideal für Steuerberatung)
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type":  "application/json",
                },
                json=payload,
            )

        if response.status_code != 200:
            err = response.json() if "application/json" in response.headers.get("content-type","") else {}
            raise HTTPException(
                response.status_code,
                err.get("error", {}).get("message", f"OpenAI Fehler {response.status_code}")
            )

        result  = response.json()
        text    = result["choices"][0]["message"]["content"]
        tokens  = result.get("usage", {}).get("completion_tokens", 0)
        modell  = result.get("model", "gpt-4o-mini")

        return {
            "content":     text,
            "tokens_used": tokens,
            "modell":      modell,
        }

    except httpx.TimeoutException:
        raise HTTPException(504, "OpenAI Timeout — bitte nochmal versuchen")
    except httpx.ConnectError:
        raise HTTPException(503, "OpenAI nicht erreichbar — Internetverbindung prüfen")


@app.get("/ki/status", tags=["KI-Assistent"], summary="KI-Verfügbarkeit prüfen")
def ki_status():
    """Prüft ob OpenAI API-Key konfiguriert ist."""
    key = os.getenv("OPENAI_API_KEY", "")
    return {
        "verfuegbar":  bool(key),
        "key_gesetzt": bool(key),
        "modell":      "gpt-4o-mini",
        "anbieter":    "OpenAI",
        "hinweis":     "" if key else "OPENAI_API_KEY in .env setzen (platform.openai.com/api-keys)",
    }


@app.get("/ki/mandant-analyse/{name}", tags=["KI-Assistent"],
         summary="Tiefe AI-Analyse eines Mandanten via OpenAI")
async def ki_mandant_analyse(name: str, _user: dict = Depends(get_current_user)):
    """
    OpenAI analysiert diesen Mandanten individuell.
    Nicht nur if-else Regeln — echtes Sprachmodell-Verständnis.
    Gibt strukturierte Empfehlung mit Begründung zurück.
    """
    store = get_ds(_user)
    m = get_mandant_or_404(name, store)
    from core.decision_engine import analysiere_mandant_komplett
    result = await analysiere_mandant_komplett(name, m, store)
    store.log_eintrag(f"AI_ANALYSE | {name} | ai_genutzt={result.get('ai_genutzt')}")
    return result


@app.get("/ki/kanzlei-zusammenfassung", tags=["KI-Assistent"],
         summary="AI-Zusammenfassung der gesamten Kanzlei")
async def ki_kanzlei_zusammenfassung(_user: dict = Depends(get_current_user)):
    """
    OpenAI erstellt eine strategische Zusammenfassung:
    - Welche 3 Mandanten brauchen sofortige Aufmerksamkeit?
    - Wie viel Umsatz ist in Gefahr?
    - Was ist die wichtigste Aktion heute?
    """
    from core.decision_engine import analysiere_alle_mandanten

    api_key = os.getenv("OPENAI_API_KEY", "")
    alle    = analysiere_alle_mandanten(get_ds(_user))

    kritische     = [m for m in alle if m["status"] in ("KRITISCH", "WICHTIG")]
    umsatz_gefahr = sum(m.get("umsatz", 0) for m in kritische)
    vips          = [m for m in alle if m.get("ist_vip")]

    if not api_key or not kritische:
        return {
            "zusammenfassung": f"{len(kritische)} Mandanten benötigen Aufmerksamkeit. "
                               f"€{umsatz_gefahr:,.0f} Jahresumsatz betroffen.",
            "top3":            [m["mandant"] for m in kritische[:3]],
            "umsatz_gefahr":   umsatz_gefahr,
            "ai_genutzt":      False,
        }

    kontext = (
        f"Kanzlei hat {len(alle)} Mandanten, Gesamtumsatz €{sum(m.get('umsatz',0) for m in alle):,.0f}.\n"
        f"Kritische Mandanten ({len(kritische)}):\n"
        + "\n".join([
            f"- {m['mandant']}: {m['status']}, €{m.get('umsatz',0):,.0f}, "
            f"{m.get('tage_ohne_antwort',0)}d kein Kontakt, {m.get('aufgaben_ueberfaellig',0)} überfällig"
            for m in kritische[:5]
        ])
        + f"\nVIP-Mandanten: {', '.join(v['mandant'] for v in vips[:3])}"
    )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": "gpt-4o-mini", "max_tokens": 200, "temperature": 0.2,
                    "messages": [
                        {"role": "system", "content":
                         "Du bist Assistent für Steuerberater. Antworte auf Deutsch, "
                         "max 3 Sätze, direkt und handlungsorientiert."},
                        {"role": "user", "content":
                         f"Erstelle eine kurze strategische Zusammenfassung für heute:\n{kontext}"},
                    ],
                },
            )
        zusammenfassung = r.json()["choices"][0]["message"]["content"] if r.status_code == 200 else None
    except Exception:
        zusammenfassung = None

    return {
        "zusammenfassung": zusammenfassung or f"{len(kritische)} Mandanten benötigen heute Aufmerksamkeit.",
        "top3":            [m["mandant"] for m in kritische[:3]],
        "umsatz_gefahr":   umsatz_gefahr,
        "kritische_anzahl":len(kritische),
        "vips_anzahl":     len(vips),
        "ai_genutzt":      zusammenfassung is not None,
    }


# ============================================================
# DOKUMENT-SCANNER — KI erkennt Dokumente und schlägt Ordner vor
# ============================================================

class DokumentScanRequest(BaseModel):
    dateiname:   str
    inhalt_b64:  str
    mandant:     Optional[str] = ""

DOKUMENT_SYSTEM_PROMPT = """Du bist ein intelligentes Dokumenten-Management-System für Steuerberater.
Analysiere das hochgeladene Dokument und antworte NUR mit einem JSON-Objekt:

{
  "dokumenttyp": "Rechnung|Kontoauszug|Vertrag|Steuerbescheid|Lohnabrechnung|Korrespondenz|Formular|Sonstiges",
  "titel": "Kurzer prägnanter Titel des Dokuments",
  "datum": "YYYY-MM-DD oder leer",
  "absender": "Name des Absenders/Ausstellers",
  "empfaenger": "Name des Empfängers",
  "betrag": 0.00,
  "wichtigkeit": "hoch|mittel|niedrig",
  "vorgeschlagener_ordner": "z.B. 2026/Steuerbescheide oder 2026/Rechnungen/Eingang",
  "schlagwoerter": ["schlüsselwort1", "schlüsselwort2"],
  "zusammenfassung": "1-2 Sätze was dieses Dokument ist",
  "handlungsbedarf": "Was muss damit getan werden (oder leer)",
  "frist": "YYYY-MM-DD falls eine Frist erkennbar ist, sonst leer",
  "vertrauens_score": 0.95
}

Ordner-Logik:
- Steuerbescheide → YYYY/Steuerbescheide
- Rechnungen eingegangen → YYYY/Rechnungen/Eingang  
- Rechnungen ausgegangen → YYYY/Rechnungen/Ausgang
- Kontoauszüge → YYYY/Bank/Kontoauszüge
- Verträge → Vertraege/[Kategorie]
- Lohnabrechnungen → YYYY/Lohn
- Behördenpost → YYYY/Behoerden/[Behoerde]
- Korrespondenz → YYYY/Korrespondenz"""

@app.post("/dokumente/scannen", tags=["Dokumente"],
          summary="Dokument mit KI scannen und klassifizieren")
async def dokument_scannen(data: DokumentScanRequest,
    _user: dict = Depends(get_current_user)):
    """
    KI analysiert ein Dokument (PDF/Bild) und:
    - Erkennt Dokumenttyp, Datum, Absender, Betrag
    - Schlägt automatisch Ordner-Struktur vor
    - Erkennt Fristen und Handlungsbedarf
    - Gibt strukturierte Metadaten zurück

    Vor dem Speichern kann der Steuerberater alles bearbeiten.
    """

    store = get_ds(_user)
    import httpx, base64 as b64

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise HTTPException(500, "OPENAI_API_KEY nicht konfiguriert")

    # Datei decodieren
    try:
        bild_bytes = b64.b64decode(data.inhalt_b64)
    except Exception:
        raise HTTPException(400, "Ungültiger Base64-Inhalt")

    # Mime-Type
    name_l = data.dateiname.lower()
    if name_l.endswith(".pdf"):
        media_type = "application/pdf"
    elif name_l.endswith(".png"):
        media_type = "image/png"
    elif name_l.endswith(".webp"):
        media_type = "image/webp"
    else:
        media_type = "image/jpeg"

    bild_b64 = b64.standard_b64encode(bild_bytes).decode()

    user_text = f"Analysiere dieses Dokument"
    if data.mandant:
        user_text += f" für Mandant '{data.mandant}'"
    user_text += ". Gib strukturierte Metadaten als JSON zurück."

    payload = {
        "model":      "gpt-4o",
        "max_tokens": 1024,
        "messages": [
            {"role": "system", "content": DOKUMENT_SYSTEM_PROMPT},
            {
            "role": "user",
            "content": [
                {"type": "image", "image_url": {"url": f"data:{media_type};base64,{bild_b64}", "detail": "high"}},
                {"type": "text", "text": user_text}
            ]
        }]
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )

        raw = response.json().get("content", [{}])[0].get("text", "{}")

        import re
        if "```" in raw:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            raw = m.group(0) if m else "{}"

        metadaten = json.loads(raw)
    except json.JSONDecodeError:
        metadaten = {"fehler": "KI konnte Dokument nicht lesen", "vertrauens_score": 0}
    except Exception as e:
        raise HTTPException(500, f"Dokument-Scan Fehler: {e}")

    # Metadaten anreichern
    metadaten["scan_id"]      = str(uuid.uuid4())
    metadaten["dateiname"]    = data.dateiname
    metadaten["mandant"]      = data.mandant
    metadaten["gescannt_am"]  = datetime.now().isoformat()
    metadaten["status"]       = "vorschau"  # vorschau → gespeichert → archiviert

    # Falls Frist erkannt: automatisch als Aufgabe vorschlagen
    if metadaten.get("frist") and metadaten.get("handlungsbedarf") and data.mandant:
        metadaten["aufgaben_vorschlag"] = {
            "beschreibung": metadaten.get("handlungsbedarf", "")[:200],
            "frist":        metadaten["frist"],
            "mandant":      data.mandant,
            "prioritaet":   "hoch" if metadaten.get("wichtigkeit") == "hoch" else "normal",
        }

    store.log_eintrag(f"DOKUMENT_GESCANNT | {data.mandant} | {data.dateiname} | {metadaten.get('dokumenttyp','?')}")
    return metadaten


@app.post("/dokumente/speichern", tags=["Dokumente"],
          summary="Gescanntes Dokument mit Metadaten speichern")
def dokument_speichern(metadaten: dict = Body(...),
    _user: dict = Depends(get_current_user)):
    """
    Speichert ein Dokument mit den vom Steuerberater bestätigten Metadaten.
    Erstellt automatisch Aufgabe wenn aufgaben_vorschlag bestätigt.
    """

    store = get_ds(_user)
    metadaten["status"]       = "gespeichert"
    metadaten["gespeichert_am"] = datetime.now().isoformat()

    # In Datenspeicher ablegen
    dokumente = _kv_get(store, "__dokumente_v1", {})
    if not isinstance(dokumente, dict):
        dokumente = {}
    dok_id = metadaten.get("scan_id", str(uuid.uuid4()))
    dokumente[dok_id] = metadaten
    _kv_set(store, "__dokumente_v1", dokumente)

    # Aufgabe automatisch erstellen wenn bestätigt
    aufgabe_erstellt = None
    if metadaten.get("aufgabe_bestaetigt") and metadaten.get("aufgaben_vorschlag"):
        vorschlag  = metadaten["aufgaben_vorschlag"]
        aufgabe_id = str(uuid.uuid4())
        aufgabe    = {
            "id":           aufgabe_id,
            "mandant":      vorschlag.get("mandant", ""),
            "beschreibung": vorschlag.get("beschreibung", ""),
            "frist":        vorschlag.get("frist", ""),
            "prioritaet":   vorschlag.get("prioritaet", "normal"),
            "kategorie":    "dokument",
            "erledigt":     False,
            "erstellt_am":  datetime.now().isoformat(),
            "quelle":       "dokument_scan",
            "dokument_id":  dok_id,
        }
        store.aufgabe_speichern(aufgabe_id, aufgabe)
        aufgabe_erstellt = aufgabe_id

    store.log_eintrag(f"DOKUMENT_GESPEICHERT | {metadaten.get('mandant','?')} | {metadaten.get('ordner','?')}")
    return {
        "status":           "gespeichert",
        "dokument_id":      dok_id,
        "ordner":           metadaten.get("vorgeschlagener_ordner", ""),
        "aufgabe_erstellt": aufgabe_erstellt,
    }


@app.get("/dokumente", tags=["Dokumente"], summary="Alle gespeicherten Dokumente")
def dokumente_alle(
    mandant: Optional[str] = Query(None),
    typ:     Optional[str] = Query(None),
    limit:   int           = Query(100),
    _user: dict = Depends(get_current_user),
):
    """Alle gescannten und gespeicherten Dokumente."""
    store = get_ds(_user)
    dokumente = _kv_get(store, "__dokumente_v1", {})
    if not isinstance(dokumente, dict):
        dokumente = {}
    docs = list(dokumente.values())
    if mandant:
        docs = [d for d in docs if d.get("mandant") == mandant]
    if typ:
        docs = [d for d in docs if d.get("dokumenttyp") == typ]
    docs.sort(key=lambda x: x.get("gescannt_am", ""), reverse=True)
    return {"dokumente": docs[:limit], "anzahl": len(docs)}


# ============================================================
# DOKUMENT-SCANNER — KI erkennt Typ, schlägt Ordner vor
# ============================================================

class DokumentAnalyseRequest(BaseModel):
    dateiname:   str
    inhalt_b64:  str
    dateityp:    str = "application/pdf"
    mandant:     Optional[str] = ""

class DokumentSpeichernRequest(BaseModel):
    dok_id:           str
    dateiname:        str
    dokumenttyp:      str = "sonstiges"
    mandant:          str
    datum:            Optional[str] = None
    frist:            Optional[str] = None
    lieferant:        Optional[str] = ""
    ordner_pfad:      str
    ordner_kategorie: str = "Sonstiges"
    jahr:             Optional[int] = None
    notiz:            Optional[str] = ""
    inhalt_b64:       Optional[str] = None  # Für Speicherung
    aufgabe_anlegen:  bool = False

DOKUMENT_SYSTEM_PROMPT = """Du bist ein KI-Assistent für eine deutsche Steuerkanzlei.
Analysiere das Dokument und erkenne alle relevanten Informationen.
Antworte NUR mit validem JSON, ohne Markdown-Backticks:

{
  "dokumenttyp": "rechnung|eingangsrechnung|vertrag|steuerbescheid|kontoauszug|lohnabrechnung|jahresabschluss|satzung|vollmacht|mahnung|lieferschein|korrespondenz|sonstiges",
  "mandant_hinweis": "Name der Person/Firma die im Dokument erwähnt wird (oder leer)",
  "datum": "YYYY-MM-DD oder leer",
  "frist": "YYYY-MM-DD wenn eine Frist erkennbar ist, sonst leer",
  "lieferant": "Absender/Ersteller des Dokuments",
  "ordner_kategorie": "Belege|Rechnungen_Eingang|Rechnungen_Ausgang|Verträge|Steuerbescheide|Jahresabschlüsse|Kontoauszüge|Lohnunterlagen|Korrespondenz|Vollmachten|Sonstiges",
  "zusammenfassung": "1-2 Sätze: Was ist dieses Dokument? Was steht drin?",
  "naechste_schritte": ["Empfohlene Aktion 1", "Empfohlene Aktion 2"],
  "betrag": 0.0,
  "vertrauens_score": 0.9
}"""

@app.post("/dokumente/analysieren", tags=["Dokumente"],
          summary="Dokument mit KI analysieren — erkennt Typ, schlägt Ordner vor")
async def dokument_analysieren(data: DokumentAnalyseRequest,
    _user: dict = Depends(get_current_user)):
    """
    KI analysiert ein Dokument und erkennt automatisch:
    - Dokumenttyp (Rechnung, Vertrag, Bescheid...)
    - Mandanten-Hinweis (wer ist betroffen?)
    - Datum und Fristen
    - Vorgeschlagene Ordnerstruktur
    - Nächste empfohlene Schritte
    """

    store = get_ds(_user)
    import httpx, base64 as b64lib, re as relib

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise HTTPException(500, "OPENAI_API_KEY fehlt in .env")

    try:
        bild_bytes = b64lib.b64decode(data.inhalt_b64)
    except Exception:
        raise HTTPException(400, "Ungültiger Base64-Inhalt")

    # Mime-Type
    name_lower = data.dateiname.lower()
    if name_lower.endswith(".pdf"):
        media_type = "application/pdf"
    elif name_lower.endswith(".png"):
        media_type = "image/png"
    else:
        media_type = "image/jpeg"

    bild_b64 = b64lib.standard_b64encode(bild_bytes).decode("utf-8")

    user_text = f"Analysiere dieses Dokument: '{data.dateiname}'"
    if data.mandant:
        user_text += f" (Mandant: {data.mandant})"

    payload = {
        "model": "gpt-4o",
        "max_tokens": 1024,
        "messages": [
            {"role": "system", "content": DOKUMENT_SYSTEM_PROMPT},
            {"role":"user","content":[
            {"type":"image","source":{"type":"base64","media_type":media_type,"data":bild_b64}},
            {"type":"text","text":user_text},
        ]}]
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
        if response.status_code != 200:
            raise RuntimeError(f"OpenAI Fehler {response.status_code}")

        raw = response.json()["content"][0]["text"].strip()
        if "```" in raw:
            match = __import__("re").search(r"\{.*\}", raw, __import__("re").DOTALL)
            raw = match.group(0) if match else "{}"

        analyse = json.loads(raw)
    except Exception as e:
        log.warning(f"Dokument-KI-Analyse fehlgeschlagen: {e}")
        # Fallback
        analyse = {
            "dokumenttyp": "sonstiges",
            "mandant_hinweis": data.mandant or "",
            "ordner_kategorie": "Sonstiges",
            "zusammenfassung": "Automatische Analyse nicht verfügbar",
            "naechste_schritte": ["Bitte manuell prüfen und kategorisieren"],
            "vertrauens_score": 0.3,
        }

    # Ordner-Pfad vorschlagen
    mandant = data.mandant or analyse.get("mandant_hinweis", "Unbekannt") or "Unbekannt"
    jahr    = (analyse.get("datum","") or "")[:4] or str(datetime.now().year)
    kat     = analyse.get("ordner_kategorie", "Sonstiges")

    dok_id = str(uuid.uuid4())
    result = {
        "dok_id":          dok_id,
        "dateiname":       data.dateiname,
        "dokumenttyp":     analyse.get("dokumenttyp", "sonstiges"),
        "mandant":         mandant,
        "datum":           analyse.get("datum", ""),
        "frist":           analyse.get("frist", ""),
        "lieferant":       analyse.get("lieferant", ""),
        "ordner_kategorie":kat,
        "ordner_pfad":     f"{mandant}/{jahr}/{kat}",
        "jahr":            int(jahr) if jahr.isdigit() else datetime.now().year,
        "zusammenfassung": analyse.get("zusammenfassung", ""),
        "naechste_schritte": analyse.get("naechste_schritte", []),
        "betrag":          analyse.get("betrag", 0.0),
        "vertrauens_score":analyse.get("vertrauens_score", 0.5),
        "notiz":           "",
        "inhalt_b64":      data.inhalt_b64,  # Für spätere Speicherung
        "analysiert_am":   datetime.now().isoformat(),
        "status":          "vorschlag",
    }

    store.log_eintrag(f"DOKUMENT_ANALYSIERT | {mandant} | {data.dateiname} | {result['dokumenttyp']}")
    return result

@app.post("/dokumente/speichern", tags=["Dokumente"],
          summary="Analysiertes Dokument bestätigen und speichern")
def dokument_speichern(data: DokumentSpeichernRequest,
    _user: dict = Depends(get_current_user)):
    """
    Speichert ein analysiertes Dokument nach Benutzer-Bestätigung.
    Legt automatisch eine Aufgabe an wenn aufgabe_anlegen=True.
    """

    store = get_ds(_user)
    import base64 as b64lib, os as _os

    # Dokument-Archiv Verzeichnis
    archiv_dir = _os.path.join("data", "dokumente", data.ordner_pfad)
    _os.makedirs(archiv_dir, exist_ok=True)

    # Datei speichern wenn Inhalt vorhanden
    if data.inhalt_b64:
        try:
            datei_bytes = b64lib.b64decode(data.inhalt_b64)
            datei_pfad  = _os.path.join(archiv_dir, data.dateiname)
            with open(datei_pfad, "wb") as f:
                f.write(datei_bytes)
        except Exception as e:
            log.warning(f"Datei-Speicherung fehlgeschlagen: {e}")

    # Metadaten in DatenSpeicher
    dokument_archiv = _kv_get(store, "__dokument_archiv_v1", {})
    if not isinstance(dokument_archiv, dict):
        dokument_archiv = {}

    dokument_archiv[data.dok_id] = {
        "dok_id":          data.dok_id,
        "dateiname":       data.dateiname,
        "dokumenttyp":     data.dokumenttyp,
        "mandant":         data.mandant,
        "datum":           data.datum,
        "frist":           data.frist,
        "lieferant":       data.lieferant,
        "ordner_pfad":     data.ordner_pfad,
        "ordner_kategorie":data.ordner_kategorie,
        "jahr":            data.jahr,
        "notiz":           data.notiz,
        "gespeichert_am":  datetime.now().isoformat(),
        "status":          "gespeichert",
    }
    _kv_set(store, "__dokument_archiv_v1", dokument_archiv)

    # Kommunikations-Eintrag
    store.kommunikation_hinzufuegen(data.mandant, {
        "typ":       "dokument_gespeichert",
        "text":      f"Dokument gespeichert: {data.dateiname} → {data.ordner_pfad}",
        "timestamp": datetime.now().isoformat(),
    })

    # Aufgabe anlegen wenn gewünscht (z.B. bei erkannter Frist)
    if data.aufgabe_anlegen and data.frist:
        aufgabe_id = str(uuid.uuid4())
        store.aufgabe_speichern(aufgabe_id, {
            "id":           aufgabe_id,
            "mandant":      data.mandant,
            "beschreibung": f"Frist aus Dokument: {data.dateiname}",
            "frist":        data.frist,
            "prioritaet":   "hoch",
            "kategorie":    data.ordner_kategorie,
            "erledigt":     False,
            "erstellt_am":  datetime.now().isoformat(),
        })

    store.log_eintrag(f"DOKUMENT_GESPEICHERT | {data.mandant} | {data.dateiname} | {data.ordner_pfad}")
    return {"status":"ok","ordner_pfad":data.ordner_pfad,"aufgabe_angelegt":data.aufgabe_anlegen}

@app.get("/dokumente/archiv", tags=["Dokumente"],
         summary="Alle gespeicherten Dokumente (Archiv)")
def dokumente_archiv(
    mandant: Optional[str] = Query(None),
    typ:     Optional[str] = Query(None),
    suche:   Optional[str] = Query(None),
    _user: dict = Depends(get_current_user),
):
    """Alle gespeicherten Dokumente, strukturiert nach Ordner-Pfad."""
    store = get_ds(_user)
    dokument_archiv = _kv_get(store, "__dokument_archiv_v1", {})
    if not isinstance(dokument_archiv, dict):
        dokument_archiv = {}
    dokumente = list(dokument_archiv.values())

    if mandant:
        dokumente = [d for d in dokumente if d.get("mandant") == mandant]
    if typ:
        dokumente = [d for d in dokumente if d.get("dokumenttyp") == typ]
    if suche:
        sl = suche.lower()
        dokumente = [d for d in dokumente if
                     sl in d.get("dateiname","").lower() or
                     sl in d.get("mandant","").lower() or
                     sl in d.get("dokumenttyp","").lower()]

    dokumente.sort(key=lambda x: x.get("gespeichert_am",""), reverse=True)
    return {"dokumente":dokumente,"anzahl":len(dokumente)}

@app.delete("/dokumente/{dok_id}", tags=["Dokumente"],
            summary="Dokument aus Archiv löschen")
def dokument_loeschen(dok_id: str,
    _user: dict = Depends(get_current_user)):
    """Dokument dauerhaft aus Archiv und Dateisystem löschen."""

    store = get_ds(_user)
    archiv = _kv_get(store, "__dokument_archiv_v1", {})
    if not isinstance(archiv, dict):
        archiv = {}

    if dok_id not in archiv:
        raise HTTPException(404, "Dokument nicht gefunden")

    dok = archiv[dok_id]
    # Physische Datei löschen
    import os as _os
    datei_pfad = _os.path.join("data","dokumente",dok.get("ordner_pfad",""),dok.get("dateiname",""))
    if _os.path.exists(datei_pfad):
        try: _os.remove(datei_pfad)
        except Exception: pass

    del archiv[dok_id]
    _kv_set(store, "__dokument_archiv_v1", archiv)
    store.log_eintrag(f"DOKUMENT_GELOESCHT | {dok.get('mandant')} | {dok.get('dateiname')}")
    return {"status":"geloescht"}


# ============================================================
# PORTAL INTEGRATION — Haupt-API leitet Portal-Anfragen weiter
# ============================================================

@app.get("/portal/unterschriften/alle", tags=["Portal"],
         summary="Alle Unterschriften-Anfragen (für Kanzlei-Übersicht)")
def portal_unterschriften_alle(
    mandant:   Optional[str] = Query(None),
    admin_key: str           = Query(...),
    _user: dict = Depends(get_current_user),
):
    """Kanzlei sieht Status aller Unterschriften direkt im Haupt-System."""
    import secrets as _s
    expected = os.getenv("PORTAL_ADMIN_KEY", "kanzlei-admin-2024")
    if not _s.compare_digest(admin_key, expected):
        raise HTTPException(403, "Ungültiger Admin-Key")

    store = get_ds(_user)
    alle = store.portal_liste("unterschrift")
    if mandant:
        alle = [u for u in alle if u.get("mandant") == mandant]

    # Sensible Daten entfernen
    return {"unterschriften": [{
        "id":            u["id"],
        "mandant":       u["mandant"],
        "dokumentname":  u["dokumentname"],
        "betreff":       u.get("betreff",""),
        "status":        u["status"],
        "erstellt_am":   u["erstellt_am"],
        "unterschrieben_am": u.get("unterschrieben_am"),
        "hat_unterschrift":  bool(u.get("unterschrift_b64")),
    } for u in sorted(alle, key=lambda x: x["erstellt_am"], reverse=True)],
    "gesamt":       len(alle),
    "unterschrieben": sum(1 for u in alle if u["status"] == "unterschrieben"),
    "ausstehend":   sum(1 for u in alle if u["status"] == "ausstehend"),
    }

@app.get("/portal/mandant/{name}/status", tags=["Portal"],
         summary="Portal-Status eines Mandanten (Uploads, Fragen, Unterschriften)")
def portal_mandant_status(name: str, _user: dict = Depends(get_current_user)):
    """Zeigt im Mandant-Detail: was hat der Mandant im Portal getan?"""
    store = get_ds(_user)
    get_mandant_or_404(name, store)
    uploads = [u for u in store.portal_liste("upload") if u.get("mandant") == name]
    signs = [u for u in store.portal_liste("unterschrift") if u.get("mandant") == name]
    bot_fragen = _kv_get(store, "__bot_fragen_v1", {})
    if not isinstance(bot_fragen, dict):
        bot_fragen = {}
    fragen = [f for f in bot_fragen.values() if f.get("mandant") == name]

    return {
        "mandant":            name,
        "uploads_gesamt":     len(uploads),
        "uploads_diese_woche": sum(1 for u in uploads if
            u.get("hochgeladen_am","") >= (datetime.now()-timedelta(days=7)).isoformat()),
        "unterschriften_offen":      sum(1 for s in signs if s["status"]=="ausstehend"),
        "unterschriften_erledigt":   sum(1 for s in signs if s["status"]=="unterschrieben"),
        "bot_fragen_offen":          sum(1 for f in fragen if f["status"]=="offen"),
        "bot_fragen_beantwortet":    sum(1 for f in fragen if f["status"]=="beantwortet"),
        "portal_link_generieren":    f"/portal/admin/token/{name}?admin_key=...",
    }


# ============================================================
# PROAKTIVER BOT
# ============================================================

class BotFrageCreate(BaseModel):
    mandant:           str
    frage_text:        str
    frage_typ:         str = "sonstiges"
    kontext:           str = ""
    betrag:            Optional[float] = None
    antwort_optionen:  Optional[List[str]] = None
    aufgabe_wenn_nein: Optional[str] = None

class BotAntwortRequest(BaseModel):
    antwort: str
    notiz:   str = ""

def _get_bot(store: DatenSpeicher):
    from core.proaktiver_bot import ProaktiverBot
    return ProaktiverBot(store)

@app.post("/bot/frage", tags=["Bot"], summary="Neue Bot-Frage an Mandant stellen")
def bot_frage_stellen(data: BotFrageCreate, _user: dict = Depends(get_current_user)):
    """Stellt eine proaktive Frage im Mandantenportal."""
    store = get_ds(_user)
    get_mandant_or_404(data.mandant, store)
    bot = _get_bot(store)
    return bot.frage_stellen(
        data.mandant, data.frage_text, data.frage_typ,
        data.kontext, data.betrag, data.antwort_optionen, data.aufgabe_wenn_nein
    )

@app.post("/bot/frage/{frage_id}/antwort", tags=["Bot"],
          summary="Antwort auf Bot-Frage erfassen")
def bot_antwort(frage_id: str, data: BotAntwortRequest, _user: dict = Depends(get_current_user)):
    bot = _get_bot(get_ds(_user))
    try:
        return bot.antwort_erfassen(frage_id, data.antwort, data.notiz)
    except ValueError as e:
        raise HTTPException(404, str(e))

@app.get("/bot/fragen", tags=["Bot"], summary="Alle Bot-Fragen")
def bot_alle_fragen(
    mandant: Optional[str] = Query(None),
    status:  Optional[str] = Query(None),
    _user: dict = Depends(get_current_user),
):
    bot    = _get_bot(get_ds(_user))
    fragen = bot.alle_fragen(status)
    if mandant:
        fragen = [f for f in fragen if f.get("mandant") == mandant]
    return {"fragen": fragen, "anzahl": len(fragen)}

@app.get("/bot/fragen/{mandant}", tags=["Bot"],
         summary="Bot-Fragen für einen Mandanten (für Portal)")
def bot_fragen_mandant(mandant: str, nur_offen: bool = Query(True),
    _user: dict = Depends(get_current_user)):
    bot = _get_bot(get_ds(_user))
    return {"fragen": bot.fragen_fuer_mandant(mandant, nur_offen)}

@app.post("/bot/analyse", tags=["Bot"],
          summary="Automatische Bot-Analyse aller Mandanten starten")
def bot_analyse(background_tasks: BackgroundTasks, _user: dict = Depends(get_current_user)):
    """Startet die vollautomatische Analyse im Hintergrund."""
    store = get_ds(_user)
    def _run():
        try:
            bot   = _get_bot(store)
            fragen = bot.analysiere_alle_mandanten()
            log.info(f"Bot-Analyse: {len(fragen)} neue Fragen")
        except Exception as e:
            log.error(f"Bot-Analyse Fehler: {e}")
    background_tasks.add_task(_run)
    return {"status": "gestartet", "hinweis": "Läuft im Hintergrund"}

@app.get("/bot/statistiken", tags=["Bot"], summary="Bot-Statistiken (gesparte Telefonate)")
def bot_statistiken(_user: dict = Depends(get_current_user)):
    return _get_bot(get_ds(_user)).statistiken()


# ============================================================
# PROFIT MONITOR
# ============================================================

def _get_profit(store: DatenSpeicher):
    from core.profit_monitor import ProfitMonitor
    return ProfitMonitor(store)

@app.get("/profit/{mandant}", tags=["Profit"],
         summary="Profitabilität eines Mandanten (verdiene ich Geld?)")
def profit_mandant(mandant: str, tage: int = Query(30, ge=1, le=365),
    _user: dict = Depends(get_current_user)):
    store = get_ds(_user)
    get_mandant_or_404(mandant, store)
    return _get_profit(store).berechne_profit(mandant, tage)

@app.get("/profit/ranking/alle", tags=["Profit"],
         summary="Alle Mandanten nach Profitabilität gerankt")
def profit_ranking(tage: int = Query(30), _user: dict = Depends(get_current_user)):
    return {"ranking": _get_profit(get_ds(_user)).profit_ranking(tage)}

@app.get("/profit/kanzlei/uebersicht", tags=["Profit"],
         summary="Kanzlei-Gesamt-Profitabilität")
def profit_kanzlei(tage: int = Query(30), _user: dict = Depends(get_current_user)):
    return _get_profit(get_ds(_user)).kanzlei_uebersicht(tage)

@app.get("/profit/{mandant}/benchmarking", tags=["Profit"],
         summary="Mandant mit Branchendurchschnitt vergleichen")
def profit_benchmarking(mandant: str, _user: dict = Depends(get_current_user)):
    store = get_ds(_user)
    get_mandant_or_404(mandant, store)
    return _get_profit(store).branchen_benchmarking(mandant)


# ============================================================
# LOHNABRECHNUNG
# ============================================================

class LohnMitarbeiterCreate(BaseModel):
    mandant:       str
    name:          str
    brutto_monat:  float
    steuer_klasse: int   = 1
    urlaubstage:   int   = 20
    wochenstunden: float = 40.0
    steuer_id:     str   = ""
    sv_nr:         str   = ""
    iban:          str   = ""
    eintritt:      Optional[str] = None

class ZeitdatenImport(BaseModel):
    arbeitstage:    int   = 21
    krankheitstage: int   = 0
    urlaubstage:    int   = 0
    ueberstunden:   float = 0.0
    zuschlaege:     float = 0.0
    abzuege:        float = 0.0
    notiz:          str   = ""
    quelle:         str   = "manuell"

def _get_lohn(store: DatenSpeicher):
    from core.lohn_service import LohnService
    return LohnService(store)

@app.post("/lohn/mitarbeiter", tags=["Lohn"], status_code=201,
          summary="Neuen Mitarbeiter für Lohnabrechnung anlegen")
def lohn_mitarbeiter_neu(data: LohnMitarbeiterCreate, _user: dict = Depends(get_current_user)):
    store = get_ds(_user)
    get_mandant_or_404(data.mandant, store)
    return _get_lohn(store).mitarbeiter_anlegen(**data.dict())

@app.get("/lohn/mitarbeiter", tags=["Lohn"], summary="Alle Mitarbeiter")
def lohn_mitarbeiter_liste(mandant: Optional[str] = Query(None),
    _user: dict = Depends(get_current_user)):
    return {"mitarbeiter": _get_lohn(get_ds(_user)).mitarbeiter_liste(mandant)}

@app.post("/lohn/zeitdaten/{ma_id}/{monat}", tags=["Lohn"],
          summary="Zeitdaten importieren (Krankheit, Urlaub, Überstunden)")
def lohn_zeitdaten(ma_id: str, monat: str, data: ZeitdatenImport,
    _user: dict = Depends(get_current_user)):
    return _get_lohn(get_ds(_user)).zeitdaten_importieren(ma_id, monat, data.dict())

@app.post("/lohn/abrechnung/{ma_id}/{monat}", tags=["Lohn"],
          summary="Lohnabrechnung berechnen (Brutto → Netto)")
def lohn_abrechnung(ma_id: str, monat: str, _user: dict = Depends(get_current_user)):
    try:
        return _get_lohn(get_ds(_user)).berechne_abrechnung(ma_id, monat)
    except ValueError as e:
        raise HTTPException(404, str(e))

@app.post("/lohn/batch/{mandant}/{monat}", tags=["Lohn"],
          summary="Alle Mitarbeiter eines Mandanten abrechnen")
def lohn_batch(mandant: str, monat: str, _user: dict = Depends(get_current_user)):
    store = get_ds(_user)
    get_mandant_or_404(mandant, store)
    abrechnungen = _get_lohn(store).batch_abrechnung(mandant, monat)
    return {"abrechnungen": abrechnungen, "anzahl": len(abrechnungen)}

@app.get("/lohn/abrechnung/{abrechnung_id}/html", tags=["Lohn"],
         summary="Lohnzettel als HTML (druckbar)")
def lohn_html(abrechnung_id: str, _user: dict = Depends(get_current_user)):
    from fastapi.responses import HTMLResponse
    try:
        html = _get_lohn(get_ds(_user)).lohnzettel_html(abrechnung_id)
        return HTMLResponse(content=html)
    except ValueError as e:
        raise HTTPException(404, str(e))

@app.get("/lohn/abrechnungen", tags=["Lohn"], summary="Alle Lohnabrechnungen")
def lohn_alle(
    mandant: Optional[str] = Query(None),
    monat:   Optional[str] = Query(None),
    _user: dict = Depends(get_current_user),
):
    return {"abrechnungen": _get_lohn(get_ds(_user)).abrechnungen_laden(mandant, monat)}


# ============================================================
# WORKFLOW BAUKASTEN (No-Code)
# ============================================================

class WorkflowRegelCreate(BaseModel):
    name:             str
    beschreibung:     str = ""
    trigger:          Dict
    bedingungen:      List[Dict] = []
    aktionen:         List[Dict]
    aktiv:            bool = True
    mandanten_filter: Optional[List[str]] = None

def _get_builder(store: DatenSpeicher):
    from core.workflow_builder import WorkflowBaukasten
    from core.proaktiver_bot   import ProaktiverBot
    bot = ProaktiverBot(store)
    return WorkflowBaukasten(store, bot=bot)

@app.post("/regeln", tags=["Workflow-Baukasten"], status_code=201,
          summary="Neue Automatisierungs-Regel erstellen")
def regel_erstellen(data: WorkflowRegelCreate, _user: dict = Depends(get_current_user)):
    try:
        return _get_builder(get_ds(_user)).regel_erstellen(**data.dict())
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.get("/regeln", tags=["Workflow-Baukasten"], summary="Alle Regeln")
def regeln_liste(nur_aktive: bool = Query(False), _user: dict = Depends(get_current_user)):
    return {"regeln": _get_builder(get_ds(_user)).regel_liste(nur_aktive)}

@app.put("/regeln/{regel_id}/aktiv", tags=["Workflow-Baukasten"],
         summary="Regel aktivieren/deaktivieren")
def regel_toggle(regel_id: str, aktiv: bool = Query(...),
    _user: dict = Depends(get_current_user)):
    try:
        return _get_builder(get_ds(_user)).regel_aktivieren(regel_id, aktiv)
    except ValueError as e:
        raise HTTPException(404, str(e))

@app.delete("/regeln/{regel_id}", tags=["Workflow-Baukasten"],
            summary="Regel löschen")
def regel_loeschen(regel_id: str, _user: dict = Depends(get_current_user)):
    _get_builder(get_ds(_user)).regel_loeschen(regel_id)
    return {"status": "gelöscht"}

@app.post("/regeln/ausfuehren", tags=["Workflow-Baukasten"],
          summary="Alle aktiven Regeln sofort ausführen")
def regeln_ausfuehren(background_tasks: BackgroundTasks, _user: dict = Depends(get_current_user)):
    store = get_ds(_user)
    def _run():
        try:
            result = _get_builder(store).fuehre_alle_aus()
            log.info(f"Workflow-Batch: {result}")
        except Exception as e:
            log.error(f"Workflow-Batch Fehler: {e}")
    background_tasks.add_task(_run)
    return {"status": "gestartet"}

@app.post("/regeln/standard-erstellen", tags=["Workflow-Baukasten"],
          summary="Standard-Workflows für neue Kanzlei erstellen")
def standard_workflows(_user: dict = Depends(get_current_user)):
    return {"erstellt": _get_builder(get_ds(_user)).erstelle_standard_workflows()}

@app.get("/regeln/statistiken", tags=["Workflow-Baukasten"],
         summary="Workflow-Statistiken")
def regeln_statistiken(_user: dict = Depends(get_current_user)):
    return _get_builder(get_ds(_user)).statistiken()

@app.get("/regeln/verfuegbare-trigger", tags=["Workflow-Baukasten"],
         summary="Alle verfügbaren Trigger-Typen")
def verfuegbare_trigger(_user: dict = Depends(get_current_user)):
    from core.workflow_builder import TRIGGER_TYPEN, AKTION_TYPEN
    return {"trigger": TRIGGER_TYPEN, "aktionen": AKTION_TYPEN}


# ============================================================
# AUTONOMER STEUERFALL AUTOPILOT
# ============================================================

class SteuerFallRequest(BaseModel):
    mandant:     str
    jahr:        int = None
    steuerart:   str = "ESt"
    auto_elster: bool = False

@app.post("/steuer/verarbeiten", tags=["Steuer-Autopilot"],
          summary="Steuerfall vollautomatisch verarbeiten (KI-gestützt)")
async def steuer_verarbeiten(data: SteuerFallRequest, background_tasks: BackgroundTasks,
    _user: dict = Depends(get_current_user)):
    """
    Vollautomatische Steuerfall-Verarbeitung:
    1. Alle Mandantendaten sammeln
    2. KI berechnet und prüft
    3. ELSTER XML vorbereiten
    4. Konfidenz-Score: >92% = fast ohne Review
    Reduziert Aufwand von 10h auf 15 Minuten.
    """
    store = get_ds(_user)
    get_mandant_or_404(data.mandant, store)
    from core.autonomer_steuerfall import AutononerSteuerfall
    autopilot = AutononerSteuerfall(store)
    api_key   = os.getenv("OPENAI_API_KEY","")
    jahr      = data.jahr or datetime.now().year - 1
    try:
        fall = await autopilot.verarbeite_steuerfall(
            data.mandant, jahr, data.steuerart, api_key, data.auto_elster
        )
        return fall
    except Exception as e:
        raise HTTPException(500, f"Steuerfall-Fehler: {e}")

@app.get("/steuer/daten/{mandant}/{jahr}", tags=["Steuer-Autopilot"],
         summary="Mandantendaten für Steuerfall sammeln (Vollständigkeits-Check)")
def steuer_daten_sammeln(mandant: str, jahr: int, _user: dict = Depends(get_current_user)):
    store = get_ds(_user)
    get_mandant_or_404(mandant, store)
    from core.autonomer_steuerfall import AutononerSteuerfall
    return AutononerSteuerfall(store).sammle_mandanten_daten(mandant, jahr)

@app.post("/steuer/{fall_id}/freigeben", tags=["Steuer-Autopilot"],
          summary="Steuerfall nach Review freigeben")
def steuer_freigeben(fall_id: str, freigegeben_von: str = Query("Steuerberater"),
    _user: dict = Depends(get_current_user)):
    from core.autonomer_steuerfall import AutononerSteuerfall
    try:
        return AutononerSteuerfall(get_ds(_user)).fall_freigeben(fall_id, freigegeben_von)
    except ValueError as e:
        raise HTTPException(404, str(e))

@app.get("/steuer/faelle", tags=["Steuer-Autopilot"],
         summary="Alle Steuerfälle")
def steuer_faelle_liste(mandant: Optional[str] = Query(None), status: Optional[str] = Query(None),
    _user: dict = Depends(get_current_user)):
    from core.autonomer_steuerfall import AutononerSteuerfall
    return {"faelle": AutononerSteuerfall(get_ds(_user)).faelle_laden(mandant, status)}

@app.get("/steuer/statistiken", tags=["Steuer-Autopilot"],
         summary="Autopilot-Statistiken (gesparte Stunden)")
def steuer_statistiken(_user: dict = Depends(get_current_user)):
    from core.autonomer_steuerfall import AutononerSteuerfall
    return AutononerSteuerfall(get_ds(_user)).statistiken()


# ============================================================
# ML BUCHUNGSASSISTENT
# ============================================================

class MLKategorisierungRequest(BaseModel):
    lieferant: str
    betrag:    float = 0.0
    dateiname: str = ""
    inhalt:    str = ""
    branche:   str = ""
    mandant:   str = ""

class MLFeedbackRequest(BaseModel):
    lieferant:   str
    betrag:      float
    kategorie:   str
    skr03_konto: str
    branche:     str = ""
    mandant:     str = ""
    inhalt:      str = ""
    mwst_satz:   int = 19
    vorsteuer:   bool = True

@app.post("/ml/kategorisieren", tags=["ML-Buchung"],
          summary="Lieferant KI-gestützt kategorisieren (lernt aus Bestätigungen)")
def ml_kategorisieren(data: MLKategorisierungRequest, _user: dict = Depends(get_current_user)):
    """
    Kategorisiert einen Lieferanten basierend auf:
    - Gelernten Patterns aus bestätigten Buchungen
    - Branchenspezifischen Regeln
    - Beleg-Inhalt (Stichworte)
    - Betrag-Analyse
    Wird mit jeder Bestätigung besser.
    """
    from core.ml_buchung import MLBuchungsassistent
    ml = MLBuchungsassistent()
    return ml.kategorisiere(
        data.lieferant, data.betrag, data.dateiname,
        data.inhalt, data.branche, data.mandant
    )

@app.post("/ml/feedback", tags=["ML-Buchung"],
          summary="Bestätigte Buchung als Training speichern")
def ml_feedback(data: MLFeedbackRequest,
    _user: dict = Depends(get_current_user)):
    """
    Jede bestätigte Buchung verbessert das System.
    Feedback-Loop: bestätigen → lernen → nächstes Mal besser.
    """

    store = get_ds(_user)
    from core.ml_buchung import MLBuchungsassistent
    ml = MLBuchungsassistent()
    ml.buchung_bestätigt(
        data.lieferant, data.betrag, data.kategorie, data.skr03_konto,
        data.branche, data.mandant, data.inhalt, data.mwst_satz, data.vorsteuer
    )
    store.log_eintrag(f"ML_TRAINING | {data.lieferant} → {data.kategorie}")
    return {"status": "gelernt", "lieferant": data.lieferant, "kategorie": data.kategorie}

@app.get("/ml/statistiken", tags=["ML-Buchung"],
         summary="ML-Statistiken (wie viel hat das System gelernt?)")
def ml_statistiken(_user: dict = Depends(get_current_user)):
    from core.ml_buchung import MLBuchungsassistent
    return MLBuchungsassistent().statistiken()

@app.get("/ml/lieferanten", tags=["ML-Buchung"],
         summary="Alle bekannten Lieferanten mit gelernten Kategorien")
def ml_lieferanten(_user: dict = Depends(get_current_user)):
    from core.ml_buchung import MLBuchungsassistent
    return {"lieferanten": MLBuchungsassistent().top_lieferanten()}


# ============================================================
# FINANZIERUNG — Nachzahlung + Ratenzahlung + Stundung
# ============================================================

class FinanzierungRequest(BaseModel):
    mandant:     str
    betrag:      float
    steuerart:   str = "ESt"
    jahr:        Optional[int] = None
    frist_datum: Optional[str] = None
    anlass:      str = "steuernachzahlung"

@app.post("/finanzierung/angebot", tags=["Finanzierung"],
          summary="Finanzierungsangebot bei Steuernachzahlung erstellen")
def finanzierung_angebot(data: FinanzierungRequest, _user: dict = Depends(get_current_user)):
    """
    Erstellt sofort passendes Finanzierungsangebot:
    - Ratenzahlungsoptionen berechnet
    - Stundungsantrag (§ 222 AO) ausgefüllt
    - Partner-Empfehlungen nach Kosten sortiert
    - Sofort-Maßnahmen je nach Dringlichkeit
    """
    store = get_ds(_user)
    get_mandant_or_404(data.mandant, store)
    from core.finanzierung_service import FinanzierungService
    fs = FinanzierungService(store)
    return fs.erstelle_angebot(
        data.mandant, data.betrag, data.anlass,
        data.frist_datum, data.steuerart, data.jahr
    )

@app.get("/finanzierung/angebote", tags=["Finanzierung"],
         summary="Alle Finanzierungsangebote")
def finanzierung_angebote(mandant: Optional[str] = Query(None),
    _user: dict = Depends(get_current_user)):
    from core.finanzierung_service import FinanzierungService
    return {"angebote": FinanzierungService(get_ds(_user)).angebote_laden(mandant)}

@app.get("/finanzierung/partner", tags=["Finanzierung"],
         summary="Alle Finanzierungs-Partner und deren Konditionen")
def finanzierung_partner(_user: dict = Depends(get_current_user)):
    from core.finanzierung_service import FINANZIERUNGS_PARTNER
    return {"partner": FINANZIERUNGS_PARTNER}

@app.get("/finanzierung/statistiken", tags=["Finanzierung"])
def finanzierung_statistiken(_user: dict = Depends(get_current_user)):
    from core.finanzierung_service import FinanzierungService
    return FinanzierungService(get_ds(_user)).statistiken()


# ============================================================
# MULTI-TENANT SaaS
# ============================================================

class TenantCreate(BaseModel):
    kanzlei_name:   str
    inhaber_name:   str
    inhaber_email:  str
    plan:           str = "starter"
    subdomain:      Optional[str] = None
    telefon:        str = ""
    adresse:        str = ""

@app.post("/saas/tenant", tags=["SaaS"], status_code=201,
          summary="Neue Kanzlei als Tenant registrieren")
def tenant_erstellen(data: TenantCreate, _m: bool = Depends(require_saas_master)):
    """
    Registriert eine neue Kanzlei als isolierten Tenant.
    Erstellt eigenen Workspace, API-Key und Subdomain.
    API-Key wird NUR einmal zurückgegeben — danach nicht mehr abrufbar!
    """
    from core.multi_tenant import get_tenant_manager
    tm = get_tenant_manager()
    try:
        return tm.tenant_erstellen(
            data.kanzlei_name, data.inhaber_name, data.inhaber_email,
            data.plan, data.subdomain, data.telefon, data.adresse,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.get("/saas/tenants", tags=["SaaS"], summary="Alle Tenants (Master-Admin)")
def tenants_liste(_m: bool = Depends(require_saas_master)):
    from core.multi_tenant import get_tenant_manager
    return {"tenants": get_tenant_manager().alle_tenants()}

@app.get("/saas/statistiken", tags=["SaaS"],
         summary="SaaS-Statistiken: MRR, ARR, Churn")
def saas_statistiken(_m: bool = Depends(require_saas_master)):
    from core.multi_tenant import get_tenant_manager
    return get_tenant_manager().saas_statistiken()

@app.put("/saas/tenant/{tenant_id}", tags=["SaaS"],
         summary="Tenant aktualisieren")
def tenant_update(tenant_id: str, updates: Dict = Body(...),
    _m: bool = Depends(require_saas_master)):
    from core.multi_tenant import get_tenant_manager
    try:
        return get_tenant_manager().tenant_aktualisieren(tenant_id, updates)
    except ValueError as e:
        raise HTTPException(404, str(e))

@app.post("/saas/tenant/{tenant_id}/sperren", tags=["SaaS"])
def tenant_sperren(tenant_id: str, grund: str = Query(""),
    _m: bool = Depends(require_saas_master)):
    from core.multi_tenant import get_tenant_manager
    get_tenant_manager().tenant_sperren(tenant_id, grund)
    return {"status": "gesperrt", "tenant_id": tenant_id}

@app.post("/saas/tenant/{tenant_id}/api-key-erneuern", tags=["SaaS"])
def api_key_erneuern(tenant_id: str, _m: bool = Depends(require_saas_master)):
    from core.multi_tenant import get_tenant_manager
    try:
        neuer_key = get_tenant_manager().api_key_erneuern(tenant_id)
        return {"api_key": neuer_key, "hinweis": "Diesen Key sicher speichern — wird nicht nochmal gezeigt!"}
    except ValueError as e:
        raise HTTPException(404, str(e))

@app.get("/saas/plaene", tags=["SaaS"], summary="Verfügbare Subscription-Pläne")
def saas_plaene(_m: bool = Depends(require_saas_master)):
    from core.multi_tenant import PLAENE
    return {"plaene": PLAENE}


# ============================================================
# ONBOARDING
# ============================================================

class OnboardingRequest(BaseModel):
    kanzlei_name:    str
    inhaber_email:   str
    stundensatz:     float = 150.0
    mit_demo_daten:  bool  = True

@app.post("/onboarding/starten", tags=["Onboarding"],
          summary="Neue Kanzlei in 5 Minuten vollständig einrichten")
def onboarding_starten(data: OnboardingRequest, background_tasks: BackgroundTasks,
    _user: dict = Depends(get_current_user)):
    """
    Komplettes Onboarding:
    1. Einstellungen konfigurieren
    2. Demo-Mandanten anlegen (3 Stück)
    3. ML-Buchungsassistent vortrainieren
    4. Standard-Workflows aktivieren
    5. Bot-Analyse starten
    Dauer: ca. 30-60 Sekunden.
    """
    from core.onboarding_service import OnboardingService
    os_svc = OnboardingService(get_ds(_user))
    return os_svc.schnell_onboarding(
        data.kanzlei_name, data.inhaber_email,
        data.stundensatz, data.mit_demo_daten,
    )

@app.get("/onboarding/status", tags=["Onboarding"],
         summary="Onboarding-Fortschritt prüfen")
def onboarding_status(_user: dict = Depends(get_current_user)):
    """Zeigt wie vollständig das Setup ist (0-100%)."""
    from core.onboarding_service import OnboardingService
    return OnboardingService(get_ds(_user)).onboarding_status()


# ============================================================
# WEBSOCKET — Live-Updates
# ============================================================

from fastapi import WebSocket, WebSocketDisconnect
import asyncio

class ConnectionManager:
    """Verwaltet alle aktiven WebSocket-Verbindungen."""
    def __init__(self):
        self.active: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def register(self, ws: WebSocket):
        """Bereits akzeptierte Verbindung registrieren (nach Auth)."""
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, data: dict):
        """Sendet Update an alle verbundenen Clients."""
        disconnected = []
        for ws in self.active:
            try:
                await ws.send_json(data)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)

ws_manager = ConnectionManager()

@app.websocket("/ws/live")
async def websocket_live(ws: WebSocket, token: Optional[str] = Query(None)):
    """
    WebSocket für Live-Dashboard-Updates (nur mit gültigem Session-Token).
    Verbindung: ws://localhost:8000/ws/live?token=SESSION_TOKEN
    """
    from core.auth import verifiziere_session, hat_irgendein_benutzer
    if hat_irgendein_benutzer():
        if not token:
            await ws.close(code=4401)
            return
        user = verifiziere_session(token)
        if not user:
            await ws.close(code=4401)
            return
    else:
        user = {"kanzlei_id": "default", "benutzername": "setup"}
    store = get_ds(user)
    await ws.accept()
    ws_manager.register(ws)
    try:
        while True:
            try:
                mandanten  = store.hole_mandanten()
                aufgaben   = store.hole_fristen()
                jetzt      = datetime.now()

                offen_aufgaben = sum(
                    1 for a in aufgaben.values() if not a.get("erledigt")
                )
                kritisch = sum(
                    1 for a in aufgaben.values()
                    if not a.get("erledigt") and
                    a.get("frist","9999") <= (jetzt + timedelta(days=2)).strftime("%Y-%m-%d")
                )

                zeiterfassung = _kv_get(store, "__zeiterfassung_v1", {"laufend": {}})
                if not isinstance(zeiterfassung, dict):
                    zeiterfassung = {"laufend": {}}
                laufend = list((zeiterfassung.get("laufend") or {}).keys())

                bot_fragen = _kv_get(store, "__bot_fragen_v1", {})
                if not isinstance(bot_fragen, dict):
                    bot_fragen = {}
                bot_offen = sum(1 for f in bot_fragen.values() if f.get("status") == "offen")

                try:
                    await ws.send_json({
                        "typ":              "live_update",
                        "zeitpunkt":        jetzt.isoformat(),
                        "mandanten_gesamt": len(mandanten),
                        "aufgaben_offen":   offen_aufgaben,
                        "aufgaben_kritisch":kritisch,
                        "timer_laufend":    len(laufend),
                        "bot_fragen_offen": bot_offen,
                    })
                except Exception:
                    break

            except Exception as e:
                log.warning(f"WebSocket Broadcast Fehler: {e}")

            await asyncio.sleep(5)

    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


# ── Broadcast-Funktion für andere Endpoints ──────────────────
async def live_update_senden(typ: str, data: dict):
    """Andere Endpoints können über diesen Helper Live-Updates senden."""
    try:
        await ws_manager.broadcast({"typ": typ, **data})
    except Exception:
        pass



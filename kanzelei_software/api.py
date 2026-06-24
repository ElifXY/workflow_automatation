from __future__ import annotations

# ============================================================
# KANZLEI AI — PRODUCTION API v3.0
# Fixes: Thread-safe DB, Rate-Limiting, Auth auf allen Endpoints,
#        Standardisierte Responses, Globales Error-Handling
# ============================================================

from fastapi import HTTPException, BackgroundTasks, Query, status, Depends, Header, Body, Request
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from fastapi.exceptions import RequestValidationError
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Optional, List, Dict, Any, Tuple

from datetime import datetime, timedelta
from pathlib import Path
import uuid
import asyncio
import os
import json
import logging
import time
import re
import smtplib
import hmac
import hashlib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import httpx
import secrets
import html as html_module
from urllib.parse import quote
from urllib.parse import urlencode
from urllib.parse import urlsplit
import base64

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
    email_outbox_dead_24h_count,
    webhook_queue_failed_24h_count,
    agent_action_record,
    agent_action_update,
    agent_actions_list,
    agent_lock_try_acquire,
    agent_lock_release,
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
from core.aufgabe_erledigt import aufgabe_ist_erledigt, aufgabe_ist_offen
from core.decision_engine import analysiere_alle_mandanten, berechne_steuerfristen, berechne_mandant_score
from core.ai_email import generate_ai_email
from core.ai_service import assistant_chat, analyze_document, analyze_receipt
from core.ai_guardrails import guard_input_text
from backend.services.mandanten_service import MandantenService
from backend.services.aufgaben_service import AufgabenService
from backend.services.settings_service import SettingsService

load_dotenv()

from backend.deps import get_current_user, require_admin, require_owner
from backend.permissions import require_permission as _require_permission
from backend.schemas import CreateUserRequest
from backend.feature_gate import should_block_advanced_path
from backend.tenant import tenant_id_from_user
from core.rbac import has_permission
from core.tenant_nav_policy import merged_settings_for_user
from core.pg_runtime import pg_primary_db
from modules.settings_manager import setting_holen as global_setting_holen


class WebhookCreateRequest(BaseModel):
    url: str
    event: str


# ── Logging ──────────────────────────────────────────────────
os.makedirs("data", exist_ok=True)
_log_dir = (os.getenv("API_LOG_DIR") or "data").strip() or "data"
os.makedirs(_log_dir, exist_ok=True)
_log_path = os.path.join(_log_dir, "api.log")

_log_handlers_api: list[logging.Handler] = [logging.StreamHandler()]
try:
    _log_handlers_api.append(logging.FileHandler(_log_path, encoding="utf-8"))
except OSError:
    pass  # bereits in backend.application geloggt oder nur stdout

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=_log_handlers_api,
)
log = logging.getLogger("kanzlei_api")

# ── App (eine Instanz: ``backend.application``) ─────────────────
from backend.application import app  # noqa: E402

ds = DatenSpeicher()   # Fallback für Startup + nicht-User-spezifische Calls

def get_ds(user: dict = None) -> DatenSpeicher:
    """
    Gibt DatenSpeicher für die Kanzlei des eingeloggten Users zurück.
    Kern des Multi-Kanzlei-Systems: jeder User sieht nur seine Daten.
    """
    kanzlei_id = (user or {}).get("tenant_id") or (user or {}).get("kanzlei_id", "default")
    if kanzlei_id == "default":
        return ds
    return DatenSpeicher(kanzlei_id=kanzlei_id)


def tenant_setting(store: DatenSpeicher, key: str, default=None):
    """Setting der eingeloggten Kanzlei (nicht global ``default``-Tenant)."""
    val = global_setting_holen(key, store=store)
    return default if val is None and default is not None else val


def _tenant_features_merged(user: dict) -> Dict[str, Any]:
    """Tenant-Feature-Flags (Defaults + Mandanten-Overrides in ``DatenSpeicher``)."""
    from core.tenant_features import FEATURE_SETTINGS_KEY, merged_features

    store = get_ds(user)
    raw = store.setting_holen(FEATURE_SETTINGS_KEY, {})
    return merged_features(raw)


def _require_tenant_feature(user: dict, feature_key: str) -> None:
    if not _tenant_features_merged(user).get(feature_key):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Feature nicht freigeschaltet: {feature_key}",
        )


def _billing_enabled() -> bool:
    return bool(global_setting_holen("billing_aktiv"))


# ── Rate-Limiting (In-Memory) ─────────────────────────────────
_rate_store: Dict[str, List[float]] = {}
# SPA: viele parallele GETs (Dashboard, Chat-Polling) — ausreichend hoch halten
RATE_LIMIT   = int(os.getenv("API_RATE_LIMIT", "2000"))   # Requests/Minute pro IP (nur ohne Login)
RATE_WINDOW  = 60  # Sekunden
_tenant_rate_store: Dict[str, List[float]] = {}

# Tenant-Limit: Schreibzugriffe und teure Endpunkte zählen; normale Lese-GETs nicht
_TENANT_RL_EXEMPT_GET_PREFIXES = (
    "/settings",
    "/kpis",
    "/heute",
    "/empfehlungen",
    "/mandanten",
    "/aufgaben",
    "/kommunikation",
    "/billing/",
    "/saas/",
    "/ready",
    "/health",
    "/portal/mandant/",
    "/portal/unterschriften/",
    "/prognose/",
    "/dashboard",
    "/email/",
)
_TENANT_RL_EXEMPT_EXACT = frozenset({"/ready", "/health", "/portal/health"})


def _effective_tenant_rate_limit() -> int:
    """0 = aus. Nur Schreibzugriffe zählen (_tenant_rate_counts). Zu niedrige Werte ignorieren."""
    try:
        v = int(global_setting_holen("api_rate_limit_pro_minute") or 0)
    except Exception:
        v = 0
    env_rl = (os.getenv("TENANT_API_RATE_LIMIT") or "").strip()
    if env_rl.isdigit():
        v = max(0, int(env_rl))
    if v > 0 and v < 500:
        log.warning("api_rate_limit_pro_minute=%s zu niedrig — deaktiviert (min. 500)", v)
        return 0
    return v


def _tenant_rate_counts(path: str, method: str) -> bool:
    """Nur Schreibzugriffe (POST/PUT/PATCH/DELETE) — Lese-Polling blockiert die SPA nicht."""
    m = (method or "GET").upper()
    if m in ("OPTIONS", "HEAD", "GET"):
        return False
    return True

def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

def _has_bearer_auth(request: Request) -> bool:
    auth = (request.headers.get("Authorization") or "").strip()
    return auth.lower().startswith("bearer ") and len(auth) > 14


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Eingeloggte Nutzer: kein IP-Limit (Polling würde sonst „Zu viele Anfragen“ auslösen)
    path = request.url.path or "/"
    if _has_bearer_auth(request) and path not in (
        "/auth/login", "/login", "/api/login", "/api/auth/login",
    ):
        return await call_next(request)

    # Auth-Endpoints strenger limitieren
    is_auth = path in frozenset(
        {
            "/auth/login",
            "/login",
            "/api/login",
            "/register",
            "/api/register",
            "/api/auth/login",
            "/auth/password/forgot",
            "/api/auth/password/forgot",
            "/auth/password/reset",
            "/api/auth/password/reset",
        }
    )
    limit   = 10 if is_auth else RATE_LIMIT
    ip      = _get_client_ip(request)
    key     = f"{ip}:{path if is_auth else ip}"

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


_env_for_logs = (os.getenv("ENVIRONMENT") or os.getenv("APP_ENV") or "development").lower()
_sal = (os.getenv("STRUCTURED_ACCESS_LOG") or "").strip().lower()
if _sal in ("1", "true", "yes"):
    _STRUCTURED_ACCESS = True
elif _sal in ("0", "false", "no", "off"):
    _STRUCTURED_ACCESS = False
else:
    _STRUCTURED_ACCESS = _env_for_logs == "production"


@app.middleware("http")
async def structured_access_log(request: Request, call_next):
    """Eine JSON-Zeile pro Request (stdout → Docker-Logs), in Production standardmäßig an."""
    if not _STRUCTURED_ACCESS:
        return await call_next(request)
    t0 = time.perf_counter()
    status_code = 500
    response = None
    try:
        response = await call_next(request)
        status_code = getattr(response, "status_code", 200)
        return response
    except Exception:
        status_code = 500
        raise
    finally:
        dur_ms = int((time.perf_counter() - t0) * 1000)
        log.info(
            json.dumps(
                {
                    "access": True,
                    "method": request.method,
                    "path": request.url.path,
                    "status": status_code,
                    "duration_ms": dur_ms,
                    "client": _get_client_ip(request),
                },
                ensure_ascii=False,
            )
        )


PLAN_USAGE_LIMITS = {
    "starter": {"ai_requests_day": 200, "exports_day": 30, "settings_changes_day": 80},
    "professional": {"ai_requests_day": 2000, "exports_day": 300, "settings_changes_day": 400},
    "enterprise": {"ai_requests_day": 100000, "exports_day": 10000, "settings_changes_day": 20000},
}


def _next_plan(plan: str) -> str:
    p = (plan or "starter").strip().lower()
    if p == "starter":
        return "professional"
    if p == "professional":
        return "enterprise"
    return "enterprise"


def _upgrade_offer_payload(plan: str, metric: str, used: int, limit: int) -> Dict[str, Any]:
    next_plan = _next_plan(plan)
    upgrade_url = (os.getenv("BILLING_UPGRADE_URL") or os.getenv("SALES_CONTACT_URL") or "").strip()
    # Default: 20% Rabatt bei jährlicher Zahlweise als Conversion-Hebel.
    annual_discount_pct = int((os.getenv("ANNUAL_DISCOUNT_PERCENT") or "20").strip() or "20")
    return {
        "current_plan": plan,
        "recommended_plan": next_plan,
        "metric": metric,
        "used": int(used),
        "limit": int(limit),
        "annual_discount_percent": max(0, min(60, annual_discount_pct)),
        "upgrade_url": upgrade_url or None,
        "message": (
            f"{metric} Limit erreicht ({used}/{limit}). "
            f"Upgrade auf {next_plan} verhindert Ausfälle in umsatzkritischen Automationen."
        ),
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
        from backend.auth import hole_kanzlei

        kid = user.get("tenant_id") or user.get("kanzlei_id") or "default"
        row = hole_kanzlei(kid) or {}
        return (row.get("plan") or "starter").strip().lower()
    except Exception as exc:  # noqa: BLE001
        log.debug("plan_for_user fallback starter: %s", exc)
        return "starter"


def _usage_auth_context_from_bearer(raw_token: str) -> Optional[dict]:
    """
    Session-Token (core.auth) oder JWT (gleiche Limits wie Session).
    Ohne gültigen Kontext: None — Request läuft ohne Quota-Check (z. B. öffentliche Routen).
    """
    token = (raw_token or "").strip()
    if not token:
        return None
    from backend.auth import verifiziere_session
    from backend.auth import jwt_secret, verify_access_token

    session = verifiziere_session(token)
    if session:
        return session
    if jwt_secret():
        claims = verify_access_token(token)
        if claims and (claims.get("typ") or "access") == "access":
            kid = claims.get("tenant_id") or claims.get("kanzlei_id") or "default"
            sub = (claims.get("sub") or "").strip()
            if sub:
                return {
                    "benutzername": sub,
                    "kanzlei_id": kid,
                    "tenant_id": kid,
                    "rolle": claims.get("rolle") or claims.get("role") or "assistent",
                }
    return None


def _usage_quota_breakdown(kanzlei_id: str, plan: str) -> Dict[str, Any]:
    """Kunden- und Umsatz-relevant: klare Auslastung + Ampel pro Metrik."""
    limits = PLAN_USAGE_LIMITS.get(plan, PLAN_USAGE_LIMITS["starter"])
    by_metric: Dict[str, Any] = {}
    overall = "ok"
    for mkey, lim in limits.items():
        if not lim:
            continue
        used = int(usage_get(kanzlei_id, mkey))
        pct = min(100, int(100 * used / max(1, int(lim))))
        remaining = max(0, int(lim) - used)
        if used >= int(lim):
            st = "limit"
            overall = "limit"
        elif pct >= 90:
            st = "critical"
            overall = "critical" if overall == "ok" else overall
        elif pct >= 75:
            st = "warning"
            if overall == "ok":
                overall = "warning"
        else:
            st = "ok"
        by_metric[mkey] = {
            "used": used,
            "limit": int(lim),
            "remaining": remaining,
            "percent_used": pct,
            "status": st,
        }
    return {"overall": overall, "by_metric": by_metric}


@app.middleware("http")
async def usage_quota_middleware(request: Request, call_next):
    metric = _usage_metric_for_path(request.url.path)
    if not metric:
        return await call_next(request)

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return await call_next(request)
    ctx = _usage_auth_context_from_bearer(auth.removeprefix("Bearer ").strip())
    if not ctx:
        return await call_next(request)

    plan = _plan_for_user(ctx)
    limit = PLAN_USAGE_LIMITS.get(plan, PLAN_USAGE_LIMITS["starter"]).get(metric, 0)
    kid = str(ctx.get("tenant_id") or ctx.get("kanzlei_id") or "default").strip() or "default"
    current = usage_get(kid, metric)
    if limit and current >= limit:
        offer = _upgrade_offer_payload(plan, metric, int(current), int(limit))
        payload = {
                "ok": False,
                "error": f"Plan-Limit erreicht ({metric}: {current}/{limit})",
                "code": 402,
                "metric": metric,
                "plan": plan,
            "hint": "Upgrade erhöht Limits und stabilisiert Umsatz-relevante Automatisierung.",
            "upgrade_offer": offer,
        }
        if offer.get("upgrade_url"):
            payload["upgrade_url"] = offer["upgrade_url"]
        return JSONResponse(status_code=402, content=payload)

    response = await call_next(request)
    if response.status_code < 400:
        try:
            usage_increment(kid, metric, 1)
            used_after = int(current) + 1
            pct = int(100 * used_after / max(1, int(limit))) if limit else 0
            if limit:
                if used_after >= int(limit):
                    qstatus = "limit"
                elif pct >= 90:
                    qstatus = "critical"
                elif pct >= 75:
                    qstatus = "warning"
                else:
                    qstatus = "ok"
                response.headers["X-Quota-Metric"] = metric
                response.headers["X-Quota-Used"] = str(used_after)
                response.headers["X-Quota-Limit"] = str(limit)
                response.headers["X-Quota-Percent"] = str(min(100, pct))
                response.headers["X-Quota-Status"] = qstatus
                response.headers["X-Quota-Plan"] = plan
                if qstatus in {"warning", "critical"}:
                    offer = _upgrade_offer_payload(plan, metric, used_after, int(limit))
                    response.headers["X-Quota-Recommend-Plan"] = str(offer["recommended_plan"])
                    if offer.get("upgrade_url"):
                        response.headers["X-Quota-Upgrade-Url"] = str(offer["upgrade_url"])
        except Exception as exc:  # noqa: BLE001
            log.warning("usage_increment failed kanzlei=%s metric=%s: %s", kid, metric, exc)
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

def ok_compat(payload: Any, message: Optional[str] = None, **kwargs) -> Dict:
    """
    Einheitliches Format ohne Breaking Changes:
    - behält bestehende Top-Level-Felder (nur bei dict)
    - ergänzt zusätzlich ok/data/message
    """
    result = {"ok": True, "data": payload}
    if isinstance(payload, dict):
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
    betreuer_email: Optional[str] = None

class MandantUpdate(BaseModel):
    umsatz:    Optional[float] = Field(None, ge=0)
    email:     Optional[str]  = None
    telefon:   Optional[str]  = None
    branche:   Optional[str]  = None
    notizen:   Optional[str]  = None
    steuer_id: Optional[str]  = None
    adresse:   Optional[str]  = None
    betreuer_email: Optional[str] = None


class BetreuerZuweisung(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    betreuer_email: Optional[str] = None


class BetreuerBulkUpdate(BaseModel):
    assignments: Optional[List[BetreuerZuweisung]] = None
    betreuer_email: Optional[str] = None
    mandanten: Optional[List[str]] = None
    nur_ohne_betreuer: bool = False

class AufgabeCreate(BaseModel):
    beschreibung: str          = Field(..., min_length=1, max_length=500)
    frist:        str          = Field(..., example="2026-06-30")
    frist_uhrzeit: Optional[str] = Field(None, example="14:00")
    prioritaet:   Optional[str] = Field("normal")
    kategorie:    Optional[str] = None
    notiz:        Optional[str] = None
    portal_sichtbar: Optional[bool] = Field(
        False,
        description="Mandant sieht und kann die Aufgabe im Portal-Chat abhaken",
    )


class AufgabeUpdate(BaseModel):
    beschreibung: Optional[str] = Field(None, min_length=1, max_length=500)
    mandant: Optional[str] = Field(None, description="Aufgabe anderem Mandanten zuordnen (Name wie in Mandantenliste)")
    frist: Optional[str] = None
    frist_uhrzeit: Optional[str] = None
    prioritaet: Optional[str] = None
    kategorie: Optional[str] = None
    notiz: Optional[str] = None

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

def get_mandant_or_404(name: str, ds_instance=None, user: Optional[dict] = None) -> Dict:
    store = ds_instance or ds
    m = store.hole_mandant(name)
    if not m:
        raise HTTPException(
            status_code=404,
            detail=f"Mandant '{name}' nicht gefunden"
        )
    if user is not None:
        from core.mandant_access import assert_mandant_access

        assert_mandant_access(user, m, name)
    return m


def _kv_get(store: DatenSpeicher, key: str, default):
    value = store.setting_holen(key, default)
    return value if value is not None else default


def _kv_set(store: DatenSpeicher, key: str, value) -> None:
    store.setting_setzen(key, value)


def _billing_obs_inc(kanzlei_id: str, key: str, delta: int = 1) -> None:
    try:
        kid = str(kanzlei_id or "default").strip() or "default"
        store = DatenSpeicher(kanzlei_id=kid)
        raw = store.setting_holen("__billing_observability_v1", {}) or {}
        obs = raw if isinstance(raw, dict) else {}
        obs[str(key)] = int(obs.get(str(key), 0)) + int(delta)
        obs["last_updated_at"] = datetime.utcnow().isoformat()
        store.setting_setzen("__billing_observability_v1", obs)
    except Exception:
        pass


def _billing_obs_get(kanzlei_id: str) -> Dict[str, Any]:
    try:
        kid = str(kanzlei_id or "default").strip() or "default"
        store = DatenSpeicher(kanzlei_id=kid)
        raw = store.setting_holen("__billing_observability_v1", {}) or {}
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


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


def send_email_smtp(
    to_email: str,
    subject: str,
    body: str,
    html_body: str = None,
    from_header: Optional[str] = None,
    reply_to: Optional[str] = None,
    store: Optional[DatenSpeicher] = None,
    *,
    allow_global_smtp: bool = False,
) -> bool:
    """
    Sendet E-Mail via SMTP (pro Kanzlei aus Einstellungen → E-Mail-Versand).
    ``allow_global_smtp``: nur System-Mails (Einladung/Verify) dürfen .env nutzen.
    """
    from core.email_sender import (
        resolve_smtp_transport,
        send_email_via_transport,
        global_smtp_transport,
    )

    transport = resolve_smtp_transport(store, allow_global=allow_global_smtp)
    if not transport and allow_global_smtp:
        transport = global_smtp_transport()
    if not transport:
        log.warning(
            "SMTP nicht konfiguriert — Kanzlei: Einstellungen → E-Mail-Versand aktivieren"
        )
        return False
    return send_email_via_transport(
        transport,
        to_email,
        subject,
        body,
        html_body,
        from_header=from_header,
        reply_to=reply_to,
    )


def _invite_registration_url(invite_token: str) -> str:
    """Öffentlicher Link zur SPA-Registrierung inkl. ``invite_token``."""
    base = (os.getenv("PORTAL_BASE_URL") or os.getenv("PUBLIC_APP_URL") or "").strip().rstrip("/")
    if not base:
        port = int(os.getenv("PORTAL_PORT") or os.getenv("API_PORT") or os.getenv("API_PUBLIC_PORT") or "8000")
        base = f"http://127.0.0.1:{port}"
    return f"{base}/register-email?invite_token={quote(invite_token, safe='')}"


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
            kid = str(row.get("kanzlei_id") or "default")
            from core.email_sender import resolve_email_from

            st_out = DatenSpeicher(kanzlei_id=kid)
            resolved = resolve_email_from(kid, st_out)
            ok_send = send_email_smtp(
                row.get("to_email", ""),
                row.get("subject", ""),
                row.get("body_text", ""),
                row.get("body_html") or None,
                from_header=resolved["from_header"],
                reply_to=resolved.get("reply_to") or None,
                store=st_out,
                allow_global_smtp=False,
            )
            if not ok_send:
                raise RuntimeError("SMTP send fehlgeschlagen")
            email_outbox_mark_sent(int(oid))
            sent += 1
            idk = str(row.get("idempotency_key") or "").strip()
            if idk.startswith("team_invite|"):
                parts = idk.split("|")
                if len(parts) >= 3:
                    inv_kid, inv_jti = parts[1], parts[2]
                    try:
                        from core.tenant_invite_records import invite_record_mark_email_smtp_sent

                        invite_record_mark_email_smtp_sent(jti=inv_jti, kanzlei_id=inv_kid)
                    except Exception:
                        pass
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
    log.info("Kanzlei Automation API v3.0 — Start")
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
    prod_errs: list[str] = []

    if environment == "production":
        database_url = (os.getenv("DATABASE_URL") or "").strip()
        if not database_url:
            prod_errs.append(
                "DATABASE_URL fehlt: Production benötigt Postgres-Verbindung (Compose setzt sie beim Service api)."
            )
        else:
            if not pg_primary_db():
                prod_errs.append(
                    "Production verlangt PostgreSQL: DATABASE_URL muss postgresql://… oder postgres://… sein."
                )
        if Path("data").exists():
            json_runtime = [
                str(p) for p in Path("data").rglob("*.json")
                if p.is_file()
            ]
            if json_runtime:
                prod_errs.append(
                    f"Production blockiert: JSON-Runtime-Dateien in data/: {json_runtime}"
                )

    # ── Daten-Verzeichnisse anlegen ───────────────────────────
    for d in ["data/uploads"]:
        os.makedirs(d, exist_ok=True)

    if environment == "production":
        allow_sqlite_fallback = (os.getenv("ALLOW_SQLITE_FALLBACK") or "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        sqlite_files = [str(p) for p in Path("data").glob("*.db") if p.is_file()]
        if sqlite_files and not allow_sqlite_fallback:
            prod_errs.append(
                "Production blockiert: SQLite-Dateien in data/ gefunden: "
                f"{sqlite_files}. Nur temporär: ALLOW_SQLITE_FALLBACK=1 für Hybrid."
            )

        gw = (os.getenv("API_GATEWAY_KEY") or "").strip()
        if gw and len(gw) < 32:
            prod_errs.append(
                "API_GATEWAY_KEY ist gesetzt, aber kürzer als 32 Zeichen."
            )
        elif not gw:
            log.warning(
                "Production: API_GATEWAY_KEY nicht gesetzt — öffentliche Routen nur per JWT/Session "
                "(empfohlen für Produktion: openssl rand -hex 24 in .env eintragen)."
            )
        raw_jwt = (os.getenv("JWT_SECRET") or "").strip()
        jsecret = raw_jwt.lower()
        if len(raw_jwt) < 48 or any(
            x in jsecret for x in ("placeholder", "dev-jwt", "change-in-prod", "minimum-64")
        ):
            prod_errs.append(
                "JWT_SECRET muss mindestens 48 Zeichen haben und keine Dev-Platzhalter-Muster enthalten."
            )
        du = (os.getenv("DATABASE_URL") or "").strip()
        if "KzDevOnly_" in du or "DevOnlyChangeBeforeProd2026X" in du:
            prod_errs.append(
                "DATABASE_URL enthält noch ein Compose-Dev-Passwort (Substring KzDevOnly_ / …). "
                "In .env POSTGRES_PASSWORD (und ggf. POSTGRES_USER) setzen — ohne dieses Muster im URL."
            )
        ru = (os.getenv("REDIS_URL") or "").strip()
        if ru and ("KzDevOnly_" in ru or "DevOnlyChangeBeforeProd2026X" in ru):
            prod_errs.append(
                "REDIS_URL enthält noch ein Compose-Dev-Passwort — REDIS_PASSWORD in .env anpassen."
            )

    if prod_errs:
        prod_errs.append(
            "Docker-Schnellstart: in .env ENVIRONMENT=development, bis alle Punkte oben erfüllt sind."
        )
        raise RuntimeError("Production-Konfiguration ungültig:\n• " + "\n• ".join(prod_errs))

    else:
        _du = (os.getenv("DATABASE_URL") or "").strip().lower()
        if _du.startswith("postgresql://"):
            log.warning(
                "Dev-Modus: DATABASE_URL ist PostgreSQL, Kern-Daten (Mandanten/Belege) nutzen "
                "DatenSpeicher weiter SQLite unter data/kanzlei.db. Für Testkunden-Production: "
                "ENVIRONMENT=production + nur Postgres (keine *.db in data/)."
            )

    # ── Auto-Agent starten ────────────────────────────────────
    asyncio.create_task(auto_agent_worker())
    asyncio.create_task(email_outbox_worker())
    asyncio.create_task(webhook_delivery_worker())
    asyncio.create_task(billing_weekly_digest_worker())
    log.info("✓ Auto-Agent gestartet")
    log.info("✓ Email-Outbox Worker gestartet")
    log.info("✓ Webhook Delivery Worker gestartet")
    log.info("✓ Weekly Digest Worker gestartet")
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
        "name": "Kanzlei Automation API",
        "version": "3.0.0",
        "status": "running",
        "docs": "/docs",
        "intro": "/api/v1/introduction",
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/health", tags=["System"])
@app.get("/api/health", tags=["System"])
def health():
    try:
        ds.hole_mandanten()
        return {"status": "healthy", "timestamp": datetime.now().isoformat()}
    except Exception as e:
        raise HTTPException(503, f"Datenspeicher nicht erreichbar: {e}")


@app.get("/ready", tags=["System"])
@app.get("/api/ready", tags=["System"])
def ready():
    """Readiness für Load-Balancer / go_live_check (ohne DB-Schreiblast)."""
    return {
        "status": "ready",
        "build": "api-deploy-20260520o",
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/system/build", tags=["System"])
@app.get("/api/system/build", tags=["System"])
def system_build():
    """Öffentlicher Deploy-Marker (ohne Auth) — zum Prüfen ob die API-Image-Version live ist."""
    return {
        "api_build": "api-deploy-20260520o",
        "ui_build_expected": "deploy-20260520o",
        "portal_build": "portal-deploy-20260520o",
        "email_absender_build": "email-absender-20260519c",
        "check_ui": "/build-info.json",
        "check_portal": "/portal/health",
    }


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
def api_v1_endpoints_catalog(_user: dict = Depends(get_current_user)):
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


@app.get("/product/focus", tags=["System"], summary="Produktfokus & ehrliche Feature-Grenzen")
def product_focus(_user: dict = Depends(get_current_user)):
    from core.product_focus import product_summary
    return ok(product_summary())


@app.get("/api/v1/introduction", tags=["System"])
def api_v1_introduction():
    from core.product_focus import PRODUCT_TAGLINE
    return ok({
        "produkt": "Kanzlei Automation",
        "kurzbeschreibung": PRODUCT_TAGLINE,
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


def require_permission(permission: str):
    """
    Backward-kompatible Fassade.

    Historisch wurde ``require_permission`` direkt in ``api.py`` gehalten.
    Die kanonische Implementierung lebt jetzt in ``backend.permissions``.
    """
    return _require_permission(permission)


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


# Jede Route außerhalb dieser Präfixe / exakten Pfade: Session (Bearer) oder X-API-Key Pflicht.
# Admin vs. User: pro Route über require_permission / RBAC (core/rbac.py).
_AUTH_EXEMPT_EXACT_PATHS = frozenset(
    {
        "/login",
        "/api/login",
        "/register",
        "/api/register",
        "/api/auth/login",
        "/api/auth/registrieren",
        "/api/auth/setup-status",
        "/billing/stripe/config",
        # Nginx / öffentliche Checks nutzen /api/* — Präfixe "/ready" schützen nicht "/api/ready".
        "/api/health",
        "/api/ready",
        "/system/build",
        "/api/system/build",
    }
)
_AUTH_EXEMPT_PREFIXES = (
    "/health",
    "/ready",
    "/system/build",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/auth/login",
    "/auth/registrieren",
    "/auth/setup-status",
    "/auth/password/forgot",
    "/auth/password/reset",
    "/auth/email/verify",
    "/auth/email/resend",
    "/auth/oauth/",
    "/api/auth/password/forgot",
    "/api/auth/password/reset",
    "/api/auth/email/verify",
    "/api/auth/email/resend",
    "/api/auth/oauth/",
    "/billing/stripe/webhook",
    "/api/v1/health",
    "/api/v1/meta",
    "/api/v1/introduction",
    "/api/v1/webhooks/verify-example",
    "/portal",
)


def _required_permission_for_path(path: str, method: str) -> Optional[str]:
    p = str(path or "/")
    m = (method or "GET").upper()

    if p.startswith("/settings"):
        return "settings:write" if m in {"POST", "PUT", "PATCH", "DELETE"} else "settings:read"
    if p.startswith("/admin/") or p.startswith("/api/admin/") or p.startswith("/users"):
        return "settings:write"
    if p.startswith("/regeln"):
        return "engine:run" if m in {"POST", "PUT", "PATCH", "DELETE"} else "engine:read"
    if p.startswith("/workflow/"):
        return "engine:run"
    if p.startswith("/engine/run"):
        return "engine:run"
    if p.startswith("/engine/"):
        return "engine:read"
    if p.startswith("/export/"):
        return "export:read"
    if p.startswith("/mandanten/") or p == "/mandanten":
        return "mandanten:write" if m in {"POST", "PUT", "PATCH", "DELETE"} else "mandanten:read"
    if p.startswith("/aufgaben/"):
        return "aufgaben:write" if m in {"POST", "PUT", "PATCH", "DELETE"} else "aufgaben:read"
    if "/aufgaben" in p:
        return "aufgaben:write" if m in {"POST", "PUT", "PATCH", "DELETE"} else "aufgaben:read"
    if p.startswith("/email/"):
        return "email:send" if m in {"POST", "PUT", "PATCH", "DELETE"} else "kommunikation:read"
    if p.startswith("/portal/mandant/"):
        return "portal:write" if m in {"POST", "PUT", "PATCH", "DELETE"} else "portal:read"
    return None


@app.middleware("http")
async def auth_guard_middleware(request: Request, call_next):
    """Jede HTTP-Route außerhalb der Whitelist: gültige Session (Bearer) oder X-API-Key."""
    path = request.url.path or "/"
    if path.startswith("/api/auth/"):
        return await call_next(request)
    if request.method == "OPTIONS":
        return await call_next(request)
    block_advanced, reason = should_block_advanced_path(path)
    if block_advanced:
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": (
                    "Advanced feature set is locked until security baseline is proven "
                    f"and activation is explicit ({reason})."
                ),
                "code": 503,
            },
        )
    if path == "/" or path in _AUTH_EXEMPT_EXACT_PATHS or path.startswith(_AUTH_EXEMPT_PREFIXES):
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

    current_kid = str(current_user.get("tenant_id") or current_user.get("kanzlei_id") or "")
    tenant_limit = _effective_tenant_rate_limit()
    if tenant_limit > 0 and _tenant_rate_counts(path, request.method):
        now = time.time()
        bucket = _tenant_rate_store.get(current_kid, [])
        bucket = [t for t in bucket if now - t < RATE_WINDOW]
        if len(bucket) >= tenant_limit:
            return JSONResponse(
                status_code=429,
                content={
                    "ok": False,
                    "error": f"Tenant Rate-Limit erreicht ({tenant_limit}/min)",
                    "code": 429,
                    "retry_after": RATE_WINDOW,
                },
            )
        bucket.append(now)
        _tenant_rate_store[current_kid] = bucket

    required_permission = _required_permission_for_path(path, request.method)
    if required_permission:
        if current_user.get("api_key_id"):
            perms = current_user.get("api_permissions") or []
            if "*" not in perms and required_permission not in perms:
                return JSONResponse(
                    status_code=403,
                    content={"ok": False, "error": f"API-Key ohne Berechtigung: {required_permission}", "code": 403},
                )
        else:
            role = str(current_user.get("rolle") or current_user.get("role") or "").strip().lower()
            _merged = merged_settings_for_user(current_user)
            if not has_permission(role, required_permission, _merged):
                return JSONResponse(
                    status_code=403,
                    content={"ok": False, "error": f"Fehlende Berechtigung: {required_permission}", "code": 403},
                )

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
    betreuer_email: Optional[str] = Query(None, description="Nur Mandanten dieses Betreuers"),
    nur_ohne_betreuer: bool = Query(False),
    nur_meine: bool = Query(False, description="Nur Mandanten des eingeloggten Users"),
    _user: dict = Depends(require_permission("mandanten:read")),
):
    from core.decision_engine import berechne_mandant_score
    from core.mandant_access import user_may_access_mandant
    store = get_ds(_user)
    svc = MandantenService(store)
    daten = svc.list_mandanten(suche=suche, branche=branche, min_umsatz=min_umsatz)
    result = []

    for row in daten:
        name = row.get("name", "")
        m = row
        if not user_may_access_mandant(_user, m):
            continue
        betr = str(m.get("betreuer_email") or "").strip().lower()
        if nur_ohne_betreuer and betr:
            continue
        if nur_meine:
            user_em = str(_user.get("email") or "").strip().lower()
            if betr and user_em and betr != user_em:
                continue
        if betreuer_email:
            want = str(betreuer_email or "").strip().lower()
            if betr != want:
                continue
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
            "betreuer_email":        m.get("betreuer_email", "") or "",
        })

    if   sortierung == "umsatz": result.sort(key=lambda x: x["umsatz"], reverse=True)
    elif sortierung == "score":  result.sort(key=lambda x: x["score"],  reverse=True)
    else:                        result.sort(key=lambda x: x["name"].lower())

    return ok(result, count=len(result))


@app.get("/suche", tags=["System"], summary="Globale Suche (Mandanten & Aufgaben)")
def globale_suche(
    q: str = Query(..., min_length=1, max_length=80),
    limit: int = Query(20, ge=1, le=40),
    _user: dict = Depends(require_permission("mandanten:read")),
):
    from core.mandant_access import user_may_access_mandant

    store = get_ds(_user)
    svc = MandantenService(store)
    needle = q.strip().lower()
    ergebnisse = []

    for row in svc.list_mandanten(suche=q):
        if not user_may_access_mandant(_user, row):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        ergebnisse.append({
            "typ": "mandant",
            "titel": name,
            "untertitel": row.get("email") or row.get("betreuer_email") or "",
            "pfad": f"/mandant/{name}",
            "tab": None,
        })
        if len(ergebnisse) >= limit:
            break

    if len(ergebnisse) < limit:
        try:
            from core.aufgabe_erledigt import aufgabe_ist_offen
            for a in store.hole_fristen().values():
                if not isinstance(a, dict) or not aufgabe_ist_offen(a):
                    continue
                mandant = str(a.get("mandant") or "").strip()
                text = str(a.get("beschreibung") or "").strip()
                if needle not in text.lower() and needle not in mandant.lower():
                    continue
                m = store.hole_mandant(mandant) or {}
                if mandant and not user_may_access_mandant(_user, m):
                    continue
                ergebnisse.append({
                    "typ": "aufgabe",
                    "titel": text[:120] or "Aufgabe",
                    "untertitel": mandant,
                    "pfad": f"/mandant/{mandant}",
                    "tab": "aufgaben",
                })
                if len(ergebnisse) >= limit:
                    break
        except Exception:
            pass

    return ok({"q": q, "ergebnisse": ergebnisse, "count": len(ergebnisse)})


@app.get("/mandanten/betreuer-matrix", tags=["Mandanten"],
         summary="Mandanten ↔ Betreuer Zuordnung (Team-Matrix)")
def mandanten_betreuer_matrix(_user: dict = Depends(require_permission("mandanten:read"))):
    from core.mandant_access import user_may_access_mandant

    store = get_ds(_user)
    svc = MandantenService(store)
    mandanten_rows = []
    for row in svc.list_mandanten():
        if not user_may_access_mandant(_user, row):
            continue
        mandanten_rows.append({
            "name": row.get("name", ""),
            "email": row.get("email", "") or "",
            "betreuer_email": row.get("betreuer_email", "") or "",
        })
    mandanten_rows.sort(key=lambda x: str(x.get("name") or "").lower())

    team_rows = []
    try:
        from backend.auth import liste_benutzer

        kid = str(_user.get("kanzlei_id") or _user.get("tenant_id") or "default")
        for u in liste_benutzer(kid) or []:
            if not isinstance(u, dict):
                continue
            em = str(u.get("email") or "").strip().lower()
            if not em or "@" not in em:
                continue
            team_rows.append({
                "email": em,
                "rolle": str(u.get("rolle") or "mitarbeiter"),
                "name": str(u.get("benutzername") or em),
            })
    except Exception:
        pass
    team_rows.sort(key=lambda x: x["email"])

    return ok({
        "mandanten": mandanten_rows,
        "team": team_rows,
        "count": len(mandanten_rows),
    })


@app.patch("/mandanten/betreuer-matrix/bulk", tags=["Mandanten"],
           summary="Betreuer bulk zuweisen")
def mandanten_betreuer_bulk(
    data: BetreuerBulkUpdate,
    _user: dict = Depends(require_permission("mandanten:write")),
):
    from core.mandant_access import user_may_access_mandant

    store = get_ds(_user)
    svc = MandantenService(store)
    updated = 0
    errors: List[str] = []

    targets: List[Dict[str, str]] = []
    if data.assignments:
        for row in data.assignments:
            targets.append({
                "name": row.name.strip(),
                "betreuer_email": (row.betreuer_email or "").strip().lower(),
            })
    else:
        names = [str(n).strip() for n in (data.mandanten or []) if str(n).strip()]
        betreuer = (data.betreuer_email or "").strip().lower()
        if not names and data.nur_ohne_betreuer:
            for row in svc.list_mandanten():
                if not user_may_access_mandant(_user, row):
                    continue
                if str(row.get("betreuer_email") or "").strip():
                    continue
                nm = str(row.get("name") or "").strip()
                if nm:
                    names.append(nm)
        for nm in names:
            targets.append({"name": nm, "betreuer_email": betreuer})

    for t in targets:
        nm = t["name"]
        try:
            m = store.hole_mandant(nm)
            if not m:
                errors.append(f"{nm}: nicht gefunden")
                continue
            if not user_may_access_mandant(_user, m):
                errors.append(f"{nm}: kein Zugriff")
                continue
            svc.update_mandant(nm, {"betreuer_email": t.get("betreuer_email") or ""})
            updated += 1
        except Exception as exc:
            errors.append(f"{nm}: {exc}")

    return ok({
        "updated": updated,
        "errors": errors[:20],
        "message": f"{updated} Mandant(en) aktualisiert",
    })


@app.get("/mandanten/papierkorb", tags=["Mandanten"],
         summary="Gelöschte Mandanten (Papierkorb)")
def get_mandanten_papierkorb(_user: dict = Depends(require_permission("mandanten:read"))):
    from core.mandant_access import user_may_access_mandant

    store = get_ds(_user)
    svc = MandantenService(store)
    rows = svc.list_papierkorb()
    rows = [r for r in rows if user_may_access_mandant(_user, r)]
    return ok(rows, count=len(rows))


@app.post("/mandanten/{name}/wiederherstellen", tags=["Mandanten"],
           summary="Mandant aus Papierkorb wiederherstellen")
def restore_mandant(name: str, _user: dict = Depends(require_permission("mandanten:write"))):
    svc = MandantenService(get_ds(_user))
    try:
        payload = svc.restore_mandant(name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return ok_compat(payload, "Mandant wiederhergestellt")


@app.get("/mandanten/{name}", tags=["Mandanten"])
def get_mandant(name: str, _user: dict = Depends(get_current_user)):
    from core.decision_engine import berechne_mandant_score
    store    = get_ds(_user)
    m        = get_mandant_or_404(name, store, _user)
    aufgaben = store.hole_aufgaben_fuer_mandant(name)

    try:
        sd = berechne_mandant_score(name, m, store)
    except Exception:
        sd = {}

    return ok({
        **m,
        "score":               sd.get("score", 0),
        "status":              sd.get("status", "OK"),
        "score_details":       sd.get("score_details", []),
        "health_score":        sd.get("health_score"),
        "health_ampel":        sd.get("health_ampel"),
        "health_label":        sd.get("health_label"),
        "health_gruende":      sd.get("health_gruende") or [],
        "tage_ohne_antwort":   sd.get("tage_ohne_antwort", 0),
        "aufgaben_offen":      sd.get("aufgaben_offen", sum(1 for a in aufgaben if aufgabe_ist_offen(a))),
        "aufgaben_ueberfaellig": sd.get("aufgaben_ueberfaellig", 0),
        "fehlende_dokumente":  sd.get("fehlende_dokumente", 0),
        "aufgaben":            aufgaben,
        "aufgaben_gesamt":     len(aufgaben),
        "aufgaben_erledigt":   sum(1 for a in aufgaben if aufgabe_ist_erledigt(a)),
    })


@app.get("/mandanten/{name}/m365-mails", tags=["Mandanten", "Integrationen"],
         summary="Outlook-Mails für Mandant (Graph Pilot)")
def mandant_m365_mails(
    name: str,
    limit: int = Query(8, ge=1, le=20),
    _user: dict = Depends(get_current_user),
):
    from core.m365_integration import fetch_mails_for_mandant

    store = get_ds(_user)
    get_mandant_or_404(name, store, _user)
    return ok(fetch_mails_for_mandant(store, name, limit=limit))


@app.post("/mandanten/{name}/m365-mails/sync-timeline", tags=["Mandanten", "Integrationen"],
          summary="M365-Mails in Kommunikations-Timeline importieren")
def mandant_m365_sync_timeline(
    name: str,
    limit: int = Query(10, ge=1, le=20),
    _user: dict = Depends(get_current_user),
):
    from core.m365_integration import sync_m365_mails_to_timeline

    store = get_ds(_user)
    get_mandant_or_404(name, store, _user)
    return ok(sync_m365_mails_to_timeline(store, name, limit=limit))


@app.post("/mandanten", tags=["Mandanten"], status_code=201)
def create_mandant(data: MandantCreate, _user: dict = Depends(require_permission("mandanten:write"))):
    svc = MandantenService(get_ds(_user))
    try:
        payload = svc.create_mandant(data)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    log.info(f"Mandant erstellt: {data.name}")
    return ok_compat(payload, "Mandant erstellt")


@app.put("/mandanten/{name}", tags=["Mandanten"])
def update_mandant(name: str, data: MandantUpdate, _user: dict = Depends(require_permission("mandanten:write"))):
    update_felder = data.dict(exclude_none=True)
    svc = MandantenService(get_ds(_user))
    try:
        payload = svc.update_mandant(name, update_felder)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return ok_compat(
        payload,
        "Mandant aktualisiert",
    )


@app.delete("/mandanten/{name}", tags=["Mandanten"])
def delete_mandant(name: str, _user: dict = Depends(require_permission("mandanten:delete"))):
    svc = MandantenService(get_ds(_user))
    try:
        payload = svc.delete_mandant(name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return ok_compat(payload, "Mandant in Papierkorb gelegt")


@app.get("/integrationen/m365/status", tags=["Integrationen"],
         summary="Microsoft 365 Integrationsstatus")
def integration_m365_status(_user: dict = Depends(require_permission("settings:read"))):
    from core.m365_integration import m365_status as m365_status_fn
    store = get_ds(_user)
    return ok(m365_status_fn(store, _user))


@app.post("/integrationen/m365/connect/start", tags=["Integrationen"],
          summary="Microsoft 365 Graph-Verbindung starten")
def integration_m365_connect_start(
    redirect_to: Optional[str] = Query("/settings"),
    _user: dict = Depends(require_permission("settings:write")),
):
    from core.m365_integration import build_m365_connect_auth_url

    client_id = _oauth_env("microsoft", "CLIENT_ID")
    client_secret = _oauth_env("microsoft", "CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(503, "Microsoft OAuth ist nicht konfiguriert")

    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    kid = str(_user.get("kanzlei_id") or _user.get("tenant_id") or "default")
    rows = _oauth_state_rows()
    rows.append(
        {
            "state": state,
            "nonce": nonce,
            "provider": "microsoft",
            "mode": "m365_connect",
            "kanzlei_id": kid,
            "redirect_to": _oauth_normalize_redirect_target(redirect_to),
            "expires_at": (datetime.now() + timedelta(minutes=10)).isoformat(),
        }
    )
    _oauth_state_save(rows)
    auth_url = build_m365_connect_auth_url(state, nonce)
    if not auth_url:
        raise HTTPException(503, "Microsoft OAuth ist nicht konfiguriert")
    return ok({"url": auth_url})


@app.post("/integrationen/m365/disconnect", tags=["Integrationen"],
          summary="Microsoft 365 Graph-Verbindung trennen")
def integration_m365_disconnect(_user: dict = Depends(require_permission("settings:write"))):
    from core.m365_integration import clear_m365_tokens

    store = get_ds(_user)
    clear_m365_tokens(store)
    return ok({"status": "disconnected", "message": "Microsoft 365 Verbindung getrennt"})


@app.get("/integrationen/m365/calendar-preview", tags=["Integrationen"],
         summary="Kalender-Vorschau (Microsoft Graph Pilot)")
def integration_m365_calendar_preview(_user: dict = Depends(require_permission("settings:read"))):
    from core.m365_integration import fetch_calendar_preview

    store = get_ds(_user)
    return ok(fetch_calendar_preview(store))


@app.get("/integrationen/m365/mail-preview", tags=["Integrationen"],
         summary="Postfach-Vorschau mit Mandanten-Zuordnung (Pilot)")
def integration_m365_mail_preview(
    limit: int = Query(10, ge=1, le=25),
    _user: dict = Depends(require_permission("settings:read")),
):
    from core.m365_integration import fetch_mail_preview

    store = get_ds(_user)
    return ok(fetch_mail_preview(store, limit=limit))


@app.post("/mandanten/{name}/antwort", tags=["Mandanten"])
def mandant_antwort_empfangen(name: str, _user: dict = Depends(get_current_user)):
    svc = MandantenService(get_ds(_user))
    try:
        payload = svc.mark_antwort(name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return ok_compat(payload, "Antwort gespeichert")


# ============================================================
# AUFGABEN — CRUD
# ============================================================

@app.get("/mandanten/{name}/aufgaben", tags=["Aufgaben"])
def get_aufgaben(
    name: str,
    nur_offen: bool = Query(False),
    prioritaet: Optional[str] = Query(None),
    bereich: str = Query(
        "alle",
        description="alle | aktiv (nur offene) | historie (erledigt, mit TTL)",
    ),
    _user: dict = Depends(get_current_user),
):
    store = get_ds(_user)
    get_mandant_or_404(name, store, _user)
    svc = AufgabenService(store)
    b_raw = bereich if isinstance(bereich, str) else "alle"
    b = (b_raw or "alle").strip().lower()
    if b not in ("alle", "aktiv", "offen", "historie"):
        b = "alle"
    return ok_compat(svc.list_for_mandant(name, nur_offen=nur_offen, prioritaet=prioritaet, bereich=b))


@app.post("/mandanten/{name}/aufgaben", tags=["Aufgaben"], status_code=status.HTTP_201_CREATED)
def create_aufgabe(name: str, data: AufgabeCreate,
    _user: dict = Depends(get_current_user)):
    store = get_ds(_user)
    get_mandant_or_404(name, store, _user)
    svc = AufgabenService(store)
    return ok_compat(svc.create(name, data), "Aufgabe erstellt")


@app.post("/mandanten/{name}/aufgaben/bulk", tags=["Aufgaben"])
def create_aufgaben_bulk(name: str, data: BulkAufgabeCreate,
    _user: dict = Depends(get_current_user)):
    store = get_ds(_user)
    get_mandant_or_404(name, store, _user)
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


@app.put("/aufgaben/{aufgabe_id}", tags=["Aufgaben"])
def update_aufgabe(
    aufgabe_id: str,
    data: AufgabeUpdate,
    _user: dict = Depends(get_current_user),
):
    svc = AufgabenService(get_ds(_user))
    try:
        payload = svc.update(aufgabe_id, data)
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
    m = get_mandant_or_404(name, store, _user)
    return ok_compat({
        "name": name,
        "fehlende_dokumente": m.get("fehlende_dokumente_liste", []),
        "anzahl_fehlend": len(m.get("fehlende_dokumente_liste", []))
    })


@app.get("/mandanten/{name}/eskalation", tags=["Mandanten"],
         summary="Eskalations-Timeline für Mandantenakte")
def mandant_eskalation(name: str, _user: dict = Depends(get_current_user)):
    from core.escalation_policy import mandant_eskalation_timeline

    store = get_ds(_user)
    m = get_mandant_or_404(name, store, _user)
    return ok_compat(mandant_eskalation_timeline(name, m, store))


@app.post("/mandanten/{name}/dokumente/anfordern", tags=["Dokumente"])
def dokument_anfordern(name: str, data: DokumentAnforderung, background_tasks: BackgroundTasks,
    _user: dict = Depends(get_current_user)):
    store = get_ds(_user)
    m = get_mandant_or_404(name, store, _user)
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
    m = get_mandant_or_404(name, store, _user)
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
    betreff:      Optional[str] = None
    email_text:   Optional[str] = None   # Plain-Text (optional)
    email_html:   Optional[str] = None   # HTML-Vorschau (bevorzugt für Mandanten-Mails)
    empfaenger:   Optional[str] = None   # Ziel-Adresse (sonst Mandanten-Stammdaten)
    force:        bool          = True

@app.get("/email/absender", tags=["Email"], summary="SMTP-Absender der Kanzlei (Anzeigename)")
def email_absender(_user: dict = Depends(get_current_user)):
    store = get_ds(_user)
    from core.email_sender import resolve_email_from

    r = resolve_email_from(store.kanzlei_id, store)
    if r.get("smtp_configured"):
        hinweis = (
            "Versand über Ihr Kanzlei-Postfach (Einstellungen → E-Mail-Versand). "
            "Anzeigename unter Kanzlei-Daten."
        )
    else:
        hinweis = (
            "Noch kein SMTP hinterlegt. Unter Einstellungen → E-Mail-Versand "
            "Server, Benutzer und App-Passwort Ihrer Kanzlei eintragen."
        )
    return ok_compat({
        "build": "email-tenant-smtp-20260520",
        "display_name": r["display_name"],
        "from_email": r["from_email"],
        "from_header": r["from_header"],
        "configured_email": r.get("configured_email") or "",
        "smtp_account": r.get("smtp_account") or "",
        "smtp_configured": bool(r.get("smtp_configured")),
        "reply_to": r.get("reply_to") or "",
        "address_mismatch": bool(r.get("address_mismatch")),
        "hinweis": hinweis,
    })


@app.post("/email/smtp/test", tags=["Email"], summary="SMTP-Verbindung der Kanzlei testen")
def email_smtp_test(
    data: Optional[dict] = Body(None),
    _user: dict = Depends(require_permission("settings:write")),
):
    store = get_ds(_user)
    from core.email_sender import resolve_email_from, send_tenant_email

    cfg = (data or {}) if isinstance(data, dict) else {}
    to_email = (cfg.get("to") or _user.get("email") or "").strip()
    if not to_email or "@" not in to_email:
        raise HTTPException(400, "Keine Ziel-Adresse — Benutzer-E-Mail oder 'to' angeben")

    resolved = resolve_email_from(store.kanzlei_id, store)
    if not resolved.get("smtp_configured"):
        raise HTTPException(
            400,
            "E-Mail-Versand nicht aktiv. Tab „E-Mail-Versand“: aktivieren, SMTP-Daten speichern.",
        )

    ok = send_tenant_email(
        store,
        to_email,
        "Kanzlei Automation — SMTP-Test",
        (
            f"SMTP-Test für Kanzlei {store.kanzlei_id}.\n"
            f"Absender: {resolved['from_header']}\n"
            "Wenn diese Mail ankommt, ist der Versand korrekt konfiguriert."
        ),
    )
    if not ok:
        raise HTTPException(502, "SMTP-Test fehlgeschlagen — Host, Port, Benutzer oder Passwort prüfen")
    return ok_compat({"status": "ok", "gesendet_an": to_email}, "Test-E-Mail gesendet")


@app.get("/email/{name}/vorschau", tags=["Email"])
def email_vorschau(name: str, _user: dict = Depends(get_current_user)):
    store    = get_ds(_user)
    m        = get_mandant_or_404(name, store, _user)
    aufgaben = store.hole_fristen()
    from core.ai_email import erstelle_email_vorschau
    from core.email_sender import resolve_email_from

    vorschau = erstelle_email_vorschau(name, m, aufgaben, store)
    absender = resolve_email_from(store.kanzlei_id, store)
    return {
        "mandant":       name,
        "empfaenger":    m.get("email", ""),
        "email_text":    vorschau["email_text"],
        "email_html":    vorschau["email_html"],
        "betreff":       vorschau["betreff"],
        "ton":           vorschau["ton"],
        "ki_generiert":  bool(vorschau.get("ki_generiert")),
        "generiert_am":  datetime.now().isoformat(),
        "absender_name": absender["display_name"],
        "absender_email": absender["from_email"],
        "absender_anzeige": absender["from_header"],
    }

@app.post("/email/{name}/senden", tags=["Email"])
def email_senden(name: str, background_tasks: BackgroundTasks,
                 data: Optional[EmailSendRequest] = None,
    _user: dict = Depends(get_current_user)):
    store = get_ds(_user)
    m = get_mandant_or_404(name, store, _user)

    to_email = (data.empfaenger if data and data.empfaenger else m.get("email") or "").strip()
    if not to_email or "@" not in to_email:
        raise HTTPException(
            400,
            f"Keine gültige Empfänger-E-Mail für '{name}'. Bitte Adresse eingeben oder im Mandanten hinterlegen.",
        )

    force = data.force if data else True
    from core.email_sender import resolve_email_from as _resolve_from

    if not _resolve_from(store.kanzlei_id, store).get("smtp_configured"):
        raise HTTPException(
            400,
            "E-Mail-Versand nicht konfiguriert. Einstellungen → E-Mail-Versand: aktivieren und SMTP speichern.",
        )
    if not force and not darf_email_senden(name, store=store):
        raise HTTPException(429, "Email bereits in den letzten 24h gesendet. Nutze force=true zum Überschreiben.")

    custom_html = (data.email_html or "").strip() if data else ""
    custom_text = (data.email_text or "").strip() if data else ""
    if custom_text and custom_text.lstrip().startswith("<!DOCTYPE"):
        custom_html = custom_html or custom_text
        custom_text = ""

    if custom_html or custom_text:
        subject = (
            data.betreff if data and data.betreff
            else f"Mitteilung Ihrer Steuerkanzlei — {datetime.now().strftime('%d.%m.%Y')}"
        )
        body_text = custom_text or "Bitte öffnen Sie diese Nachricht in einem HTML-fähigen E-Mail-Programm."
        body_html = custom_html or ""
        idem_src = (
            f"{store.kanzlei_id}|{name}|manual|{datetime.now().strftime('%Y-%m-%d-%H')}"
            f"|{to_email}|{subject}|{(body_html or body_text)[:160]}"
        )
        idem = hashlib.sha256(idem_src.encode("utf-8")).hexdigest()
        enq = email_outbox_enqueue(
            kanzlei_id=store.kanzlei_id,
            mandant=name,
            to_email=to_email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            idempotency_key=idem,
            max_attempts=5,
        )
        store.log_eintrag(f"EMAIL_MANUELL_ENQUEUED | {name} | {to_email} | outbox_id={enq.get('id')}")
        background_tasks.add_task(_process_email_outbox_once, 5)
        _track_action_for_suggestions(store, "email_send_manual")
    else:
        if to_email != (m.get("email") or "").strip():
            from core.ai_email import erstelle_email_vorschau
            v = erstelle_email_vorschau(name, m, store.hole_fristen(), store)
            subject = data.betreff if data and data.betreff else v["betreff"]
            idem_src = f"{store.kanzlei_id}|{name}|manual|{datetime.now().isoformat()}|{to_email}|{subject}"
            idem = hashlib.sha256(idem_src.encode("utf-8")).hexdigest()
            enq = email_outbox_enqueue(
                kanzlei_id=store.kanzlei_id,
                mandant=name,
                to_email=to_email,
                subject=subject,
                body_text=v["email_text"],
                body_html=v["email_html"],
                idempotency_key=idem,
                max_attempts=5,
            )
            store.log_eintrag(f"EMAIL_MANUELL_ENQUEUED | {name} | {to_email} | outbox_id={enq.get('id')}")
            background_tasks.add_task(_process_email_outbox_once, 5)
            _track_action_for_suggestions(store, "email_send_manual")
        else:
            background_tasks.add_task(_email_fuer_mandant_senden, name, store)
            background_tasks.add_task(_process_email_outbox_once, 5)
            _track_action_for_suggestions(store, "email_send_auto")

    return ok_compat(
        {"status": "queued", "mandant": name, "empfaenger": to_email},
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
    if not _billing_enabled():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Billing-Modul ist deaktiviert")
    kid = str(_user.get("tenant_id") or _user.get("kanzlei_id") or "default").strip() or "default"
    plan = _plan_for_user(_user)
    limits = PLAN_USAGE_LIMITS.get(plan, PLAN_USAGE_LIMITS["starter"])
    usage_today = {m: usage_get(kid, m) for m in limits}
    quota = _usage_quota_breakdown(kid, plan)
    upgrade_url = (os.getenv("BILLING_UPGRADE_URL") or os.getenv("SALES_CONTACT_URL") or "").strip()
    support_email = (os.getenv("SUPPORT_EMAIL") or "").strip()
    return ok({
        "kanzlei_id": kid,
        "tenant_id": kid,
        "plan": plan,
        "limits": limits,
        "usage_today": usage_today,
        "quota": quota,
        "customer_success": {
            "satisfaction_hint": (
                "Bei Ampel „warning“ oder „critical“: Plan prüfen — vermeidet KI-Ausfälle im Mandantenverkehr."
            ),
            "upgrade_url": upgrade_url or None,
            "support_email": support_email or None,
        },
    })


@app.get("/billing/metrics", tags=["Billing"], summary="Revenue-/Retention-Metriken (Tenant)")
def billing_metrics(_user: dict = Depends(get_current_user)):
    if not _billing_enabled():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Billing-Modul ist deaktiviert")
    kid = str(_user.get("tenant_id") or _user.get("kanzlei_id") or "default").strip() or "default"
    plan = _plan_for_user(_user)
    limits = PLAN_USAGE_LIMITS.get(plan, PLAN_USAGE_LIMITS["starter"])
    quota = _usage_quota_breakdown(kid, plan)

    usage_today = {m: int(usage_get(kid, m)) for m in limits}
    # Preise bewusst serverseitig zentral, später durch Stripe-Planpreise ersetzbar.
    billing_model = str(global_setting_holen("billing_modell") or "pauschal").strip().lower()
    if billing_model == "pauschal":
        mrr_estimate = int(float(global_setting_holen("billing_pauschal_euro") or 299))
    elif billing_model == "pro_buchung":
        per_item = float(global_setting_holen("billing_pro_buchung_euro") or 0.2)
        mrr_estimate = int(round(per_item * max(1, usage_today.get("ai_requests_day", 0))))
    elif billing_model == "pro_mitarbeiter":
        per_user = float(global_setting_holen("billing_pro_mitarbeiter_euro") or 15.0)
        mrr_estimate = int(round(per_user * 5))  # conservative default cohort size
    else:
        mrr_estimate = int(float(global_setting_holen("billing_value_tier_1_euro") or 199))
    arr_estimate = int(mrr_estimate * 12)

    # "Woche" als einfache Hochrechnung aus Tagesnutzung (v1, robust ohne neues Schema).
    usage_week_projection = {k: int(v * 7) for k, v in usage_today.items()}

    quota_status = str((quota.get("overall") or "ok")).lower()
    churn_risk = "low"
    if quota_status == "warning":
        churn_risk = "medium"
    elif quota_status in {"critical", "limit"}:
        churn_risk = "high"

    recommended_offer = None
    ranked = sorted(
        quota.get("by_metric", {}).items(),
        key=lambda kv: ({"limit": 4, "critical": 3, "warning": 2, "ok": 1}.get(kv[1].get("status"), 0), kv[1].get("percent_used", 0)),
        reverse=True,
    )
    if ranked:
        m, row = ranked[0]
        recommended_offer = _upgrade_offer_payload(plan, m, int(row.get("used") or 0), int(row.get("limit") or 0))

    return ok(
        {
            "kanzlei_id": kid,
            "tenant_id": kid,
            "plan": plan,
            "billing_modell": billing_model,
            "mrr_estimate": mrr_estimate,
            "arr_estimate": arr_estimate,
            "quota_status": quota_status,
            "churn_risk": churn_risk,
            "usage_today": usage_today,
            "usage_week_projection": usage_week_projection,
            "quota": quota,
            "recommended_offer": recommended_offer,
            "funnel_24h": _billing_funnel_summary(kid, lookback_hours=24),
        }
    )


@app.get("/billing/observability", tags=["Billing"], summary="Billing-Observability Counter (Owner/Admin)")
def billing_observability(_user: dict = Depends(get_current_user)):
    from core.rbac import canonical_role
    role = canonical_role(_user.get("role") or _user.get("rolle"))
    if role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Nur Owner/Admin dürfen Billing-Observability sehen.")
    kid = str(_user.get("tenant_id") or _user.get("kanzlei_id") or "default").strip() or "default"
    obs = _billing_obs_get(kid)
    return ok(
        {
            "kanzlei_id": kid,
            "digest_enqueue_calls": int(obs.get("digest_enqueue_calls", 0) or 0),
            "digest_sent": int(obs.get("digest_sent", 0) or 0),
            "digest_skipped_no_recipients": int(obs.get("digest_skipped_no_recipients", 0) or 0),
            "digest_enqueue_noop": int(obs.get("digest_enqueue_noop", 0) or 0),
            "channel_shift_detected": int(obs.get("channel_shift_detected", 0) or 0),
            "last_updated_at": obs.get("last_updated_at"),
        }
    )


@app.get("/billing/report/weekly", tags=["Billing"], summary="Weekly Revenue Digest mit Handlungsempfehlungen")
def billing_report_weekly(_user: dict = Depends(get_current_user)):
    if not _billing_enabled():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Billing-Modul ist deaktiviert")
    kid = str(_user.get("tenant_id") or _user.get("kanzlei_id") or "default").strip() or "default"
    return ok(_billing_report_weekly_for_tenant(kid))


@app.post("/billing/report/weekly/send", tags=["Billing"], summary="Weekly Revenue Digest per E-Mail an Owner/Admin senden")
def billing_report_weekly_send(
    background_tasks: BackgroundTasks,
    _user: dict = Depends(get_current_user),
):
    if not _billing_enabled():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Billing-Modul ist deaktiviert")
    from core.rbac import canonical_role
    role = canonical_role(_user.get("role") or _user.get("rolle"))
    if role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Nur Owner/Admin dürfen den Digest versenden.")
    kid = str(_user.get("tenant_id") or _user.get("kanzlei_id") or "default").strip() or "default"
    result = _enqueue_weekly_digest_for_tenant(kid)
    background_tasks.add_task(_process_email_outbox_once, 12)
    return ok(result)


@app.get("/billing/upgrade-offer", tags=["Billing"], summary="Upgrade-Empfehlung aus Nutzung und Plan")
def billing_upgrade_offer(_user: dict = Depends(get_current_user)):
    if not _billing_enabled():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Billing-Modul ist deaktiviert")
    kid = str(_user.get("tenant_id") or _user.get("kanzlei_id") or "default").strip() or "default"
    plan = _plan_for_user(_user)
    quota = _usage_quota_breakdown(kid, plan)
    limits = PLAN_USAGE_LIMITS.get(plan, PLAN_USAGE_LIMITS["starter"])
    usage_today = {m: int(usage_get(kid, m)) for m in limits}

    # Priorisiere kritischste Metrik als Upgrade-Trigger.
    ranked = sorted(
        quota.get("by_metric", {}).items(),
        key=lambda kv: ({"limit": 4, "critical": 3, "warning": 2, "ok": 1}.get(kv[1].get("status"), 0), kv[1].get("percent_used", 0)),
        reverse=True,
    )
    if ranked:
        metric, row = ranked[0]
        offer = _upgrade_offer_payload(plan, metric, int(row.get("used") or 0), int(row.get("limit") or 0))
    else:
        offer = _upgrade_offer_payload(plan, "ai_requests_day", 0, int(limits.get("ai_requests_day") or 0))
    return ok(
        {
            "kanzlei_id": kid,
            "tenant_id": kid,
            "plan": plan,
            "quota": quota,
            "usage_today": usage_today,
            "offer": offer,
        }
    )


@app.get("/billing/funnel", tags=["Billing"], summary="Billing-Funnel-Analytics")
def billing_funnel(_user: dict = Depends(get_current_user), lookback_hours: int = Query(24, ge=1, le=168)):
    if not _billing_enabled():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Billing-Modul ist deaktiviert")
    kid = str(_user.get("tenant_id") or _user.get("kanzlei_id") or "default").strip() or "default"
    return ok(
        {
            "kanzlei_id": kid,
            "tenant_id": kid,
            "funnel": _billing_funnel_summary(kid, lookback_hours=lookback_hours),
        }
    )


@app.post("/billing/funnel/event", tags=["Billing"], summary="Billing-Funnel Event erfassen")
def billing_funnel_event(
    body: Dict[str, Any] = Body(...),
    _user: dict = Depends(get_current_user),
    request: Request = None,
):
    if not _billing_enabled():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Billing-Modul ist deaktiviert")
    kid = str(_user.get("tenant_id") or _user.get("kanzlei_id") or "default").strip() or "default"
    stage = str(body.get("stage") or "").strip().lower()
    meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}
    meta = {**meta, **_attribution_from_request(request)}
    _billing_funnel_record(kid, stage, meta)
    return ok({"accepted": True, "stage": stage})


class StripeCheckoutRequest(BaseModel):
    """Stripe Checkout Session (Subscription) für Plan-Upgrade."""
    success_url: str = Field(..., min_length=12, max_length=500)
    cancel_url: str = Field(..., min_length=12, max_length=500)
    target_plan: str = Field("professional", description="professional | enterprise")


class StripePortalRequest(BaseModel):
    return_url: str = Field(..., min_length=12, max_length=500)


class BillingFunnelEventRequest(BaseModel):
    stage: str = Field(..., min_length=3, max_length=64, description="cta_view|cta_click|checkout_start|checkout_success|checkout_cancel")
    meta: Optional[Dict[str, Any]] = None


def _billing_funnel_record(kanzlei_id: str, stage: str, meta: Optional[Dict[str, Any]] = None) -> None:
    """Persistiert Funnel-Events tenant-scoped in Rolling-Window-Form."""
    kid = str(kanzlei_id or "default").strip() or "default"
    st = str(stage or "").strip().lower()
    if st not in {"cta_view", "cta_click", "checkout_start", "checkout_success", "checkout_cancel", "paywall_402"}:
        return
    try:
        store = DatenSpeicher(kanzlei_id=kid)
        raw = store.setting_holen("__billing_funnel_events_v1", []) or []
        events = raw if isinstance(raw, list) else []
        events.append({"ts": datetime.utcnow().isoformat(), "stage": st, "meta": meta or {}})
        store.setting_setzen("__billing_funnel_events_v1", events[-400:])
    except Exception as exc:  # noqa: BLE001
        log.debug("billing_funnel_record skipped: %s", exc)


def _billing_funnel_summary(kanzlei_id: str, *, lookback_hours: int = 24) -> Dict[str, Any]:
    kid = str(kanzlei_id or "default").strip() or "default"
    try:
        store = DatenSpeicher(kanzlei_id=kid)
        raw = store.setting_holen("__billing_funnel_events_v1", []) or []
        events = raw if isinstance(raw, list) else []
    except Exception:
        events = []

    threshold = datetime.utcnow() - timedelta(hours=max(1, int(lookback_hours)))
    stages = {"cta_view": 0, "cta_click": 0, "checkout_start": 0, "checkout_success": 0, "checkout_cancel": 0, "paywall_402": 0}
    source_totals: Dict[str, int] = {}
    source_views: Dict[str, int] = {}
    source_paid: Dict[str, int] = {}
    for ev in events:
        if not isinstance(ev, dict):
            continue
        stage = str(ev.get("stage") or "").strip().lower()
        if stage not in stages:
            continue
        try:
            dt = datetime.fromisoformat(str(ev.get("ts") or "").replace("Z", ""))
            if dt < threshold:
                continue
        except Exception:
            continue
        stages[stage] += 1
        meta = ev.get("meta") if isinstance(ev.get("meta"), dict) else {}
        src = str(meta.get("utm_source") or "direct").strip().lower() or "direct"
        source_totals[src] = source_totals.get(src, 0) + 1
        if stage == "cta_view":
            source_views[src] = source_views.get(src, 0) + 1
        if stage == "checkout_success":
            source_paid[src] = source_paid.get(src, 0) + 1
    views = max(1, stages["cta_view"])
    starts = max(1, stages["checkout_start"])
    paid = stages["checkout_success"]
    top_sources = sorted(source_totals.items(), key=lambda kv: kv[1], reverse=True)[:8]
    source_breakdown = [
        {
            "utm_source": src,
            "events": int(total),
            "views": int(source_views.get(src, 0)),
            "paid": int(source_paid.get(src, 0)),
            "view_to_paid_percent": round(100 * int(source_paid.get(src, 0)) / max(1, int(source_views.get(src, 0))), 2),
        }
        for src, total in top_sources
    ]
    return {
        "lookback_hours": int(lookback_hours),
        "stages": stages,
        "rates": {
            "ctr_percent": round(100 * stages["cta_click"] / views, 2),
            "checkout_to_paid_percent": round(100 * paid / starts, 2),
            "view_to_paid_percent": round(100 * paid / views, 2),
        },
        "source_breakdown": source_breakdown,
    }


def _billing_report_email_subject(plan: str) -> str:
    return f"Weekly Revenue Digest ({str(plan or 'starter').upper()})"


def _billing_digest_recipients(kanzlei_id: str) -> List[str]:
    try:
        from backend.auth import liste_benutzer
        from core.rbac import canonical_role
        users = liste_benutzer(kanzlei_id) or []
    except Exception:
        users = []
    seen = set()
    recipients: List[str] = []
    for u in users:
        role = canonical_role((u or {}).get("rolle") or (u or {}).get("role"))
        if role not in {"owner", "admin"}:
            continue
        email = str((u or {}).get("email") or "").strip().lower()
        if not email or email in seen:
            continue
        seen.add(email)
        recipients.append(email)
    return recipients[:20]


def _billing_report_email_body(report: Dict[str, Any]) -> str:
    funnel = report.get("funnel_7d") or {}
    rates = funnel.get("rates") or {}
    actions = report.get("recommended_actions") or []
    utm = report.get("utm_ranking") or {}
    top = utm.get("top_source") or {}
    flop = utm.get("flop_source") or {}
    lines = [
        "Weekly Revenue Digest",
        "",
        f"Plan: {report.get('plan')}",
        f"MRR (est.): €{report.get('mrr_estimate', 0)}",
        f"ARR (est.): €{report.get('arr_estimate', 0)}",
        f"Quota-Status: {report.get('quota_status')}",
        "",
        "Funnel (7d):",
        f"- CTR: {rates.get('ctr_percent', 0)}%",
        f"- Checkout->Paid: {rates.get('checkout_to_paid_percent', 0)}%",
        f"- View->Paid: {rates.get('view_to_paid_percent', 0)}%",
    ]
    if top:
        lines.append(f"- Top UTM: {top.get('utm_source')} ({top.get('view_to_paid_percent', 0)}% View->Paid)")
    if flop:
        lines.append(f"- Flop UTM: {flop.get('utm_source')} ({flop.get('view_to_paid_percent', 0)}% View->Paid)")
    lines.extend(["", "Top Actions:"])
    for idx, a in enumerate(actions[:5], start=1):
        lines.append(f"{idx}. {a}")
    return "\n".join(lines)


def _billing_report_weekly_for_tenant(kanzlei_id: str) -> Dict[str, Any]:
    from backend.auth import hole_kanzlei
    kid = str(kanzlei_id or "default").strip() or "default"
    krow = hole_kanzlei(kid) or {}
    plan = str(krow.get("plan") or "starter").strip().lower()
    metrics = billing_metrics({"tenant_id": kid, "kanzlei_id": kid})
    mdata = metrics.get("data") if isinstance(metrics, dict) and isinstance(metrics.get("data"), dict) else metrics
    funnel_7d = _billing_funnel_summary(kid, lookback_hours=168)
    actions: List[str] = []
    rates = funnel_7d.get("rates") or {}
    ctr = float(rates.get("ctr_percent") or 0.0)
    checkout_to_paid = float(rates.get("checkout_to_paid_percent") or 0.0)
    quota_status = str(mdata.get("quota_status") or "ok").lower() if isinstance(mdata, dict) else "ok"
    if ctr < 8:
        actions.append("CTA-Headline in Banner/Modal testen (A/B), Ziel CTR > 8%.")
    if checkout_to_paid < 20:
        actions.append("Checkout-Friktion reduzieren: Stripe-Konfig + klarere Planbenefits im Modal.")
    if quota_status in {"warning", "critical", "limit"}:
        actions.append("Proaktive Upgrade-Kampagne starten (In-App + E-Mail) für betroffene Tenants.")
    src_rows = funnel_7d.get("source_breakdown") or []
    top_source = None
    flop_source = None
    if src_rows:
        ranked = [r for r in src_rows if int(r.get("views") or 0) >= 1]
        if not ranked:
            ranked = [r for r in src_rows if int(r.get("events") or 0) >= 2]
        if not ranked:
            ranked = src_rows
        ranked = sorted(
            ranked,
            key=lambda r: (
                float(r.get("view_to_paid_percent") or 0.0),
                int(r.get("paid") or 0),
                int(r.get("events") or 0),
            ),
            reverse=True,
        )
        top_source = ranked[0] if ranked else None
        flop_source = ranked[-1] if len(ranked) > 1 else None
    prev_top_map = _kv_get(ds, "__billing_top_source_last_week__", {})
    if not isinstance(prev_top_map, dict):
        prev_top_map = {}
    prev_top_source = str(prev_top_map.get(kid) or "").strip().lower()
    current_top_source = str((top_source or {}).get("utm_source") or "").strip().lower()
    channel_shift_alert = None
    if prev_top_source and current_top_source and prev_top_source != current_top_source:
        channel_shift_alert = {
            "type": "top_channel_shift",
            "previous_top_source": prev_top_source,
            "current_top_source": current_top_source,
            "message": (
                f"Top-Kanal hat gewechselt: '{prev_top_source}' -> '{current_top_source}'. "
                "Budget- und Landing-Strategie sofort prüfen."
            ),
        }
    if src_rows:
        top = top_source or src_rows[0]
        if float(top.get("view_to_paid_percent") or 0.0) < 5:
            actions.append(f"UTM-Quelle '{top.get('utm_source')}' optimieren (Landing/Offer), da View->Paid aktuell niedrig ist.")
    if top_source and flop_source and str(top_source.get("utm_source")) != str(flop_source.get("utm_source")):
        actions.insert(
            0,
            (
                "Budget priorisieren: mehr Traffic auf "
                f"'{top_source.get('utm_source')}' ({top_source.get('view_to_paid_percent', 0)}%), "
                f"weniger auf '{flop_source.get('utm_source')}' ({flop_source.get('view_to_paid_percent', 0)}%)."
            ),
        )
    if not actions:
        actions.append("Funnel stabil — Fokus auf Traffic/Lead-Generierung zur Volumensteigerung.")
    return {
        "kanzlei_id": kid,
        "tenant_id": kid,
        "plan": plan,
        "mrr_estimate": int((mdata or {}).get("mrr_estimate") or 0),
        "arr_estimate": int((mdata or {}).get("arr_estimate") or 0),
        "quota_status": quota_status,
        "funnel_7d": funnel_7d,
        "utm_ranking": {
            "top_source": top_source,
            "flop_source": flop_source,
        },
        "channel_shift_alert": channel_shift_alert,
        "recommended_actions": actions,
        "generated_at": datetime.utcnow().isoformat(),
    }


def _enqueue_weekly_digest_for_tenant(kanzlei_id: str) -> Dict[str, Any]:
    kid = str(kanzlei_id or "default").strip() or "default"
    _billing_obs_inc(kid, "digest_enqueue_calls", 1)
    report_data = _billing_report_weekly_for_tenant(kid)
    recipients = _billing_digest_recipients(kid)
    if not recipients:
        _billing_obs_inc(kid, "digest_skipped_no_recipients", 1)
        return {"kanzlei_id": kid, "sent": 0, "recipients": []}
    subject = _billing_report_email_subject(str(report_data.get("plan") or "starter"))
    body = _billing_report_email_body(report_data)
    sent = 0
    for email in recipients:
        idem_src = f"{kid}|weekly-digest|{datetime.utcnow().strftime('%G-%V')}|{email}"
        idem = hashlib.sha256(idem_src.encode("utf-8")).hexdigest()
        enq = email_outbox_enqueue(
            kanzlei_id=kid,
            mandant="weekly_digest",
            to_email=email,
            subject=subject,
            body_text=body,
            body_html="",
            idempotency_key=idem,
            max_attempts=5,
        )
        if enq and (enq.get("created") or enq.get("id")):
            sent += 1
    if sent > 0:
        _billing_obs_inc(kid, "digest_sent", int(sent))
    else:
        _billing_obs_inc(kid, "digest_enqueue_noop", 1)
    if (report_data.get("channel_shift_alert") or {}).get("type") == "top_channel_shift":
        _billing_obs_inc(kid, "channel_shift_detected", 1)
    try:
        current_top = str((((report_data.get("utm_ranking") or {}).get("top_source") or {}).get("utm_source") or "")).strip().lower()
        if current_top:
            mp = _kv_get(ds, "__billing_top_source_last_week__", {})
            if not isinstance(mp, dict):
                mp = {}
            mp[kid] = current_top
            _kv_set(ds, "__billing_top_source_last_week__", mp)
    except Exception:
        pass
    return {"kanzlei_id": kid, "sent": sent, "recipients": recipients}


async def billing_weekly_digest_worker():
    enabled = (os.getenv("BILLING_WEEKLY_DIGEST_AUTO", "1").strip().lower() in {"1", "true", "yes"})
    if not enabled:
        log.info("Weekly Digest Worker deaktiviert (BILLING_WEEKLY_DIGEST_AUTO=0)")
        return
    if not (os.getenv("EMAIL_USER") or "").strip() or not (os.getenv("EMAIL_PASS") or "").strip():
        log.warning("Weekly Digest Worker übersprungen: EMAIL_USER/EMAIL_PASS fehlen.")
        return
    try:
        target_day = int(os.getenv("BILLING_WEEKLY_DIGEST_DAY_ISO", "1") or "1")
    except Exception:
        target_day = 1
    try:
        target_hour = int(os.getenv("BILLING_WEEKLY_DIGEST_HOUR_UTC", "8") or "8")
    except Exception:
        target_hour = 8
    target_day = max(1, min(7, int(target_day)))   # 1=Montag
    target_hour = max(0, min(23, int(target_hour))) # UTC hour
    while True:
        try:
            now = datetime.utcnow()
            if now.isoweekday() == target_day and now.hour >= target_hour:
                week_key = now.strftime("%G-%V")
                sent_map = _kv_get(ds, "__billing_weekly_digest_sent__", {})
                if not isinstance(sent_map, dict):
                    sent_map = {}
                from backend.auth import liste_kanzleien
                ten = liste_kanzleien() or []
                attempted = 0
                sent_total = 0
                skipped_week = 0
                for row in ten:
                    kid = str((row or {}).get("id") or "").strip()
                    if not kid:
                        continue
                    if str(sent_map.get(kid) or "") == week_key:
                        skipped_week += 1
                        continue
                    attempted += 1
                    res = _enqueue_weekly_digest_for_tenant(kid)
                    sent_total += int(res.get("sent") or 0)
                    if int(res.get("sent") or 0) > 0:
                        sent_map[kid] = week_key
                _kv_set(ds, "__billing_weekly_digest_sent__", sent_map)
                _process_email_outbox_once(limit=40)
                log.info(
                    "billing_weekly_digest_worker run: attempted=%s sent_total=%s skipped_week=%s week=%s",
                    attempted,
                    sent_total,
                    skipped_week,
                    week_key,
                )
        except Exception as exc:
            log.warning("billing_weekly_digest_worker Fehler: %s", exc)
        await asyncio.sleep(60 * 30)


def _attribution_from_request(request: Optional[Request]) -> Dict[str, Any]:
    if request is None:
        return {}
    q = request.query_params
    out = {
        "utm_source": (q.get("utm_source") or "").strip(),
        "utm_medium": (q.get("utm_medium") or "").strip(),
        "utm_campaign": (q.get("utm_campaign") or "").strip(),
        "referrer": (request.headers.get("referer") or request.headers.get("referrer") or "").strip(),
        "user_agent": (request.headers.get("user-agent") or "").strip()[:180],
    }
    return {k: v for k, v in out.items() if v}


@app.get("/billing/stripe/config", tags=["Billing"], summary="Öffentliche Stripe-Konfiguration (Publishable Key)")
def stripe_public_config():
    """Nur Publishable Key — kein Secret. Für SPA vor Checkout."""
    from core.stripe_integration import (
        stripe_publishable_key,
        stripe_checkout_ready,
        stripe_enterprise_price_configured,
    )

    pk = stripe_publishable_key()
    return ok(
        {
            "publishable_key": pk or None,
            "checkout_ready": stripe_checkout_ready(),
            "enterprise_price_configured": stripe_enterprise_price_configured(),
        }
    )


@app.post("/billing/stripe/checkout-session", tags=["Billing"], summary="Stripe Checkout Session (Upgrade)")
def stripe_create_checkout(
    body: StripeCheckoutRequest,
    user: dict = Depends(get_current_user),
    request: Request = None,
):
    if not _billing_enabled():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Billing-Modul ist deaktiviert")
    from core.stripe_integration import create_checkout_session, stripe_secret_configured

    if user.get("api_key_id"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nicht mit API-Key erlaubt")
    if not stripe_secret_configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Stripe ist nicht konfiguriert (STRIPE_SECRET_KEY)")
    kid = str(user.get("tenant_id") or user.get("kanzlei_id") or "default").strip() or "default"
    email = (user.get("email") or "").strip() or None
    try:
        meta = {"target_plan": body.target_plan.strip().lower(), **_attribution_from_request(request)}
        _billing_funnel_record(kid, "checkout_start", meta)
        sess = create_checkout_session(
            kanzlei_id=kid,
            success_url=body.success_url.strip(),
            cancel_url=body.cancel_url.strip(),
            target_plan=body.target_plan.strip().lower(),
            customer_email=email,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return ok(sess, "checkout_session_created")


@app.post("/billing/stripe/portal-session", tags=["Billing"], summary="Stripe Customer Portal (Abo verwalten)")
def stripe_billing_portal(
    body: StripePortalRequest,
    user: dict = Depends(get_current_user),
):
    if not _billing_enabled():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Billing-Modul ist deaktiviert")
    from core.stripe_integration import create_billing_portal_session, stripe_secret_configured
    from core.daten_speicher import DatenSpeicher

    if user.get("api_key_id"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nicht mit API-Key erlaubt")
    if not stripe_secret_configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Stripe ist nicht konfiguriert")
    kid = str(user.get("tenant_id") or user.get("kanzlei_id") or "default").strip() or "default"
    store = DatenSpeicher(kanzlei_id=kid)
    prof = store.setting_holen("__tenant_profile__", {}) or {}
    cid = (prof.get("stripe_customer_id") or "").strip() if isinstance(prof, dict) else ""
    if not cid.startswith("cus_"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Kein Stripe-Kunde hinterlegt — zuerst per Checkout abonnieren.",
        )
    try:
        ps = create_billing_portal_session(customer_id=cid, return_url=body.return_url.strip())
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return ok(ps, "portal_session_created")


@app.post("/billing/stripe/webhook", tags=["Billing"], summary="Stripe Webhook (Signaturpflicht)")
async def stripe_webhook(request: Request):
    """
    Roh-Body für Signaturprüfung. Kein Bearer — nur ``Stripe-Signature`` + ``STRIPE_WEBHOOK_SECRET``.
    """
    from core.stripe_integration import handle_stripe_event, verify_webhook_event

    import stripe as stripe_sdk

    payload = await request.body()
    sig = request.headers.get("stripe-signature") or request.headers.get("Stripe-Signature") or ""
    try:
        event = verify_webhook_event(payload, sig)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except stripe_sdk.error.SignatureVerificationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ungültige Stripe-Signatur") from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("Stripe webhook verify: %s", exc)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Webhook-Verarbeitung fehlgeschlagen") from exc

    try:
        result = handle_stripe_event(event)
    except Exception as exc:  # noqa: BLE001
        log.exception("Stripe webhook handler: %s", exc)
        result = {"action": "handler_error", "error": str(exc)}
    try:
        action = str(result.get("action") or "")
        kid = str(result.get("kanzlei_id") or "").strip()
        if kid and action == "plan_activated":
            _billing_funnel_record(kid, "checkout_success", {"plan": result.get("plan")})
    except Exception:
        pass
    return ok({"received": True, **result})


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    permissions: Optional[List[str]] = None


class WebhookCreateRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=500)
    events: List[str] = Field(default_factory=lambda: ["email.sent", "settings.changed"])
    secret: Optional[str] = Field(None, min_length=8, max_length=120)


class ApiKeyRotateRequest(BaseModel):
    new_name: Optional[str] = Field(None, min_length=2, max_length=120)


@app.post("/saas/apikeys", tags=["SaaS"], summary="API-Key erzeugen (einmal anzeigen)")
def saas_api_key_create(
    _user: dict = Depends(require_permission("settings:write")),
    payload: ApiKeyCreateRequest = Body(...),
):
    kid = _user.get("tenant_id") or _user.get("kanzlei_id", "default")
    created = api_key_create(kid, payload.name, permissions=payload.permissions or [])
    _emit_webhook_event(kid, "apikey.created", {"id": created["id"], "name": payload.name})
    return ok({
        "id": created["id"],
        "api_key": created["key"],
        "hinweis": "Dieser Key wird nur einmal angezeigt.",
    })


@app.get("/saas/apikeys", tags=["SaaS"], summary="API-Keys der Kanzlei")
def saas_api_keys(_user: dict = Depends(require_permission("settings:read"))):
    kid = _user.get("tenant_id") or _user.get("kanzlei_id", "default")
    return ok({"eintraege": api_key_list(kid)})


@app.delete("/saas/apikeys/{key_id}", tags=["SaaS"], summary="API-Key deaktivieren")
def saas_api_key_delete(
    key_id: str,
    _user: dict = Depends(require_permission("settings:write")),
):
    kid = _user.get("tenant_id") or _user.get("kanzlei_id", "default")
    ok_del = api_key_deactivate(kid, key_id)
    if not ok_del:
        raise HTTPException(404, "API-Key nicht gefunden")
    _emit_webhook_event(kid, "apikey.revoked", {"id": key_id})
    return ok({"status": "deactivated", "id": key_id})


@app.post("/saas/apikeys/{key_id}/rotate", tags=["SaaS"], summary="API-Key rotieren")
def saas_api_key_rotate(
    key_id: str,
    data: ApiKeyRotateRequest = Body(default=ApiKeyRotateRequest()),
    _user: dict = Depends(require_permission("settings:write")),
):
    kid = _user.get("tenant_id") or _user.get("kanzlei_id", "default")
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
    _user: dict = Depends(require_permission("settings:write")),
    payload: WebhookCreateRequest = Body(...),
):
    _require_tenant_feature(_user, "api_webhooks_write")
    kid = _user.get("tenant_id") or _user.get("kanzlei_id", "default")
    if not (payload.url.startswith("http://") or payload.url.startswith("https://")):
        raise HTTPException(400, "Webhook URL muss mit http:// oder https:// starten")
    configured = str(global_setting_holen("webhook_url") or "").strip()
    if configured and payload.url.strip() != configured:
        raise HTTPException(400, "Webhook URL muss dem Wert aus Einstellungen entsprechen")
    w = webhook_endpoint_create(kid, payload.url, payload.events, payload.secret)
    return ok({"id": w["id"], "secret": w["secret"], "events": payload.events, "url": payload.url})


@app.get("/saas/webhooks", tags=["SaaS"], summary="Webhook Endpoints listen")
def saas_webhook_list(_user: dict = Depends(require_permission("settings:read"))):
    kid = _user.get("tenant_id") or _user.get("kanzlei_id", "default")
    return ok({"eintraege": webhook_endpoint_list(kid)})


@app.delete("/saas/webhooks/{webhook_id}", tags=["SaaS"], summary="Webhook Endpoint löschen")
def saas_webhook_delete(
    webhook_id: str,
    _user: dict = Depends(require_permission("settings:write")),
):
    _require_tenant_feature(_user, "api_webhooks_write")
    kid = _user.get("tenant_id") or _user.get("kanzlei_id", "default")
    ok_del = webhook_endpoint_delete(kid, webhook_id)
    if not ok_del:
        raise HTTPException(404, "Webhook nicht gefunden")
    return ok({"status": "deleted", "id": webhook_id})


@app.post("/saas/webhooks/{webhook_id}/test", tags=["SaaS"], summary="Testevent enqueuen")
def saas_webhook_test(
    webhook_id: str,
    _user: dict = Depends(require_permission("settings:write")),
):
    _require_tenant_feature(_user, "api_webhooks_write")
    kid = _user.get("tenant_id") or _user.get("kanzlei_id", "default")
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
    data = agent_actions_list(store.kanzlei_id, limit)
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
    offene_aufgaben = sum(1 for a in aufgaben.values() if aufgabe_ist_offen(a))

    ueberfaellig = []
    faellig_heute = []
    faellig_diese_woche = []

    from core.frist_utils import tage_bis_frist

    for a in aufgaben.values():
        if aufgabe_ist_erledigt(a):
            continue
        tage = tage_bis_frist(a.get("frist"), heute=jetzt.date())
        if tage is None:
            continue
        eintrag = {**a, "tage_bis_frist": tage}
        if tage < 0:
            ueberfaellig.append(eintrag)
        elif tage == 0:
            faellig_heute.append(eintrag)
        elif tage <= 7:
            faellig_diese_woche.append(eintrag)

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
        if aufgabe_ist_erledigt(a):
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
                "id": a.get("id"),
                "mandant": a.get("mandant"),
                "beschreibung": a.get("beschreibung"),
                "text": f"{a.get('mandant', '?')} -> {a.get('beschreibung', '?')}",
                "label": label,
                "prioritaet": a.get("prioritaet", "normal"),
                "frist": a["frist"],
                "frist_uhrzeit": a.get("frist_uhrzeit") or "",
                "tage": tage,
                "sort_score": prio,
            })

        except Exception:
            continue

    result.sort(key=lambda x: x["sort_score"], reverse=True)
    return ok_compat({"eintraege": result[:15], "anzahl": len(result[:15])})


@app.get("/dashboard/heute-ops", tags=["Dashboard"],
          summary="Heute: Bot-Fragen, fehlende Belege, überfällige Aufgaben")
def dashboard_heute_ops(_user: dict = Depends(get_current_user)):
    from core.dashboard_ops import heute_operations

    store = get_ds(_user)
    return ok_compat(heute_operations(store))


@app.get("/dashboard/blockierung", tags=["Dashboard"],
         summary="Blockierungszentrum — was hält die Kanzlei auf")
def dashboard_blockierung(
    limit: int = Query(30, ge=1, le=100),
    _user: dict = Depends(get_current_user),
):
    from core.dashboard_ops import blockierungszentrum

    store = get_ds(_user)
    return ok_compat(blockierungszentrum(store, limit=limit))


@app.get("/dashboard/autopilot", tags=["Dashboard"],
         summary="Autopilot-Center — heute automatisch erledigt")
def dashboard_autopilot(_user: dict = Depends(get_current_user)):
    from core.dashboard_ops import autopilot_stats

    store = get_ds(_user)
    return ok_compat(autopilot_stats(store))


@app.get("/dashboard/roi", tags=["Dashboard"],
         summary="ROI-Zusammenfassung (Zeitersparnis)")
def dashboard_roi(_user: dict = Depends(get_current_user)):
    from core.dashboard_ops import roi_monatsbericht

    store = get_ds(_user)
    return ok_compat(roi_monatsbericht(store))


@app.get("/dashboard/automation-audit", tags=["Dashboard"],
         summary="Audit-Trail der Automationen (Workflow, Eskalation, Bot)")
def dashboard_automation_audit(
    limit: int = Query(50, ge=1, le=200),
    _user: dict = Depends(require_permission("engine:read")),
):
    from core.automation_audit import automation_audit

    store = get_ds(_user)
    return ok_compat(automation_audit(store, limit=limit))


@app.post("/dashboard/roi/email", tags=["Dashboard"],
          summary="ROI-Monatsbericht per E-Mail senden (manuell oder Scheduler)")
def dashboard_roi_email_senden(_user: dict = Depends(require_permission("settings:write"))):
    from core.roi_email import send_roi_monatsbericht_email

    store = get_ds(_user)
    result = send_roi_monatsbericht_email(store)
    return ok_compat(result)


@app.get("/regeln/vorlagen", tags=["Automation"],
         summary="Vorinstallierte Workflow-Vorlagen (Marktplatz)")
def regeln_vorlagen_liste(_user: dict = Depends(get_current_user)):
    from core.workflow_templates import liste_vorlagen, zaehle_betroffene_mandanten, vorlage_by_id

    store = get_ds(_user)
    out = []
    for meta in liste_vorlagen():
        tpl = vorlage_by_id(meta["id"])
        betroffen = 0
        if tpl:
            betroffen = zaehle_betroffene_mandanten(store, tpl["regel"])
        out.append({**meta, "betroffene_mandanten": betroffen})
    return ok_compat({"vorlagen": out, "anzahl": len(out)})


@app.post("/regeln/vorlagen/{template_id}/aktivieren", tags=["Automation"],
          summary="Workflow-Vorlage mit einem Klick aktivieren")
def regeln_vorlage_aktivieren(
    template_id: str,
    bestaetigen: bool = Query(False, description="True nach Vorschau-Bestätigung"),
    _user: dict = Depends(require_permission("engine:run")),
):
    from core.workflow_templates import aktiviere_vorlage, vorlage_by_id, zaehle_betroffene_mandanten

    store = get_ds(_user)
    tpl = vorlage_by_id(template_id)
    if not tpl:
        raise HTTPException(404, f"Vorlage '{template_id}' nicht gefunden")
    betroffen = zaehle_betroffene_mandanten(store, tpl["regel"])
    if not bestaetigen:
        return ok_compat({
            "status": "vorschau",
            "vorlage": template_id,
            "betroffene_mandanten": betroffen,
            "hinweis": f"Diese Regel würde aktuell ca. {betroffen} Mandanten betreffen. "
                       "Erneut mit ?bestaetigen=true aufrufen zum Aktivieren.",
        })
    try:
        result = aktiviere_vorlage(store, template_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return ok_compat(result, "Vorlage aktiviert")


@app.get("/dashboard/pilot-scorecard", tags=["Dashboard"],
          summary="Pilot-Scorecard (Woche, Vorher/Nachher)")
def dashboard_pilot_scorecard(_user: dict = Depends(get_current_user)):
    from core.dashboard_ops import pilot_scorecard

    store = get_ds(_user)
    return ok_compat(pilot_scorecard(store))


@app.post("/dashboard/pilot-baseline", tags=["Dashboard"],
          summary="Pilot-Baseline auf aktuellen Stand setzen")
def dashboard_pilot_baseline_setzen(_user: dict = Depends(get_current_user)):
    from core.proaktiver_bot import ProaktiverBot

    store = get_ds(_user)
    stats = ProaktiverBot(store).statistiken()
    payload = {
        "gestartet_am": datetime.now().isoformat(),
        "fragen_gesamt": stats.get("fragen_gesamt", 0),
        "fragen_beantwortet": stats.get("fragen_beantwortet", 0),
        "gesparte_stunden": stats.get("gesparte_stunden", 0),
        "notiz": "Manuell gesetzt",
    }
    store.setting_setzen("pilot_baseline", payload)
    return ok_compat({"status": "ok", "baseline": payload})


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
    m = get_mandant_or_404(name, store, _user)
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
    m = get_mandant_or_404(name, store, _user)
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
    """
    Outbox/Webhook-Zähler laufen über ``daten_speicher`` (SQLite + PostgreSQL korrekt).
    Kein rohes ``datetime('now',…)`` mehr hier — das bricht unter PG.
    """
    store = get_ds(_user)
    kid = str(store.kanzlei_id or "default").strip() or "default"
    alerts: List[Dict[str, Any]] = []
    try:
        dead_mail = int(email_outbox_dead_24h_count(kid))
        if dead_mail >= 3:
            alerts.append({
                "severity": "high",
                "policy": "email_delivery",
                "title": "Mehrere Emails endgültig fehlgeschlagen",
                "details": f"{dead_mail} Dead-Letter in den letzten 24h",
            })

        failed_webhooks = int(webhook_queue_failed_24h_count(kid))
        if failed_webhooks >= 5:
            alerts.append({
                "severity": "medium",
                "policy": "webhook_delivery",
                "title": "Webhook Zustellungen instabil",
                "details": f"{failed_webhooks} fehlgeschlagene Webhook-Events in 24h",
            })

        settings_changes = int(usage_get(kid, "settings_changes_day"))
        if settings_changes >= 20:
            alerts.append({
                "severity": "low",
                "policy": "settings_churn",
                "title": "Viele Settings-Änderungen heute",
                "details": f"{settings_changes} Änderungen — mögliche Fehlkonfiguration prüfen",
            })
    except Exception as exc:  # noqa: BLE001
        log.warning("audit_policies degraded for kanzlei_id=%s: %s", kid, exc)
        return ok({"alerts": [], "count": 0, "degraded": True, "error": "policy_check_unavailable"})

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
    outbox_dead = email_outbox_dead_24h_count(kid)
    webhooks_failed = webhook_queue_failed_24h_count(kid)
    api_keys = api_key_list(kid)
    webhooks = webhook_endpoint_list(kid)
    alerts = audit_policies(_user).get("data", {}).get("alerts", [])
    compliance = _compliance_status()
    billing_obs = _billing_obs_get(kid)

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
            "billing_observability": {
                "digest_sent": int(billing_obs.get("digest_sent", 0) or 0),
                "digest_skipped_no_recipients": int(billing_obs.get("digest_skipped_no_recipients", 0) or 0),
                "channel_shift_detected": int(billing_obs.get("channel_shift_detected", 0) or 0),
                "last_updated_at": billing_obs.get("last_updated_at"),
            },
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
    Prozessübergreifender Lock (SQLite oder PostgreSQL), damit bei mehreren Workern
    nicht mehrere Auto-Agents parallel laufen.
    """
    return agent_lock_try_acquire(_agent_owner, ttl_seconds, "auto_agent")


def _release_agent_lock() -> None:
    agent_lock_release(_agent_owner, "auto_agent")

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
    get_mandant_or_404(name, store, _user)
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
    get_mandant_or_404(name, store, _user)
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
    get_mandant_or_404(name, store, _user)
    from core.engine import Engine

    engine = Engine(store)
    result = engine.workflow_neuer_mandant(name)
    _track_action_for_suggestions(store, "workflow_onboarding")
    return ok_compat(result)


# ============================================================
# ENGINE — Manuelle Steuerung & Trigger
# ============================================================

@app.post("/engine/run", tags=["Engine"], summary="Engine manuell triggern")
def engine_run(_user: dict = Depends(get_current_user)):
    """
    Führt alle Daily Checks sofort aus (ohne auf den Auto-Agent zu warten).
    Gibt Zusammenfassung (Mandanten, Warnungen, Aktionen) direkt zurück.
    """
    from core.engine import Engine
    store = get_ds(_user)
    engine = Engine(store)
    result = engine.run_daily_checks()
    log.info(
        f"Engine manuell getriggert | {result.get('mandanten_geprueft', 0)} Mandanten | "
        f"{len(result.get('warnungen', []))} Warnungen"
    )
    _track_action_for_suggestions(store, "engine_run_manual")
    return ok_compat({
        "status":    "fertig",
        "timestamp": datetime.now().isoformat(),
        **result,
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
    get_mandant_or_404(name, store, _user)
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
    get_mandant_or_404(name, store, _user)
    komm     = store.hole_kommunikation(name)
    sortiert = sorted(
        komm,
        key=lambda x: x.get("timestamp") or x.get("erstellt_am") or x.get("zeit") or "",
        reverse=True,
    )
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
    get_mandant_or_404(name, store, _user)

    eintrag = {
        "typ":       data.get("typ", "manuell"),
        "text":      data.get("text", ""),
        "timestamp": datetime.now().isoformat(),
    }

    store.kommunikation_hinzufuegen(name, eintrag)

    # Letzte Mandanten-Antwort nur bei eingehendem Kontakt (nicht Kanzlei-Ausgang)
    richtung = str(data.get("richtung") or "").strip().lower()
    typ = str(eintrag["typ"] or "").strip().lower()
    if richtung == "eingehend" or typ in ("mandant_antwort", "portal_nachricht", "portal_upload"):
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

    from modules.settings_manager import load_settings_for_store

    bestaetigt = load_settings_for_store(store).get(key)
    usage_increment(store.kanzlei_id, "settings_changes_day", 1)
    _emit_webhook_event(store.kanzlei_id, "settings.changed", {"key": key, "wert": wert})
    _track_action_for_suggestions(store, "settings_change")
    return ok_compat({
        **payload,
        "kanzlei_id": store.kanzlei_id,
        "bestaetigt": bestaetigt,
    })


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
    from modules.settings_manager import FESTGESCHRIEBEN

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
    svc = SettingsService(store)
    try:
        svc.update_one(key, wert)
        ok_set = True
    except (PermissionError, ValueError):
        ok_set = False
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
    """Legacy + modern Login-Body: Benutzername/Passwort oder E-Mail/Password.

    Einige Clients senden bei E-Mail-Login ``passwort`` statt ``password`` — wird zusammengeführt.
    Leere Strings für optionale Felder werden zu ``None`` (sonst scheitert ``min_length``).
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    benutzername: Optional[str] = Field(default=None, min_length=2, max_length=200)
    passwort: Optional[str] = Field(default=None, max_length=500)
    email: Optional[str] = Field(default=None, min_length=5, max_length=254)
    # Kein min_length: ältere Konten / importierte Nutzer können kürzere Passwörter haben.
    password: Optional[str] = Field(default=None, max_length=500)

    @field_validator("benutzername", "passwort", "email", "password", mode="before")
    @classmethod
    def _empty_str_to_none(cls, v):
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("email", mode="after")
    @classmethod
    def _norm_login_email_field(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return v
        s = str(v).strip()
        return s.lower() if "@" in s else s

    @model_validator(mode="after")
    def _validate_login_payload(self):
        has_user = bool((self.benutzername or "").strip())
        has_passwort = bool((self.passwort or "").strip())
        has_email = bool((self.email or "").strip())
        # E-Mail-Login: Passwort unter ``password`` (SPA) oder ``passwort`` (Legacy)
        has_password = bool(
            (self.password or "").strip() or (self.passwort or "").strip()
        )
        if has_user and has_passwort and len((self.passwort or "").strip()) < 4:
            raise ValueError("passwort zu kurz")
        if (has_user and has_passwort) or (has_email and has_password):
            return self
        raise ValueError("Provide benutzername+passwort or email+password")


_EMAIL_LOGIN_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", re.IGNORECASE)


class EmailPasswordLoginRequest(BaseModel):
    """OAuth-ähnlicher Login per E-Mail (Tabellenfeld ``benutzer.email``)."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    email: str = Field(..., min_length=5, max_length=254)
    password: str = Field(
        ...,
        min_length=4,
        max_length=500,
        validation_alias=AliasChoices("password", "passwort"),
    )

    @field_validator("email")
    @classmethod
    def _norm_login_email(cls, v: str) -> str:
        s = (v or "").strip().lower()
        if not _EMAIL_LOGIN_RE.match(s):
            raise ValueError("invalid email")
        return s


class EmailPasswordRegisterRequest(BaseModel):
    """Registrierung per E-Mail — Passwort min. 12 Zeichen (bcrypt in ``benutzer``)."""
    email: str = Field(..., min_length=5, max_length=254)
    password: str = Field(..., min_length=12, max_length=500)
    admin_key: Optional[str] = Field(
        None,
        description="Ab dem zweiten Benutzer: gleicher Wert wie PORTAL_ADMIN_KEY in .env",
    )
    rolle: Optional[str] = Field(None, description="Optional; Standard steuerberater")
    invite_token: Optional[str] = Field(
        None,
        description="Einladung: Token von POST /api/tenant/invites (Beitritt zur Kanzlei, Rolle aus Token)",
    )

    @field_validator("email")
    @classmethod
    def _norm_register_email(cls, v: str) -> str:
        s = (v or "").strip().lower()
        if not _EMAIL_LOGIN_RE.match(s):
            raise ValueError("invalid email")
        return s

    @field_validator("password")
    @classmethod
    def _validate_password_strength(cls, v: str) -> str:
        pw = str(v or "")
        if not re.search(r"[A-Z]", pw):
            raise ValueError("password needs uppercase")
        if not re.search(r"[a-z]", pw):
            raise ValueError("password needs lowercase")
        if not re.search(r"\d", pw):
            raise ValueError("password needs digit")
        if not re.search(r"[^A-Za-z0-9]", pw):
            raise ValueError("password needs special char")
        if " " in pw:
            raise ValueError("password must not contain spaces")
        return pw


class TenantInviteCreateRequest(BaseModel):
    """Einladungslink erzeugen (nur Mandanten-Admin)."""
    rolle: str = Field("assistent", description="assistent oder steuerberater")
    email_lock: Optional[str] = Field(
        None,
        description="Optional: nur diese E-Mail darf sich mit dem Token registrieren",
    )
    ttl_hours: int = Field(168, ge=1, le=720)

    @field_validator("email_lock")
    @classmethod
    def _norm_invite_lock(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not str(v).strip():
            return None
        s = str(v).strip().lower()
        if not _EMAIL_LOGIN_RE.match(s):
            raise ValueError("invalid locked email")
        return s

    @field_validator("rolle")
    @classmethod
    def _invite_role_only(cls, v: str) -> str:
        r = (v or "assistent").strip().lower()
        if r not in {"assistent", "steuerberater"}:
            raise ValueError("invite role must be assistent or steuerberater")
        return r


class TenantUserCreateRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)
    password: str = Field(..., min_length=12, max_length=500)
    rolle: str = Field("assistent", description="admin, steuerberater, assistent, user, mitarbeiter, worker")

    @field_validator("email")
    @classmethod
    def _norm_tenant_user_email(cls, v: str) -> str:
        s = (v or "").strip().lower()
        if not _EMAIL_LOGIN_RE.match(s):
            raise ValueError("invalid email")
        return s


class TenantUserRoleRequest(BaseModel):
    rolle: str = Field(..., min_length=3, max_length=40)


class ApiUsersRolePatchRequest(BaseModel):
    role: str = Field(..., min_length=3, max_length=40)


class ApiUsersInviteRequest(BaseModel):
    """REST: Einladungslink für Team-User erzeugen (Admin)."""
    role: str = Field("assistent", description="assistent | steuerberater")
    email: Optional[str] = Field(
        None,
        description="Empfänger-E-Mail (bei send_email) und optional gleichzeitig Lock für den Token",
    )
    ttl_hours: int = Field(168, ge=1, le=720)
    send_email: bool = Field(False, description="Einladungs-E-Mail über die Outbox versenden")

    @model_validator(mode="after")
    def _email_required_if_send(self):
        if self.send_email and not (self.email and str(self.email).strip()):
            raise ValueError("email is required when send_email is true")
        return self

    @field_validator("email")
    @classmethod
    def _norm_invite_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not str(v).strip():
            return None
        s = str(v).strip().lower()
        if not _EMAIL_LOGIN_RE.match(s):
            raise ValueError("invalid email")
        return s

    @field_validator("role")
    @classmethod
    def _invite_role_only(cls, v: str) -> str:
        r = (v or "assistent").strip().lower()
        if r == "user":
            return "assistent"
        if r not in {"assistent", "steuerberater"}:
            raise ValueError("role must be assistent or steuerberater")
        return r


class RegistrierRequest(BaseModel):
    benutzername: str  = Field(..., min_length=2, max_length=50)
    passwort:     str  = Field(..., min_length=12)
    anzeigename:  Optional[str] = None
    email:        Optional[str] = None
    rolle:        Optional[str] = Field("steuerberater")
    admin_key:    Optional[str] = None  # Für nicht-ersten Benutzer

class PasswortRequest(BaseModel):
    altes_passwort: str = Field(..., min_length=4)
    neues_passwort: str = Field(..., min_length=12)


class MeUpdateRequest(BaseModel):
    vorname: Optional[str] = Field(None, max_length=120)
    nachname: Optional[str] = Field(None, max_length=120)
    telefon: Optional[str] = Field(None, max_length=80)
    sprache: Optional[str] = Field(None, max_length=8)
    dark_mode: Optional[bool] = None
    notify_email: Optional[bool] = None
    notify_updates: Optional[bool] = None
    notify_deadlines: Optional[bool] = None


class MePasswordRequest(BaseModel):
    aktuelles_passwort: str = Field(..., min_length=4)
    neues_passwort: str = Field(..., min_length=12)
    bestaetigen: str = Field(..., min_length=12)


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., min_length=20)


class PasswortForgotRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)

    @field_validator("email")
    @classmethod
    def _norm_email(cls, v: str) -> str:
        s = (v or "").strip().lower()
        if not _EMAIL_LOGIN_RE.match(s):
            raise ValueError("invalid email")
        return s


class PasswortResetRequest(BaseModel):
    token: str = Field(..., min_length=20, max_length=512)
    neues_passwort: str = Field(..., min_length=12)
    bestaetigen: str = Field(..., min_length=12)


class EmailVerifyRequest(BaseModel):
    token: str = Field(..., min_length=20, max_length=512)


class OAuthExchangeRequest(BaseModel):
    code: str = Field(..., min_length=20, max_length=200)


def _pwreset_store() -> DatenSpeicher:
    # Passwort-Reset ist mandantenübergreifend nutzerbasiert -> zentraler Store.
    return ds


_pwreset_rate_store: Dict[str, List[float]] = {}
PWRESET_FORGOT_LIMIT_IP = int(os.getenv("PWRESET_FORGOT_LIMIT_IP", "6"))
PWRESET_FORGOT_LIMIT_EMAIL = int(os.getenv("PWRESET_FORGOT_LIMIT_EMAIL", "3"))
PWRESET_RESET_LIMIT_IP = int(os.getenv("PWRESET_RESET_LIMIT_IP", "20"))
PWRESET_RATE_WINDOW_SECONDS = int(os.getenv("PWRESET_RATE_WINDOW_SECONDS", "3600"))


def _pwreset_rate_allow(bucket: str, limit: int, window_seconds: int) -> bool:
    now_ts = time.time()
    valid = [t for t in _pwreset_rate_store.get(bucket, []) if now_ts - t < window_seconds]
    if len(valid) >= max(1, int(limit)):
        _pwreset_rate_store[bucket] = valid
        return False
    valid.append(now_ts)
    _pwreset_rate_store[bucket] = valid
    return True


def _pwreset_tokens() -> List[Dict[str, Any]]:
    store = _pwreset_store()
    rows = _kv_get(store, "__password_reset_tokens__", [])
    if not isinstance(rows, list):
        return []

    now = datetime.now()
    cleaned: List[Dict[str, Any]] = []
    changed = False
    for r in rows:
        if not isinstance(r, dict):
            changed = True
            continue
        exp_raw = str(r.get("expires_at") or "").strip()
        used_raw = str(r.get("used_at") or "").strip()
        try:
            exp_dt = datetime.fromisoformat(exp_raw) if exp_raw else now - timedelta(days=3650)
        except Exception:
            changed = True
            continue
        # Expired Tokens verwerfen
        if now > exp_dt:
            changed = True
            continue
        # Bereits verwendete Tokens nur sehr kurz behalten
        if used_raw:
            try:
                used_dt = datetime.fromisoformat(used_raw)
            except Exception:
                changed = True
                continue
            if now - used_dt > timedelta(hours=24):
                changed = True
                continue
        cleaned.append(r)

    # harte Obergrenze, falls ein Bot den Store floodet
    if len(cleaned) > 5000:
        cleaned = cleaned[-5000:]
        changed = True

    if changed:
        _pwreset_tokens_save(cleaned)
    return cleaned


def _pwreset_tokens_save(rows: List[Dict[str, Any]]) -> None:
    _kv_set(_pwreset_store(), "__password_reset_tokens__", rows)


def _pwreset_hash(token_plain: str) -> str:
    return hashlib.sha256((token_plain or "").encode("utf-8")).hexdigest()


def _email_verify_store() -> DatenSpeicher:
    return ds


def _email_verified_map() -> Dict[str, bool]:
    raw = _kv_get(_email_verify_store(), "__email_verified__", {})
    return raw if isinstance(raw, dict) else {}


def _email_verified_set(email: str, verified: bool) -> None:
    e = (email or "").strip().lower()
    if not e:
        return
    rows = _email_verified_map()
    rows[e] = bool(verified)
    _kv_set(_email_verify_store(), "__email_verified__", rows)


def _email_is_verified(email: str) -> bool:
    e = (email or "").strip().lower()
    if not e:
        return False
    m = _email_verified_map()
    # Nur explizit gesetzte False-Werte (z. B. nach /api/register) blockieren.
    # Fehlender Schlüssel = Konten vor dem Verifizierungs-Store / manuelle Admin-Nutzer → als verifiziert behandeln.
    if e in m:
        return bool(m[e])
    return True


def _email_verify_tokens() -> List[Dict[str, Any]]:
    rows = _kv_get(_email_verify_store(), "__email_verify_tokens__", [])
    if not isinstance(rows, list):
        return []
    now = datetime.now()
    cleaned: List[Dict[str, Any]] = []
    changed = False
    for r in rows:
        if not isinstance(r, dict):
            changed = True
            continue
        exp_raw = str(r.get("expires_at") or "").strip()
        used_raw = str(r.get("used_at") or "").strip()
        try:
            exp_dt = datetime.fromisoformat(exp_raw) if exp_raw else now - timedelta(days=3650)
        except Exception:
            changed = True
            continue
        if now > exp_dt:
            changed = True
            continue
        if used_raw:
            changed = True
            continue
        cleaned.append(r)
    if len(cleaned) > 5000:
        cleaned = cleaned[-5000:]
        changed = True
    if changed:
        _kv_set(_email_verify_store(), "__email_verify_tokens__", cleaned)
    return cleaned


def _email_verify_tokens_save(rows: List[Dict[str, Any]]) -> None:
    _kv_set(_email_verify_store(), "__email_verify_tokens__", rows)


def _email_verify_send(email: str) -> None:
    e = (email or "").strip().lower()
    if not e:
        return
    token_plain = secrets.token_urlsafe(40)
    token_hash = hashlib.sha256(token_plain.encode("utf-8")).hexdigest()
    rows = [r for r in _email_verify_tokens() if (r.get("email") or "").strip().lower() != e]
    now = datetime.now()
    rows.append(
        {
            "token_hash": token_hash,
            "email": e,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=24)).isoformat(),
            "used_at": "",
        }
    )
    _email_verify_tokens_save(rows)
    base = (os.getenv("PUBLIC_APP_URL") or os.getenv("PORTAL_BASE_URL") or "").strip().rstrip("/")
    if not base:
        base = "https://kanzlei-automation.com"
    verify_url = f"{base}/verify-email?token={quote(token_plain, safe='')}"
    subject = "E-Mail bestätigen — Kanzlei Automation"
    plain = (
        "Bitte bestätigen Sie Ihre E-Mail-Adresse.\n\n"
        f"Bestätigungslink (24h gültig): {verify_url}\n\n"
        "Wenn Sie diese Registrierung nicht gestartet haben, ignorieren Sie diese E-Mail."
    )
    html = (
        "<p>Bitte bestätigen Sie Ihre E-Mail-Adresse.</p>"
        f'<p><a href="{html_module.escape(verify_url)}">E-Mail jetzt bestätigen</a></p>'
        "<p>Der Link ist 24 Stunden gültig.</p>"
    )
    send_email_smtp(e, subject, plain, html, allow_global_smtp=True)


OAUTH_PROVIDERS: Dict[str, Dict[str, str]] = {
    "google": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
        "scope": "openid email profile",
    },
    "microsoft": {
        "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "userinfo_url": "https://graph.microsoft.com/oidc/userinfo",
        "scope": "openid email profile",
    },
}


def _oauth_env(provider: str, key: str) -> str:
    p = (provider or "").strip().upper()
    return (os.getenv(f"OAUTH_{p}_{key}") or "").strip()


def _oauth_redirect_uri(provider: str) -> str:
    explicit = _oauth_env(provider, "REDIRECT_URI")
    if explicit:
        return explicit
    base = (os.getenv("PUBLIC_APP_URL") or os.getenv("PORTAL_BASE_URL") or "").strip().rstrip("/")
    if not base:
        base = "https://kanzlei-automation.com"
    return f"{base}/api/auth/oauth/{provider}/callback"


def _oauth_state_rows() -> List[Dict[str, Any]]:
    rows = _kv_get(ds, "__oauth_state__", [])
    if not isinstance(rows, list):
        return []
    now = datetime.now()
    cleaned: List[Dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        try:
            exp = datetime.fromisoformat(str(r.get("expires_at") or ""))
        except Exception:
            continue
        if now <= exp:
            cleaned.append(r)
    _kv_set(ds, "__oauth_state__", cleaned[-2000:])
    return cleaned[-2000:]


def _oauth_state_save(rows: List[Dict[str, Any]]) -> None:
    _kv_set(ds, "__oauth_state__", rows[-2000:])


def _oauth_parse_jwt_payload(jwt_token: str) -> Dict[str, Any]:
    token = (jwt_token or "").strip()
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload.encode("utf-8")).decode("utf-8")
        data = json.loads(decoded)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _oauth_validate_id_token_claims(provider: str, claims: Dict[str, Any], *, expected_client_id: str, expected_nonce: str) -> bool:
    if not claims:
        return False
    now = int(time.time())
    try:
        exp = int(claims.get("exp") or 0)
    except Exception:
        return False
    if exp and now > exp:
        return False
    nonce = str(claims.get("nonce") or "")
    if expected_nonce and nonce != expected_nonce:
        return False
    aud = claims.get("aud")
    aud_ok = False
    if isinstance(aud, str):
        aud_ok = aud == expected_client_id
    elif isinstance(aud, list):
        aud_ok = expected_client_id in [str(x) for x in aud]
    if not aud_ok:
        return False
    iss = str(claims.get("iss") or "")
    issuer_map = {
        "google": {"https://accounts.google.com", "accounts.google.com"},
        "microsoft": {
            "https://login.microsoftonline.com/common/v2.0",
            "https://login.microsoftonline.com/organizations/v2.0",
            "https://sts.windows.net/",
        },
    }
    expected_issuers = issuer_map.get((provider or "").strip().lower())
    if expected_issuers and iss not in expected_issuers:
        return False
    return True


def _oauth_normalize_redirect_target(redirect_to: Optional[str]) -> str:
    """
    Open-Redirect Schutz: nur relative Pfade innerhalb SPA erlauben.
    """
    raw = (redirect_to or "").strip()
    if not raw:
        return "/login"
    if not raw.startswith("/"):
        return "/login"
    parts = urlsplit(raw)
    if parts.scheme or parts.netloc:
        return "/login"
    path = parts.path or "/login"
    allowed_prefixes = ("/login", "/profile", "/settings", "/")
    if not any(path == p or path.startswith(p.rstrip("/") + "/") for p in allowed_prefixes):
        return "/login"
    # Query behalten, Fragment verwerfen
    return path + (f"?{parts.query}" if parts.query else "")


def _looks_like_jwt(token: str) -> bool:
    t = (token or "").strip()
    return bool(t) and t.count(".") == 2 and len(t) > 40


def _session_or_jwt_access_token(session_token: str, jwt_access: str) -> str:
    """Bearer für SPA: Redis-Session bevorzugen; JWT nur wenn keine Session."""
    jwt_access = (jwt_access or "").strip()
    session_token = (session_token or "").strip()
    if len(session_token) >= 32:
        return session_token
    if _looks_like_jwt(jwt_access):
        return jwt_access
    if len(jwt_access) >= 32:
        return jwt_access
    return session_token or jwt_access


def _issue_auth_tokens(
    *,
    sub: str,
    kanzlei_id: str,
    rolle: str,
    email: str,
    benutzername: str,
    uid: Optional[int] = None,
) -> Dict[str, Any]:
    from backend.auth import (
        access_token_ttl_minutes,
        create_access_token,
        create_refresh_token,
        refresh_token_expire_days,
    )

    e = (email or "").strip().lower()
    pwv = _auth_pw_version_get(e) if e else 1
    jti = secrets.token_urlsafe(20)
    extra: Dict[str, Any] = {
        "kanzlei_id": kanzlei_id,
        "tenant_id": kanzlei_id,
        "rolle": rolle,
        "role": rolle,
        "email": e,
        "benutzername": benutzername,
        "pv": pwv,
        "jti": jti,
    }
    if uid is not None:
        extra["uid"] = int(uid)
    access = create_access_token({"sub": sub, **extra})
    refresh = create_refresh_token(sub, extra_claims=extra)
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": access_token_ttl_minutes() * 60,
        "refresh_expires_in": refresh_token_expire_days() * 24 * 60 * 60,
        "pv": pwv,
        "jti": jti,
    }


def _auth_state_store() -> DatenSpeicher:
    return ds


def _auth_pw_version_get(email: str) -> int:
    e = (email or "").strip().lower()
    if not e:
        return 1
    raw = _kv_get(_auth_state_store(), "__auth_pw_version__", {})
    mp = raw if isinstance(raw, dict) else {}
    v = mp.get(e, 1)
    try:
        return max(1, int(v))
    except Exception:
        return 1


def _auth_pw_version_bump(email: str) -> int:
    e = (email or "").strip().lower()
    if not e:
        return 1
    raw = _kv_get(_auth_state_store(), "__auth_pw_version__", {})
    mp = raw if isinstance(raw, dict) else {}
    cur = _auth_pw_version_get(e)
    nxt = cur + 1
    mp[e] = nxt
    _kv_set(_auth_state_store(), "__auth_pw_version__", mp)
    return nxt


def _refresh_jti_is_used(jti: str) -> bool:
    key = (jti or "").strip()
    if not key:
        return True
    raw = _kv_get(_auth_state_store(), "__used_refresh_jti__", {})
    mp = raw if isinstance(raw, dict) else {}
    return key in mp


def _refresh_jti_mark_used(jti: str) -> None:
    key = (jti or "").strip()
    if not key:
        return
    raw = _kv_get(_auth_state_store(), "__used_refresh_jti__", {})
    mp = raw if isinstance(raw, dict) else {}
    mp[key] = int(time.time())
    # Speicherbegrenzung
    if len(mp) > 10000:
        keep = sorted(mp.items(), key=lambda kv: kv[1], reverse=True)[:8000]
        mp = {k: v for k, v in keep}
    _kv_set(_auth_state_store(), "__used_refresh_jti__", mp)


def _oauth_login_codes() -> Dict[str, Dict[str, Any]]:
    raw = _kv_get(ds, "__oauth_login_codes__", {})
    return raw if isinstance(raw, dict) else {}


def _oauth_login_codes_save(mp: Dict[str, Dict[str, Any]]) -> None:
    _kv_set(ds, "__oauth_login_codes__", mp)


def _oauth_login_code_store(payload: Dict[str, Any], ttl_seconds: int = 120) -> str:
    code = secrets.token_urlsafe(32)
    now = int(time.time())
    mp = _oauth_login_codes()
    mp[code] = {"expires": now + max(30, int(ttl_seconds)), "payload": payload}
    if len(mp) > 4000:
        # prune oldest by expiry
        keep = sorted(mp.items(), key=lambda kv: int((kv[1] or {}).get("expires", 0)), reverse=True)[:3000]
        mp = {k: v for k, v in keep}
    _oauth_login_codes_save(mp)
    return code


def _oauth_login_code_consume(code: str) -> Optional[Dict[str, Any]]:
    key = (code or "").strip()
    if not key:
        return None
    now = int(time.time())
    mp = _oauth_login_codes()
    row = mp.pop(key, None)
    # purge expired on every consume
    for k in list(mp.keys()):
        try:
            if now > int((mp[k] or {}).get("expires", 0)):
                mp.pop(k, None)
        except Exception:
            mp.pop(k, None)
    _oauth_login_codes_save(mp)
    if not row:
        return None
    try:
        if now > int((row or {}).get("expires", 0)):
            return None
    except Exception:
        return None
    payload = (row or {}).get("payload")
    return payload if isinstance(payload, dict) else None


@app.post("/auth/password/forgot", tags=["Auth"], summary="Passwort vergessen — Reset-Link senden")
@app.post("/api/auth/password/forgot", tags=["Auth"], summary="Passwort vergessen — Reset-Link senden (/api Alias)")
def auth_password_forgot(data: PasswortForgotRequest, request: Request):
    """
    Gibt immer eine generische Erfolgsantwort zurück (keine User-Enumeration).
    """
    from backend.auth import finde_benutzer_nach_email

    email = data.email.strip().lower()
    ip = _get_client_ip(request)
    allow_ip = _pwreset_rate_allow(f"forgot:ip:{ip}", PWRESET_FORGOT_LIMIT_IP, PWRESET_RATE_WINDOW_SECONDS)
    allow_email = _pwreset_rate_allow(
        f"forgot:email:{hashlib.sha256(email.encode('utf-8')).hexdigest()}",
        PWRESET_FORGOT_LIMIT_EMAIL,
        PWRESET_RATE_WINDOW_SECONDS,
    )
    if not allow_ip or not allow_email:
        _pwreset_store().log_eintrag(f"PASSWORT_RESET_RATE_LIMIT | forgot | ip={ip} | email={email}")
        raise HTTPException(429, "Zu viele Passwort-Reset-Anfragen. Bitte später erneut versuchen.")

    row = finde_benutzer_nach_email(email)
    _pwreset_store().log_eintrag(f"PASSWORT_RESET_FORGOT | email={email} | ip={ip} | exists={1 if row else 0}")
    if row:
        token_plain = secrets.token_urlsafe(48)
        now = datetime.now()
        expires = now + timedelta(minutes=45)
        entry = {
            "token_hash": _pwreset_hash(token_plain),
            "email": email,
            "benutzername": row.get("benutzername"),
            "kanzlei_id": row.get("kanzlei_id") or "default",
            "created_at": now.isoformat(),
            "expires_at": expires.isoformat(),
            "used_at": "",
            "ip": ip,
        }
        rows = [r for r in _pwreset_tokens() if (r.get("used_at") or "") == ""]
        # alte Tokens für dieselbe Mail ungültig machen
        rows = [r for r in rows if (r.get("email") or "").lower() != email]
        rows.append(entry)
        _pwreset_tokens_save(rows)

        base = (os.getenv("PUBLIC_APP_URL") or os.getenv("PORTAL_BASE_URL") or "").strip().rstrip("/")
        if not base:
            base = "https://kanzlei-automation.com"
        reset_url = f"{base}/reset-password?token={quote(token_plain, safe='')}"
        subject = "Passwort zurücksetzen — Kanzlei Automation"
        plain = (
            "Sie haben eine Passwort-Zurücksetzung angefordert.\n\n"
            f"Link (45 Minuten gültig): {reset_url}\n\n"
            "Wenn Sie das nicht waren, ignorieren Sie diese E-Mail."
        )
        html = (
            "<p>Sie haben eine Passwort-Zurücksetzung angefordert.</p>"
            f'<p><a href="{html_module.escape(reset_url)}">Passwort jetzt zurücksetzen</a></p>'
            "<p>Der Link ist 45 Minuten gültig. Wenn Sie das nicht waren, ignorieren Sie diese E-Mail.</p>"
        )
        send_email_smtp(email, subject, plain, html, allow_global_smtp=True)
        _pwreset_store().log_eintrag(f"PASSWORT_RESET_LINK_GESENDET | {row.get('benutzername')} | {row.get('kanzlei_id')}")

    return {"status": "ok", "message": "Falls die E-Mail existiert, wurde ein Reset-Link versendet."}


@app.post("/auth/password/reset", tags=["Auth"], summary="Passwort mit Reset-Token setzen")
@app.post("/api/auth/password/reset", tags=["Auth"], summary="Passwort mit Reset-Token setzen (/api Alias)")
def auth_password_reset(data: PasswortResetRequest, request: Request):
    from backend.auth import logout_all_user_sessions, setze_passwort_ohne_altes

    if data.neues_passwort != data.bestaetigen:
        raise HTTPException(400, "Neues Passwort und Bestätigung stimmen nicht überein")

    ip = _get_client_ip(request)
    if not _pwreset_rate_allow(f"reset:ip:{ip}", PWRESET_RESET_LIMIT_IP, PWRESET_RATE_WINDOW_SECONDS):
        _pwreset_store().log_eintrag(f"PASSWORT_RESET_RATE_LIMIT | reset | ip={ip}")
        raise HTTPException(429, "Zu viele Reset-Versuche. Bitte später erneut versuchen.")

    token_hash = _pwreset_hash(data.token)
    rows = _pwreset_tokens()
    now = datetime.now()
    match = None
    for r in rows:
        if (r.get("token_hash") or "") != token_hash:
            continue
        if (r.get("used_at") or "").strip():
            continue
        try:
            exp = datetime.fromisoformat(r.get("expires_at") or "")
        except Exception:
            continue
        if now > exp:
            continue
        match = r
        break

    if not match:
        _pwreset_store().log_eintrag(f"PASSWORT_RESET_INVALID_TOKEN | ip={ip}")
        raise HTTPException(400, "Reset-Token ungültig oder abgelaufen")

    benutzername = str(match.get("benutzername") or "").strip()
    kanzlei_id = str(match.get("kanzlei_id") or "default").strip() or "default"
    if not benutzername:
        raise HTTPException(400, "Reset-Token enthält keinen Benutzer")

    ok = setze_passwort_ohne_altes(benutzername, kanzlei_id, data.neues_passwort)
    if not ok:
        raise HTTPException(500, "Passwort konnte nicht gesetzt werden")

    match["used_at"] = now.isoformat()
    _pwreset_tokens_save(rows)
    try:
        logout_all_user_sessions(benutzername, kanzlei_id)
    except Exception:
        pass
    # Alle bestehenden Refresh-Tokens über Passwort-Version invalidieren.
    email = str(match.get("email") or "").strip().lower()
    if email:
        _auth_pw_version_bump(email)
    _pwreset_store().log_eintrag(f"PASSWORT_RESET | {benutzername} | {kanzlei_id} | ip={ip}")
    return {"status": "ok", "message": "Passwort wurde erfolgreich zurückgesetzt."}


@app.post("/auth/email/verify", tags=["Auth"], summary="E-Mail-Adresse bestätigen")
@app.post("/api/auth/email/verify", tags=["Auth"], summary="E-Mail-Adresse bestätigen (/api Alias)")
def auth_email_verify(data: EmailVerifyRequest):
    token_hash = hashlib.sha256((data.token or "").encode("utf-8")).hexdigest()
    rows = _email_verify_tokens()
    match = None
    for r in rows:
        if (r.get("token_hash") or "") == token_hash and not str(r.get("used_at") or "").strip():
            match = r
            break
    if not match:
        raise HTTPException(400, "Verifizierungs-Token ungültig oder abgelaufen")
    email = str(match.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(400, "Ungültiger Verifizierungs-Token")
    match["used_at"] = datetime.now().isoformat()
    _email_verify_tokens_save(rows)
    _email_verified_set(email, True)
    ds.log_eintrag(f"EMAIL_VERIFIED | {email}")
    return {"status": "ok", "message": "E-Mail erfolgreich bestätigt."}


@app.post("/auth/email/resend", tags=["Auth"], summary="Verifizierungs-E-Mail erneut senden")
@app.post("/api/auth/email/resend", tags=["Auth"], summary="Verifizierungs-E-Mail erneut senden (/api Alias)")
def auth_email_resend(data: PasswortForgotRequest):
    email = (data.email or "").strip().lower()
    if not email:
        raise HTTPException(400, "Ungültige E-Mail")
    if _email_is_verified(email):
        return {"status": "ok", "message": "E-Mail ist bereits verifiziert."}
    _email_verify_send(email)
    ds.log_eintrag(f"EMAIL_VERIFY_RESEND | {email}")
    return {"status": "ok", "message": "Falls die E-Mail existiert, wurde ein Bestätigungslink gesendet."}


@app.get("/auth/oauth/{provider}/start", tags=["Auth"], summary="OAuth/OIDC Login starten")
@app.get("/api/auth/oauth/{provider}/start", tags=["Auth"], summary="OAuth/OIDC Login starten (/api Alias)")
def auth_oauth_start(provider: str, redirect_to: Optional[str] = Query(None)):
    p = (provider or "").strip().lower()
    cfg = OAUTH_PROVIDERS.get(p)
    if not cfg:
        raise HTTPException(404, "OAuth-Provider nicht unterstützt")
    client_id = _oauth_env(p, "CLIENT_ID")
    client_secret = _oauth_env(p, "CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(503, f"OAuth für {p} ist nicht konfiguriert")
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    rows = _oauth_state_rows()
    rows.append(
        {
            "state": state,
            "nonce": nonce,
            "provider": p,
            "redirect_to": _oauth_normalize_redirect_target(redirect_to),
            "expires_at": (datetime.now() + timedelta(minutes=10)).isoformat(),
        }
    )
    _oauth_state_save(rows)
    params = {
        "client_id": client_id,
        "redirect_uri": _oauth_redirect_uri(p),
        "response_type": "code",
        "scope": cfg["scope"],
        "state": state,
    }
    if p in {"google", "microsoft"}:
        params["nonce"] = nonce
    if p == "google":
        params["access_type"] = "offline"
        params["prompt"] = "select_account"
    auth_url = f"{cfg['auth_url']}?{urlencode(params)}"
    return RedirectResponse(auth_url, status_code=302)


@app.get("/auth/oauth/{provider}/callback", tags=["Auth"], summary="OAuth/OIDC Callback")
@app.get("/api/auth/oauth/{provider}/callback", tags=["Auth"], summary="OAuth/OIDC Callback (/api Alias)")
async def auth_oauth_callback(provider: str, code: str = Query(...), state: str = Query(...)):
    p = (provider or "").strip().lower()
    cfg = OAUTH_PROVIDERS.get(p)
    if not cfg:
        raise HTTPException(404, "OAuth-Provider nicht unterstützt")
    rows = _oauth_state_rows()
    st = next((r for r in rows if r.get("state") == state and r.get("provider") == p), None)
    if not st:
        raise HTTPException(400, "Ungültiger OAuth-Status")
    rows = [r for r in rows if r.get("state") != state]
    _oauth_state_save(rows)

    client_id = _oauth_env(p, "CLIENT_ID")
    client_secret = _oauth_env(p, "CLIENT_SECRET")
    redirect_uri = _oauth_redirect_uri(p)
    token_payload = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    }
    async with httpx.AsyncClient(timeout=20) as cli:
        token_res = await cli.post(cfg["token_url"], data=token_payload, headers={"Content-Type": "application/x-www-form-urlencoded"})
        if token_res.status_code >= 400:
            detail = (token_res.text or "")[:1200]
            log.warning("OAuth token endpoint error (%s): status=%s body=%s", p, token_res.status_code, detail)
            raise HTTPException(400, f"OAuth Token-Fehler ({p})")
        try:
            token_data = token_res.json() if token_res.content else {}
        except Exception:
            raise HTTPException(400, f"OAuth Token-Antwort ungültig ({p})") from None

        email = ""
        if cfg.get("userinfo_url"):
            at = str(token_data.get("access_token") or "")
            ures = await cli.get(cfg["userinfo_url"], headers={"Authorization": f"Bearer {at}"})
            if ures.status_code < 400:
                try:
                    ujson = ures.json() if ures.content else {}
                except Exception:
                    ujson = {}
                email = str(ujson.get("email") or "").strip().lower()
        if not email:
            claims = _oauth_parse_jwt_payload(str(token_data.get("id_token") or ""))
            expected_nonce = str(st.get("nonce") or "")
            if not _oauth_validate_id_token_claims(
                p,
                claims,
                expected_client_id=client_id,
                expected_nonce=expected_nonce,
            ):
                raise HTTPException(400, "OIDC Token-Claims ungültig")
            email = str(claims.get("email") or "").strip().lower()
        if not email:
            raise HTTPException(400, "OAuth lieferte keine E-Mail-Adresse")

    if st.get("mode") == "m365_connect":
        if p != "microsoft":
            raise HTTPException(400, "M365 Connect nur für Microsoft")
        kid = str(st.get("kanzlei_id") or "default")
        tenant_store = get_ds({"kanzlei_id": kid, "tenant_id": kid})
        from core.m365_integration import save_m365_tokens

        save_m365_tokens(tenant_store, token_data, email=email)
        target = _oauth_normalize_redirect_target(st.get("redirect_to"))
        sep = "&" if "?" in target else "?"
        redirect_url = f"{target}{sep}m365=connected"
        html = (
            "<!doctype html><html><body>"
            "<script>window.location.href="
            + json.dumps(redirect_url)
            + ";</script>"
            "</body></html>"
        )
        return HTMLResponse(content=html, status_code=200)

    try:
        from backend.auth import finde_benutzer_nach_email, registriere_per_email
        row = finde_benutzer_nach_email(email)
        if not row:
            # Neue Registrierung über Social Login (eigene Kanzlei)
            random_pw = secrets.token_urlsafe(24) + "Aa1!"
            registriere_per_email(email, random_pw)
            row = finde_benutzer_nach_email(email)
    except HTTPException:
        raise
    except Exception:
        log.exception("oauth user create/find failed (%s)", p)
        raise HTTPException(500, "OAuth Anmeldung fehlgeschlagen") from None
    if not row:
        raise HTTPException(500, "Social Login konnte Benutzer nicht erzeugen")

    _email_verified_set(email, True)
    kid = str(row.get("kanzlei_id") or "default")
    bname = str(row.get("benutzername") or "")
    rolle = str(row.get("rolle") or "assistent")
    uid = row.get("id")
    sub = str(int(uid)) if uid is not None and str(uid).isdigit() else bname
    tokens = _issue_auth_tokens(
        sub=sub,
        kanzlei_id=kid,
        rolle=rolle,
        email=email,
        benutzername=bname,
        uid=int(uid) if uid is not None and str(uid).isdigit() else None,
    )
    target = _oauth_normalize_redirect_target(st.get("redirect_to"))
    sep = "&" if "?" in target else "?"
    session_tok = ""
    try:
        from datetime import datetime, timedelta

        import secrets

        from backend.auth import TOKEN_TTL, _session_speichern

        session_tok = secrets.token_urlsafe(48)
        expires = datetime.now() + timedelta(seconds=TOKEN_TTL)
        _session_speichern(
            session_tok,
            {
                "benutzername": bname,
                "kanzlei_id": kid,
                "tenant_id": kid,
                "rolle": rolle,
                "email": email,
                "user_id": int(uid) if uid is not None and str(uid).isdigit() else None,
                "expires": expires.timestamp(),
                "ip": "oauth",
            },
        )
    except Exception:
        log.exception("OAuth: Session-Token konnte nicht angelegt werden")
    oauth_access = _session_or_jwt_access_token(
        session_tok,
        str(tokens.get("access_token") or ""),
    )
    oauth_code = _oauth_login_code_store(
        {
            "token": session_tok or oauth_access,
            "access_token": oauth_access,
            "refresh_token": tokens["refresh_token"],
            "token_type": tokens["token_type"],
            "expires_in": tokens["expires_in"],
            "refresh_expires_in": tokens["refresh_expires_in"],
            "role": rolle,
            "email": email,
        }
    )
    redirect_url = f"{target}{sep}oauth=ok&code={quote(oauth_code, safe='')}"
    try:
        ds.log_eintrag(f"OAUTH_LOGIN | {p} | {email}")
    except Exception:
        # OAuth Login darf nicht an optionalem Audit-Log scheitern.
        log.exception("oauth log_eintrag failed (%s)", p)
    html = (
        "<!doctype html><html><body>"
        "<script>window.location.href="
        + json.dumps(redirect_url)
        + ";</script>"
        "</body></html>"
    )
    return HTMLResponse(content=html, status_code=200)


@app.post("/auth/oauth/exchange", tags=["Auth"], summary="OAuth Login-Code gegen Tokens tauschen")
@app.post("/api/auth/oauth/exchange", tags=["Auth"], summary="OAuth Login-Code gegen Tokens tauschen (/api Alias)")
def auth_oauth_exchange(data: OAuthExchangeRequest):
    payload = _oauth_login_code_consume(data.code)
    if not payload:
        raise HTTPException(400, "OAuth-Code ungültig oder abgelaufen")
    return payload


@app.post("/auth/login", tags=["Auth"], summary="Login — Session-Token erhalten")
async def auth_login(data: LoginRequest, request: Request):
    """Login mit Rate-Limiting; akzeptiert benutzername/passwort oder email/password."""

    from backend.auth import (
        hat_irgendein_benutzer,
        login,
        login_by_email,
        _sanitize_benutzername_raw,
        _sanitize_login_passwort,
    )
    if not hat_irgendein_benutzer():
        raise HTTPException(503, "System nicht initialisiert: bitte zuerst einen Admin registrieren")
    ip = _get_client_ip(request)
    try:
        if (data.email or "").strip():
            pw = _sanitize_login_passwort(str(data.password or data.passwort or ""))
            result = login_by_email(str(data.email or ""), pw, ip=ip)
        else:
            result = login(
                _sanitize_benutzername_raw(str(data.benutzername or "")),
                _sanitize_login_passwort(str(data.passwort or "")),
                ip=ip,
            )
        if not result:
            try:
                from backend.audit import audit_event as _audit
                _audit(
                    {"benutzername": (data.benutzername or data.email or "")},
                    "LOGIN_FAIL",
                    status="deny",
                    ip=ip,
                    details={"reason": "invalid_credentials"},
                )
            except Exception:
                pass
            if (data.email or "").strip():
                raise HTTPException(401, "E-Mail oder Passwort falsch.")
            raise HTTPException(401, "Benutzername oder Passwort falsch")
        require_verified = (os.getenv("AUTH_REQUIRE_EMAIL_VERIFIED") or "0").strip().lower() in {"1", "true", "yes", "on"}
        mail = str(result.get("email") or "").strip().lower()
        if mail and not _email_is_verified(mail):
            _email_verified_set(mail, True)
        if require_verified and mail and not _email_is_verified(mail):
            try:
                from backend.audit import audit_event as _audit
                _audit(result, "LOGIN_FAIL", status="deny", ip=ip,
                       details={"reason": "email_not_verified"})
            except Exception:
                pass
            raise HTTPException(403, "E-Mail noch nicht bestätigt")
        kid = result.get("kanzlei_id", "default")
        log_store = DatenSpeicher(kanzlei_id=kid)
        _log_bn = str(result.get("benutzername") or data.benutzername or data.email or "?").strip()
        log_store.log_eintrag(f"LOGIN | {_log_bn}", benutzer=_log_bn, ip=ip)
        try:
            from backend.audit import audit_event as _audit
            _audit(result, "LOGIN_OK", status="ok", ip=ip)
        except Exception:
            pass
        try:
            from backend.auth import (
                jwt_secret,
            )

            if jwt_secret():
                uid = result.get("user_id")
                kid_jwt = result.get("kanzlei_id", "default")
                rol = result.get("rolle", "assistent")
                jwt_sub = str(int(uid)) if uid is not None else result["benutzername"]
                issued = _issue_auth_tokens(
                    sub=jwt_sub,
                    kanzlei_id=kid_jwt,
                    rolle=rol,
                    email=result.get("email") or "",
                    benutzername=result["benutzername"],
                    uid=int(uid) if uid is not None else None,
                )
                result["access_token"] = _session_or_jwt_access_token(
                    str(result.get("token") or ""),
                    str(issued.get("access_token") or ""),
                )
                result["refresh_token"] = issued["refresh_token"]
                result["token_type"] = issued["token_type"]
                result["expires_in"] = issued["expires_in"]
                result["refresh_expires_in"] = issued["refresh_expires_in"]
        except (ValueError, ImportError) as exc:
            log.warning("JWT-Ausstellung fehlgeschlagen, nutze Session-Token: %s", exc)
            if result.get("token"):
                result["access_token"] = result["token"]
        if result.get("token"):
            result["access_token"] = str(result["token"])
        try:
            from backend.deps import reset_security_last_seen

            reset_security_last_seen(
                str(result.get("benutzername") or ""),
                str(result.get("kanzlei_id") or "default"),
            )
        except Exception:
            pass
        # Konsistenz für Frontends: role + rolle + bearer (Session)
        result["role"] = result.get("rolle", "user")
        if result.get("token"):
            result["bearer"] = str(result["token"])
        return ok_compat(result, "Login erfolgreich")
    except ValueError as e:
        raise HTTPException(429, str(e))


@app.post("/auth/refresh", tags=["Auth"], summary="Neues Access-Token aus Refresh-Token")
def auth_refresh(data: RefreshTokenRequest):
    from backend.auth import (
        verify_refresh_token,
    )

    claims = verify_refresh_token(data.refresh_token)
    if not claims:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    if (claims.get("typ") or "") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token type")
    sub = str(claims.get("sub") or "").strip()
    if not sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token payload")
    old_jti = str(claims.get("jti") or "").strip()
    if not old_jti or _refresh_jti_is_used(old_jti):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token was already used")
    email = str(claims.get("email") or "").strip().lower()
    token_pv = int(claims.get("pv") or 1)
    current_pv = _auth_pw_version_get(email) if email else token_pv
    if token_pv != current_pv:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token invalidated by password change")
    _refresh_jti_mark_used(old_jti)
    extra = {
        "kanzlei_id": claims.get("kanzlei_id") or claims.get("tenant_id") or "default",
        "tenant_id": claims.get("tenant_id") or claims.get("kanzlei_id") or "default",
        "rolle": claims.get("rolle") or claims.get("role") or "assistent",
        "role": claims.get("role") or claims.get("rolle") or "assistent",
        "email": email,
        "benutzername": claims.get("benutzername") or "",
    }
    if claims.get("uid") is not None:
        extra["uid"] = claims.get("uid")
    issued = _issue_auth_tokens(
        sub=sub,
        kanzlei_id=str(extra["kanzlei_id"]),
        rolle=str(extra["rolle"]),
        email=email,
        benutzername=str(extra["benutzername"] or ""),
        uid=int(extra["uid"]) if extra.get("uid") is not None and str(extra.get("uid")).isdigit() else None,
    )
    return {
        "access_token": issued["access_token"],
        "refresh_token": issued["refresh_token"],
        "token_type": issued["token_type"],
        "expires_in": issued["expires_in"],
        "refresh_expires_in": issued["refresh_expires_in"],
    }


@app.post("/login", tags=["Auth"], summary="Login per E-Mail — JWT + Session (Nginx: /api/login → /login)")
@app.post("/api/login", tags=["Auth"], summary="Login per E-Mail — JWT + Session (direkt auf Uvicorn)")
async def api_login_email_jwt(data: EmailPasswordLoginRequest, request: Request):
    """
    Flache JSON-Antwort (``access_token``, ``token_type``) für SPA/curl.
    ``access_token`` ist bei gesetztem ``JWT_SECRET`` ein HS256-JWT; sonst dasselbe Session-Token wie ``token``.
    """
    from backend.auth import hat_irgendein_benutzer, login_by_email, _sanitize_login_passwort
    from backend.auth import access_token_ttl_minutes, jwt_secret as jwt_secret_fn

    if not hat_irgendein_benutzer():
        raise HTTPException(503, "System nicht initialisiert: bitte zuerst einen Admin registrieren")
    ip = _get_client_ip(request)
    try:
        result = login_by_email(data.email, _sanitize_login_passwort(data.password), ip=ip)
    except ValueError as e:
        raise HTTPException(429, str(e))
    if not result:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "E-Mail oder Passwort falsch. Reine Benutzernamen-Zugänge: im Feld ohne @ eintragen.",
        )
    require_verified = (os.getenv("AUTH_REQUIRE_EMAIL_VERIFIED") or "0").strip().lower() in {"1", "true", "yes", "on"}
    mail = str(result.get("email") or "").strip().lower()
    if mail and not _email_is_verified(mail):
        _email_verified_set(mail, True)
    if require_verified and mail and not _email_is_verified(mail):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "E-Mail noch nicht bestätigt")

    kid = result.get("kanzlei_id", "default")
    log_store = DatenSpeicher(kanzlei_id=kid)
    log_store.log_eintrag(
        f"LOGIN_EMAIL | {result['benutzername']}", benutzer=result["benutzername"], ip=ip
    )

    from backend.auth import refresh_token_expire_days

    if jwt_secret_fn():
        rol = result.get("rolle", "assistent")
        uid = result.get("user_id")
        sub = str(int(uid)) if uid is not None else result["benutzername"]
        try:
            issued = _issue_auth_tokens(
                sub=sub,
                kanzlei_id=kid,
                rolle=rol,
                email=result.get("email") or "",
                benutzername=result["benutzername"],
                uid=int(uid) if uid is not None else None,
            )
            access = _session_or_jwt_access_token(
                str(result.get("token") or ""),
                str(issued.get("access_token") or ""),
            )
            refresh = issued["refresh_token"]
            refresh_expires_in = issued["refresh_expires_in"]
        except (ValueError, ImportError) as exc:
            log.warning("JWT-Ausstellung fehlgeschlagen (/login), Session-Token: %s", exc)
            access = result["token"]
            refresh = ""
            refresh_expires_in = 0
    else:
        access = result["token"]
        refresh = ""
        refresh_expires_in = 0

    body = {
        "access_token": access,
        "token_type": "bearer",
        "token": result["token"],
        "benutzername": result["benutzername"],
        "kanzlei_id": kid,
        "tenant_id": kid,
        "role": result.get("rolle", "user"),
        "rolle": result.get("rolle", "user"),
        "expires_in": access_token_ttl_minutes() * 60,
    }
    if refresh:
        body["refresh_token"] = refresh
        body["refresh_expires_in"] = refresh_expires_in or (refresh_token_expire_days() * 24 * 60 * 60)
    if result.get("token"):
        body["access_token"] = str(result["token"])
        body["bearer"] = str(result["token"])
    try:
        from backend.deps import reset_security_last_seen

        reset_security_last_seen(str(result.get("benutzername") or ""), kid)
    except Exception:
        pass
    return body


@app.get("/api/me", tags=["Auth"], summary="Kurzprofil — Alias für Nginx /api/")
def api_me_minimal(current_user: dict = Depends(get_current_user)):
    # Legacy endpoint now returns the richer MVP profile payload.
    return auth_me(current_user)


@app.get("/api/protected", tags=["Auth"], summary="Geschützter Endpoint-Check")
def api_protected_probe(current_user: dict = Depends(get_current_user)):
    """Minimaler Probe-Endpoint für Deploy/Frontend-Guards."""
    return {
        "ok": True,
        "user": {
            "benutzername": current_user.get("benutzername"),
            "tenant_id": current_user.get("tenant_id") or current_user.get("kanzlei_id"),
            "role": current_user.get("role") or current_user.get("rolle"),
        },
    }


@app.post(
    "/register",
    tags=["Auth"],
    summary="Registrierung per E-Mail (Nginx: /api/register → /register)",
    status_code=status.HTTP_201_CREATED,
)
@app.post(
    "/api/register",
    tags=["Auth"],
    summary="Registrierung per E-Mail (direkt auf Uvicorn)",
    status_code=status.HTTP_201_CREATED,
)
def api_register_email(data: EmailPasswordRegisterRequest, request: Request):
    """
    Legt einen Benutzer mit internem Login-Namen an; Login erfolgt weiter per E-Mail (``/login``).
    Fehlerdetails bewusst generisch (Enumeration).
    """
    from backend.auth import registriere_per_email

    _fail = HTTPException(status.HTTP_400_BAD_REQUEST, "Registration could not be completed")
    ip = _get_client_ip(request)
    try:
        created = registriere_per_email(
            str(data.email),
            data.password,
            admin_key=data.admin_key,
            rolle=data.rolle,
            invite_token=data.invite_token,
        )
        kid_reg = (created or {}).get("kanzlei_id") or "default"
        try:
            log_store = DatenSpeicher(kanzlei_id=kid_reg)
            log_store.log_eintrag(f"REGISTER_EMAIL | {data.email}", benutzer=str(data.email), ip=ip)
        except Exception:
            pass
    except ValueError:
        raise _fail from None
    except Exception:
        log.exception("api_register_email")
        raise _fail from None
    _email_verified_set(data.email, False)
    try:
        _email_verify_send(data.email)
    except Exception:
        log.exception("email verify send failed")
    return {
        "message": "User created",
        "kanzlei_id": kid_reg,
        "tenant_id": kid_reg,
        "email_verification_required": True,
    }


@app.post("/auth/logout", tags=["Auth"], summary="Logout — Session beenden")
def auth_logout(
    authorization: Optional[str] = Header(None),
    _user: dict = Depends(get_current_user),
):
    """Session-Token invalidieren."""
    from backend.auth import logout
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

    from backend.auth import erstelle_benutzer, hat_irgendein_benutzer
    import os
    # Legacy-Endpoint bleibt kompatibel, aber der harte Admin-Key-Gate ist optional,
    # damit Self-Service Registrierung nicht durch "Admin-Key erforderlich" blockiert.
    legacy_gate = (os.getenv("AUTH_REQUIRE_ADMIN_KEY_FOR_LEGACY_REGISTER") or "0").strip().lower() in {"1", "true", "yes", "on"}
    if legacy_gate and hat_irgendein_benutzer():
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
    kid = str(current_user.get("tenant_id") or current_user.get("kanzlei_id") or "default").strip() or "default"
    bname = str(current_user.get("benutzername") or "").strip()
    store = DatenSpeicher(kanzlei_id=kid)
    user_profiles = store.setting_holen("__user_profiles__", {}) or {}
    profile = user_profiles.get(bname, {}) if isinstance(user_profiles, dict) else {}
    tenant_profile = store.setting_holen("__tenant_profile__", {}) or {}
    return {
        **current_user,
        "vorname": profile.get("vorname") or "",
        "nachname": profile.get("nachname") or "",
        "telefon": profile.get("telefon") or "",
        "sprache": profile.get("sprache") or "de",
        "dark_mode": bool(profile.get("dark_mode", True)),
        "notify_email": bool(profile.get("notify_email", True)),
        "notify_updates": bool(profile.get("notify_updates", True)),
        "notify_deadlines": bool(profile.get("notify_deadlines", True)),
        "password_last_changed_at": profile.get("password_last_changed_at"),
        "last_login": current_user.get("letzter_login") or profile.get("last_login"),
        "kanzlei_profil": {
            "name": tenant_profile.get("kanzlei_name") or "",
            "adresse": tenant_profile.get("kanzlei_adresse") or "",
            "telefon": tenant_profile.get("kanzlei_telefon") or "",
            "logo_url": tenant_profile.get("kanzlei_logo_url") or "",
        },
    }


@app.get("/me", tags=["Auth"], summary="Basis-Profil (MVP)")
def me_get_alias(current_user: dict = Depends(get_current_user)):
    return auth_me(current_user)


@app.put("/me", tags=["Auth"], summary="Basis-Profil aktualisieren (MVP)")
@app.put("/api/me", tags=["Auth"], summary="Basis-Profil aktualisieren (MVP, /api Alias)")
def me_update(data: MeUpdateRequest, current_user: dict = Depends(get_current_user)):
    kid = str(current_user.get("tenant_id") or current_user.get("kanzlei_id") or "default").strip() or "default"
    bname = str(current_user.get("benutzername") or "").strip()
    if not bname:
        raise HTTPException(400, "Ungültiger Benutzerkontext")
    store = DatenSpeicher(kanzlei_id=kid)
    user_profiles = store.setting_holen("__user_profiles__", {}) or {}
    if not isinstance(user_profiles, dict):
        user_profiles = {}
    profile = user_profiles.get(bname, {}) if isinstance(user_profiles.get(bname), dict) else {}
    payload = data.model_dump(exclude_none=True)
    for key, value in payload.items():
        profile[key] = value
    user_profiles[bname] = profile
    if not store.setting_setzen("__user_profiles__", user_profiles):
        raise HTTPException(500, "Profil konnte nicht gespeichert werden")
    return {"status": "ok", "message": "Profil aktualisiert"}

@app.get("/auth/benutzer", tags=["Auth"], summary="Alle Benutzer (nur Admin)")
def auth_benutzer_liste(current_user: dict = Depends(require_permission("settings:write"))):
    """Alle Kanzlei-Mitarbeiter auflisten."""
    from backend.auth import liste_benutzer
    if current_user.get("rolle") not in ["admin"]:
        raise HTTPException(403, "Nur für Admins")
    return liste_benutzer(current_user.get("kanzlei_id", "default"))


@app.get("/admin/users", tags=["Auth"], summary="Alle Benutzer (Admin)")
@app.get("/api/admin/users", tags=["Auth"], summary="Alle Benutzer (Admin, /api Alias)")
def api_admin_users(admin: dict = Depends(require_admin)):
    """
    RBAC-kritischer Endpunkt: Nur ``rolle=admin``.
    """
    from backend.auth import liste_benutzer

    kid = admin.get("kanzlei_id", "default")
    users = liste_benutzer(kid)
    # Niemals Hash/Salt zurückgeben; nur Safe-View.
    return [
        {
            "benutzername": u.get("benutzername"),
            "email": u.get("email"),
            "rolle": u.get("rolle"),
            "aktiv": u.get("aktiv"),
            "erstellt_am": u.get("erstellt_am"),
            "letzter_login": u.get("letzter_login"),
        }
        for u in users
    ]


@app.get("/api/admin/test", tags=["Auth"], summary="Admin-Gate (Smoke-Test)")
def api_admin_test(admin: dict = Depends(require_admin)):
    """Nur Admins (Session/JWT mit ``role``/``rolle`` = admin). API-Key: 403."""
    return {"message": "Admin access works"}


@app.put("/auth/passwort", tags=["Auth"], summary="Passwort ändern")
def auth_passwort(data: PasswortRequest, current_user: dict = Depends(get_current_user)):
    """Eigenes Passwort ändern."""

    store = get_ds(current_user)
    from backend.auth import aendere_passwort
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


@app.put("/me/password", tags=["Auth"], summary="Passwort ändern (MVP)")
@app.put("/api/me/password", tags=["Auth"], summary="Passwort ändern (MVP, /api Alias)")
def me_password(data: MePasswordRequest, current_user: dict = Depends(get_current_user)):
    if data.neues_passwort != data.bestaetigen:
        raise HTTPException(400, "Neues Passwort und Bestätigung stimmen nicht überein")
    auth_passwort(
        PasswortRequest(
            altes_passwort=data.aktuelles_passwort,
            neues_passwort=data.neues_passwort,
        ),
        current_user,
    )
    kid = str(current_user.get("tenant_id") or current_user.get("kanzlei_id") or "default").strip() or "default"
    bname = str(current_user.get("benutzername") or "").strip()
    email = str(current_user.get("email") or "").strip().lower()
    store = DatenSpeicher(kanzlei_id=kid)
    user_profiles = store.setting_holen("__user_profiles__", {}) or {}
    if isinstance(user_profiles, dict) and bname:
        profile = user_profiles.get(bname, {}) if isinstance(user_profiles.get(bname), dict) else {}
        profile["password_last_changed_at"] = datetime.now().isoformat()
        user_profiles[bname] = profile
        store.setting_setzen("__user_profiles__", user_profiles)
    if email:
        _auth_pw_version_bump(email)
    return {"status": "ok", "message": "Passwort geändert"}


@app.post("/me/logout-all", tags=["Auth"], summary="Alle Sessions abmelden")
@app.post("/api/me/logout-all", tags=["Auth"], summary="Alle Sessions abmelden (/api Alias)")
def me_logout_all(
    authorization: Optional[str] = Header(None),
    current_user: dict = Depends(get_current_user),
):
    from backend.auth import logout, logout_all_user_sessions

    kid = str(current_user.get("tenant_id") or current_user.get("kanzlei_id") or "default").strip() or "default"
    bname = str(current_user.get("benutzername") or "").strip()
    invalidated = logout_all_user_sessions(bname, kid)
    if authorization and authorization.startswith("Bearer "):
        logout(authorization.replace("Bearer ", ""))
    return {"status": "ok", "invalidated_sessions": max(1, int(invalidated))}

@app.get("/auth/setup-status", tags=["Auth"], summary="Prüft ob System eingerichtet")
def auth_setup_status():
    """Prüft ob bereits Benutzer angelegt sind (für Ersteinrichtung)."""
    from backend.auth import hat_irgendein_benutzer
    return {"eingerichtet": hat_irgendein_benutzer()}


# ── Strukturierte Auth-Pfade: /api/auth/* (Aliase zu /auth/*) ─
from fastapi import APIRouter as _APIRouterAuthAlias

_api_auth_alias = _APIRouterAuthAlias(prefix="/api/auth", tags=["Auth"])


@_api_auth_alias.post("/login")
async def api_auth_login_alias(data: LoginRequest, request: Request):
    return await auth_login(data, request)


@_api_auth_alias.post("/refresh", summary="Token erneuern (SPA unter /api/)")
def api_auth_refresh_alias(data: RefreshTokenRequest):
    """Gleiche Logik wie ``POST /auth/refresh`` — Nginx leitet nur ``/api/*`` zum Backend."""
    return auth_refresh(data)


@_api_auth_alias.post("/logout")
def api_auth_logout_alias(
    authorization: Optional[str] = Header(None),
    _user: dict = Depends(get_current_user),
):
    return auth_logout(authorization, _user)


@_api_auth_alias.post("/registrieren", status_code=status.HTTP_201_CREATED)
def api_auth_registrieren_alias(data: RegistrierRequest):
    return auth_registrieren(data)


@_api_auth_alias.get("/me")
def api_auth_me_alias(current_user: dict = Depends(get_current_user)):
    return auth_me(current_user)


@_api_auth_alias.get("/benutzer")
def api_auth_benutzer_alias(current_user: dict = Depends(require_permission("settings:write"))):
    return auth_benutzer_liste(current_user)


@_api_auth_alias.put("/passwort")
def api_auth_passwort_alias(data: PasswortRequest, current_user: dict = Depends(get_current_user)):
    return auth_passwort(data, current_user)


@_api_auth_alias.get("/setup-status")
def api_auth_setup_status_alias():
    return auth_setup_status()


app.include_router(_api_auth_alias)


# ── Strukturierte Pfade: /api/users/*, /api/data/* (parallel zu /auth/*) ─
from fastapi import APIRouter as _APIRouterUsersData

_api_users_struct = _APIRouterUsersData(prefix="/api/users", tags=["Users"])


def _public_user_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Einheitliche API-Antwort ohne sensible Felder."""
    r = dict(row)
    rid = r.get("id")
    rl = r.get("rolle") or "assistent"
    active = bool(int(r.get("aktiv", 1) or 0))
    return {
        "id": int(rid) if rid is not None and str(rid).isdigit() else rid,
        "email": (r.get("email") or "").strip(),
        "benutzername": r.get("benutzername"),
        "rolle": rl,
        "role": rl,
        "aktiv": active,
        "is_active": active,
        "erstellt_am": r.get("erstellt_am"),
        "letzter_login": r.get("letzter_login"),
    }


@_api_users_struct.get("/me")
def api_users_me_struct(current_user: dict = Depends(get_current_user)):
    return auth_me(current_user)


@_api_users_struct.get("/benutzer")
def api_users_benutzer_struct(current_user: dict = Depends(require_permission("settings:write"))):
    return auth_benutzer_liste(current_user)


@_api_users_struct.get("", summary="Benutzer der Kanzlei (nur Admin)")
def api_users_list(admin: dict = Depends(require_admin)):
    """
    Mandanten-Liste: nur Benutzer mit ``benutzer.kanzlei_id ==`` Mandant des Admins.

    Entspricht tutorial-seitig ``User.tenant_id == user['tenant_id']`` — bei uns
    erzwingt ``backend.auth.liste_benutzer(kanzlei_id)`` die WHERE-Klausel; es gibt
    **keinen** Query-Parameter zur Mandantenwahl (kein Cross-Tenant-Leak).
    """
    from backend.auth import liste_benutzer

    if admin.get("api_key_id"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized")
    kid = tenant_id_from_user(admin)
    rows = liste_benutzer(kid)
    return ok([_public_user_row(x) for x in rows if isinstance(x, dict)])


@_api_users_struct.post("", status_code=status.HTTP_201_CREATED, summary="Benutzer anlegen (nur Admin)")
def api_users_create(data: CreateUserRequest, admin: dict = Depends(require_admin)):
    """
    Mandanten-sicher: ``kanzlei_id`` / ``tenant_id`` ausschließlich aus ``admin`` (niemals aus dem Body).

    Persistenz: ``backend.auth.erstelle_benutzer`` (Tabelle ``benutzer``), Passwort-Hashing dort per bcrypt.
    """
    from backend.auth import email_adresse_bereits_registriert, erstelle_benutzer, loginname_aus_email

    if admin.get("api_key_id"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized")
    kid = tenant_id_from_user(admin)
    if email_adresse_bereits_registriert(data.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "User already exists")
    bname = loginname_aus_email(data.email)
    try:
        row = erstelle_benutzer(
            bname,
            data.password,
            rolle=data.role,
            email=data.email,
            kanzlei_id=kid,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return ok(_public_user_row(row), "User created")


@_api_users_struct.get("/invites", summary="Einladungen der Kanzlei (Audit, nur Admin)")
def api_users_invites_list(
    admin: dict = Depends(require_admin),
    limit: int = Query(50, ge=1, le=200),
):
    from core.tenant_invite_records import invite_records_list

    if admin.get("api_key_id"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized")
    kid = tenant_id_from_user(admin)
    return ok(invite_records_list(kanzlei_id=str(kid), limit=limit))


@_api_users_struct.post("/invites", status_code=status.HTTP_201_CREATED, summary="Einladungslink erzeugen (nur Admin)")
def api_users_create_invite(
    background_tasks: BackgroundTasks,
    data: ApiUsersInviteRequest,
    admin: dict = Depends(require_admin),
):
    from core.tenant_invite_records import invite_record_insert, invite_record_mark_email_enqueued
    from core.tenant_invites import create_tenant_invite_token, invite_secret_configured, verify_tenant_invite_token

    if admin.get("api_key_id"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized")
    kid = tenant_id_from_user(admin)
    if not invite_secret_configured():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Einladungen benötigen INVITE_TOKEN_SECRET oder JWT_SECRET/PORTAL_SECRET (jeweils ≥32 Zeichen).",
        )
    lock = (data.email or "").strip().lower() or None
    try:
        tok = create_tenant_invite_token(
            kanzlei_id=str(kid),
            invited_by=str(admin.get("benutzername") or ""),
            rolle=data.role,
            email_lock=lock,
            ttl_hours=data.ttl_hours,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    meta = verify_tenant_invite_token(tok)
    if not meta or not meta.get("jti"):
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "invite_meta_failed")

    invite_record_insert(
        kanzlei_id=str(kid),
        jti=str(meta["jti"]),
        role=str(meta.get("role") or data.role),
        email_lock=meta.get("email_lock"),
        target_email=(data.email or "").strip().lower() if data.send_email else None,
        invited_by=str(admin.get("benutzername") or ""),
        expires_at=int(meta.get("exp") or 0),
    )

    invite_url = _invite_registration_url(tok)
    payload: Dict[str, Any] = {
        "invite_token": tok,
        "invite_url": invite_url,
        "jti": meta.get("jti"),
        "tenant_id": kid,
        "kanzlei_id": kid,
        "ttl_hours": data.ttl_hours,
        "role": data.role,
        "rolle": data.role,
        "email_lock": meta.get("email_lock"),
        "send_email": data.send_email,
    }

    if data.send_email:
        to = (data.email or "").strip().lower()
        subject = "Einladung: Kanzlei-Zugang"
        body = (
            "Sie wurden zu einer Kanzlei eingeladen.\n\n"
            f"Bitte registrieren Sie sich unter diesem Link (Passwort selbst wählen):\n{invite_url}\n\n"
            "Der Link ist nur begrenzt gültig.\n"
        )
        safe_url = html_module.escape(invite_url, quote=True)
        html_body = (
            "<p>Sie wurden zu einer Kanzlei eingeladen.</p>"
            f'<p><a href="{safe_url}">Jetzt registrieren</a></p>'
            "<p>Der Link ist nur begrenzt gültig.</p>"
        )
        idk = f"team_invite|{kid}|{meta['jti']}|v1"
        enq = email_outbox_enqueue(
            kanzlei_id=str(kid),
            mandant="__team_invite__",
            to_email=to,
            subject=subject,
            body_text=body,
            body_html=html_body,
            idempotency_key=idk,
        )
        invite_record_mark_email_enqueued(
            jti=str(meta["jti"]),
            kanzlei_id=str(kid),
            outbox_id=enq.get("id"),
        )
        payload["email_outbox"] = enq

    background_tasks.add_task(_process_email_outbox_once, 8)
    return ok(payload, "Invite created")


@_api_users_struct.delete("/invites/{jti}", summary="Einladung widerrufen (nur Admin)")
def api_users_invite_revoke(jti: str, admin: dict = Depends(require_admin)):
    from core.tenant_invite_records import invite_record_revoke

    if admin.get("api_key_id"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized")
    kid = tenant_id_from_user(admin)
    if not invite_record_revoke(jti=(jti or "").strip(), kanzlei_id=str(kid)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invite not found or not revocable")
    return ok({"jti": jti, "status": "revoked"}, "Invite revoked")


@_api_users_struct.patch("/{user_id}/role", summary="Rolle setzen (nur Admin)")
def api_users_patch_role(
    user_id: int,
    data: ApiUsersRolePatchRequest,
    admin: dict = Depends(require_admin),
):
    from backend.auth import benutzer_rolle_setzen_nach_id, hole_benutzer_kurz_nach_id

    if admin.get("api_key_id"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized")
    kid = tenant_id_from_user(admin)
    row = hole_benutzer_kurz_nach_id(int(user_id), kid)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if str(row.get("benutzername") or "").strip() == (admin.get("benutzername") or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Eigene Rolle hier nicht änderbar")
    old_role = str(row.get("rolle") or "")
    # Owner-Schutz: nur Owner darf Owner setzen oder absetzen.
    from core.rbac import canonical_role as _canon, is_owner as _is_owner
    new_canonical = _canon(data.role)
    if _is_owner(old_role) and new_canonical != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Owner kann nicht herabgestuft werden")
    if new_canonical == "owner" and not _is_owner(admin.get("rolle")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nur ein Owner darf Owner-Rolle vergeben")
    if not benutzer_rolle_setzen_nach_id(int(user_id), kid, data.role):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    try:
        from backend.audit import audit_event as _audit
        _audit(
            admin,
            "ROLE_CHANGE",
            target=f"user:{user_id}",
            details={"old": old_role, "new": data.role, "username": row.get("benutzername")},
        )
    except Exception:
        pass
    return ok({"id": user_id, "role": data.role, "rolle": data.role}, "Rolle aktualisiert")


@_api_users_struct.delete("/{user_id}", summary="Benutzer deaktivieren / Soft-delete (nur Admin)")
def api_users_delete(user_id: int, admin: dict = Depends(require_admin)):
    from backend.auth import benutzer_deaktivieren_nach_id, hole_benutzer_kurz_nach_id
    from core.rbac import is_owner as _is_owner

    if admin.get("api_key_id"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized")
    kid = tenant_id_from_user(admin)
    row = hole_benutzer_kurz_nach_id(int(user_id), kid)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if str(row.get("benutzername") or "").strip() == (admin.get("benutzername") or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Eigenes Konto nicht deaktivieren")
    aid = admin.get("user_id")
    if aid is not None and int(aid) == int(user_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Eigenes Konto nicht deaktivieren")
    if _is_owner(row.get("rolle")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Owner kann nicht deaktiviert werden")
    if not benutzer_deaktivieren_nach_id(int(user_id), kid):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    try:
        from backend.audit import audit_event as _audit

        _audit(
            admin,
            "USER_DEACTIVATE",
            target=f"user:{user_id}",
            details={"username": row.get("benutzername"), "role": row.get("rolle")},
        )
    except Exception:
        pass
    return ok({"id": user_id, "aktiv": False, "message": "deleted"})


_api_data_struct = _APIRouterUsersData(prefix="/api/data", tags=["Data"])


@_api_data_struct.get("/status")
def api_data_status(_user: dict = Depends(get_current_user)):
    du_pg = pg_primary_db()
    use_pg_m = (os.getenv("USE_POSTGRES_DATA") or "").strip().lower() in ("1", "true", "yes")
    pg_only = (os.getenv("POSTGRES_ONLY_DATA") or "").strip().lower() in ("1", "true", "yes")
    kid_status = _user.get("tenant_id") or _user.get("kanzlei_id")
    return ok(
        {
            "kanzlei_id": _user.get("kanzlei_id"),
            "tenant_id": kid_status,
            "auth_kanzleien_db": "postgresql" if du_pg else "sqlite",
            "mandanten_db": "postgresql" if (du_pg and use_pg_m) else "sqlite",
            "saas_tables_db": "postgresql" if du_pg else "sqlite",
            "sqlite_get_connection_disabled": pg_only,
        },
        "Datenlage-Kurzinfo",
    )


app.include_router(_api_users_struct)
app.include_router(_api_data_struct)


_api_tenant = _APIRouterUsersData(prefix="/api/tenant", tags=["Tenant SaaS"])


@_api_tenant.post("/invites", summary="Einladungs-Token erzeugen (Admin)")
def tenant_create_invite(data: TenantInviteCreateRequest, admin: dict = Depends(require_admin)):
    from core.tenant_invites import create_tenant_invite_token, invite_secret_configured

    if admin.get("api_key_id"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized")
    kid = tenant_id_from_user(admin)
    if not invite_secret_configured():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Einladungen benötigen INVITE_TOKEN_SECRET oder JWT_SECRET/PORTAL_SECRET (jeweils ≥32 Zeichen).",
        )
    try:
        tok = create_tenant_invite_token(
            kanzlei_id=str(kid),
            invited_by=str(admin.get("benutzername") or ""),
            rolle=data.rolle,
            email_lock=data.email_lock,
            ttl_hours=data.ttl_hours,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    try:
        from core.tenant_invite_records import invite_record_insert
        from core.tenant_invites import verify_tenant_invite_token

        meta = verify_tenant_invite_token(tok)
        if meta and meta.get("jti"):
            el = (data.email_lock or "").strip().lower() or None
            invite_record_insert(
                kanzlei_id=str(kid),
                jti=str(meta["jti"]),
                role=str(meta.get("role") or data.rolle),
                email_lock=el,
                target_email=None,
                invited_by=str(admin.get("benutzername") or ""),
                expires_at=int(meta.get("exp") or 0),
            )
    except Exception:
        log.exception("tenant_create_invite: invite_record_insert")

    return ok(
        {
            "invite_token": tok,
            "tenant_id": kid,
            "kanzlei_id": kid,
            "ttl_hours": data.ttl_hours,
            "rolle": data.rolle,
            "email_lock": data.email_lock,
        },
        "Einladung erstellt",
    )


@_api_tenant.get("/users", summary="Benutzer der eigenen Kanzlei (Admin)")
def tenant_list_users(admin: dict = Depends(require_admin)):
    from backend.auth import liste_benutzer

    kid = tenant_id_from_user(admin)
    return ok(liste_benutzer(kid))


@_api_tenant.post("/users", status_code=status.HTTP_201_CREATED, summary="Benutzer in der Kanzlei anlegen (Admin)")
def tenant_create_user(data: TenantUserCreateRequest, admin: dict = Depends(require_admin)):
    from backend.auth import email_adresse_bereits_registriert, erstelle_benutzer, loginname_aus_email
    from core.rbac import canonical_role as _canon, is_owner as _is_owner

    kid = tenant_id_from_user(admin)
    requested_role = _canon(data.rolle)
    if requested_role in {"owner", "admin"} and not _is_owner(admin.get("rolle")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nur ein Owner darf Admin/Owner-Benutzer anlegen")
    if email_adresse_bereits_registriert(data.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "E-Mail bereits registriert")
    bname = loginname_aus_email(data.email)
    try:
        row = erstelle_benutzer(
            bname,
            data.password,
            rolle=data.rolle,
            email=data.email,
            kanzlei_id=kid,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return ok(row, "Benutzer erstellt")


@_api_tenant.patch("/users/{benutzername}/role", summary="Rolle setzen (Admin)")
def tenant_set_user_role(
    benutzername: str,
    data: TenantUserRoleRequest,
    admin: dict = Depends(require_admin),
):
    from backend.auth import benutzer_rolle_setzen, liste_benutzer
    from core.rbac import canonical_role as _canon, is_owner as _is_owner

    kid = tenant_id_from_user(admin)
    target_name = benutzername.strip()
    if target_name == (admin.get("benutzername") or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Eigene Rolle hier nicht änderbar")
    users = [u for u in (liste_benutzer(kid) or []) if str(u.get("benutzername") or "").strip() == target_name]
    if not users:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Benutzer nicht gefunden")
    old_role = str(users[0].get("rolle") or "")
    new_canonical = _canon(data.rolle)
    if _is_owner(old_role) and new_canonical != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Owner kann nicht herabgestuft werden")
    if new_canonical == "owner" and not _is_owner(admin.get("rolle")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nur ein Owner darf Owner-Rolle vergeben")
    if new_canonical == "admin" and not _is_owner(admin.get("rolle")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nur ein Owner darf Admin-Rolle vergeben")
    if not benutzer_rolle_setzen(target_name, kid, data.rolle):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Benutzer nicht gefunden oder nicht aktiv")
    try:
        from backend.audit import audit_event as _audit

        _audit(
            admin,
            "ROLE_CHANGE",
            target=f"user:{target_name}",
            details={"old": old_role, "new": data.rolle, "username": target_name},
        )
    except Exception:
        pass
    return ok({"benutzername": target_name, "rolle": data.rolle}, "Rolle aktualisiert")


@_api_tenant.delete("/users/{benutzername}", summary="Benutzer deaktivieren (Admin)")
def tenant_deactivate_user(benutzername: str, admin: dict = Depends(require_admin)):
    from backend.auth import benutzer_deaktivieren, liste_benutzer
    from core.rbac import is_owner as _is_owner

    kid = tenant_id_from_user(admin)
    target_name = benutzername.strip()
    if target_name == (admin.get("benutzername") or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Eigenes Konto nicht deaktivieren")
    users = [u for u in (liste_benutzer(kid) or []) if str(u.get("benutzername") or "").strip() == target_name]
    if not users:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Benutzer nicht gefunden")
    if _is_owner(users[0].get("rolle")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Owner kann nicht deaktiviert werden")
    if not benutzer_deaktivieren(target_name, kid):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Benutzer nicht gefunden")
    try:
        from backend.audit import audit_event as _audit

        _audit(
            admin,
            "USER_DEACTIVATE",
            target=f"user:{target_name}",
            details={"username": target_name, "role": users[0].get("rolle")},
        )
    except Exception:
        pass
    return ok({"benutzername": target_name, "aktiv": False}, "Benutzer deaktiviert")


@_api_tenant.get("/features", summary="Feature-Flags (Mandant)")
def tenant_features_get(_user: dict = Depends(get_current_user)):
    from core.tenant_features import FEATURE_SETTINGS_KEY, merged_features

    store = get_ds(_user)
    raw = store.setting_holen(FEATURE_SETTINGS_KEY, {})
    return ok(merged_features(raw))


@_api_tenant.put("/features", summary="Feature-Flags mergen (Owner)")
def tenant_features_put(body: Dict[str, Any], admin: dict = Depends(require_owner)):
    from core.tenant_features import FEATURE_SETTINGS_KEY, merge_patch, merged_features

    store = get_ds(admin)
    current = store.setting_holen(FEATURE_SETTINGS_KEY, {})
    merged = merge_patch(current if isinstance(current, dict) else {}, body or {})
    if not store.setting_setzen(FEATURE_SETTINGS_KEY, merged):
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Speichern fehlgeschlagen")
    return ok(merged_features(merged), "Feature-Flags gespeichert")


app.include_router(_api_tenant)


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
    m             = get_mandant_or_404(name, store, _user)
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

@app.get("/export/{name}/datev/info", tags=["Export"],
         summary="DATEV Export-Vorschau (Nutzen, Buchungen, Hinweise)")
def export_datev_info(
    name: str,
    berater_nr: str = Query(""),
    _user: dict = Depends(require_permission("export:datev")),
):
    """Vor dem Download: Relevanz und erwartete Buchungszeilen."""
    if not bool(global_setting_holen("datev_export_aktiv")):
        raise HTTPException(503, "DATEV Export ist deaktiviert")
    from core.datev_export_utils import assess_datev_export_relevance, normalize_berater_nr
    store = get_ds(_user)
    m = get_mandant_or_404(name, store, _user)
    aufgaben = [a for a in store.hole_fristen().values() if a.get("mandant") == name]
    alle_mandanten = store.hole_mandanten()
    bnr = normalize_berater_nr(berater_nr or global_setting_holen("datev_berater_nr") or "12345")
    return assess_datev_export_relevance(name, m, aufgaben, bnr, alle_mandanten)


@app.get("/export/{name}/datev", tags=["Export"],
         summary="DATEV Buchungsstapel CSV (EXTF v700)")
def export_datev(
    name:         str,
    berater_nr:   str = Query(""),
    mandanten_nr: str = Query(""),
    jahr:         int = Query(None),
    _user: dict = Depends(require_permission("export:datev")),
):
    """DATEV EXTF v700 Buchungsstapel — Übergabe an DATEV (Buchführung bleibt in DATEV)."""
    if not bool(global_setting_holen("datev_export_aktiv")):
        raise HTTPException(503, "DATEV Export ist deaktiviert")
    from fastapi.responses import StreamingResponse
    from core.export_service import export_datev_buchungsstapel
    from core.datev_export_utils import (
        assess_datev_export_relevance,
        normalize_berater_nr,
        validate_datev_buchungsstapel_csv,
    )
    import io
    store = get_ds(_user)
    m        = get_mandant_or_404(name, store, _user)
    alle_mandanten = store.hole_mandanten()
    aufgaben = [a for a in store.hole_fristen().values() if a.get("mandant") == name]
    bnr = normalize_berater_nr(berater_nr or global_setting_holen("datev_berater_nr") or "12345")
    try:
        rel = assess_datev_export_relevance(name, m, aufgaben, bnr, alle_mandanten)
        if not rel.get("exportierbar", True):
            raise HTTPException(400, (rel.get("hinweise") or ["Export nicht möglich"])[0])
        csv_bytes = export_datev_buchungsstapel(
            name, m, aufgaben, bnr, mandanten_nr or None, jahr, alle_mandanten=alle_mandanten
        )
        meta = validate_datev_buchungsstapel_csv(csv_bytes, strict=True)
        datum     = datetime.now().strftime("%Y%m%d")
        safe = re.sub(r"[^\w\-]+", "_", name).strip("_") or "Mandant"
        filename  = f"EXTF_{datum}_{safe}_Buchungsstapel.csv"
        store.log_eintrag(f"EXPORT_DATEV | {name} | {meta.get('buchungen', 0)} Buchungen")
        from core.product_focus import DATEV_EXPORT_HINWEIS
        warn_parts = list(meta.get("warnings") or [])
        if rel.get("hinweise"):
            warn_parts.extend(rel["hinweise"][:2])
        warn = "; ".join(warn_parts)[:300]
        return StreamingResponse(
            io.BytesIO(csv_bytes),
            media_type="text/csv; charset=windows-1252",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-DATEV-Hinweis": DATEV_EXPORT_HINWEIS[:200],
                "X-DATEV-Warnings": warn,
                "X-DATEV-Buchungen": str(meta.get("buchungen", 0)),
                "X-DATEV-Nutzen": str(rel.get("nutzen", ""))[:20],
                "X-DATEV-Debitor": str(rel.get("debitoren_konto", ""))[:12],
            },
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"DATEV Export Fehler: {e}")

@app.get("/export/datev/stammdaten", tags=["Export"],
         summary="DATEV Stammdaten aller Mandanten als Debitoren")
def export_datev_stammdaten_ep(berater_nr: str = Query(""),
    _user: dict = Depends(require_permission("export:datev"))):
    """Alle Mandanten als DATEV-Debitorenstammdaten exportieren."""
    if not bool(global_setting_holen("datev_export_aktiv")):
        raise HTTPException(503, "DATEV Export ist deaktiviert")

    store = get_ds(_user)
    from fastapi.responses import StreamingResponse
    from core.export_service import export_datev_stammdaten
    from core.datev_export_utils import normalize_berater_nr
    import io
    mandanten = store.hole_mandanten()
    if not mandanten:
        raise HTTPException(404, "Keine Mandanten vorhanden")
    bnr = normalize_berater_nr(berater_nr or global_setting_holen("datev_berater_nr") or "12345")
    try:
        csv_bytes = export_datev_stammdaten(mandanten, bnr)
        datum     = datetime.now().strftime("%Y%m%d")
        store.log_eintrag("EXPORT_DATEV_STAMMDATEN")
        return StreamingResponse(
            io.BytesIO(csv_bytes),
            media_type="text/csv; charset=windows-1252",
            headers={"Content-Disposition": f'attachment; filename="EXTF_{datum}_Stammdaten.csv"'}
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
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
    if not bool(global_setting_holen("elster_aktiv")):
        raise HTTPException(503, "ELSTER Export ist deaktiviert")
    from fastapi.responses import StreamingResponse
    from core.export_service import export_elster_xml
    import io
    store = get_ds(_user)
    m = get_mandant_or_404(name, store, _user)
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
    _require_tenant_feature(_user, "bulk_export")
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
    _require_tenant_feature(_user, "bulk_export")
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
def export_komplett(name: str, _user: dict = Depends(require_permission("export:read"))):
    """
    ZIP mit allem: DATEV Buchungsstapel + Stammdaten, ELSTER XML,
    Excel-Report, Mandanten-CSV, Aufgaben-CSV + README.
    Ein Klick — alles für DATEV/Finanzamt.
    """
    _require_tenant_feature(_user, "bulk_export")
    from fastapi.responses import StreamingResponse
    from core.export_service import export_komplettpaket
    import io
    store = get_ds(_user)
    m              = get_mandant_or_404(name, store, _user)
    alle_mandanten = store.hole_mandanten()
    alle_aufgaben  = store.hole_fristen()
    aufgaben_list  = [a for a in alle_aufgaben.values() if a.get("mandant") == name]
    kommunikation  = store.hole_kommunikation(name)
    try:
        from core.datev_export_utils import normalize_berater_nr
        bnr = normalize_berater_nr(global_setting_holen("datev_berater_nr") or "12345")
        datev_on = bool(global_setting_holen("datev_export_aktiv"))
        zip_bytes, manifest = export_komplettpaket(
            name,
            m,
            aufgaben_list,
            alle_mandanten,
            alle_aufgaben,
            kommunikation,
            berater_nr=bnr,
            datev_aktiv=datev_on,
        )
        datum    = datetime.now().strftime("%Y%m%d")
        safe = re.sub(r"[^\w\-]+", "_", name).strip("_") or "Mandant"
        filename = f"{datum}_{safe}_KanzleiAI_Export.zip"
        store.log_eintrag(
            f"EXPORT_KOMPLETT | {name} | {manifest.get('dateien_gesamt', 0)} Dateien"
        )
        rel = manifest.get("datev_relevanz") or {}
        return StreamingResponse(
            io.BytesIO(zip_bytes),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Export-Dateien": str(manifest.get("dateien_gesamt", 0)),
                "X-Export-Fehler": str(len(manifest.get("fehler") or [])),
                "X-DATEV-Nutzen": str(rel.get("nutzen", ""))[:20],
            },
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        log.error(f"Komplett-Export Fehler: {e}")
        raise HTTPException(500, f"Export Fehler: {e}")


# ============================================================
# PORTAL ADMIN (in Haupt-API integriert)
# ============================================================

@app.post("/portal/admin/token/{mandant}", tags=["Portal"],
          summary="Zugangs-Link für Mandantenportal generieren")
def generiere_portal_token(
    mandant: str,
    _user: dict = Depends(get_current_user),
):
    """
    Generiert einen sicheren Login-Link für das Mandantenportal.
    Nur für eingeloggte Kanzlei-Benutzer (JWT) — kein separater Admin-Key nötig.
    Link ist 7 Tage gültig und kann per E-Mail an den Mandanten gesendet werden.
    """
    import os
    store = get_ds(_user)
    if not bool(tenant_setting(store, "portal_aktiv")):
        raise HTTPException(503, "Mandantenportal ist deaktiviert")
    get_mandant_or_404(mandant, store, _user)
    try:
        import sys
        sys.path.insert(0, ".")
        from portal_api import erstelle_token
        token    = erstelle_token(mandant)
        port     = os.getenv("API_PUBLIC_PORT", os.getenv("PORTAL_PORT", "8000"))
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

@app.post("/legacy/dokumente/analysieren-v1", tags=["Dokument-Scanner"],
          summary="Legacy v1 Dokumentanalyse (deprecated)")
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

    _require_tenant_feature(_user, "ai_document_scan")
    _require_tenant_feature(_user, "ai_document_scan")
    store = get_ds(_user)
    try:
        result = await analyze_document(filename=data.dateiname, b64_content=data.inhalt_b64)
        payload = result.model_dump()
        store.log_eintrag(f"DOKUMENT_ANALYSIERT | {data.dateiname} | {payload.get('doktyp','?')}")
        return payload
    except Exception as e:
        log.warning(f"Dokument-Analyse Fehler: {e}")
        name_lower = (data.dateiname or "").lower()
        doktyp = "sonstiges"
        ordner = "Sonstiges"
        if any(x in name_lower for x in ["rechnung", "invoice", "re-"]):
            doktyp, ordner = "rechnung", "Rechnungen/Eingang"
        elif any(x in name_lower for x in ["konto", "auszug", "kontoauszug"]):
            doktyp, ordner = "kontoauszug", "Bank/Kontoauszüge"
        elif any(x in name_lower for x in ["bescheid", "finanzamt"]):
            doktyp, ordner = "steuerbescheid", "Steuerbescheide"
        return {
            "doktyp": doktyp,
            "ordner": ordner,
            "datum": "",
            "absender": "",
            "empfaenger": "",
            "betrag": 0.0,
            "mandant": "",
            "aufgabe": "",
            "frist": "",
            "ki_zusammenfassung": f"Automatische Analyse nicht möglich: {str(e)[:100]}. Bitte manuell zuordnen.",
            "konfidenz": 0.25,
            "unsichere_felder": ["doktyp", "ordner", "datum", "betrag"],
        }


@app.post("/legacy/dokumente/speichern-v1", tags=["Dokument-Scanner"],
          summary="Legacy v1 Dokumentspeicherung (deprecated)")
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
    _require_tenant_feature(_user, "ai_receipt_scan")
    from core.beleg_service import beleg_speichern
    store = get_ds(_user)

    from core.beleg_service import SKR03_KATEGORIEN, beleg_ohne_ki_parsen

    try:
        parsed = await analyze_receipt(
            filename=data.dateiname,
            b64_content=data.inhalt_b64,
            mandant=data.mandant or "",
        )
        beleg = parsed.model_dump()
        beleg["beleg_id"] = str(uuid.uuid4())
        beleg["dateiname"] = data.dateiname
        beleg["mandant"] = data.mandant or ""
        beleg["analysiert_am"] = datetime.now().isoformat()
        beleg["status"] = "vorschlag"
        kat = (beleg.get("kategorie") or "sonstiges").strip().lower()
        konto = SKR03_KATEGORIEN.get(kat, SKR03_KATEGORIEN["sonstiges"])
        beleg["kategorie_name"] = konto["name"]
        if (beleg.get("betrag_brutto") or 0) <= 0:
            beleg["notiz"] = (
                f"{beleg.get('notiz', '')} KI konnte Beträge nicht lesen — bitte korrigieren."
            ).strip()
    except Exception as e:
        log.warning(f"KI-Analyse fehlgeschlagen, Fallback: {e}")
        beleg = beleg_ohne_ki_parsen(data.dateiname, {"mandant": data.mandant})
        beleg["notiz"] = f"{beleg.get('notiz', '')} KI nicht verfügbar ({e}). Bitte manuell erfassen.".strip()
        beleg["vertrauens_score"] = 0.35
        beleg["unsichere_felder"] = [
            "betrag_brutto", "betrag_netto", "mwst_betrag", "datum", "kategorie", "lieferant",
        ]

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
        korr = (
            korrekturen.model_dump(exclude_none=True)
            if korrekturen and hasattr(korrekturen, "model_dump")
            else (korrekturen.dict(exclude_none=True) if korrekturen else {})
        )
        return beleg_bestaetigen(store, beleg_id, korr)
    except ValueError as e:
        msg = str(e)
        code = 400 if "Mandant" in msg else 404
        raise HTTPException(code, msg)

@app.post("/belege/{beleg_id}/ablehnen", tags=["Belege"],
          summary="Beleg ins Archiv verschieben")
def beleg_ablehnen(beleg_id: str,
    _user: dict = Depends(get_current_user)):
    """Vorschlag ablehnen oder gebuchten Beleg ins Archiv legen (endgültig löschen nur im Archiv)."""
    from core.beleg_service import beleg_ablehnen as beleg_ablehnen_core
    store = get_ds(_user)
    try:
        return beleg_ablehnen_core(store, beleg_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))

@app.get("/belege/statistiken", tags=["Belege"],
         summary="Beleg-Statistiken (Kategorien, Vorsteuer)")
def beleg_statistiken_ep(mandant: Optional[str] = Query(None),
    _user: dict = Depends(get_current_user)):
    """Ausgaben, Einnahmen, Vorsteuer aufgeschlüsselt nach Kategorie."""
    from core.beleg_service import belege_statistiken
    store = get_ds(_user)
    return belege_statistiken(store, mandant)


@app.post("/belege/{beleg_id}/wiederherstellen", tags=["Belege"],
          summary="Abgelehnten Beleg wieder aktivieren")
def beleg_wiederherstellen_ep(beleg_id: str, _user: dict = Depends(get_current_user)):
    from core.beleg_service import beleg_wiederherstellen as beleg_wiederherstellen_core
    store = get_ds(_user)
    try:
        return beleg_wiederherstellen_core(store, beleg_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@app.delete("/belege/{beleg_id}", tags=["Belege"],
            summary="Beleg löschen (Archiv oder gebucht/offen)")
def beleg_delete_ep(
    beleg_id: str,
    quelle: Optional[str] = Query(
        None,
        description="pipeline = gebuchter/offener Beleg; sonst nur Archiv",
    ),
    _user: dict = Depends(get_current_user),
):
    from core.beleg_service import beleg_aus_pipeline_loeschen, beleg_endgueltig_loeschen

    store = get_ds(_user)
    try:
        if (quelle or "").strip().lower() in {"pipeline", "scanner", "aktiv"}:
            return beleg_aus_pipeline_loeschen(store, beleg_id)
        return beleg_endgueltig_loeschen(store, beleg_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@app.post("/belege/archiv/leeren", tags=["Belege"],
          summary="Gesamtes Beleg-Archiv leeren")
def beleg_archiv_leeren_ep(mandant: Optional[str] = Query(None),
    _user: dict = Depends(get_current_user)):
    from core.beleg_service import belege_archiv_alle_loeschen
    store = get_ds(_user)
    m = (mandant or "").strip()
    payload = belege_archiv_alle_loeschen(store, m or None)
    return ok_compat(payload)


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
    get_mandant_or_404(data.mandant, store, _user)
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
                send_email_smtp,
                r["mandant_email"],
                subject,
                text,
                None,
                None,
                None,
                store,
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
        send_email_smtp,
        r["mandant_email"],
        f"Honorarrechnung {r['rechnungsnummer']} — {r.get('kanzlei', {}).get('name', 'Kanzlei')}",
        "",
        html,
        None,
        None,
        store,
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
    _require_tenant_feature(_user, "ai_assistant")
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise HTTPException(500, "OPENAI_API_KEY fehlt in .env")

    system_text = guard_input_text(data.system or "")

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

    try:
        result = await assistant_chat(
            history=data.messages[-20:],
            system_text=system_text,
            max_tokens=data.max_tokens,
            mandant=data.mandant,
        )
        return {
            "content": result.content,
            "tokens_used": result.tokens_used,
            "modell": result.modell,
            "trace_id": result.trace_id,
        }
    except Exception as e:
        msg = str(e).lower()
        if "timeout" in msg:
            raise HTTPException(504, "OpenAI Timeout — bitte nochmal versuchen")
        if "not reachable" in msg or "network" in msg:
            raise HTTPException(503, "OpenAI nicht erreichbar — Internetverbindung prüfen")
        if "api key" in msg:
            raise HTTPException(500, "OPENAI_API_KEY fehlt in .env")
        raise HTTPException(502, f"KI-Fehler: {str(e)[:200]}")


@app.get("/ki/status", tags=["KI-Assistent"], summary="KI-Verfügbarkeit prüfen")
def ki_status(_user: dict = Depends(get_current_user)):
    """Prüft ob OpenAI API-Key konfiguriert ist (nur für angemeldete Nutzer)."""
    key = os.getenv("OPENAI_API_KEY", "")
    return {
        "verfuegbar":  bool(key),
        "key_gesetzt": bool(key),
        "modell":      os.getenv("OPENAI_MODEL_DEFAULT", "gpt-4o-mini"),
        "anbieter":    "OpenAI",
        "policy":      "balanced",
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
    m = get_mandant_or_404(name, store, _user)
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


@app.post("/legacy/dokumente/speichern-v2", tags=["Dokumente"],
          summary="Legacy v2 Dokumentspeicherung (deprecated)")
def dokument_speichern_legacy_v2(metadaten: dict = Body(...),
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
    aufgabe:          Optional[str] = ""
    ki_zusammenfassung: Optional[str] = ""
    betrag:           Optional[float] = None


class DokumentUpdateRequest(BaseModel):
    dokumenttyp:      Optional[str] = None
    mandant:          Optional[str] = None
    datum:            Optional[str] = None
    frist:            Optional[str] = None
    aufgabe:          Optional[str] = None
    aufgabe_anlegen:  Optional[bool] = None
    lieferant:        Optional[str] = None
    ordner_pfad:      Optional[str] = None
    ordner_kategorie: Optional[str] = None
    jahr:             Optional[int] = None
    notiz:            Optional[str] = None
    betrag:           Optional[float] = None
    ki_zusammenfassung: Optional[str] = None


def _dokument_archiv_holen(store) -> Dict[str, Any]:
    archiv = _kv_get(store, "__dokument_archiv_v1", {})
    return archiv if isinstance(archiv, dict) else {}


def _dokument_datei_pfad(dok: Dict[str, Any]) -> str:
    import os as _os
    pfad = (dok.get("pfad") or "").strip()
    if pfad and _os.path.isfile(pfad):
        return pfad
    return _os.path.join(
        "data",
        "dokumente",
        (dok.get("ordner_pfad") or "").replace("\\", "/").strip("/"),
        dok.get("dateiname") or "",
    )


def _dokument_media_type(dateiname: str) -> str:
    ext = (Path(dateiname or "").suffix or "").lower()
    return {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".xml": "application/xml",
        ".txt": "text/plain",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }.get(ext, "application/octet-stream")


def _dokument_aufgabe_sync(store, dok: Dict[str, Any], beschreibung: str) -> None:
    """Optional Aufgabe zum Archiv-Dokument anlegen/aktualisieren."""
    mandant = (dok.get("mandant") or "").strip()
    frist = (dok.get("frist") or "").strip()
    text = (beschreibung or dok.get("aufgabe") or "").strip()
    if not mandant or not frist or not text:
        return
    aufgabe_id = dok.get("aufgabe_id") or str(uuid.uuid4())
    store.aufgabe_speichern(aufgabe_id, {
        "id": aufgabe_id,
        "mandant": mandant,
        "beschreibung": text,
        "frist": frist,
        "prioritaet": "normal",
        "kategorie": dok.get("ordner_kategorie") or dok.get("dokumenttyp") or "dokument",
        "erledigt": False,
        "erstellt_am": datetime.now().isoformat(),
    })
    dok["aufgabe_id"] = aufgabe_id
    dok["aufgabe"] = text


def _dokument_legacy_zu_archiv(leg: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Scanner v1 (__gescannte_dokumente_v1) → einheitliches Archiv-Format."""
    import hashlib as _hashlib

    dateiname = leg.get("dateiname") or "dokument"
    mandant = leg.get("mandant") or ""
    ordner = leg.get("ordner") or leg.get("ordner_kategorie") or "Sonstiges"
    pfad = (leg.get("pfad") or "").strip()
    ordner_pfad = (leg.get("ordner_pfad") or "").strip()
    if not ordner_pfad and pfad:
        ordner_pfad = pfad.replace("\\", "/")
        if "data/dokumente/" in ordner_pfad:
            ordner_pfad = ordner_pfad.split("data/dokumente/", 1)[-1]
        if ordner_pfad.endswith("/" + dateiname):
            ordner_pfad = ordner_pfad[: -(len(dateiname) + 1)]
    if not ordner_pfad and mandant:
        ordner_pfad = f"{mandant}/{ordner}"
    dok_id = leg.get("dok_id") or _hashlib.sha1(
        f"{dateiname}|{mandant}|{pfad}|{leg.get('gespeichert_am','')}".encode("utf-8")
    ).hexdigest()[:16]
    if not str(dok_id).startswith("legacy-"):
        dok_id = f"legacy-{dok_id}"

    jahr = leg.get("jahr")
    if jahr is None and leg.get("datum"):
        try:
            jahr = int(str(leg.get("datum"))[:4])
        except (TypeError, ValueError):
            jahr = None

    return {
        "dok_id": dok_id,
        "dateiname": dateiname,
        "dokumenttyp": leg.get("dokumenttyp") or leg.get("doktyp") or "sonstiges",
        "mandant": mandant,
        "datum": leg.get("datum"),
        "frist": leg.get("frist"),
        "lieferant": leg.get("lieferant") or leg.get("absender") or "",
        "ordner_pfad": ordner_pfad,
        "ordner_kategorie": ordner,
        "jahr": jahr,
        "notiz": leg.get("notiz") or "",
        "betrag": leg.get("betrag"),
        "ki_zusammenfassung": leg.get("ki_zusammenfassung") or "",
        "gespeichert_am": leg.get("gespeichert_am") or "",
        "status": leg.get("status") or "gespeichert",
        "geloescht_am": None,
        "pfad": pfad or None,
        "legacy_v1": True,
    }


def _dokument_archiv_liste(store) -> List[Dict[str, Any]]:
    """Neues Archiv (KV-Dict) + ältere Scanner-Liste zusammenführen."""
    archiv = _dokument_archiv_holen(store)
    dokumente: List[Dict[str, Any]] = [dict(v) for v in archiv.values() if isinstance(v, dict)]

    seen_ids = {str(d.get("dok_id") or "") for d in dokumente}
    seen_files = {
        (
            (d.get("dateiname") or "").lower(),
            (d.get("mandant") or "").lower(),
            (d.get("ordner_pfad") or "").lower(),
        )
        for d in dokumente
    }

    legacy = _kv_get(store, "__gescannte_dokumente_v1", [])
    if isinstance(legacy, list):
        for i, leg in enumerate(legacy):
            if not isinstance(leg, dict):
                continue
            mapped = _dokument_legacy_zu_archiv(leg, i)
            sig = (
                (mapped.get("dateiname") or "").lower(),
                (mapped.get("mandant") or "").lower(),
                (mapped.get("ordner_pfad") or "").lower(),
            )
            if mapped.get("dok_id") in seen_ids or sig in seen_files:
                continue
            dokumente.append(mapped)
            seen_ids.add(mapped.get("dok_id") or "")
            seen_files.add(sig)

    return dokumente


def _dokument_archiv_ensure(store, dok_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Lädt Dokument aus Archiv-KV; Legacy-Einträge werden einmalig übernommen."""
    archiv = _dokument_archiv_holen(store)
    if dok_id in archiv:
        return archiv, dict(archiv[dok_id])
    for d in _dokument_archiv_liste(store):
        if str(d.get("dok_id")) == str(dok_id):
            entry = {k: v for k, v in d.items() if k != "legacy_v1"}
            archiv[dok_id] = entry
            _kv_set(store, "__dokument_archiv_v1", archiv)
            return archiv, dict(entry)
    raise HTTPException(404, "Dokument nicht gefunden")


DOKUMENT_SYSTEM_PROMPT = """Du bist ein KI-Assistent für eine deutsche Steuerkanzlei.
Analysiere das Dokument und erkenne alle relevanten Informationen.
Antworte NUR mit validem JSON, ohne Markdown-Backticks:

{
  "dokumenttyp": "eingangsrechnung|ausgangsrechnung|gutschreibung|angebot|lieferschein|quittung|bewirtungsbeleg|reisekosten|kontoauszug|bankbrief|steuerbescheid|ust_bescheid|gewerbesteuer|finanzamt|jahresabschluss|bilanz|vertrag|mietvertrag|vollmacht|gesellschaftsvertrag|handelsregister|kündigung|protokoll|lohnabrechnung|lohnsteuerbescheinigung|rentenbescheid|sozialversicherung|versicherung|mahnung|inkasso|korrespondenz|formular|sonstiges",
  "mandant_hinweis": "Name der Person/Firma die im Dokument erwähnt wird (oder leer)",
  "datum": "YYYY-MM-DD oder leer",
  "frist": "YYYY-MM-DD wenn eine Frist erkennbar ist, sonst leer",
  "lieferant": "Absender/Ersteller des Dokuments",
  "ordner_kategorie": "Rechnungen/Eingang|Rechnungen/Ausgang|Bank/Kontoauszüge|Steuerbescheide/Einkommensteuer|Steuerbescheide/Umsatzsteuer|Steuerbescheide/Gewerbesteuer|Jahresabschlüsse|Lohnbuchhaltung|Verträge|Vollmachten|Immobilien|Sozialversicherung/Rente|Sozialversicherung/Krankenkasse|Versicherungen|Korrespondenz/Finanzamt|Korrespondenz/Mandant|Mahnungen|Formulare|Sonstiges",
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

    def _mandant_aus_hinweis(hinweis: str) -> str:
        h = (hinweis or "").strip()
        if not h or h.lower() in {"unbekannt", "unknown", "—"}:
            return ""
        mandanten_map = store.hole_mandanten() or {}
        if h in mandanten_map:
            return h
        hl = h.lower()
        for name in mandanten_map:
            if name.lower() == hl or hl in name.lower() or name.lower() in hl:
                return name
        return ""

    try:
        parsed = await analyze_document(filename=data.dateiname, b64_content=data.inhalt_b64)
        analyse = {
            "dokumenttyp": parsed.doktyp,
            "mandant_hinweis": (parsed.mandant or data.mandant or "").strip(),
            "datum": parsed.datum,
            "frist": parsed.frist,
            "lieferant": parsed.absender,
            "ordner_kategorie": parsed.ordner or "Sonstiges",
            "zusammenfassung": parsed.ki_zusammenfassung,
            "naechste_schritte": [parsed.aufgabe] if parsed.aufgabe else [],
            "betrag": parsed.betrag,
            "vertrauens_score": parsed.konfidenz,
            "unsichere_felder": parsed.unsichere_felder,
            "aufgabe": parsed.aufgabe,
        }
    except Exception as e:
        log.warning(f"Dokument-KI-Analyse fehlgeschlagen: {e}")
        analyse = {
            "dokumenttyp": "sonstiges",
            "mandant_hinweis": (data.mandant or "").strip(),
            "ordner_kategorie": "Sonstiges",
            "zusammenfassung": f"Automatische Analyse nicht verfügbar ({e}). Bitte Felder manuell ausfüllen.",
            "naechste_schritte": ["Bitte manuell prüfen und kategorisieren"],
            "vertrauens_score": 0.3,
            "unsichere_felder": ["dokumenttyp", "datum", "betrag", "mandant"],
            "betrag": 0.0,
            "datum": "",
            "frist": "",
            "lieferant": "",
            "aufgabe": "",
        }

    mandant_hinweis = (analyse.get("mandant_hinweis") or "").strip()
    mandant = _mandant_aus_hinweis(data.mandant or mandant_hinweis)
    jahr = (analyse.get("datum", "") or "")[:4] or str(datetime.now().year)
    kat = analyse.get("ordner_kategorie", "Sonstiges")
    ordner_pfad_name = mandant or "Ohne-Zuordnung"

    dok_id = str(uuid.uuid4())
    doktyp = analyse.get("dokumenttyp", "sonstiges")
    zusammenfassung = analyse.get("zusammenfassung", "")
    konfidenz = float(analyse.get("vertrauens_score", 0.5) or 0.5)

    result = {
        "dok_id": dok_id,
        "dateiname": data.dateiname,
        "dokumenttyp": doktyp,
        "doktyp": doktyp,
        "mandant": mandant,
        "mandant_hinweis": mandant_hinweis,
        "datum": analyse.get("datum", ""),
        "frist": analyse.get("frist", ""),
        "lieferant": analyse.get("lieferant", ""),
        "absender": analyse.get("lieferant", ""),
        "ordner_kategorie": kat,
        "ordner": kat,
        "ordner_pfad": f"{ordner_pfad_name}/{jahr}/{kat}",
        "jahr": int(jahr) if jahr.isdigit() else datetime.now().year,
        "zusammenfassung": zusammenfassung,
        "ki_zusammenfassung": zusammenfassung,
        "naechste_schritte": analyse.get("naechste_schritte", []),
        "aufgabe": analyse.get("aufgabe", ""),
        "betrag": analyse.get("betrag", 0.0),
        "vertrauens_score": konfidenz,
        "konfidenz": konfidenz,
        "unsichere_felder": analyse.get("unsichere_felder", []),
        "notiz": "",
        "inhalt_b64": data.inhalt_b64,
        "analysiert_am": datetime.now().isoformat(),
        "status": "vorschlag",
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
        "aufgabe":         (data.aufgabe or "").strip(),
        "lieferant":       data.lieferant,
        "ordner_pfad":     data.ordner_pfad,
        "ordner_kategorie":data.ordner_kategorie,
        "jahr":            data.jahr,
        "notiz":           data.notiz,
        "betrag":          data.betrag,
        "ki_zusammenfassung": (data.ki_zusammenfassung or "").strip(),
        "gespeichert_am":  datetime.now().isoformat(),
        "status":          "gespeichert",
        "geloescht_am":    None,
    }
    _kv_set(store, "__dokument_archiv_v1", dokument_archiv)

    # Kommunikations-Eintrag
    store.kommunikation_hinzufuegen(data.mandant, {
        "typ":       "dokument_gespeichert",
        "text":      f"Dokument gespeichert: {data.dateiname} → {data.ordner_pfad}",
        "timestamp": datetime.now().isoformat(),
    })

    # Aufgabe anlegen wenn gewünscht
    if data.aufgabe_anlegen and data.frist and data.mandant:
        _dokument_aufgabe_sync(
            store,
            dokument_archiv[data.dok_id],
            (data.aufgabe or "").strip() or f"Frist aus Dokument: {data.dateiname}",
        )
        _kv_set(store, "__dokument_archiv_v1", dokument_archiv)

    store.log_eintrag(f"DOKUMENT_GESPEICHERT | {data.mandant} | {data.dateiname} | {data.ordner_pfad}")
    return {
        "status": "ok",
        "dok_id": data.dok_id,
        "ordner_pfad": data.ordner_pfad,
        "aufgabe_angelegt": data.aufgabe_anlegen,
    }

@app.get("/dokumente/archiv", tags=["Dokumente"],
         summary="Alle gespeicherten Dokumente (Archiv)")
def dokumente_archiv(
    mandant: Optional[str] = Query(None),
    typ:     Optional[str] = Query(None),
    suche:   Optional[str] = Query(None),
    status:  Optional[str] = Query(
        None,
        description="gespeichert | geloescht | alle (Standard: gespeichert)",
    ),
    _user: dict = Depends(get_current_user),
):
    """Alle gespeicherten Dokumente (neues Archiv + ältere Scanner-Speicherung)."""
    store = get_ds(_user)
    dokumente = _dokument_archiv_liste(store)

    st_filter = (status or "gespeichert").strip().lower()
    if st_filter not in ("alle", "all"):
        dokumente = [
            d for d in dokumente
            if (d.get("status") or "gespeichert") == st_filter
        ]

    if mandant:
        dokumente = [d for d in dokumente if d.get("mandant") == mandant]
    if typ:
        dokumente = [d for d in dokumente if d.get("dokumenttyp") == typ]
    if suche:
        sl = suche.lower()
        dokumente = [
            d for d in dokumente
            if sl in (d.get("dateiname") or "").lower()
            or sl in (d.get("mandant") or "").lower()
            or sl in (d.get("dokumenttyp") or "").lower()
            or sl in (d.get("lieferant") or "").lower()
            or sl in (d.get("ki_zusammenfassung") or "").lower()
            or sl in (d.get("ordner_pfad") or "").lower()
        ]

    dokumente.sort(key=lambda x: x.get("gespeichert_am", ""), reverse=True)
    return {"dokumente": dokumente, "anzahl": len(dokumente)}


@app.get("/dokumente/{dok_id}", tags=["Dokumente"],
         summary="Einzelnes Archiv-Dokument (Metadaten)")
def dokument_archiv_einzel(dok_id: str, _user: dict = Depends(get_current_user)):
    store = get_ds(_user)
    archiv = _dokument_archiv_holen(store)
    if dok_id in archiv:
        dok = dict(archiv[dok_id])
    else:
        dok = next(
            (d for d in _dokument_archiv_liste(store) if str(d.get("dok_id")) == str(dok_id)),
            None,
        )
        if not dok:
            raise HTTPException(404, "Dokument nicht gefunden")
    dok["datei_vorhanden"] = Path(_dokument_datei_pfad(dok)).is_file()
    return dok


@app.get("/dokumente/{dok_id}/datei", tags=["Dokumente"],
         summary="Gespeicherte Datei herunterladen / öffnen")
def dokument_datei_holen(dok_id: str, _user: dict = Depends(get_current_user)):
    from fastapi.responses import FileResponse

    store = get_ds(_user)
    archiv = _dokument_archiv_holen(store)
    if dok_id in archiv:
        dok = archiv[dok_id]
    else:
        dok = next(
            (d for d in _dokument_archiv_liste(store) if str(d.get("dok_id")) == str(dok_id)),
            None,
        )
        if not dok:
            raise HTTPException(404, "Dokument nicht gefunden")
    datei_pfad = _dokument_datei_pfad(dok)
    if not Path(datei_pfad).is_file():
        raise HTTPException(404, "Datei nicht auf dem Server gefunden")

    dateiname = dok.get("dateiname") or "dokument"
    media = _dokument_media_type(dateiname)
    return FileResponse(
        datei_pfad,
        media_type=media,
        headers={
            "Content-Disposition": f'inline; filename="{dateiname}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.put("/dokumente/{dok_id}", tags=["Dokumente"],
         summary="Archiv-Dokument bearbeiten (Metadaten)")
def dokument_archiv_aktualisieren(
    dok_id: str,
    data: DokumentUpdateRequest,
    _user: dict = Depends(get_current_user),
):
    import os as _os
    import shutil as _shutil

    store = get_ds(_user)
    archiv, dok = _dokument_archiv_ensure(store, dok_id)
    if (dok.get("status") or "") == "geloescht":
        raise HTTPException(400, "Im Papierkorb — zuerst wiederherstellen, dann bearbeiten")

    alt_pfad = _dokument_datei_pfad(dok)
    updates = data.model_dump(exclude_unset=True)
    for key, val in updates.items():
        dok[key] = val

    if data.ordner_pfad or data.mandant or data.jahr is not None:
        mand = dok.get("mandant") or "Ohne-Zuordnung"
        jahr = str(dok.get("jahr") or datetime.now().year)
        kat = dok.get("ordner_kategorie") or "Sonstiges"
        if data.ordner_pfad:
            dok["ordner_pfad"] = data.ordner_pfad.strip().replace("\\", "/")
        else:
            dok["ordner_pfad"] = f"{mand}/{jahr}/{kat}"

    neu_pfad = _dokument_datei_pfad(dok)
    if Path(alt_pfad).is_file() and alt_pfad != neu_pfad:
        _os.makedirs(_os.path.dirname(neu_pfad), exist_ok=True)
        try:
            _shutil.move(alt_pfad, neu_pfad)
        except OSError as exc:
            log.warning("Dokument verschieben fehlgeschlagen: %s", exc)

    if data.aufgabe is not None:
        dok["aufgabe"] = (data.aufgabe or "").strip()
    if data.frist is not None:
        dok["frist"] = data.frist
    if data.aufgabe_anlegen and dok.get("mandant") and dok.get("frist"):
        _dokument_aufgabe_sync(store, dok, dok.get("aufgabe") or f"Aufgabe: {dok.get('dateiname')}")

    dok["aktualisiert_am"] = datetime.now().isoformat()
    archiv[dok_id] = dok
    _kv_set(store, "__dokument_archiv_v1", archiv)
    store.log_eintrag(f"DOKUMENT_AKTUALISIERT | {dok.get('mandant')} | {dok.get('dateiname')}")
    return dok


@app.post("/dokumente/archiv/in-papierkorb-alle", tags=["Dokumente"],
          summary="Alle Archiv-Dokumente in den Papierkorb legen")
def dokument_archiv_in_papierkorb_alle(
    mandant: Optional[str] = Query(None, description="Optional nur diesen Mandanten"),
    _user: dict = Depends(get_current_user),
):
    """Alle gespeicherten Archiv-Einträge → Papierkorb (endgültig löschen unter Papierkorb)."""
    store = get_ds(_user)
    archiv = _dokument_archiv_holen(store)
    count = 0
    for dok_id, dok in list(archiv.items()):
        if not isinstance(dok, dict):
            continue
        if (dok.get("status") or "gespeichert") != "gespeichert":
            continue
        if mandant and (dok.get("mandant") or "") != mandant:
            continue
        dok["status"] = "geloescht"
        dok["geloescht_am"] = datetime.now().isoformat()
        archiv[dok_id] = dok
        count += 1
    _kv_set(store, "__dokument_archiv_v1", archiv)
    store.log_eintrag(f"DOKUMENT_ARCHIV_PAPIERKORB_ALLE | {count}")
    return {"status": "ok", "in_papierkorb": count}


@app.post("/dokumente/papierkorb/leeren", tags=["Dokumente"],
          summary="Alle Dokumente im Papierkorb endgültig löschen")
def dokument_papierkorb_leeren(_user: dict = Depends(get_current_user)):
    import os as _os

    store = get_ds(_user)
    archiv = _dokument_archiv_holen(store)
    geloescht_ids = [
        dok_id for dok_id, d in archiv.items()
        if isinstance(d, dict) and (d.get("status") or "") == "geloescht"
    ]
    count = 0
    for dok_id in geloescht_ids:
        dok = archiv.get(dok_id) or {}
        datei_pfad = _dokument_datei_pfad(dok)
        if _os.path.exists(datei_pfad):
            try:
                _os.remove(datei_pfad)
            except OSError as exc:
                log.warning("Papierkorb Datei löschen fehlgeschlagen: %s (%s)", datei_pfad, exc)
        del archiv[dok_id]
        count += 1
    _kv_set(store, "__dokument_archiv_v1", archiv)
    store.log_eintrag(f"DOKUMENT_PAPIERKORB_GELEERT | {count}")
    return {"status": "ok", "geloescht": count}


@app.post("/dokumente/papierkorb/wiederherstellen-alle", tags=["Dokumente"],
          summary="Alle Dokumente aus dem Papierkorb ins Archiv zurückholen")
def dokument_papierkorb_wiederherstellen_alle(_user: dict = Depends(get_current_user)):
    store = get_ds(_user)
    archiv = _dokument_archiv_holen(store)
    count = 0
    for dok_id, dok in list(archiv.items()):
        if not isinstance(dok, dict) or (dok.get("status") or "") != "geloescht":
            continue
        dok["status"] = "gespeichert"
        dok["geloescht_am"] = None
        dok["wiederhergestellt_am"] = datetime.now().isoformat()
        archiv[dok_id] = dok
        count += 1
    _kv_set(store, "__dokument_archiv_v1", archiv)
    store.log_eintrag(f"DOKUMENT_PAPIERKORB_WIEDERHERGESTELLT_ALLE | {count}")
    return {"status": "ok", "wiederhergestellt": count}


@app.delete("/dokumente/{dok_id}", tags=["Dokumente"],
            summary="Dokument in Papierkorb legen oder endgültig löschen")
def dokument_loeschen(
    dok_id: str,
    endgueltig: bool = Query(False, description="True = Datei und Eintrag dauerhaft entfernen"),
    _user: dict = Depends(get_current_user),
):
    store = get_ds(_user)
    archiv, dok = _dokument_archiv_ensure(store, dok_id)
    import os as _os

    if endgueltig or (dok.get("status") or "") == "geloescht":
        datei_pfad = _dokument_datei_pfad(dok)
        if _os.path.exists(datei_pfad):
            try:
                _os.remove(datei_pfad)
            except OSError as exc:
                log.warning("Dokument Datei konnte nicht geloescht werden: %s (%s)", datei_pfad, exc)
        del archiv[dok_id]
        _kv_set(store, "__dokument_archiv_v1", archiv)
        store.log_eintrag(f"DOKUMENT_GELOESCHT | {dok.get('mandant')} | {dok.get('dateiname')}")
        return {"status": "geloescht", "endgueltig": True}

    dok["status"] = "geloescht"
    dok["geloescht_am"] = datetime.now().isoformat()
    archiv[dok_id] = dok
    _kv_set(store, "__dokument_archiv_v1", archiv)
    store.log_eintrag(f"DOKUMENT_PAPIERKORB | {dok.get('mandant')} | {dok.get('dateiname')}")
    return {"status": "geloescht", "endgueltig": False}


@app.post("/dokumente/{dok_id}/wiederherstellen", tags=["Dokumente"],
          summary="Dokument aus Papierkorb wiederherstellen")
def dokument_wiederherstellen(dok_id: str, _user: dict = Depends(get_current_user)):
    store = get_ds(_user)
    archiv, dok = _dokument_archiv_ensure(store, dok_id)
    dok["status"] = "gespeichert"
    dok["geloescht_am"] = None
    dok["wiederhergestellt_am"] = datetime.now().isoformat()
    archiv[dok_id] = dok
    _kv_set(store, "__dokument_archiv_v1", archiv)
    store.log_eintrag(f"DOKUMENT_WIEDERHERGESTELLT | {dok.get('mandant')} | {dok.get('dateiname')}")
    return dok


# ============================================================
# PORTAL INTEGRATION — Haupt-API leitet Portal-Anfragen weiter
# ============================================================

def _portal_dokument_baum(dateien: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ordnerbaum mit Dateien je Knoten (Kanzlei-Dokument-Explorer)."""
    wurzel: Dict[str, Any] = {"ordner": {}, "dateien": []}

    def _node(parts: List[str]) -> Dict[str, Any]:
        cur = wurzel
        acc: List[str] = []
        for part in parts:
            acc.append(part)
            cur = cur["ordner"].setdefault(part, {
                "name": part,
                "typ": "ordner",
                "pfad": "/".join(acc),
                "ordner": {},
                "dateien": [],
            })
        return cur

    for item in dateien:
        pfad = (item.get("ordner_pfad") or item.get("pfad") or "Sonstiges").replace("\\", "/").strip("/")
        parts = [p for p in pfad.split("/") if p] or ["Sonstiges"]
        node = _node(parts)
        node["dateien"].append({
            "id": item.get("id"),
            "quelle": item.get("quelle"),
            "dateiname": item.get("dateiname") or "",
            "dateityp": item.get("dateityp") or "application/pdf",
            "ordner_pfad": node.get("pfad") or pfad,
        })

    def _serialize(node: Dict[str, Any]) -> List[Dict[str, Any]]:
        out = []
        for key in sorted((node.get("ordner") or {}).keys(), key=lambda x: x.lower()):
            ch = node["ordner"][key]
            out.append({
                "name": ch["name"],
                "typ": "ordner",
                "pfad": ch["pfad"],
                "dateien": ch.get("dateien") or [],
                "kinder": _serialize(ch),
            })
        return out

    return _serialize(wurzel)


@app.get("/portal/mandant/{name}/dokument-quellen", tags=["Portal"],
         summary="Dokument-Explorer für Unterschrift (Archiv + Portal-Uploads)")
def portal_mandant_dokument_quellen(name: str, _user: dict = Depends(get_current_user)):
    store = get_ds(_user)
    get_mandant_or_404(name, store, _user)
    dateien: List[Dict[str, Any]] = []

    for d in _dokument_archiv_liste(store):
        if (d.get("mandant") or "").strip() != name:
            continue
        if (d.get("status") or "gespeichert") != "gespeichert":
            continue
        dok_id = str(d.get("dok_id") or "")
        if not dok_id:
            continue
        dateiname = d.get("dateiname") or "dokument"
        dateien.append({
            "id": dok_id,
            "quelle": "archiv",
            "dateiname": dateiname,
            "dateityp": _dokument_media_type(dateiname),
            "ordner_pfad": d.get("ordner_pfad") or f"{name}/{d.get('ordner_kategorie') or 'Sonstiges'}",
            "datei_vorhanden": Path(_dokument_datei_pfad(d)).is_file(),
        })

    for u in store.portal_liste("upload", mandant=name):
        uid = str(u.get("id") or "")
        if not uid:
            continue
        kat = (u.get("kategorie") or "Portal-Uploads").strip()
        dateiname = u.get("original") or u.get("dateiname") or "upload"
        pfad = os.path.join("data", "uploads", name.replace(" ", "_"), u.get("dateiname") or "")
        dateien.append({
            "id": uid,
            "quelle": "upload",
            "dateiname": dateiname,
            "dateityp": _dokument_media_type(dateiname),
            "ordner_pfad": f"{name}/Portal-Uploads/{kat}",
            "datei_vorhanden": Path(pfad).is_file() if pfad else False,
        })

    baum = _portal_dokument_baum(dateien)
    return ok_compat({
        "mandant": name,
        "baum": baum,
        "dateien": dateien,
        "anzahl": len(dateien),
    })


@app.get("/portal/mandant/{name}/dokument-quellen/{quelle}/{item_id}/inhalt", tags=["Portal"],
         summary="Dateiinhalt für Unterschriftsanfrage (Base64)")
def portal_mandant_dokument_quelle_inhalt(
    name: str,
    quelle: str,
    item_id: str,
    _user: dict = Depends(get_current_user),
):
    store = get_ds(_user)
    get_mandant_or_404(name, store, _user)
    quelle = (quelle or "").strip().lower()
    if quelle == "archiv":
        archiv = _dokument_archiv_holen(store)
        dok = archiv.get(item_id)
        if not dok:
            dok = next(
                (d for d in _dokument_archiv_liste(store) if str(d.get("dok_id")) == str(item_id)),
                None,
            )
        if not dok or (dok.get("mandant") or "").strip() != name:
            raise HTTPException(404, "Dokument nicht gefunden")
        datei_pfad = _dokument_datei_pfad(dok)
        if not Path(datei_pfad).is_file():
            raise HTTPException(404, "Datei nicht auf dem Server gefunden")
        with open(datei_pfad, "rb") as f:
            raw = f.read()
        dateiname = dok.get("dateiname") or "dokument.pdf"
        return ok_compat({
            "quelle": "archiv",
            "id": item_id,
            "dateiname": dateiname,
            "dateityp": _dokument_media_type(dateiname),
            "inhalt_b64": base64.b64encode(raw).decode("ascii"),
            "groesse_kb": round(len(raw) / 1024, 1),
        })

    if quelle == "upload":
        u = store.portal_holen("upload", item_id) or {}
        if not u or u.get("mandant") != name:
            raise HTTPException(404, "Upload nicht gefunden")
        datei_pfad = u.get("dateipfad") or ""
        if not datei_pfad or not Path(datei_pfad).is_file():
            raise HTTPException(404, "Datei nicht gefunden")
        with open(datei_pfad, "rb") as f:
            raw = f.read()
        dateiname = u.get("original") or u.get("dateiname") or "upload.pdf"
        return ok_compat({
            "quelle": "upload",
            "id": item_id,
            "dateiname": dateiname,
            "dateityp": _dokument_media_type(dateiname),
            "inhalt_b64": base64.b64encode(raw).decode("ascii"),
            "groesse_kb": round(len(raw) / 1024, 1),
        })

    raise HTTPException(400, "quelle muss archiv oder upload sein")


@app.get("/portal/mandant/{name}/unterschrift/{uid}", tags=["Portal"],
         summary="Unterschrifts-Detail (Kanzlei, inkl. Vorschau-Flags)")
def portal_mandant_unterschrift_detail(
    name: str,
    uid: str,
    _user: dict = Depends(get_current_user),
):
    store = get_ds(_user)
    if not bool(tenant_setting(store, "portal_unterschrift_aktiv")):
        raise HTTPException(503, "Digitale Unterschrift ist deaktiviert")
    get_mandant_or_404(name, store, _user)
    u = store.portal_holen("unterschrift", uid) or {}
    if not u or u.get("mandant") != name:
        raise HTTPException(404, "Unterschrift nicht gefunden")
    return ok_compat({
        "id": uid,
        "mandant": name,
        "dokumentname": u.get("dokumentname"),
        "betreff": u.get("betreff", ""),
        "status": u.get("status"),
        "erstellt_am": u.get("erstellt_am"),
        "unterschrieben_am": u.get("unterschrieben_am"),
        "hat_dokument": bool(u.get("dokument_b64") or u.get("signed_dokument_b64")),
        "hat_unterschrift": bool(u.get("unterschrift_b64")),
        "hat_signed_pdf": bool(u.get("signed_dokument_b64")),
        "signatur_modus": u.get("signatur_modus"),
        "signatur_platzierung": u.get("signatur_platzierung"),
        "audit_trail": u.get("audit_trail") or [],
        "unterzeichner_info": u.get("unterzeichner_info"),
    })


@app.get("/portal/mandant/{name}/unterschrift/{uid}/unterschrift-bild", tags=["Portal"],
         summary="Unterschrifts-Bild (PNG) für Kanzlei")
def portal_mandant_unterschrift_bild(
    name: str,
    uid: str,
    _user: dict = Depends(get_current_user),
):
    store = get_ds(_user)
    if not bool(tenant_setting(store, "portal_unterschrift_aktiv")):
        raise HTTPException(503, "Digitale Unterschrift ist deaktiviert")
    get_mandant_or_404(name, store, _user)
    u = store.portal_holen("unterschrift", uid) or {}
    if not u or u.get("mandant") != name:
        raise HTTPException(404, "Unterschrift nicht gefunden")
    if u.get("status") != "unterschrieben" or not u.get("unterschrift_b64"):
        raise HTTPException(404, "Noch keine Unterschrift vorhanden")
    return ok_compat({
        "unterschrift_b64": u.get("unterschrift_b64"),
        "dokumentname": u.get("dokumentname"),
        "unterschrieben_am": u.get("unterschrieben_am"),
        "signatur_platzierung": u.get("signatur_platzierung"),
    })


@app.get("/portal/mandant/{name}/unterschrift/{uid}/dokument", tags=["Portal"],
         summary="Zu unterzeichnendes / unterschriebenes Dokument (Kanzlei)")
def portal_mandant_unterschrift_dokument(
    name: str,
    uid: str,
    _user: dict = Depends(get_current_user),
):
    store = get_ds(_user)
    if not bool(tenant_setting(store, "portal_unterschrift_aktiv")):
        raise HTTPException(503, "Digitale Unterschrift ist deaktiviert")
    get_mandant_or_404(name, store, _user)
    u = store.portal_holen("unterschrift", uid) or {}
    if not u or u.get("mandant") != name:
        raise HTTPException(404, "Unterschrift nicht gefunden")
    dok_b64 = u.get("signed_dokument_b64") or u.get("dokument_b64") or ""
    if not dok_b64:
        raise HTTPException(404, "Kein Dokument gespeichert")
    dok_typ = u.get("dokumenttyp") or "application/pdf"
    if dok_typ == "pdf":
        dok_typ = "application/pdf"
    return ok_compat({
        "dokument_b64": dok_b64,
        "dokumenttyp": dok_typ,
        "dokumentname": u.get("dokumentname", ""),
        "status": u.get("status"),
        "unterschrift_b64": u.get("unterschrift_b64") if u.get("status") == "unterschrieben" else None,
        "signatur_platzierung": u.get("signatur_platzierung"),
    })


@app.get("/portal/unterschriften/alle", tags=["Portal"],
         summary="Alle Unterschriften-Anfragen (für Kanzlei-Übersicht)")
def portal_unterschriften_alle(
    mandant: Optional[str] = Query(None),
    _user: dict = Depends(get_current_user),
):
    """Kanzlei sieht Status aller Unterschriften direkt im Haupt-System (JWT)."""
    store = get_ds(_user)
    if not bool(tenant_setting(store, "portal_unterschrift_aktiv")):
        raise HTTPException(503, "Digitale Unterschrift ist deaktiviert")

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
        "hat_signed_pdf":    bool(u.get("signed_dokument_b64")),
        "signatur_modus":    u.get("signatur_modus"),
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
    get_mandant_or_404(name, store, _user)
    uploads = [u for u in store.portal_liste("upload") if u.get("mandant") == name]
    signs = [u for u in store.portal_liste("unterschrift") if u.get("mandant") == name]
    bot_fragen = store.bot_fragen_liste()
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
        "portal_link_generieren":    f"POST /portal/admin/token/{name}",
        "portal_aktiv": bool(tenant_setting(store, "portal_aktiv")),
        "portal_unterschrift_aktiv": bool(tenant_setting(store, "portal_unterschrift_aktiv")),
        "portal_upload_max_mb": int(tenant_setting(store, "portal_upload_max_mb", 20) or 20),
        "portal_projektnummer_pflicht": bool(tenant_setting(store, "portal_projektnummer_pflicht")),
    }


class PortalUnterschriftAnfrage(BaseModel):
    dokumentname: str = Field(..., min_length=1, max_length=255)
    dokument_b64: str = Field(..., min_length=10)
    dokumenttyp: str = "application/pdf"
    betreff: str = Field(default="Bitte unterzeichnen", max_length=200)
    hinweis: str = Field(default="", max_length=2000)
    gueltig_tage: int = Field(default=30, ge=1, le=365)
    portal_sichtbar: bool = Field(
        default=True,
        description="False = nur Kanzlei-Suite, nicht im Mandantenportal",
    )


class PortalAntwortBody(BaseModel):
    betreff: str = Field(..., min_length=1, max_length=200)
    text: str = Field(..., min_length=1, max_length=5000)


@app.get("/portal/mandant/{name}/uploads", tags=["Portal"],
         summary="Portal-Uploads eines Mandanten (Kanzlei-Ansicht)")
def portal_mandant_uploads(name: str, _user: dict = Depends(get_current_user)):
    store = get_ds(_user)
    get_mandant_or_404(name, store, _user)
    uploads = sorted(
        store.portal_liste("upload", mandant=name),
        key=lambda x: x.get("hochgeladen_am", ""),
        reverse=True,
    )
    return ok_compat({"mandant": name, "uploads": uploads, "anzahl": len(uploads)})


@app.post("/portal/mandant/{name}/unterschrift-anfragen", tags=["Portal"],
          summary="Unterschrift beim Mandanten anfordern (ohne Admin-Key)")
def portal_mandant_unterschrift_anfragen(
    name: str,
    data: PortalUnterschriftAnfrage,
    _user: dict = Depends(get_current_user),
):
    from portal_api import erstelle_unterschrift_anfrage

    store = get_ds(_user)
    get_mandant_or_404(name, store, _user)
    result = erstelle_unterschrift_anfrage(
        store,
        name,
        data.dokumentname.strip(),
        data.dokument_b64,
        data.dokumenttyp,
        data.betreff,
        data.hinweis,
        data.gueltig_tage,
        portal_sichtbar=bool(data.portal_sichtbar),
    )
    return ok_compat(result)


@app.post("/kommunikation/{name}/portal-antwort", tags=["Kommunikation"],
          summary="Antwort an Mandant (erscheint im Portal)")
def kommunikation_portal_antwort(
    name: str,
    data: PortalAntwortBody,
    _user: dict = Depends(get_current_user),
):
    store = get_ds(_user)
    get_mandant_or_404(name, store, _user)
    text_voll = f"Betreff: {data.betreff.strip()}\n\n{data.text.strip()}"
    from modules import portal_chat as pc

    msg = pc.chat_text_nachricht(store, name, text_voll, "kanzlei")
    store.kommunikation_hinzufuegen(name, {
        "typ": "kanzlei_antwort",
        "text": text_voll,
        "richtung": "ausgehend",
        "timestamp": msg["zeit"],
    })
    store.log_eintrag(f"PORTAL_ANTWORT | {name} | {data.betreff[:50]}")
    return ok_compat({"status": "gesendet", "mandant": name, "nachricht": msg})


class PortalChatText(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)


class PortalChatAufgabe(BaseModel):
    beschreibung: str = Field(..., min_length=1, max_length=500)
    frist: str = Field(..., example="2026-06-30")
    hinweis: str = Field(default="", max_length=2000)
    prioritaet: Optional[str] = "normal"
    portal_sichtbar: bool = Field(default=True, description="Im Mandantenportal sichtbar")


class PortalChatDokument(BaseModel):
    dokument_name: str = Field(..., min_length=2, max_length=200)
    beschreibung: str = Field(default="", max_length=2000)
    frist: Optional[str] = None
    portal_sichtbar: bool = Field(default=True, description="Im Mandantenportal sichtbar")


@app.get("/portal/mandant/chat/unread-summary", tags=["Portal-Chat"],
         summary="Ungelesene Chat-Nachrichten (Kanzlei, alle Mandanten)")
def portal_mandant_chat_unread(_user: dict = Depends(get_current_user)):
    from modules import portal_chat as pc

    store = get_ds(_user)
    summary = pc.total_unread_kanzlei(store)
    return ok_compat(summary)


@app.get("/portal/mandant/chat/inbox", tags=["Portal-Chat"],
         summary="Alle Mandanten-Chats (Übersicht, WhatsApp-Liste)")
def portal_mandant_chat_inbox(_user: dict = Depends(get_current_user)):
    from modules import portal_chat as pc

    store = get_ds(_user)
    namen = sorted((store.hole_mandanten() or {}).keys())
    inbox = pc.list_inbox(store, namen)
    summary = pc.total_unread_kanzlei(store)
    return ok_compat({
        "inbox": inbox,
        "anzahl": len(inbox),
        "ungelesen_gesamt": summary.get("total", 0),
    })


@app.post("/portal/mandant/{name}/chat/read", tags=["Portal-Chat"],
          summary="Chat mit Mandant als gelesen markieren (Kanzlei)")
def portal_mandant_chat_read(
    name: str,
    _user: dict = Depends(get_current_user),
):
    from modules import portal_chat as pc

    store = get_ds(_user)
    get_mandant_or_404(name, store, _user)
    n = pc.mark_chat_gelesen(store, name, "kanzlei")
    return ok_compat({
        "status": "ok",
        "markiert": n,
        "ungelesen": pc.zaehle_ungelesen(store, name, "kanzlei"),
    })


@app.get("/portal/mandant/{name}/chat", tags=["Portal-Chat"],
         summary="Chat-Verlauf mit Mandant (Kanzlei)")
def portal_mandant_chat(
    name: str,
    limit: int = Query(200, ge=1, le=500),
    seit: Optional[str] = Query(None),
    _user: dict = Depends(get_current_user),
):
    from modules import portal_chat as pc

    store = get_ds(_user)
    get_mandant_or_404(name, store, _user)
    pc.mark_chat_gelesen(store, name, "kanzlei")
    nachrichten = pc.list_chat(store, name, limit=limit, seit_id=seit)
    ungelesen = pc.zaehle_ungelesen(store, name, "kanzlei")
    return ok_compat({
        "mandant": name,
        "nachrichten": nachrichten,
        "anzahl": len(nachrichten),
        "ungelesen": ungelesen,
    })


@app.post("/portal/mandant/{name}/chat", tags=["Portal-Chat"],
          summary="Nachricht im Portal-Chat senden")
def portal_mandant_chat_senden(
    name: str,
    data: PortalChatText,
    _user: dict = Depends(get_current_user),
):
    from modules import portal_chat as pc

    store = get_ds(_user)
    get_mandant_or_404(name, store, _user)
    msg = pc.chat_text_nachricht(store, name, data.text.strip(), "kanzlei")
    store.log_eintrag(f"PORTAL_CHAT_KANZLEI | {name}")
    return ok_compat({"status": "gesendet", "nachricht": msg})


class PortalChatBearbeiten(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)


@app.patch("/portal/mandant/{name}/chat/{msg_id}", tags=["Portal-Chat"],
           summary="Eigene Textnachricht bearbeiten (Kanzlei)")
def portal_mandant_chat_bearbeiten(
    name: str,
    msg_id: str,
    data: PortalChatBearbeiten,
    _user: dict = Depends(get_current_user),
):
    from modules import portal_chat as pc

    store = get_ds(_user)
    get_mandant_or_404(name, store, _user)
    try:
        msg = pc.bearbeite_nachricht(store, name, msg_id, data.text.strip(), "kanzlei")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return ok_compat({"status": "bearbeitet", "nachricht": msg})


@app.delete("/portal/mandant/{name}/chat/{msg_id}", tags=["Portal-Chat"],
            summary="Eigene Nachricht löschen (Kanzlei)")
def portal_mandant_chat_loeschen(
    name: str,
    msg_id: str,
    _user: dict = Depends(get_current_user),
):
    from modules import portal_chat as pc

    store = get_ds(_user)
    get_mandant_or_404(name, store, _user)
    try:
        pc.loesche_nachricht(store, name, msg_id, "kanzlei")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return ok_compat({"status": "geloescht"})


@app.post("/portal/mandant/{name}/chat/aufgabe", tags=["Portal-Chat"],
          summary="Aufgabe im Chat an Mandant zuweisen (abhackbar)")
def portal_mandant_chat_aufgabe(
    name: str,
    data: PortalChatAufgabe,
    _user: dict = Depends(get_current_user),
):
    from modules import portal_chat as pc

    store = get_ds(_user)
    get_mandant_or_404(name, store, _user)
    svc = AufgabenService(store)
    sichtbar = bool(data.portal_sichtbar)
    created = svc.create(
        name,
        AufgabeCreate(
            beschreibung=data.beschreibung,
            frist=data.frist,
            prioritaet=data.prioritaet,
            portal_sichtbar=sichtbar,
        ),
        portal_sichtbar=sichtbar,
    )
    aid = created.get("id")
    msg = pc.chat_aufgabe(
        store,
        name,
        aid,
        data.beschreibung,
        data.frist,
        hinweis=data.hinweis.strip(),
        portal_sichtbar=sichtbar,
    )
    return ok_compat({"status": "erstellt", "aufgabe_id": aid, "nachricht": msg})


@app.post("/portal/mandant/{name}/chat/dokument-anfrage", tags=["Portal-Chat"],
          summary="Dokument im Chat anfordern")
def portal_mandant_chat_dokument(
    name: str,
    data: PortalChatDokument,
    _user: dict = Depends(get_current_user),
):
    from modules import portal_chat as pc

    store = get_ds(_user)
    m = get_mandant_or_404(name, store, _user)
    fehlende = list(m.get("fehlende_dokumente_liste") or [])
    if data.dokument_name not in fehlende:
        fehlende.append(data.dokument_name)
        m["fehlende_dokumente_liste"] = fehlende
        store.mandant_speichern(name, m)
    msg = pc.chat_dokument_anfrage(
        store,
        name,
        data.dokument_name,
        data.beschreibung,
        data.frist or "",
        portal_sichtbar=bool(data.portal_sichtbar),
    )
    store.log_eintrag(f"PORTAL_CHAT_DOK | {name} | {data.dokument_name}")
    return ok_compat({"status": "angefordert", "nachricht": msg})


@app.post("/portal/mandant/{name}/chat/unterschrift", tags=["Portal-Chat"],
          summary="Unterschrift im Chat anfordern")
def portal_mandant_chat_unterschrift(
    name: str,
    data: PortalUnterschriftAnfrage,
    _user: dict = Depends(get_current_user),
):
    from portal_api import erstelle_unterschrift_anfrage
    from modules import portal_chat as pc

    store = get_ds(_user)
    get_mandant_or_404(name, store, _user)
    result = erstelle_unterschrift_anfrage(
        store,
        name,
        data.dokumentname.strip(),
        data.dokument_b64,
        data.dokumenttyp,
        data.betreff,
        data.hinweis,
        data.gueltig_tage,
        portal_sichtbar=bool(data.portal_sichtbar),
    )
    return ok_compat(result)


class PortalChatUpload(BaseModel):
    dateiname: str = Field(..., min_length=1, max_length=255)
    inhalt_b64: str = Field(..., min_length=8)
    dateityp: str = Field(default="application/pdf")
    beschreibung: str = Field(default="", max_length=2000)
    kategorie: str = Field(default="Sonstiges", max_length=80)
    portal_sichtbar: bool = Field(
        default=True,
        description="Im Mandantenportal für den Mandanten sichtbar",
    )


@app.post("/portal/mandant/{name}/chat/dokument-anfrage/{msg_id}/hochladen", tags=["Portal-Chat"],
          summary="Angefordertes Dokument im Chat hochladen (Kanzlei-Test)")
def portal_mandant_chat_dok_upload(
    name: str,
    msg_id: str,
    data: PortalChatUpload,
    _user: dict = Depends(get_current_user),
):
    from portal_api import DokumentUpload, _verarbeite_upload

    store = get_ds(_user)
    get_mandant_or_404(name, store, _user)
    result = _verarbeite_upload(
        name,
        DokumentUpload(
            dateiname=data.dateiname.strip(),
            dateityp=data.dateityp or "application/octet-stream",
            inhalt_b64=data.inhalt_b64,
            beschreibung=data.beschreibung or "",
            kategorie=data.kategorie or "Sonstiges",
        ),
        upload_von="kanzlei",
        portal_sichtbar=bool(data.portal_sichtbar),
        chat_msg_id=msg_id,
    )
    return ok_compat(result)


@app.post("/portal/mandant/{name}/chat/upload", tags=["Portal-Chat"],
          summary="Dokument für Mandant im Chat bereitstellen (Kanzlei)")
def portal_mandant_chat_upload(
    name: str,
    data: PortalChatUpload,
    _user: dict = Depends(get_current_user),
):
    from portal_api import DokumentUpload, _verarbeite_upload

    store = get_ds(_user)
    get_mandant_or_404(name, store, _user)
    result = _verarbeite_upload(
        name,
        DokumentUpload(
            dateiname=data.dateiname.strip(),
            dateityp=data.dateityp or "application/pdf",
            inhalt_b64=data.inhalt_b64,
            beschreibung=data.beschreibung or "",
            kategorie=data.kategorie or "Sonstiges",
        ),
        upload_von="kanzlei",
        portal_sichtbar=bool(data.portal_sichtbar),
    )
    store.log_eintrag(
        f"PORTAL_CHAT_UPLOAD_KANZLEI | {name} | {data.dateiname[:80]} | sichtbar={data.portal_sichtbar}"
    )
    return ok_compat(result)


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
    get_mandant_or_404(data.mandant, store, _user)
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
def bot_analyse(_user: dict = Depends(get_current_user)):
    """Analysiert alle Mandanten und legt fehlende Bot-Fragen an."""
    store = get_ds(_user)
    try:
        bot = _get_bot(store)
        fragen, pruefung = bot.analysiere_alle_mandanten()
        log.info(f"Bot-Analyse: {len(fragen)} neue Fragen")
        if fragen:
            try:
                from core.bot_notifications import notify_kanzlei_bot_analyse

                notify_kanzlei_bot_analyse(store, fragen)
            except Exception as mail_e:
                log.warning("Bot-Analyse Kanzlei-Mail: %s", mail_e)
        return ok_compat({
            "status":       "fertig",
            "neue_fragen":  len(fragen),
            "fragen":       fragen[:50],
            "pruefung":     pruefung,
            "timestamp":    datetime.now().isoformat(),
        })
    except Exception as e:
        log.error(f"Bot-Analyse Fehler: {e}", exc_info=True)
        msg = str(e).strip() or "Bot-Analyse fehlgeschlagen"
        raise HTTPException(status_code=500, detail=msg)

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
    get_mandant_or_404(mandant, store, _user)
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
    get_mandant_or_404(mandant, store, _user)
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
    mandanten:     Optional[List[str]] = None
    sozialversicherung: bool = True


class LohnMitarbeiterUpdate(BaseModel):
    mandant:       Optional[str] = None
    name:          Optional[str] = None
    brutto_monat:  Optional[float] = None
    steuer_klasse: Optional[int] = None
    urlaubstage:   Optional[int] = None
    wochenstunden: Optional[float] = None
    steuer_id:     Optional[str] = None
    sv_nr:         Optional[str] = None
    iban:          Optional[str] = None
    eintritt:      Optional[str] = None
    mandanten:     Optional[List[str]] = None
    sozialversicherung: Optional[bool] = None
    aktiv:         Optional[bool] = None

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
    get_mandant_or_404(data.mandant, store, _user)
    return _get_lohn(store).mitarbeiter_anlegen(**data.dict())

@app.get("/lohn/mitarbeiter", tags=["Lohn"], summary="Alle Mitarbeiter")
def lohn_mitarbeiter_liste(mandant: Optional[str] = Query(None),
    _user: dict = Depends(get_current_user)):
    return {"mitarbeiter": _get_lohn(get_ds(_user)).mitarbeiter_liste(mandant)}


@app.get("/lohn/mitarbeiter/{ma_id}", tags=["Lohn"], summary="Mitarbeiter-Details")
def lohn_mitarbeiter_detail(ma_id: str, _user: dict = Depends(get_current_user)):
    try:
        return _get_lohn(get_ds(_user)).mitarbeiter_holen(ma_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.patch("/lohn/mitarbeiter/{ma_id}", tags=["Lohn"], summary="Mitarbeiter bearbeiten")
def lohn_mitarbeiter_update(
    ma_id: str,
    data: LohnMitarbeiterUpdate,
    _user: dict = Depends(get_current_user),
):
    store = get_ds(_user)
    patch = data.dict(exclude_unset=True)
    if patch.get("mandant"):
        get_mandant_or_404(patch["mandant"], store, _user)
    if patch.get("mandanten"):
        for m in patch["mandanten"]:
            get_mandant_or_404(m, store, _user)
    try:
        return _get_lohn(store).mitarbeiter_aktualisieren(ma_id, **patch)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/lohn/mitarbeiter/{ma_id}", tags=["Lohn"], summary="Mitarbeiter löschen (deaktivieren)")
def lohn_mitarbeiter_loeschen(
    ma_id: str,
    endgueltig: bool = Query(False, description="Statt Deaktivierung komplett aus Daten entfernen"),
    _user: dict = Depends(get_current_user),
):
    try:
        _get_lohn(get_ds(_user)).mitarbeiter_loeschen(ma_id, endgueltig=endgueltig)
        return ok_compat({"status": "geloescht", "endgueltig": endgueltig})
    except ValueError as e:
        raise HTTPException(404, str(e))

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
    get_mandant_or_404(mandant, store, _user)
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
def regeln_ausfuehren(_user: dict = Depends(get_current_user)):
    store = get_ds(_user)
    try:
        result = _get_builder(store).fuehre_alle_aus()
        log.info(f"Workflow-Batch: {result}")
        return ok_compat({"status": "fertig", **result})
    except Exception as e:
        log.error(f"Workflow-Batch Fehler: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

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
    get_mandant_or_404(data.mandant, store, _user)
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
    get_mandant_or_404(mandant, store, _user)
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
         summary="Steuerfälle (pool=aktiv|historie|alle)")
def steuer_faelle_liste(
    mandant: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    pool: Optional[str] = Query(
        None,
        description="aktiv = nicht in Historie; historie = archiviert/freigegeben mit TTL; alle = komplett",
    ),
    _user: dict = Depends(get_current_user),
):
    from core.autonomer_steuerfall import AutononerSteuerfall
    ds = get_ds(_user)
    p = (pool or "").strip().lower() or None
    if p and p not in ("aktiv", "historie", "alle"):
        p = None
    ap = AutononerSteuerfall(ds)
    faelle = ap.faelle_laden(mandant, status, p)
    if p == "historie":
        from core.kanzlei_historie import historie_steuerfaelle_tage
        return {"faelle": faelle, "historie_ttl_tage": historie_steuerfaelle_tage(ds)}
    return {"faelle": faelle}


@app.post("/steuer/{fall_id}/historie", tags=["Steuer-Autopilot"],
          summary="Steuerfall manuell in die Historie legen")
def steuer_fall_historie(fall_id: str, _user: dict = Depends(get_current_user)):
    from core.autonomer_steuerfall import AutononerSteuerfall
    try:
        return AutononerSteuerfall(get_ds(_user)).fall_nach_historie(fall_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.post("/steuer/{fall_id}/wiederherstellen", tags=["Steuer-Autopilot"],
          summary="Steuerfall aus der Historie zurück in die Bearbeitung")
def steuer_fall_wiederherstellen(fall_id: str, _user: dict = Depends(get_current_user)):
    from core.autonomer_steuerfall import AutononerSteuerfall
    try:
        return AutononerSteuerfall(get_ds(_user)).fall_aus_historie(fall_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.delete("/steuer/{fall_id}", tags=["Steuer-Autopilot"],
            summary="Steuerfall endgültig löschen")
def steuer_fall_loeschen(fall_id: str, _user: dict = Depends(get_current_user)):
    from core.autonomer_steuerfall import AutononerSteuerfall
    try:
        return AutononerSteuerfall(get_ds(_user)).fall_loeschen(fall_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))

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
    get_mandant_or_404(data.mandant, store, _user)
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


# ── Strukturierte Admin-Pfade: /api/admin/* (Aliase zu /saas/*) ─
from fastapi import APIRouter as _APIRouterAdminAlias

_api_admin_alias = _APIRouterAdminAlias(prefix="/api/admin", tags=["Admin"])


@_api_admin_alias.post("/apikeys")
def api_admin_apikeys_create(
    data: ApiKeyCreateRequest,
    _user: dict = Depends(require_permission("settings:write")),
):
    return saas_api_key_create(data, _user)


@_api_admin_alias.get("/apikeys")
def api_admin_apikeys_list(_user: dict = Depends(require_permission("settings:read"))):
    return saas_api_keys(_user)


@_api_admin_alias.delete("/apikeys/{key_id}")
def api_admin_apikeys_delete(
    key_id: str,
    _user: dict = Depends(require_permission("settings:write")),
):
    return saas_api_key_delete(key_id, _user)


@_api_admin_alias.post("/apikeys/{key_id}/rotate")
def api_admin_apikeys_rotate(
    key_id: str,
    data: ApiKeyRotateRequest = Body(default=ApiKeyRotateRequest()),
    _user: dict = Depends(require_permission("settings:write")),
):
    return saas_api_key_rotate(key_id, data, _user)


@_api_admin_alias.post("/webhooks")
def api_admin_webhooks_create(
    data: WebhookCreateRequest,
    _user: dict = Depends(require_permission("settings:write")),
):
    return saas_webhook_create(data, _user)


@_api_admin_alias.get("/webhooks")
def api_admin_webhooks_list(_user: dict = Depends(require_permission("settings:read"))):
    return saas_webhook_list(_user)


@_api_admin_alias.delete("/webhooks/{webhook_id}")
def api_admin_webhooks_delete(
    webhook_id: str,
    _user: dict = Depends(require_permission("settings:write")),
):
    return saas_webhook_delete(webhook_id, _user)


@_api_admin_alias.post("/webhooks/{webhook_id}/test")
def api_admin_webhooks_test(
    webhook_id: str,
    _user: dict = Depends(require_permission("settings:write")),
):
    return saas_webhook_test(webhook_id, _user)


@_api_admin_alias.get("/readiness")
def api_admin_readiness(_user: dict = Depends(require_permission("reports:read"))):
    return saas_readiness(_user)


@_api_admin_alias.post("/tenant", status_code=201)
def api_admin_tenant_create(data: TenantCreate, _m: bool = Depends(require_saas_master)):
    return tenant_erstellen(data, _m)


@_api_admin_alias.get("/tenants")
def api_admin_tenants_list(_m: bool = Depends(require_saas_master)):
    return tenants_liste(_m)


@_api_admin_alias.get("/statistiken")
def api_admin_statistiken(_m: bool = Depends(require_saas_master)):
    return saas_statistiken(_m)


@_api_admin_alias.put("/tenant/{tenant_id}")
def api_admin_tenant_put(
    tenant_id: str,
    updates: Dict = Body(...),
    _m: bool = Depends(require_saas_master),
):
    return tenant_update(tenant_id, updates, _m)


@_api_admin_alias.post("/tenant/{tenant_id}/sperren")
def api_admin_tenant_sperren(
    tenant_id: str,
    grund: str = Query(""),
    _m: bool = Depends(require_saas_master),
):
    return tenant_sperren(tenant_id, grund, _m)


@_api_admin_alias.post("/tenant/{tenant_id}/api-key-erneuern")
def api_admin_tenant_api_key_erneuern(
    tenant_id: str,
    _m: bool = Depends(require_saas_master),
):
    return api_key_erneuern(tenant_id, _m)


@_api_admin_alias.get("/plaene")
def api_admin_plaene(_m: bool = Depends(require_saas_master)):
    return saas_plaene(_m)


app.include_router(_api_admin_alias)


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
    from backend.auth import verifiziere_session, hat_irgendein_benutzer
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

                bot_fragen = store.bot_fragen_liste()
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


# ── Ein Prozess: Mandantenportal-Routen auf dieselbe App ─────
try:
    from portal_api import register_portal_with_app

    register_portal_with_app(app)
except Exception as _portal_err:
    log.warning("Portal-Router konnte nicht registriert werden: %s", _portal_err)

# ── Optional: schrittweise Split-Router aktivieren (opt-in per ENV) ──
try:
    from backend.routes import mount_split_routers

    mount_split_routers(app)
except Exception as _split_err:
    log.warning("Split-Router konnten nicht registriert werden: %s", _split_err)


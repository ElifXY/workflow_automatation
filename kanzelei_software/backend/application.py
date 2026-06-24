"""
Zentrale FastAPI-Instanz: Erzeugung, globale Middleware, Exception-Handler.

Routen werden nach dem Anlegen von ``app`` über ``import api`` registriert
(``api.py`` importiert ``app`` von hier — keine zweite ``FastAPI()``-Instanz).

HTTP-Server (Produktion/Docker): ``uvicorn backend.api:app`` oder ``uvicorn backend.application:app``
(beides identisch). Das Projekt-``main.py`` im Root ist **nur** die CLI-Oberfläche, kein Uvicorn-Einstieg.

    uvicorn backend.application:app
    uvicorn backend.api:app
"""
from __future__ import annotations

import hmac
import logging
import os
import sys

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

load_dotenv()

_log_dir = (os.getenv("API_LOG_DIR") or "data").strip() or "data"
os.makedirs("data", exist_ok=True)
os.makedirs(_log_dir, exist_ok=True)
_log_path = os.path.join(_log_dir, "api.log")

_log_handlers: list[logging.Handler] = [logging.StreamHandler()]
try:
    _log_handlers.append(logging.FileHandler(_log_path, encoding="utf-8"))
except OSError as e:
    # Docker: ./logs/api auf dem Host oft root — User kanzlei (UID 1000) kann nicht schreiben.
    sys.stderr.write(f"[kanzlei_api] WARN: Datei-Log {_log_path} nicht nutzbar ({e}); nur stdout.\n")

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=_log_handlers,
)
log = logging.getLogger("kanzlei_api")

app = FastAPI(
    title="Kanzlei Automation — API v3.0",
    description="Vollautomatisches Kanzlei-Management",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

_is_production_api = (os.getenv("ENVIRONMENT") or os.getenv("APP_ENV") or "").lower() == "production"

# Globale Exception-Handler: in ``api.py`` registriert (überschreiben ggf. Defaults).

app.add_middleware(GZipMiddleware, minimum_size=1000)
_origins_env = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:80,http://127.0.0.1:80,"
    "https://kanzlei-automation.com,https://www.kanzlei-automation.com",
)
_cors_origins = [o.strip() for o in _origins_env.split(",") if o.strip()]
_domain = (os.getenv("DOMAIN") or "").strip()
if _domain:
    for _o in (
        f"https://{_domain}",
        f"https://www.{_domain}",
        f"http://{_domain}",
        f"http://www.{_domain}",
    ):
        if _o not in _cors_origins:
            _cors_origins.append(_o)
    _front = [f"https://{_domain}", f"https://www.{_domain}"]
    _tail = [o for o in _cors_origins if o not in _front]
    _cors_origins = [u for u in _front if u in _cors_origins] + _tail
_cors_creds = "*" not in _cors_origins and not (
    len(_cors_origins) == 1 and _cors_origins[0] == "*"
)
_portal_cors_extra = (os.getenv("PORTAL_ALLOWED_ORIGINS") or "").strip()
if _portal_cors_extra:
    for _po in [x.strip() for x in _portal_cors_extra.split(",") if x.strip()]:
        if _po not in _cors_origins:
            _cors_origins.append(_po)
_cors_strict_prod = (os.getenv("CORS_STRICT_PRODUCTION") or "").strip().lower() in (
    "1",
    "true",
    "yes",
)
if _is_production_api and _cors_strict_prod:
    _primary_origin = (os.getenv("CORS_PRIMARY_ORIGIN") or "").strip() or (
        f"https://{(os.getenv('DOMAIN') or 'kanzlei-automation.com').strip()}"
    )
    _cors_origins = [_primary_origin]
    _cors_creds = True
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins if _cors_origins else ["http://localhost:3000"],
    allow_credentials=_cors_creds,
    allow_methods=["*"],
    allow_headers=["*"],
)

_API_GATEWAY_KEY = (os.getenv("API_GATEWAY_KEY") or "").strip()
_API_GATEWAY_EXEMPT_PREFIXES = (
    "/docs",
    "/redoc",
    "/openapi.json",
    "/auth/",
    "/api/auth/",
    # Mandantenportal: eigene Auth (Login-Token, Portal-Bearer); nicht Kanzlei-JWT/Gateway
    "/portal",
)
_API_GATEWAY_EXACT = frozenset(
    {
        "/",
        "/health",
        "/ready",
        "/api/health",
        "/api/ready",
        "/api/v1/health",
        "/api/v1/meta",
        "/api/v1/introduction",
        "/api/v1/webhooks/verify-example",
        "/billing/stripe/webhook",
        "/billing/stripe/config",
        "/system/build",
        "/api/system/build",
        # E-Mail-Login (öffentlich wie /auth/login) — sonst 403 hinter API_GATEWAY_KEY
        "/login",
        "/api/login",
        "/register",
        "/api/register",
    }
)


def _gateway_bearer_ok(token: str) -> bool:
    if not token:
        return False
    from backend.auth import jwt_secret, verifiziere_session, verify_access_token

    if verifiziere_session(token):
        return True
    if jwt_secret():
        claims = verify_access_token(token)
        if claims and claims.get("typ") == "access" and claims.get("sub"):
            return True
    return False


@app.middleware("http")
async def optional_api_gateway(request: Request, call_next):
    """Wenn API_GATEWAY_KEY gesetzt: Session- oder JWT-Bearer oder X-Api-Gateway-Key."""
    if not _API_GATEWAY_KEY:
        return await call_next(request)
    if request.method == "OPTIONS":
        return await call_next(request)
    path = request.url.path
    if path in _API_GATEWAY_EXACT:
        return await call_next(request)
    if any(path.startswith(p) for p in _API_GATEWAY_EXEMPT_PREFIXES):
        return await call_next(request)
    hdr = request.headers.get("X-Api-Gateway-Key") or ""
    if len(hdr) == len(_API_GATEWAY_KEY) and hmac.compare_digest(
        hdr.encode("utf-8"), _API_GATEWAY_KEY.encode("utf-8")
    ):
        return await call_next(request)
    auth = request.headers.get("Authorization") or ""
    if auth.startswith("Bearer "):
        token = auth.removeprefix("Bearer ").strip()
        if _gateway_bearer_ok(token):
            return await call_next(request)
    return JSONResponse(
        status_code=403,
        content={
            "ok": False,
            "detail": "Zugriff verweigert — gültige Session/JWT (Bearer) oder X-Api-Gateway-Key erforderlich",
        },
    )


# Pfade, die im Backend bewusst mit /api/… registriert sind (nicht auf /… kürzen).
_NATIVE_API_PREFIX_PATHS = frozenset(
    {
        "/api/health",
        "/api/ready",
    }
)


@app.middleware("http")
async def strip_public_api_prefix(request: Request, call_next):
    """
    SPA nutzt REACT_APP_API_URL=/api; Monolith-Routen: /mandanten, /ki/chat, /kpis, …

    Nginx soll ``/api/`` entfernen. Wenn der Upstream ``/api/mandanten`` durchreicht,
    hier auf ``/mandanten`` normalisieren. ``/api/v1/*`` und native Aliase bleiben.
    """
    path = request.scope.get("path") or request.url.path
    if path == "/api" or path.startswith("/api/"):
        if path.startswith("/api/v1/") or path in _NATIVE_API_PREFIX_PATHS:
            return await call_next(request)
        rest = path[4:] if len(path) > 4 else "/"
        if not rest.startswith("/"):
            rest = "/" + rest
        request.scope["path"] = rest
    return await call_next(request)


import api as _api_routes  # noqa: E402,F401 — registriert alle Routen auf ``app``

__all__ = ["app", "log", "_is_production_api"]

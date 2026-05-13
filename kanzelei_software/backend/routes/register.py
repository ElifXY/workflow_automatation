"""
Sammelpunkt für schrittweise Router-Auslagerung aus ``api.py``.

Migration-Strategie:
- Legacy-Route-Registrierungen (monolithisch) entfernen
- dieselben Pfade über modulare Router wieder einhängen
- Business-Logik bleibt zunächst unverändert in ``api.py``
"""
from __future__ import annotations

import logging
import os
from typing import Iterable, Tuple

from fastapi import FastAPI

log = logging.getLogger("kanzlei_api")

RouteSpec = Tuple[str, str]


def _drop_legacy_routes(app: FastAPI, specs: Iterable[RouteSpec]) -> int:
    wanted = {(m.upper(), p) for (m, p) in specs}
    kept = []
    removed = 0
    for route in app.router.routes:
        methods = set(getattr(route, "methods", []) or [])
        path = getattr(route, "path", None)
        if path and any((m.upper(), path) in wanted for m in methods):
            removed += 1
            continue
        kept.append(route)
    app.router.routes = kept
    return removed


def mount_split_routers(app: FastAPI) -> None:
    """
    Registriert ausgelagerte Routenmodule.

    Standardmäßig aktiv. Deaktivieren via ``ENABLE_SPLIT_ROUTES=0``.
    """
    flag = (os.getenv("ENABLE_SPLIT_ROUTES", "1") or "").strip().lower()
    if flag in {"0", "false", "no"}:
        return

    auth_specs = [
        ("POST", "/auth/login"),
        ("POST", "/login"),
        ("POST", "/api/login"),
        ("GET", "/me"),
        ("GET", "/api/me"),
        ("POST", "/register"),
        ("POST", "/api/register"),
        ("POST", "/auth/logout"),
        ("POST", "/auth/refresh"),
        ("POST", "/auth/registrieren"),
        ("GET", "/auth/me"),
        ("GET", "/auth/benutzer"),
        ("PUT", "/auth/passwort"),
        ("GET", "/auth/setup-status"),
    ]
    try:
        from backend.routes.auth_router import router as auth_router

        removed = _drop_legacy_routes(app, auth_specs)
        app.include_router(auth_router)
        log.info("Split routes aktiviert: auth_router (legacy removed=%s)", removed)
    except Exception as exc:
        log.warning("Split routes konnten nicht gemountet werden (auth_router): %s", exc)

    mandanten_specs = [
        ("GET", "/mandanten"),
        ("GET", "/mandanten/{name}"),
        ("POST", "/mandanten"),
        ("PUT", "/mandanten/{name}"),
        ("DELETE", "/mandanten/{name}"),
        ("POST", "/mandanten/{name}/antwort"),
        ("GET", "/mandanten/{name}/aufgaben"),
        ("POST", "/mandanten/{name}/aufgaben"),
        ("POST", "/mandanten/{name}/aufgaben/bulk"),
        ("POST", "/aufgaben/{aufgabe_id}/erledigen"),
        ("DELETE", "/aufgaben/{aufgabe_id}"),
        ("GET", "/mandanten/{name}/dokumente"),
        ("POST", "/mandanten/{name}/dokumente/anfordern"),
        ("POST", "/mandanten/{name}/dokumente/erhalten"),
        ("POST", "/mandanten/{name}/simulation"),
        ("GET", "/mandanten/{name}/report"),
    ]
    try:
        from backend.routes.mandanten_router import router as mandanten_router

        removed = _drop_legacy_routes(app, mandanten_specs)
        app.include_router(mandanten_router)
        log.info("Split routes aktiviert: mandanten_router (legacy removed=%s)", removed)
    except Exception as exc:
        log.warning("Split routes konnten nicht gemountet werden (mandanten_router): %s", exc)

    billing_specs = [
        ("GET", "/billing/usage"),
        ("GET", "/billing/stripe/config"),
        ("POST", "/billing/stripe/checkout-session"),
        ("POST", "/billing/stripe/portal-session"),
        ("POST", "/billing/stripe/webhook"),
    ]
    try:
        from backend.routes.billing_router import router as billing_router

        removed = _drop_legacy_routes(app, billing_specs)
        app.include_router(billing_router)
        log.info("Split routes aktiviert: billing_router (legacy removed=%s)", removed)
    except Exception as exc:
        log.warning("Split routes konnten nicht gemountet werden (billing_router): %s", exc)

    system_specs = [
        ("GET", "/health"),
        ("GET", "/api/health"),
        ("GET", "/ready"),
        ("GET", "/api/ready"),
        ("GET", "/api/v1/meta"),
        ("GET", "/api/v1/health"),
        ("GET", "/compliance/status"),
        ("GET", "/saas/readiness"),
    ]
    try:
        from backend.routes.system_router import router as system_router

        removed = _drop_legacy_routes(app, system_specs)
        app.include_router(system_router)
        log.info("Split routes aktiviert: system_router (legacy removed=%s)", removed)
    except Exception as exc:
        log.warning("Split routes konnten nicht gemountet werden (system_router): %s", exc)

    ai_specs = [
        ("POST", "/ki/chat"),
        ("GET", "/ki/status"),
        ("GET", "/ki/mandant-analyse/{name}"),
        ("GET", "/ki/kanzlei-zusammenfassung"),
    ]
    try:
        from backend.routes.ai_router import router as ai_router

        removed = _drop_legacy_routes(app, ai_specs)
        app.include_router(ai_router)
        log.info("Split routes aktiviert: ai_router (legacy removed=%s)", removed)
    except Exception as exc:
        log.warning("Split routes konnten nicht gemountet werden (ai_router): %s", exc)

    automation_specs = [
        ("POST", "/workflow/monatsabschluss/{name}"),
        ("POST", "/workflow/jahresabschluss/{name}"),
        ("POST", "/workflow/onboarding/{name}"),
        ("POST", "/bot/frage"),
        ("POST", "/bot/frage/{frage_id}/antwort"),
        ("GET", "/bot/fragen"),
        ("GET", "/bot/fragen/{mandant}"),
        ("POST", "/bot/analyse"),
        ("GET", "/bot/statistiken"),
        ("POST", "/ml/kategorisieren"),
        ("POST", "/ml/feedback"),
        ("GET", "/ml/statistiken"),
        ("GET", "/ml/lieferanten"),
    ]
    try:
        from backend.routes.automation_router import router as automation_router

        removed = _drop_legacy_routes(app, automation_specs)
        app.include_router(automation_router)
        log.info("Split routes aktiviert: automation_router (legacy removed=%s)", removed)
    except Exception as exc:
        log.warning("Split routes konnten nicht gemountet werden (automation_router): %s", exc)

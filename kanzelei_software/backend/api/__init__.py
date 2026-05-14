"""
Kanonischer Uvicorn-Einstieg: ``app`` (eine FastAPI-Instanz).

**Uvicorn**

    uvicorn backend.api:app --host 0.0.0.0 --port 8000

**Checkliste (Umsetzungsstand)**

1. **Ein HTTP-Entrypoint:** Eine ``app``-Instanz in ``backend.application`` (exportiert als
   ``backend.api:app``); Routen in Root-``api.py``. Root-``main.py`` ist nur die CLI, kein Uvicorn-Ziel.
   Mandantenportal per ``register_portal_with_app``. Kein zweiter Uvicorn-Prozess für Portal.
2. **DB:** Auth + Tenant + (optional) Mandanten auf PostgreSQL bei ``DATABASE_URL=postgresql://…``.
   In Production mit PostgreSQL-DSN ist ``get_connection`` (SQLite) ohne ``ALLOW_SQLITE_FALLBACK=1`` gesperrt;
   ``POSTGRES_ONLY_DATA=1`` bleibt der härteste Schalter. Bei Postgres-DSN liegen API-Keys, Webhooks,
   Outbox, Usage und ``agent_actions`` in PostgreSQL (nicht mehr über SQLite).
3. **User-Modelle:** ``backend.models.user.UserRead`` (API) + optional SQLAlchemy ``backend.db.sqlalchemy_models.User`` (Tabelle ``users``; ``tenant_id`` = Mandanten-String wie ``kanzlei_id``).
4. **Auth:** öffentlicher Einstieg ``backend.auth`` (intern ``core.auth`` + ``core.auth_postgres``).
5. **``get_current_user``:** ``backend.deps.get_current_user``.
6. **Routen:** ``/api/auth/*``, ``/api/users/*``, ``/api/data/*``, ``/api/admin/*`` (SaaS-Aliase).
7. **CORS:** Middleware in ``backend.application``; ``CORS_STRICT_PRODUCTION=1`` + optional ``CORS_PRIMARY_ORIGIN``
   (sonst ``https://$DOMAIN``) in Production.
8. **Passwörter:** bcrypt über ``backend.auth`` (kein Klartext-Speicher).
9. **JWT-ENV:** ``JWT_SECRET``, …; Login liefert optional ``access_token``; ``get_current_user``
   akzeptiert Session- oder JWT-Bearer (siehe ``backend.deps``).
10. **Fehler:** globale Handler in ``api.py`` (Production ohne Stacktrace-Body).

Refresh-Tokens: ``core.jwt_tokens``; Login-Rate-Limit via ``backend.auth``.
"""
from __future__ import annotations

import os
import sys

from fastapi import FastAPI

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.application import app  # noqa: E402,F401

assert isinstance(app, FastAPI)

__all__ = ["app"]

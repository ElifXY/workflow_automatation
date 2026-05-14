"""
Gemeinsame PostgreSQL-Verbindung (Thread-lokal) für Auth, TenantManager u. a.

Eine Verbindung pro Thread — dieselbe DATABASE_URL wie überall.
"""
from __future__ import annotations

import os
import threading
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

_local = threading.local()


def pg_primary_db() -> bool:
    """True, wenn DATABASE_URL auf PostgreSQL zeigt (Kern-Tabellen dort).

    Akzeptiert sowohl ``postgresql://`` als auch das gängige Alias ``postgres://``
    (z. B. aus Tools, Kubernetes-Secrets, älteren Compose-Snippets).
    """
    d = (os.getenv("DATABASE_URL") or "").strip().lower()
    return d.startswith("postgresql://") or d.startswith("postgres://")


def get_pg_connection() -> Any:
    """Thread-lokale psycopg2-Verbindung mit RealDictCursor."""
    if not hasattr(_local, "conn") or _local.conn is None:
        dsn = (os.getenv("DATABASE_URL") or "").strip()
        dl = dsn.lower()
        if not (dl.startswith("postgresql://") or dl.startswith("postgres://")):
            raise RuntimeError(
                "get_pg_connection: DATABASE_URL muss postgresql://… oder postgres://… sein."
            )
        _local.conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
    return _local.conn

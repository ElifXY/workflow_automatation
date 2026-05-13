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
    """True, wenn DATABASE_URL auf PostgreSQL zeigt (Kern-Tabellen dort)."""
    return (os.getenv("DATABASE_URL") or "").strip().lower().startswith("postgresql://")


def get_pg_connection() -> Any:
    """Thread-lokale psycopg2-Verbindung mit RealDictCursor."""
    if not hasattr(_local, "conn") or _local.conn is None:
        dsn = (os.getenv("DATABASE_URL") or "").strip()
        if not dsn.lower().startswith("postgresql://"):
            raise RuntimeError("get_pg_connection: DATABASE_URL muss postgresql://… sein.")
        _local.conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
    return _local.conn

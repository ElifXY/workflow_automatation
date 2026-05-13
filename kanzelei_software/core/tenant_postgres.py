"""PostgreSQL: Tabelle kanzleien für TenantManager (gleiche DB wie Auth)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from core.pg_runtime import get_pg_connection


def _norm_row(d: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(d)
    v = out.get("erstellt_am")
    if isinstance(v, (datetime, date)):
        out["erstellt_am"] = v.isoformat()
    return out


def tp_fetch_by_id(tenant_id: str) -> Optional[Dict[str, Any]]:
    with get_pg_connection().cursor() as cur:
        cur.execute(
            "SELECT id, name, email, plan, aktiv, erstellt_am FROM kanzleien WHERE id = %s",
            (tenant_id,),
        )
        row = cur.fetchone()
    return _norm_row(dict(row)) if row else None


def tp_insert_kanzlei(
    tenant_id: str, kanzlei_name: str, inhaber_email: str, plan: str
) -> None:
    cn = get_pg_connection()
    with cn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO kanzleien (id, name, email, plan, aktiv)
            VALUES (%s, %s, %s, %s, 1)
            """,
            (tenant_id, kanzlei_name, inhaber_email or "", plan),
        )
    cn.commit()


def tp_update_kanzlei(
    tenant_id: str, name: str, email: str, plan: str, aktiv: int
) -> None:
    cn = get_pg_connection()
    with cn.cursor() as cur:
        cur.execute(
            """
            UPDATE kanzleien SET name = %s, email = %s, plan = %s, aktiv = %s
            WHERE id = %s
            """,
            (name, email, plan, aktiv, tenant_id),
        )
    cn.commit()


def tp_list_all() -> List[Dict[str, Any]]:
    with get_pg_connection().cursor() as cur:
        cur.execute(
            "SELECT id, name, email, plan, aktiv, erstellt_am FROM kanzleien ORDER BY erstellt_am DESC"
        )
        rows = cur.fetchall()
    return [_norm_row(dict(r)) for r in rows]

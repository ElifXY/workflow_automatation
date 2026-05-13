"""
Persistente Mandanten-Einladungen (Audit, Revoke, E-Mail-Status).

Ergänzt die stateless HMAC-Tokens aus ``core.tenant_invites``:
- Jede neue Einladung wird mit ``jti`` persistiert.
- ``verify_tenant_invite_token`` lehnt Tokens ab, die in der DB ``used``/``revoked`` sind.
- Nach erfolgreicher Registrierung wird der Datensatz auf ``used`` gesetzt.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

log = logging.getLogger("kanzlei_invites")


def _pg() -> bool:
    from core.daten_speicher import _pg_saas_backend

    return _pg_saas_backend()


def _ensure_sqlite_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tenant_invite_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kanzlei_id TEXT NOT NULL DEFAULT 'default',
            jti TEXT NOT NULL UNIQUE,
            role TEXT NOT NULL DEFAULT 'assistent',
            email_lock TEXT,
            target_email TEXT,
            invited_by TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            expires_at INTEGER NOT NULL,
            revoked_at TEXT,
            used_at TEXT,
            used_email TEXT,
            email_outbox_id INTEGER,
            email_queued_at TEXT,
            email_sent_at TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tenant_invite_records_kid ON tenant_invite_records(kanzlei_id, id DESC)"
    )
    conn.commit()
    try:
        conn.execute("ALTER TABLE tenant_invite_records ADD COLUMN email_queued_at TEXT")
        conn.commit()
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE tenant_invite_records ADD COLUMN email_sent_at TEXT")
        conn.commit()
    except Exception:
        pass


def invite_token_allowed(*, jti: str, kanzlei_id: str) -> bool:
    """False, wenn JTI in der DB gesperrt/verbraucht ist (oder falscher Mandant)."""
    jti = (jti or "").strip()
    kid = (kanzlei_id or "").strip()
    if not jti or not kid:
        return False
    try:
        if _pg():
            from core.daten_speicher import _pg_conn

            cn = _pg_conn()
            with cn.cursor() as cur:
                cur.execute(
                    "SELECT kanzlei_id, status FROM tenant_invite_records WHERE jti = %s",
                    (jti,),
                )
                row = cur.fetchone()
        else:
            from core.daten_speicher import get_connection

            conn = get_connection()
            _ensure_sqlite_schema(conn)
            row = conn.execute(
                "SELECT kanzlei_id, status FROM tenant_invite_records WHERE jti = ?",
                (jti,),
            ).fetchone()
            if row is not None:
                row = dict(row)
        if not row:
            return True
        rkid = str(row.get("kanzlei_id") or "").strip()
        if rkid != kid:
            return False
        st = str(row.get("status") or "").strip().lower()
        if st in {"revoked", "used"}:
            return False
        return True
    except Exception as e:
        log.error("invite_token_allowed: %s", e)
        return True


def invite_record_insert(
    *,
    kanzlei_id: str,
    jti: str,
    role: str,
    email_lock: Optional[str],
    target_email: Optional[str],
    invited_by: str,
    expires_at: int,
) -> None:
    kid = (kanzlei_id or "").strip()
    jti = (jti or "").strip()
    if not kid or not jti:
        return
    el = (email_lock or "").strip().lower() or None
    te = (target_email or "").strip().lower() or None
    try:
        if _pg():
            from core.daten_speicher import _pg_conn

            cn = _pg_conn()
            with cn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO tenant_invite_records
                        (kanzlei_id, jti, role, email_lock, target_email, invited_by, status, expires_at)
                    VALUES (%s, %s, %s, %s, %s, %s, 'pending', %s)
                    ON CONFLICT (jti) DO NOTHING
                    """,
                    (kid, jti, (role or "assistent").strip(), el, te, (invited_by or "")[:120], int(expires_at)),
                )
            cn.commit()
        else:
            from core.daten_speicher import get_connection

            conn = get_connection()
            _ensure_sqlite_schema(conn)
            conn.execute(
                """
                INSERT OR IGNORE INTO tenant_invite_records
                    (kanzlei_id, jti, role, email_lock, target_email, invited_by, status, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (kid, jti, (role or "assistent").strip(), el, te, (invited_by or "")[:120], int(expires_at)),
            )
            conn.commit()
    except Exception as e:
        log.error("invite_record_insert: %s", e)


def invite_record_mark_used(*, jti: str, kanzlei_id: str, used_email: str) -> None:
    jti = (jti or "").strip()
    kid = (kanzlei_id or "").strip()
    em = (used_email or "").strip().lower()
    if not jti or not kid:
        return
    try:
        if _pg():
            from core.daten_speicher import _pg_conn

            cn = _pg_conn()
            with cn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE tenant_invite_records
                    SET status = 'used', used_at = NOW(), used_email = %s
                    WHERE jti = %s AND kanzlei_id = %s AND status = 'pending'
                    """,
                    (em, jti, kid),
                )
            cn.commit()
        else:
            from core.daten_speicher import get_connection

            conn = get_connection()
            _ensure_sqlite_schema(conn)
            conn.execute(
                """
                UPDATE tenant_invite_records
                SET status = 'used', used_at = datetime('now'), used_email = ?
                WHERE jti = ? AND kanzlei_id = ? AND status = 'pending'
                """,
                (em, jti, kid),
            )
            conn.commit()
    except Exception as e:
        log.error("invite_record_mark_used: %s", e)


def invite_record_revoke(*, jti: str, kanzlei_id: str) -> bool:
    jti = (jti or "").strip()
    kid = (kanzlei_id or "").strip()
    if not jti or not kid:
        return False
    try:
        if _pg():
            from core.daten_speicher import _pg_conn

            cn = _pg_conn()
            with cn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE tenant_invite_records
                    SET status = 'revoked', revoked_at = NOW()
                    WHERE jti = %s AND kanzlei_id = %s AND status = 'pending'
                    """,
                    (jti, kid),
                )
                n = cur.rowcount
            cn.commit()
            return n > 0
        from core.daten_speicher import get_connection

        conn = get_connection()
        _ensure_sqlite_schema(conn)
        cur = conn.execute(
            """
            UPDATE tenant_invite_records
            SET status = 'revoked', revoked_at = datetime('now')
            WHERE jti = ? AND kanzlei_id = ? AND status = 'pending'
            """,
            (jti, kid),
        )
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        log.error("invite_record_revoke: %s", e)
        return False


def invite_record_mark_email_enqueued(*, jti: str, kanzlei_id: str, outbox_id: Optional[int]) -> None:
    jti = (jti or "").strip()
    kid = (kanzlei_id or "").strip()
    if not jti or not kid:
        return
    oid = int(outbox_id) if outbox_id is not None else None
    try:
        if _pg():
            from core.daten_speicher import _pg_conn

            cn = _pg_conn()
            with cn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE tenant_invite_records
                    SET email_outbox_id = %s, email_queued_at = NOW()
                    WHERE jti = %s AND kanzlei_id = %s
                    """,
                    (oid, jti, kid),
                )
            cn.commit()
        else:
            from core.daten_speicher import get_connection

            conn = get_connection()
            _ensure_sqlite_schema(conn)
            conn.execute(
                """
                UPDATE tenant_invite_records
                SET email_outbox_id = ?, email_queued_at = datetime('now')
                WHERE jti = ? AND kanzlei_id = ?
                """,
                (oid, jti, kid),
            )
            conn.commit()
    except Exception as e:
        log.error("invite_record_mark_email_enqueued: %s", e)


def invite_record_mark_email_smtp_sent(*, jti: str, kanzlei_id: str) -> None:
    """Nach erfolgreichem SMTP-Versand (Outbox-Worker)."""
    jti = (jti or "").strip()
    kid = (kanzlei_id or "").strip()
    if not jti or not kid:
        return
    try:
        if _pg():
            from core.daten_speicher import _pg_conn

            cn = _pg_conn()
            with cn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE tenant_invite_records
                    SET email_sent_at = NOW()
                    WHERE jti = %s AND kanzlei_id = %s
                    """,
                    (jti, kid),
                )
            cn.commit()
        else:
            from core.daten_speicher import get_connection

            conn = get_connection()
            _ensure_sqlite_schema(conn)
            conn.execute(
                """
                UPDATE tenant_invite_records
                SET email_sent_at = datetime('now')
                WHERE jti = ? AND kanzlei_id = ?
                """,
                (jti, kid),
            )
            conn.commit()
    except Exception as e:
        log.error("invite_record_mark_email_smtp_sent: %s", e)


def invite_records_list(*, kanzlei_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    kid = (kanzlei_id or "").strip()
    lim = max(1, min(int(limit or 50), 200))
    now = int(time.time())
    rows: List[Dict[str, Any]] = []
    try:
        if _pg():
            from core.daten_speicher import _pg_conn

            cn = _pg_conn()
            with cn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, jti, role, email_lock, target_email, invited_by, status,
                           EXTRACT(EPOCH FROM created_at)::bigint AS created_ts,
                           expires_at,
                           EXTRACT(EPOCH FROM revoked_at)::bigint AS revoked_ts,
                           EXTRACT(EPOCH FROM used_at)::bigint AS used_ts,
                           used_email, email_outbox_id,
                           EXTRACT(EPOCH FROM email_queued_at)::bigint AS email_queued_ts,
                           EXTRACT(EPOCH FROM email_sent_at)::bigint AS email_sent_ts
                    FROM tenant_invite_records
                    WHERE kanzlei_id = %s
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (kid, lim),
                )
                rows = [dict(r) for r in cur.fetchall()]
        else:
            from core.daten_speicher import get_connection

            conn = get_connection()
            _ensure_sqlite_schema(conn)
            q = conn.execute(
                """
                SELECT id, jti, role, email_lock, target_email, invited_by, status,
                       created_at, expires_at, revoked_at, used_at, used_email, email_outbox_id,
                       email_queued_at, email_sent_at
                FROM tenant_invite_records
                WHERE kanzlei_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (kid, lim),
            ).fetchall()
            rows = [dict(r) for r in q]
    except Exception as e:
        log.error("invite_records_list: %s", e)
        return []

    out: List[Dict[str, Any]] = []
    for r in rows:
        st = str(r.get("status") or "").lower()
        exp = int(r.get("expires_at") or 0)
        disp = st
        if st == "pending" and exp and now > exp:
            disp = "expired"
        item = {
            "id": r.get("id"),
            "jti": r.get("jti"),
            "role": r.get("role"),
            "email_lock": r.get("email_lock"),
            "target_email": r.get("target_email"),
            "invited_by": r.get("invited_by"),
            "status": disp,
            "db_status": st,
            "expires_at": exp,
            "used_email": r.get("used_email"),
            "email_outbox_id": r.get("email_outbox_id"),
        }
        if "created_ts" in r:
            item["created_at"] = r.get("created_ts")
        else:
            item["created_at"] = r.get("created_at")
        item["revoked_at"] = r.get("revoked_ts") if "revoked_ts" in r else r.get("revoked_at")
        item["used_at"] = r.get("used_ts") if "used_ts" in r else r.get("used_at")
        item["email_queued_at"] = r.get("email_queued_ts") if "email_queued_ts" in r else r.get("email_queued_at")
        item["email_sent_at"] = r.get("email_sent_ts") if "email_sent_ts" in r else r.get("email_sent_at")
        out.append(item)
    return out

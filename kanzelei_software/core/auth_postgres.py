"""
PostgreSQL-Pfade für core.auth (Benutzer + Kanzleien).

Voraussetzung: scripts/postgres_bootstrap.sql (oder Migration) auf derselben
DATABASE_URL wie die übrige App — kein paralleles SQLite für Login.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from core.pg_runtime import get_pg_connection, pg_primary_db

log = logging.getLogger("kanzlei_auth_pg")


def auth_pg_enabled() -> bool:
    return pg_primary_db()


def pg_hat_benutzer(kanzlei_id: str = "default") -> bool:
    with get_pg_connection().cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS n FROM benutzer WHERE kanzlei_id = %s AND aktiv = 1",
            (kanzlei_id,),
        )
        row = cur.fetchone()
    return int(row["n"] or 0) > 0


def pg_hat_irgendein_benutzer() -> bool:
    with get_pg_connection().cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM benutzer WHERE aktiv = 1")
        row = cur.fetchone()
    return int(row["n"] or 0) > 0


def pg_erstelle_kanzlei(name: str, email: str = "", plan: str = "starter") -> Dict[str, Any]:
    kid = str(uuid.uuid4())[:8]
    cn = get_pg_connection()
    with cn.cursor() as cur:
        cur.execute(
            "INSERT INTO kanzleien (id, name, email, plan) VALUES (%s, %s, %s, %s)",
            (kid, name, email or "", plan),
        )
    cn.commit()
    log.info("Kanzlei erstellt (PG): %s (id=%s)", name, kid)
    return {"kanzlei_id": kid, "name": name, "plan": plan}


def pg_hole_kanzlei(kanzlei_id: str) -> Optional[Dict[str, Any]]:
    with get_pg_connection().cursor() as cur:
        cur.execute(
            "SELECT * FROM kanzleien WHERE id = %s AND aktiv = 1",
            (kanzlei_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def pg_liste_kanzleien() -> List[Dict[str, Any]]:
    with get_pg_connection().cursor() as cur:
        cur.execute(
            "SELECT id, name, email, plan, aktiv, erstellt_am FROM kanzleien ORDER BY name"
        )
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def pg_erstelle_benutzer(
    benutzername: str,
    rolle: str,
    email: str,
    kanzlei_id: str,
    hash_wert: str,
    salt: str,
) -> None:
    cn = get_pg_connection()
    with cn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO benutzer (kanzlei_id, benutzername, hash, salt, rolle, email)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (kanzlei_id, benutzername, hash_wert, salt, rolle, email or ""),
        )
    cn.commit()


def pg_benutzer_existiert(kanzlei_id: str, benutzername: str) -> bool:
    with get_pg_connection().cursor() as cur:
        cur.execute(
            "SELECT 1 FROM benutzer WHERE kanzlei_id = %s AND benutzername = %s",
            (kanzlei_id, benutzername),
        )
        return cur.fetchone() is not None


def pg_liste_benutzer(kanzlei_id: str = "default") -> List[Dict[str, Any]]:
    with get_pg_connection().cursor() as cur:
        cur.execute(
            """
            SELECT id, benutzername, rolle, email, aktiv, erstellt_am, letzter_login
            FROM benutzer WHERE kanzlei_id = %s ORDER BY benutzername
            """,
            (kanzlei_id,),
        )
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def pg_fetch_password_row(kanzlei_id: str, benutzername: str) -> Optional[Dict[str, Any]]:
    with get_pg_connection().cursor() as cur:
        cur.execute(
            "SELECT hash, salt FROM benutzer WHERE kanzlei_id = %s AND benutzername = %s AND aktiv = 1",
            (kanzlei_id, benutzername),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def pg_aendere_passwort(
    benutzername: str, kanzlei_id: str, neuer_hash: str, neuer_salt: str
) -> None:
    cn = get_pg_connection()
    with cn.cursor() as cur:
        cur.execute(
            "UPDATE benutzer SET hash=%s, salt=%s WHERE kanzlei_id=%s AND benutzername=%s",
            (neuer_hash, neuer_salt, kanzlei_id, benutzername),
        )
    cn.commit()


def pg_benutzer_deaktivieren(benutzername: str, kanzlei_id: str = "default") -> None:
    cn = get_pg_connection()
    with cn.cursor() as cur:
        cur.execute(
            "UPDATE benutzer SET aktiv = 0 WHERE kanzlei_id = %s AND benutzername = %s",
            (kanzlei_id, benutzername),
        )
    cn.commit()


def pg_login_fetch(benutzername: str) -> Optional[Dict[str, Any]]:
    with get_pg_connection().cursor() as cur:
        cur.execute(
            "SELECT * FROM benutzer WHERE benutzername = %s AND aktiv = 1",
            (benutzername,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def pg_email_adresse_bereits_registriert(email: str) -> bool:
    e = (email or "").strip()
    if not e:
        return False
    with get_pg_connection().cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM benutzer
            WHERE LOWER(TRIM(COALESCE(email, ''))) = LOWER(TRIM(%s))
            LIMIT 1
            """,
            (e,),
        )
        return cur.fetchone() is not None


def pg_lade_benutzer_profil(benutzername: str, kanzlei_id: str) -> Optional[Dict[str, Any]]:
    with get_pg_connection().cursor() as cur:
        cur.execute(
            """
            SELECT id, benutzername, email, rolle, kanzlei_id
            FROM benutzer
            WHERE benutzername = %s AND kanzlei_id = %s AND aktiv = 1
            """,
            (benutzername, kanzlei_id),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def pg_login_fetch_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Aktiven Benutzer anhand E-Mail (case-insensitive, getrimmt)."""
    e = (email or "").strip()
    if not e:
        return None
    with get_pg_connection().cursor() as cur:
        cur.execute(
            """
            SELECT * FROM benutzer
            WHERE LOWER(TRIM(COALESCE(email, ''))) = LOWER(TRIM(%s))
              AND aktiv = 1
            LIMIT 2
            """,
            (e,),
        )
        rows = cur.fetchall()
    if len(rows) > 1:
        log.warning("Login-by-email: mehrere aktive Benutzer mit derselben E-Mail — erste Zeile genutzt")
    return dict(rows[0]) if rows else None


def pg_login_touch(benutzername: str, kanzlei_id: str) -> None:
    cn = get_pg_connection()
    with cn.cursor() as cur:
        cur.execute(
            "UPDATE benutzer SET letzter_login = NOW() WHERE benutzername = %s AND kanzlei_id = %s",
            (benutzername, kanzlei_id),
        )
    cn.commit()


def pg_benutzer_rolle_setzen(benutzername: str, kanzlei_id: str, rolle: str) -> None:
    cn = get_pg_connection()
    with cn.cursor() as cur:
        cur.execute(
            """
            UPDATE benutzer SET rolle = %s
            WHERE kanzlei_id = %s AND benutzername = %s AND aktiv = 1
            """,
            (rolle, kanzlei_id, benutzername),
        )
    cn.commit()

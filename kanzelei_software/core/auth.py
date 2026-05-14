# ============================================================
# KANZLEI AI — AUTH v4.0
# INTERNAL: Nutzung nur über ``backend.auth``.
# Multi-Kanzlei: Jeder Benutzer gehört zu einer Kanzlei.
# Login gibt kanzlei_id in Session zurück.
# Alle Datenzugriffe werden dann mit dieser ID gefiltert.
# ============================================================

import os
import json
import secrets
import logging
import hashlib
import hmac
import time
import uuid
import importlib
import bcrypt
import re
from datetime import datetime, timedelta
from typing import Any, Optional, Dict, Tuple
from collections import defaultdict

log = logging.getLogger("kanzlei_auth")

TOKEN_TTL    = int(os.getenv("SESSION_TIMEOUT_MINUTEN", "60")) * 60
MAX_VERSUCHE = 5
SPERRE_DAUER = 300

_sessions:       Dict[str, Dict] = {}
_login_versuche: Dict[str, list] = defaultdict(list)
_gesperrte_ips:  Dict[str, float] = {}

# Redis (optional): Sessions über alle Uvicorn-Worker / Instanzen teilen
_redis_client = None
_redis_unavailable: Optional[bool] = None


def _session_redis_key(token: str) -> str:
    return f"kanzlei:session:{token}"


def _get_redis():
    """Redis nur wenn REDIS_URL gesetzt und erreichbar — sonst In-Memory-Fallback."""
    global _redis_client, _redis_unavailable
    if _redis_unavailable:
        return None
    if _redis_client is not None:
        return _redis_client
    url = (os.getenv("REDIS_URL") or "").strip()
    if not url:
        return None
    try:
        redis_mod = importlib.import_module("redis")
        r = redis_mod.Redis.from_url(url, decode_responses=True, socket_connect_timeout=2)
        r.ping()
        _redis_client = r
        log.info("Sessions: Redis aktiv (geteilt über Worker/Instanzen)")
        return r
    except Exception as e:
        log.warning(f"Sessions: Redis nicht nutzbar ({e}) — Fallback In-Memory (nicht für mehrere Worker!)")
        _redis_unavailable = True
        return None


def _session_speichern(token: str, session: Dict) -> None:
    r = _get_redis()
    if r:
        r.setex(_session_redis_key(token), TOKEN_TTL, json.dumps(session))
    else:
        _sessions[token] = session


def _session_laden(token: str) -> Optional[Dict]:
    r = _get_redis()
    if r:
        raw = r.get(_session_redis_key(token))
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return _sessions.get(token)


def _session_entfernen(token: str) -> None:
    r = _get_redis()
    if r:
        r.delete(_session_redis_key(token))
    _sessions.pop(token, None)


# ═══════════════════════════════════════════════════════════
# PASSWORT-HASHING
# ═══════════════════════════════════════════════════════════

def _hash_passwort(passwort: str, salt: str = None) -> Tuple[str, str]:
    # bcrypt (salt im Hash enthalten). salt-Feld bleibt für Legacy-Kompatibilität.
    hashed = bcrypt.hashpw(passwort.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    return hashed, "bcrypt"


def _verifiziere_passwort(passwort: str, hash_gespeichert: Any, salt: Any) -> bool:
    def _txt(v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, memoryview):
            return v.tobytes().decode("utf-8", errors="replace")
        if isinstance(v, (bytes, bytearray)):
            return bytes(v).decode("utf-8", errors="replace")
        return str(v).strip()

    h = _txt(hash_gespeichert)
    s = _txt(salt)
    # Neuer Standard: bcrypt (rohes bcrypt + passlib — gleiche Hashes, unterschiedliche Randfälle)
    if s.lower() == "bcrypt" or h.startswith("$2"):
        if not h:
            return False
        # passlib zuerst: $2y$ und Randfälle, bei denen bcrypt.checkpw scheitert
        try:
            from passlib.context import CryptContext

            ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
            if ctx.verify(passwort, h):
                return True
        except Exception:
            pass
        try:
            return bool(bcrypt.checkpw(passwort.encode("utf-8"), h.encode("utf-8")))
        except Exception:
            return False

    # Legacy-Fallback: PBKDF2
    neu_hash = hashlib.pbkdf2_hmac(
        "sha256", passwort.encode("utf-8"), s.encode("utf-8"),
        iterations=260000,
    ).hex()
    return hmac.compare_digest(neu_hash, h)


_PW_UPPER_RE = re.compile(r"[A-Z]")
_PW_LOWER_RE = re.compile(r"[a-z]")
_PW_DIGIT_RE = re.compile(r"\d")
_PW_SPECIAL_RE = re.compile(r"[^A-Za-z0-9]")


def _assert_strong_password(passwort: str, email: str = "") -> None:
    pw = str(passwort or "")
    if len(pw) < 12:
        raise ValueError("Passwort muss mindestens 12 Zeichen haben")
    if not _PW_UPPER_RE.search(pw):
        raise ValueError("Passwort muss mindestens einen Großbuchstaben enthalten")
    if not _PW_LOWER_RE.search(pw):
        raise ValueError("Passwort muss mindestens einen Kleinbuchstaben enthalten")
    if not _PW_DIGIT_RE.search(pw):
        raise ValueError("Passwort muss mindestens eine Zahl enthalten")
    if not _PW_SPECIAL_RE.search(pw):
        raise ValueError("Passwort muss mindestens ein Sonderzeichen enthalten")
    if " " in pw:
        raise ValueError("Passwort darf keine Leerzeichen enthalten")
    mail = str(email or "").strip().lower()
    if mail and "@" in mail:
        local = mail.split("@", 1)[0]
        if local and local in pw.lower():
            raise ValueError("Passwort darf keinen Teil der E-Mail enthalten")


# ═══════════════════════════════════════════════════════════
# DB-SCHEMA (benutzer mit kanzlei_id)
# ═══════════════════════════════════════════════════════════

def _get_conn():
    """Nur SQLite — bei DATABASE_URL=postgresql:// nutzt Auth core.auth_postgres."""
    from core.auth_postgres import auth_pg_enabled

    if auth_pg_enabled():
        raise RuntimeError("Auth nutzt PostgreSQL — kein SQLite-_get_conn().")
    from core.daten_speicher import get_connection
    conn = get_connection()
    conn.executescript("""
        -- Kanzleien-Tabelle (falls noch nicht durch daten_speicher erstellt)
        CREATE TABLE IF NOT EXISTS kanzleien (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            email       TEXT DEFAULT '',
            plan        TEXT DEFAULT 'starter',
            aktiv       INTEGER DEFAULT 1,
            erstellt_am TEXT NOT NULL DEFAULT (datetime('now'))
        );

        INSERT OR IGNORE INTO kanzleien (id, name) VALUES ('default', 'Standard-Kanzlei');

        -- Benutzer MIT kanzlei_id (Multi-Kanzlei)
        CREATE TABLE IF NOT EXISTS benutzer (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            kanzlei_id    TEXT NOT NULL DEFAULT 'default',
            benutzername  TEXT NOT NULL,
            hash          TEXT NOT NULL,
            salt          TEXT NOT NULL,
            rolle         TEXT DEFAULT 'assistent'
                          CHECK(rolle IN ('admin','steuerberater','assistent')),
            email         TEXT DEFAULT '',
            aktiv         INTEGER DEFAULT 1,
            erstellt_am   TEXT DEFAULT (datetime('now')),
            letzter_login TEXT,
            UNIQUE(kanzlei_id, benutzername)
        );
    """)
    conn.commit()
    return conn


# ═══════════════════════════════════════════════════════════
# KANZLEI-VERWALTUNG
# ═══════════════════════════════════════════════════════════

def erstelle_kanzlei(name: str, email: str = "", plan: str = "starter") -> Dict:
    """Neue Kanzlei anlegen. Gibt kanzlei_id zurück."""
    from core.auth_postgres import auth_pg_enabled, pg_erstelle_kanzlei

    if auth_pg_enabled():
        return pg_erstelle_kanzlei(name, email, plan)
    kid = str(uuid.uuid4())[:8]
    conn = _get_conn()
    conn.execute(
        "INSERT INTO kanzleien (id, name, email, plan) VALUES (?, ?, ?, ?)",
        (kid, name, email, plan)
    )
    conn.commit()
    log.info(f"Kanzlei erstellt: {name} (id={kid})")
    return {"kanzlei_id": kid, "name": name, "plan": plan}


def hole_kanzlei(kanzlei_id: str) -> Optional[Dict]:
    from core.auth_postgres import auth_pg_enabled, pg_hole_kanzlei

    if auth_pg_enabled():
        return pg_hole_kanzlei(kanzlei_id)
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM kanzleien WHERE id = ? AND aktiv = 1", (kanzlei_id,)
    ).fetchone()
    return dict(row) if row else None


def liste_kanzleien() -> list:
    from core.auth_postgres import auth_pg_enabled, pg_liste_kanzleien

    if auth_pg_enabled():
        return pg_liste_kanzleien()
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, name, email, plan, aktiv, erstellt_am FROM kanzleien ORDER BY name"
    ).fetchall()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════
# BENUTZER-VERWALTUNG
# ═══════════════════════════════════════════════════════════

def hat_benutzer(kanzlei_id: str = "default") -> bool:
    """Prüft ob mindestens ein Benutzer in dieser Kanzlei existiert."""
    from core.auth_postgres import auth_pg_enabled, pg_hat_benutzer

    try:
        if auth_pg_enabled():
            return pg_hat_benutzer(kanzlei_id)
        conn = _get_conn()
        row = conn.execute(
            "SELECT COUNT(*) FROM benutzer WHERE kanzlei_id = ? AND aktiv = 1",
            (kanzlei_id,)
        ).fetchone()
        return row[0] > 0
    except Exception:
        return False


def hat_irgendein_benutzer() -> bool:
    """Prüft ob überhaupt ein Benutzer existiert (für Setup-Check)."""
    from core.auth_postgres import auth_pg_enabled, pg_hat_irgendein_benutzer

    try:
        if auth_pg_enabled():
            return pg_hat_irgendein_benutzer()
        conn = _get_conn()
        row = conn.execute("SELECT COUNT(*) FROM benutzer WHERE aktiv = 1").fetchone()
        return row[0] > 0
    except Exception:
        return False


def erstelle_benutzer(
    benutzername: str,
    passwort: str,
    rolle: str = "assistent",
    email: str = "",
    kanzlei_id: str = "default",
) -> Dict:
    """Neuen Benutzer anlegen. Gehört zu kanzlei_id."""
    from core.auth_postgres import (
        auth_pg_enabled,
        pg_benutzer_existiert,
        pg_erstelle_benutzer,
        pg_lade_benutzer_profil,
    )

    _assert_strong_password(passwort, email)
    if not benutzername.strip():
        raise ValueError("Benutzername darf nicht leer sein")

    rolle_map = {
        "OWNER": "owner",
        "owner": "owner",
        "ADMIN": "admin",
        "MITARBEITER": "assistent",
        "USER": "assistent",
        "admin": "admin",
        "user": "assistent",
        "mitarbeiter": "assistent",
        "steuerberater": "steuerberater",
        "selbststaendig": "steuerberater",
        "assistent": "assistent",
    }
    rolle = rolle_map.get((rolle or "").strip(), "assistent")
    if auth_pg_enabled():
        if pg_benutzer_existiert(kanzlei_id, benutzername):
            raise ValueError(f"Benutzer '{benutzername}' existiert bereits in dieser Kanzlei")
        hash_wert, salt = _hash_passwort(passwort)
        pg_erstelle_benutzer(benutzername, rolle, email, kanzlei_id, hash_wert, salt)
        log.info(f"Benutzer erstellt (PG): {benutzername} | Kanzlei: {kanzlei_id} | Rolle: {rolle}")
        prof = pg_lade_benutzer_profil(benutzername, kanzlei_id)
        uid = int(prof["id"]) if prof and prof.get("id") is not None else None
        return {"id": uid, "benutzername": benutzername, "rolle": rolle, "email": email, "kanzlei_id": kanzlei_id}

    conn = _get_conn()
    existing = conn.execute(
        "SELECT 1 FROM benutzer WHERE kanzlei_id = ? AND benutzername = ?",
        (kanzlei_id, benutzername)
    ).fetchone()
    if existing:
        raise ValueError(f"Benutzer '{benutzername}' existiert bereits in dieser Kanzlei")

    hash_wert, salt = _hash_passwort(passwort)
    conn.execute("""
        INSERT INTO benutzer (kanzlei_id, benutzername, hash, salt, rolle, email)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (kanzlei_id, benutzername, hash_wert, salt, rolle, email))
    conn.commit()

    log.info(f"Benutzer erstellt: {benutzername} | Kanzlei: {kanzlei_id} | Rolle: {rolle}")
    row = conn.execute(
        "SELECT id FROM benutzer WHERE kanzlei_id = ? AND benutzername = ?",
        (kanzlei_id, benutzername),
    ).fetchone()
    uid = int(row["id"]) if row else None
    return {"id": uid, "benutzername": benutzername, "rolle": rolle, "email": email, "kanzlei_id": kanzlei_id}


def setup_erstbenutzer(
    benutzername: str = "admin",
    passwort: Optional[str] = None,
    kanzlei_id: str = "default",
) -> bool:
    """Erstellt Standard-Admin wenn noch kein Benutzer existiert."""
    if hat_irgendein_benutzer():
        return False
    try:
        pw = (passwort or os.getenv("INITIAL_ADMIN_PASSWORD") or "").strip()
        if len(pw) < 12:
            raise ValueError("INITIAL_ADMIN_PASSWORD fehlt oder zu kurz (>=12)")
        admin_email = (os.getenv("INITIAL_ADMIN_EMAIL") or "").strip().lower()
        erstelle_benutzer(
            benutzername, pw, rolle="owner", kanzlei_id=kanzlei_id, email=admin_email
        )
        log.info(f"Erstbenutzer angelegt: {benutzername} in Kanzlei {kanzlei_id}")
        return True
    except Exception as e:
        log.error(f"Erstbenutzer fehlgeschlagen: {e}")
        return False


def liste_benutzer(kanzlei_id: str = "default") -> list:
    from core.auth_postgres import auth_pg_enabled, pg_liste_benutzer

    try:
        if auth_pg_enabled():
            return pg_liste_benutzer(kanzlei_id)
        conn = _get_conn()
        cols = {
            str(r["name"]).lower()
            for r in conn.execute("PRAGMA table_info(benutzer)").fetchall()
            if isinstance(r, dict) and r.get("name")
        }
        if "letzter_login" in cols:
            sql = (
                "SELECT id, benutzername, rolle, email, aktiv, erstellt_am, letzter_login "
                "FROM benutzer WHERE kanzlei_id = ? ORDER BY benutzername"
            )
        else:
            # Legacy-Schema ohne letzter_login
            sql = (
                "SELECT id, benutzername, rolle, email, aktiv, erstellt_am, NULL AS letzter_login "
                "FROM benutzer WHERE kanzlei_id = ? ORDER BY benutzername"
            )
        rows = conn.execute(sql, (kanzlei_id,)).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        log.error(f"liste_benutzer: {e}")
        return []


def aendere_passwort(
    benutzername: str, altes_passwort: str, neues_passwort: str,
    kanzlei_id: str = "default",
) -> bool:
    from core.auth_postgres import auth_pg_enabled

    _assert_strong_password(neues_passwort)
    if auth_pg_enabled():
        from core.auth_postgres import pg_fetch_password_row

        row = pg_fetch_password_row(kanzlei_id, benutzername)
        if not row:
            raise ValueError("Benutzer nicht gefunden")
        if not _verifiziere_passwort(altes_passwort, row["hash"], row["salt"]):
            raise ValueError("Altes Passwort falsch")
        neuer_hash, neuer_salt = _hash_passwort(neues_passwort)
        from core.auth_postgres import pg_aendere_passwort

        pg_aendere_passwort(benutzername, kanzlei_id, neuer_hash, neuer_salt)
        log.info(f"Passwort geändert (PG): {benutzername} in {kanzlei_id}")
        return True

    conn = _get_conn()
    row = conn.execute(
        "SELECT hash, salt FROM benutzer WHERE kanzlei_id = ? AND benutzername = ? AND aktiv = 1",
        (kanzlei_id, benutzername)
    ).fetchone()
    if not row:
        raise ValueError("Benutzer nicht gefunden")
    if not _verifiziere_passwort(altes_passwort, row["hash"], row["salt"]):
        raise ValueError("Altes Passwort falsch")
    neuer_hash, neuer_salt = _hash_passwort(neues_passwort)
    conn.execute(
        "UPDATE benutzer SET hash=?, salt=? WHERE kanzlei_id=? AND benutzername=?",
        (neuer_hash, neuer_salt, kanzlei_id, benutzername)
    )
    conn.commit()
    log.info(f"Passwort geändert: {benutzername} in {kanzlei_id}")
    return True


def finde_benutzer_nach_email(email: str) -> Optional[Dict[str, Any]]:
    """Aktiven Benutzer über E-Mail finden (kanzlei_id + benutzername)."""
    e = (email or "").strip()
    if not e:
        return None
    from core.auth_postgres import auth_pg_enabled

    try:
        if auth_pg_enabled():
            from core.pg_runtime import get_pg_connection

            with get_pg_connection().cursor() as cur:
                cur.execute(
                    """
                    SELECT id, benutzername, kanzlei_id, email, rolle, aktiv
                    FROM benutzer
                    WHERE LOWER(TRIM(COALESCE(email, ''))) = LOWER(TRIM(%s))
                      AND aktiv = 1
                    ORDER BY id ASC
                    LIMIT 1
                    """,
                    (e,),
                )
                row = cur.fetchone()
            return dict(row) if row else None
        conn = _get_conn()
        row = conn.execute(
            """
            SELECT id, benutzername, kanzlei_id, email, rolle, aktiv
            FROM benutzer
            WHERE LOWER(TRIM(COALESCE(email, ''))) = LOWER(TRIM(?))
              AND aktiv = 1
            ORDER BY id ASC
            LIMIT 1
            """,
            (e,),
        ).fetchone()
        return dict(row) if row else None
    except Exception as ex:
        log.error(f"finde_benutzer_nach_email: {ex}")
        return None


def setze_passwort_ohne_altes(benutzername: str, kanzlei_id: str, neues_passwort: str) -> bool:
    """Admin-/Reset-Pfad: Passwort ohne altes Passwort setzen."""
    from core.auth_postgres import auth_pg_enabled

    _assert_strong_password(neues_passwort)

    neuer_hash, neuer_salt = _hash_passwort(neues_passwort)
    try:
        if auth_pg_enabled():
            from core.pg_runtime import get_pg_connection

            cn = get_pg_connection()
            with cn.cursor() as cur:
                cur.execute(
                    "UPDATE benutzer SET hash=%s, salt=%s WHERE kanzlei_id=%s AND benutzername=%s AND aktiv=1",
                    (neuer_hash, neuer_salt, kanzlei_id, benutzername),
                )
                changed = cur.rowcount
            cn.commit()
            return changed > 0
        conn = _get_conn()
        cur = conn.execute(
            "UPDATE benutzer SET hash=?, salt=? WHERE kanzlei_id=? AND benutzername=? AND aktiv=1",
            (neuer_hash, neuer_salt, kanzlei_id, benutzername),
        )
        conn.commit()
        return cur.rowcount > 0
    except Exception as ex:
        log.error(f"setze_passwort_ohne_altes: {ex}")
        return False


def benutzer_rolle_setzen(benutzername: str, kanzlei_id: str, neue_rolle: str) -> bool:
    """Rolle eines Benutzers in der Kanzlei ändern (nur bekannte Rollen)."""
    from core.auth_postgres import auth_pg_enabled, pg_benutzer_rolle_setzen

    rolle_map = {
        "OWNER": "owner",
        "owner": "owner",
        "ADMIN": "admin",
        "MITARBEITER": "assistent",
        "admin": "admin",
        "mitarbeiter": "assistent",
        "steuerberater": "steuerberater",
        "selbststaendig": "steuerberater",
        "assistent": "assistent",
        "user": "assistent",
    }
    rolle = rolle_map.get((neue_rolle or "").strip(), "assistent")

    # Owner-Schutz: ein bestehender Owner darf nicht herabgestuft werden.
    try:
        from core.auth_postgres import auth_pg_enabled as _pg_on, pg_lade_benutzer_profil

        if _pg_on():
            current = pg_lade_benutzer_profil(benutzername, kanzlei_id) or {}
        else:
            row = _get_conn().execute(
                "SELECT rolle FROM benutzer WHERE kanzlei_id = ? AND benutzername = ? AND aktiv = 1",
                (kanzlei_id, benutzername),
            ).fetchone()
            current = dict(row) if row else {}
        current_role = (current.get("rolle") or "").strip().lower()
        if current_role == "owner" and rolle != "owner":
            log.warning(
                "benutzer_rolle_setzen: Owner-Schutz - %s in %s bleibt owner",
                benutzername,
                kanzlei_id,
            )
            return False
    except Exception:
        # Schutz darf den Pfad nicht hart blockieren, falls Profil-Lookup fehlt.
        pass

    try:
        if auth_pg_enabled():
            pg_benutzer_rolle_setzen(benutzername, kanzlei_id, rolle)
            return True
        conn = _get_conn()
        conn.execute(
            "UPDATE benutzer SET rolle = ? WHERE kanzlei_id = ? AND benutzername = ? AND aktiv = 1",
            (rolle, kanzlei_id, benutzername),
        )
        conn.commit()
        log.info(f"Rolle geändert: {benutzername} in {kanzlei_id} -> {rolle}")
        return True
    except Exception as e:
        log.error(f"benutzer_rolle_setzen: {e}")
        return False


def benutzer_deaktivieren(benutzername: str, kanzlei_id: str = "default") -> bool:
    from core.auth_postgres import auth_pg_enabled, pg_benutzer_deaktivieren

    try:
        if auth_pg_enabled():
            pg_benutzer_deaktivieren(benutzername, kanzlei_id)
            return True
        conn = _get_conn()
        conn.execute(
            "UPDATE benutzer SET aktiv = 0 WHERE kanzlei_id = ? AND benutzername = ?",
            (kanzlei_id, benutzername)
        )
        conn.commit()
        return True
    except Exception as e:
        log.error(f"benutzer_deaktivieren: {e}")
        return False


def hole_benutzer_kurz_nach_id(user_id: int, kanzlei_id: str) -> Optional[Dict[str, Any]]:
    """Benutzerzeile nach numerischer ``id`` innerhalb ``kanzlei_id`` (aktiv oder inaktiv)."""
    from core.auth_postgres import auth_pg_enabled
    from core.pg_runtime import get_pg_connection

    try:
        if auth_pg_enabled():
            with get_pg_connection().cursor() as cur:
                cur.execute(
                    """
                    SELECT id, benutzername, email, rolle, aktiv
                    FROM benutzer WHERE id = %s AND kanzlei_id = %s
                    """,
                    (int(user_id), kanzlei_id),
                )
                row = cur.fetchone()
            return dict(row) if row else None
        conn = _get_conn()
        row = conn.execute(
            """
            SELECT id, benutzername, email, rolle, aktiv
            FROM benutzer WHERE id = ? AND kanzlei_id = ?
            """,
            (int(user_id), kanzlei_id),
        ).fetchone()
        return dict(row) if row else None
    except Exception as e:
        log.error(f"hole_benutzer_kurz_nach_id: {e}")
        return None


def benutzer_deaktivieren_nach_id(user_id: int, kanzlei_id: str) -> bool:
    """Soft-Delete (``aktiv=0``) per numerischer User-ID, nur innerhalb ``kanzlei_id``."""
    from core.auth_postgres import auth_pg_enabled
    from core.pg_runtime import get_pg_connection

    try:
        if auth_pg_enabled():
            cn = get_pg_connection()
            with cn.cursor() as cur:
                cur.execute(
                    "UPDATE benutzer SET aktiv = 0 WHERE kanzlei_id = %s AND id = %s",
                    (kanzlei_id, int(user_id)),
                )
                n = cur.rowcount
            cn.commit()
            return n > 0
        conn = _get_conn()
        cur = conn.execute(
            "UPDATE benutzer SET aktiv = 0 WHERE kanzlei_id = ? AND id = ?",
            (kanzlei_id, int(user_id)),
        )
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        log.error(f"benutzer_deaktivieren_nach_id: {e}")
        return False


def benutzer_rolle_setzen_nach_id(user_id: int, kanzlei_id: str, neue_rolle: str) -> bool:
    row = hole_benutzer_kurz_nach_id(int(user_id), kanzlei_id)
    if not row:
        return False
    return benutzer_rolle_setzen(str(row["benutzername"]), kanzlei_id, neue_rolle)


# ═══════════════════════════════════════════════════════════
# RATE-LIMITING
# ═══════════════════════════════════════════════════════════

def _prüfe_rate_limit(ip: str) -> bool:
    jetzt = time.time()
    if ip in _gesperrte_ips:
        if jetzt < _gesperrte_ips[ip]:
            return False
        del _gesperrte_ips[ip]
        _login_versuche[ip] = []

    _login_versuche[ip] = [t for t in _login_versuche[ip] if jetzt - t < 300]
    if len(_login_versuche[ip]) >= MAX_VERSUCHE:
        _gesperrte_ips[ip] = jetzt + SPERRE_DAUER
        log.warning(f"Rate-Limit: IP {ip} gesperrt für {SPERRE_DAUER}s")
        return False
    _login_versuche[ip].append(jetzt)
    return True


def verbleibende_versuche(ip: str) -> int:
    jetzt = time.time()
    recent = [t for t in _login_versuche.get(ip, []) if jetzt - t < 300]
    return max(0, MAX_VERSUCHE - len(recent))


# ═══════════════════════════════════════════════════════════
# LOGIN / LOGOUT — gibt kanzlei_id in Session zurück
# ═══════════════════════════════════════════════════════════

def login(benutzername: str, passwort: str, ip: str = "unknown") -> Optional[Dict]:
    """
    Login. Gibt Session-Dict mit kanzlei_id zurück.
    Die kanzlei_id bestimmt welche Daten der User sieht.
    """
    if not _prüfe_rate_limit(ip):
        remaining = max(0, _gesperrte_ips.get(ip, time.time()) - time.time())
        raise ValueError(f"Zu viele Login-Versuche. Bitte {int(remaining)}s warten.")

    from core.auth_postgres import auth_pg_enabled, pg_login_fetch, pg_login_touch

    try:
        if auth_pg_enabled():
            row = pg_login_fetch(benutzername)
        else:
            conn = _get_conn()
            row = conn.execute(
                "SELECT * FROM benutzer WHERE benutzername = ? AND aktiv = 1",
                (benutzername,)
            ).fetchone()
            if row:
                row = dict(row)
    except Exception as e:
        log.error(f"Login DB-Fehler: {e}")
        return None

    if not row:
        log.warning(f"Login: Benutzer '{benutzername}' nicht gefunden")
        return None

    if not _verifiziere_passwort(passwort, row["hash"], row["salt"]):
        log.warning(f"Login: Falsches Passwort für '{benutzername}'")
        return None

    kanzlei_id = row["kanzlei_id"] or "default"
    token      = secrets.token_urlsafe(48)
    expires    = datetime.now() + timedelta(seconds=TOKEN_TTL)

    # Session enthält kanzlei_id — das ist der Kern des Multi-Kanzlei-Systems
    uid = row.get("id")
    _session_speichern(
        token,
        {
            "benutzername": benutzername,
            "kanzlei_id": kanzlei_id,
            "tenant_id": kanzlei_id,
            "rolle": row["rolle"],
            "email": row["email"] or "",
            "user_id": int(uid) if uid is not None else None,
            "expires": expires.timestamp(),
            "ip": ip,
        },
    )

    try:
        if auth_pg_enabled():
            pg_login_touch(benutzername, kanzlei_id)
        else:
            conn = _get_conn()
            conn.execute(
                "UPDATE benutzer SET letzter_login = datetime('now') WHERE benutzername = ? AND kanzlei_id = ?",
                (benutzername, kanzlei_id)
            )
            conn.commit()
    except Exception:
        pass

    _login_versuche[ip] = []
    log.info(f"Login: {benutzername} | Kanzlei: {kanzlei_id} | IP: {ip}")

    return {
        "token": token,
        "benutzername": benutzername,
        "kanzlei_id": kanzlei_id,
        "tenant_id": kanzlei_id,
        "rolle": row["rolle"],
        "email": row.get("email") or "",
        "user_id": int(row["id"]) if row.get("id") is not None else None,
        "expires": expires.isoformat(),
    }


def login_by_email(email: str, passwort: str, ip: str = "unknown") -> Optional[Dict]:
    """
    Lookup über ``benutzer.email``, identischen ``benutzername`` (selten) oder
    internem Namen ``u``+SHA256 (Standard bei ``registriere_per_email``).
    """
    email = (email or "").strip()
    if "@" in email:
        email = email.lower()
    if not email:
        return None
    if not _prüfe_rate_limit(ip):
        remaining = max(0, _gesperrte_ips.get(ip, time.time()) - time.time())
        raise ValueError(f"Zu viele Login-Versuche. Bitte {int(remaining)}s warten.")

    internal_login = _interner_benutzername_fuer_email(email) if "@" in email else ""

    from core.auth_postgres import auth_pg_enabled, pg_login_fetch_by_email, pg_login_fetch, pg_login_touch

    try:
        if auth_pg_enabled():
            row = pg_login_fetch_by_email(email, internal_login)
        else:
            conn = _get_conn()
            if internal_login:
                row = conn.execute(
                    """
                    SELECT * FROM benutzer
                    WHERE aktiv = 1
                      AND (
                            LOWER(TRIM(COALESCE(email, ''))) = LOWER(?)
                         OR LOWER(TRIM(benutzername)) = LOWER(?)
                         OR benutzername = ?
                          )
                    """,
                    (email, email, internal_login),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT * FROM benutzer
                    WHERE aktiv = 1
                      AND (
                            LOWER(TRIM(COALESCE(email, ''))) = LOWER(?)
                         OR LOWER(TRIM(benutzername)) = LOWER(?)
                          )
                    """,
                    (email, email),
                ).fetchone()
            if row:
                row = dict(row)
    except Exception as e:
        log.error("Login-by-email DB-Fehler: %s", e, exc_info=True)
        row = None
        try:
            if auth_pg_enabled():
                from core.pg_runtime import get_pg_connection

                get_pg_connection().rollback()
        except Exception:
            pass

    if not row and internal_login:
        try:
            if auth_pg_enabled():
                row = pg_login_fetch(internal_login)
            else:
                conn = _get_conn()
                r2 = conn.execute(
                    "SELECT * FROM benutzer WHERE benutzername = ? AND aktiv = 1",
                    (internal_login,),
                ).fetchone()
                row = dict(r2) if r2 else None
        except Exception as e2:
            log.warning("login_by_email Fallback interner Benutzername: %s", e2)
            row = None

    if not row:
        log.warning("Login-by-email: keine Zeile für E-Mail")
        return None

    benutzername = row["benutzername"]
    if not _verifiziere_passwort(passwort, row["hash"], row["salt"]):
        log.warning(f"Login-by-email: falsches Passwort für '{benutzername}'")
        return None

    kanzlei_id = row["kanzlei_id"] or "default"
    token = secrets.token_urlsafe(48)
    expires = datetime.now() + timedelta(seconds=TOKEN_TTL)

    uid = row.get("id")
    _session_speichern(
        token,
        {
            "benutzername": benutzername,
            "kanzlei_id": kanzlei_id,
            "tenant_id": kanzlei_id,
            "rolle": row["rolle"],
            "email": row.get("email") or "",
            "user_id": int(uid) if uid is not None else None,
            "expires": expires.timestamp(),
            "ip": ip,
        },
    )

    try:
        if auth_pg_enabled():
            pg_login_touch(benutzername, kanzlei_id)
        else:
            conn = _get_conn()
            conn.execute(
                "UPDATE benutzer SET letzter_login = datetime('now') WHERE benutzername = ? AND kanzlei_id = ?",
                (benutzername, kanzlei_id),
            )
            conn.commit()
    except Exception:
        pass

    _login_versuche[ip] = []
    log.info(f"Login-by-email: {benutzername} | Kanzlei: {kanzlei_id} | IP: {ip}")

    return {
        "token": token,
        "benutzername": benutzername,
        "kanzlei_id": kanzlei_id,
        "tenant_id": kanzlei_id,
        "rolle": row["rolle"],
        "email": row.get("email") or "",
        "user_id": int(row["id"]) if row.get("id") is not None else None,
        "expires": expires.isoformat(),
    }


def email_adresse_bereits_registriert(email: str) -> bool:
    """True, wenn diese E-Mail (unabhängig von Kanzlei) schon in ``benutzer`` vorkommt."""
    e = (email or "").strip()
    if not e:
        return False
    from core.auth_postgres import auth_pg_enabled, pg_email_adresse_bereits_registriert

    try:
        if auth_pg_enabled():
            return pg_email_adresse_bereits_registriert(e)
        conn = _get_conn()
        row = conn.execute(
            """
            SELECT 1 FROM benutzer
            WHERE LOWER(TRIM(COALESCE(email, ''))) = LOWER(?)
            LIMIT 1
            """,
            (e,),
        ).fetchone()
        return row is not None
    except Exception as ex:
        log.error(f"email_adresse_bereits_registriert: {ex}")
        return True


def _interner_benutzername_fuer_email(email: str) -> str:
    """Stabiler interner Login-Name aus E-Mail (≤ 50 Zeichen, kollisionssicher)."""
    norm = email.strip().lower()
    h = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:24]
    return f"u{h}"


def loginname_aus_email(email: str) -> str:
    """Öffentlicher Helfer: interner Login-Name für E-Mail-Registrierung / Einladungen."""
    return _interner_benutzername_fuer_email(email)


def lade_benutzer_profil(benutzername: str, kanzlei_id: str = "default") -> Optional[Dict[str, Any]]:
    """Aktiven Benutzer inkl. numerischer ``id`` für /api/me."""
    from core.auth_postgres import auth_pg_enabled, pg_lade_benutzer_profil

    try:
        if auth_pg_enabled():
            return pg_lade_benutzer_profil(benutzername, kanzlei_id)
        conn = _get_conn()
        row = conn.execute(
            """
            SELECT id, benutzername, email, rolle, kanzlei_id
            FROM benutzer
            WHERE benutzername = ? AND kanzlei_id = ? AND aktiv = 1
            """,
            (benutzername, kanzlei_id),
        ).fetchone()
        return dict(row) if row else None
    except Exception as e:
        log.error(f"lade_benutzer_profil: {e}")
        return None


def registriere_per_email(
    email: str,
    passwort: str,
    *,
    admin_key: Optional[str] = None,
    rolle: Optional[str] = None,
    invite_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    SaaS-Registrierung per E-Mail (Passwort ≥ 12, bcrypt in DB).

    - **Standard:** eigene Kanzlei pro Signup (``erstelle_kanzlei``) + erste Rolle ``admin``
      (oder ``rolle`` aus dem Request bei neuen Kanzleien).
    - **Einladung:** gültiges ``invite_token`` → Beitritt zu bestehender Kanzlei; Rolle nur aus dem Token.
    """
    e = (email or "").strip().lower()
    if not e or "@" not in e:
        raise ValueError("invalid")
    try:
        _assert_strong_password(passwort, e)
    except ValueError:
        raise ValueError("invalid")
    if email_adresse_bereits_registriert(e):
        raise ValueError("invalid")

    from core.tenant_invites import verify_tenant_invite_token

    inv = verify_tenant_invite_token((invite_token or "").strip()) if invite_token else None

    # Default: Public signup für SaaS-Growth.
    # Invite-only: ohne Token nur mit Admin-Key (außer erster User), wenn ALLOW_PUBLIC_REGISTER=0.
    allow_public = (os.getenv("ALLOW_PUBLIC_REGISTER") or "1").strip().lower() in {"1", "true", "yes", "on"}
    if not inv and not allow_public and hat_irgendein_benutzer():
        import secrets as sc

        expected = (os.getenv("PORTAL_ADMIN_KEY") or "").strip()
        if len(expected) < 20:
            raise ValueError("invalid")
        if not admin_key or not sc.compare_digest((admin_key or "").strip(), expected):
            raise ValueError("invalid")

    if inv:
        kid = inv["kanzlei_id"]
        lock = inv.get("email_lock")
        if lock and lock != e:
            raise ValueError("invalid")
        eff_rolle = inv["role"]
        if not hole_kanzlei(kid):
            raise ValueError("invalid")
    else:
        local = e.split("@", 1)[0][:40]
        tenant = erstelle_kanzlei(name=f"Kanzlei {local}", email=e, plan="starter")
        kid = tenant["kanzlei_id"]
        # Erste/r Nutzer/in einer neuen Kanzlei wird Owner — unabhängig vom UI-Wunsch.
        # Damit gibt es pro Tenant immer genau eine unantastbare Top-Rolle.
        eff_rolle = "owner"

    bname = _interner_benutzername_fuer_email(e)
    row = erstelle_benutzer(bname, passwort, rolle=eff_rolle, email=e, kanzlei_id=kid)
    if inv and inv.get("jti"):
        try:
            from core.tenant_invite_records import invite_record_mark_used

            invite_record_mark_used(jti=str(inv["jti"]), kanzlei_id=str(kid), used_email=e)
        except Exception:
            pass
    return row


def logout(token: str) -> bool:
    session = _session_laden(token) if token else None
    if session:
        user = session.get("benutzername", "?")
        _session_entfernen(token)
        log.info(f"Logout: {user}")
        return True
    return False


def logout_all_user_sessions(benutzername: str, kanzlei_id: str) -> int:
    """
    Invalidiert alle Sessions eines Benutzers innerhalb derselben Kanzlei.
    Rückgabe: Anzahl invalidierter Sessions.
    """
    bname = (benutzername or "").strip()
    kid = (kanzlei_id or "default").strip() or "default"
    if not bname:
        return 0

    removed = 0

    # In-memory sessions
    for token, sess in list(_sessions.items()):
        if str(sess.get("benutzername") or "").strip() == bname and str(sess.get("kanzlei_id") or "default").strip() == kid:
            _sessions.pop(token, None)
            removed += 1

    # Redis sessions
    r = _get_redis()
    if r:
        try:
            for key in r.scan_iter("kanzlei:session:*"):
                raw = r.get(key)
                if not raw:
                    continue
                try:
                    sess = json.loads(raw)
                except Exception:
                    continue
                if str(sess.get("benutzername") or "").strip() == bname and str(sess.get("kanzlei_id") or "default").strip() == kid:
                    r.delete(key)
                    removed += 1
        except Exception:
            pass

    log.info("Logout all sessions: %s | kanzlei=%s | invalidated=%s", bname, kid, removed)
    return removed


def verifiziere_session(token: str) -> Optional[Dict]:
    """Gibt Session-Dict mit kanzlei_id zurück oder None."""
    if not token:
        return None
    session = _session_laden(token)
    if not session:
        return None
    if time.time() > session.get("expires", 0):
        _session_entfernen(token)
        log.debug(f"Session abgelaufen: {session.get('benutzername')}")
        return None
    return session


def sessions_bereinigen():
    """Nur In-Memory — Redis-Sessions laufen per TTL aus."""
    jetzt = time.time()
    abgelaufen = [t for t, s in list(_sessions.items()) if jetzt > s.get("expires", 0)]
    for t in abgelaufen:
        _sessions.pop(t, None)


def aktive_sessions() -> int:
    sessions_bereinigen()
    r = _get_redis()
    if r:
        try:
            return len(r.keys("kanzlei:session:*"))
        except Exception:
            pass
    return len(_sessions)
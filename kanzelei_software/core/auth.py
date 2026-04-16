# ============================================================
# KANZLEI AI — AUTH v4.0
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
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
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


def _verifiziere_passwort(passwort: str, hash_gespeichert: str, salt: str) -> bool:
    # Neuer Standard: bcrypt
    if (salt or "").lower() == "bcrypt" or (hash_gespeichert or "").startswith("$2"):
        try:
            return bcrypt.checkpw(passwort.encode("utf-8"), hash_gespeichert.encode("utf-8"))
        except Exception:
            return False

    # Legacy-Fallback: PBKDF2
    neu_hash = hashlib.pbkdf2_hmac(
        "sha256", passwort.encode("utf-8"), (salt or "").encode("utf-8"),
        iterations=260000,
    ).hex()
    return hmac.compare_digest(neu_hash, hash_gespeichert)


# ═══════════════════════════════════════════════════════════
# DB-SCHEMA (benutzer mit kanzlei_id)
# ═══════════════════════════════════════════════════════════

def _get_conn():
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
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM kanzleien WHERE id = ? AND aktiv = 1", (kanzlei_id,)
    ).fetchone()
    return dict(row) if row else None


def liste_kanzleien() -> list:
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
    try:
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
    try:
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
    if len(passwort) < 8:
        raise ValueError("Passwort muss mindestens 8 Zeichen haben")
    if not benutzername.strip():
        raise ValueError("Benutzername darf nicht leer sein")

    conn = _get_conn()
    rolle_map = {
        "ADMIN": "admin",
        "MITARBEITER": "assistent",
        "admin": "admin",
        "mitarbeiter": "assistent",
        "steuerberater": "steuerberater",
        "assistent": "assistent",
    }
    rolle = rolle_map.get((rolle or "").strip(), "assistent")
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
    return {"benutzername": benutzername, "rolle": rolle, "email": email, "kanzlei_id": kanzlei_id}


def setup_erstbenutzer(
    benutzername: str = "admin",
    passwort: str = "Admin2024!",
    kanzlei_id: str = "default",
) -> bool:
    """Erstellt Standard-Admin wenn noch kein Benutzer existiert."""
    if hat_irgendein_benutzer():
        return False
    try:
        erstelle_benutzer(benutzername, passwort, rolle="admin", kanzlei_id=kanzlei_id)
        log.info(f"Erstbenutzer angelegt: {benutzername} in Kanzlei {kanzlei_id}")
        return True
    except Exception as e:
        log.error(f"Erstbenutzer fehlgeschlagen: {e}")
        return False


def liste_benutzer(kanzlei_id: str = "default") -> list:
    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT benutzername, rolle, email, aktiv, erstellt_am, letzter_login "
            "FROM benutzer WHERE kanzlei_id = ? ORDER BY benutzername",
            (kanzlei_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        log.error(f"liste_benutzer: {e}")
        return []


def aendere_passwort(
    benutzername: str, altes_passwort: str, neues_passwort: str,
    kanzlei_id: str = "default",
) -> bool:
    if len(neues_passwort) < 8:
        raise ValueError("Neues Passwort muss mindestens 8 Zeichen haben")
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


def benutzer_deaktivieren(benutzername: str, kanzlei_id: str = "default") -> bool:
    try:
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

    try:
        conn = _get_conn()
        row = conn.execute(
            "SELECT * FROM benutzer WHERE benutzername = ? AND aktiv = 1",
            (benutzername,)
        ).fetchone()
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
    _session_speichern(token, {
        "benutzername": benutzername,
        "kanzlei_id":   kanzlei_id,
        "rolle":        row["rolle"],
        "email":        row["email"] or "",
        "expires":      expires.timestamp(),
        "ip":           ip,
    })

    try:
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
        "token":        token,
        "benutzername": benutzername,
        "kanzlei_id":   kanzlei_id,
        "rolle":        row["rolle"],
        "expires":      expires.isoformat(),
    }


def logout(token: str) -> bool:
    session = _session_laden(token) if token else None
    if session:
        user = session.get("benutzername", "?")
        _session_entfernen(token)
        log.info(f"Logout: {user}")
        return True
    return False


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
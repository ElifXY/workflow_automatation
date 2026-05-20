# ============================================================
# KANZLEI AI — DATENSPEICHER v4.0
# SQLite (Dev) — Multi-Kanzlei, Thread-safe
#
# Bei DATABASE_URL=postgresql://… (pg_primary_db):
#   API-Keys, Webhooks, Webhook-Queue, Usage-Metriken, Email-Outbox, agent_actions
#   werden auf PostgreSQL geführt (scripts/postgres_bootstrap.sql + init_pg).
#
# PRODUCTION (ENVIRONMENT=production):
#   SQLite nur noch mit explizitem Übergang (ALLOW_SQLITE_FALLBACK) für nicht migrierte
#   Domänen; Mandanten auf PG mit USE_POSTGRES_DATA=1 + DATABASE_URL.
#
# ARCHITEKTUR:
#   1 DB + kanzlei_id in Tabellen — Kanzlei A sieht keine Daten von Kanzlei B.
# ============================================================

import os
from pathlib import Path
import sqlite3
import json
import logging
import threading
import time
import uuid
import hashlib
import secrets
from copy import deepcopy
from contextlib import contextmanager
from datetime import date, datetime
from typing import Dict, List, Optional, Any, Tuple

from core.pg_runtime import pg_primary_db

log = logging.getLogger("kanzlei_db")

_BASE_DIR = Path(__file__).resolve().parents[1]
_raw_data_dir = (os.getenv("DATA_DIR") or "").strip()
if _raw_data_dir:
    _data_dir_candidate = Path(_raw_data_dir)
    if not _data_dir_candidate.is_absolute():
        _data_dir_candidate = (_BASE_DIR / _data_dir_candidate).resolve()
    _DATA_DIR = _data_dir_candidate
else:
    _DATA_DIR = (_BASE_DIR / "data").resolve()
DB_PFAD = str((_DATA_DIR / "kanzlei.db").resolve())
DEFAULT_KID = "default"   # Bestehende Daten

_local = threading.local()
_pg_sqlite_warned = False
_pg_hybrid_logged = False
_pg_dokumente_table_known: Optional[bool] = None


def _postgres_data_flag_on() -> bool:
    return (os.getenv("USE_POSTGRES_DATA") or "").strip().lower() in ("1", "true", "yes")


def _allow_sqlite_fallback() -> bool:
    """Nur für Übergang: Production + PostgreSQL-DSN erlaubt sonst kein SQLite in get_connection."""
    return (os.getenv("ALLOW_SQLITE_FALLBACK") or "").strip().lower() in ("1", "true", "yes")


def _pg_mandanten_mode() -> bool:
    """
    True: Mandanten-CRUD läuft über PostgreSQL (USE_POSTGRES_DATA + DATABASE_URL).
    Wirft, wenn Flag gesetzt ist, aber keine Postgres-DSN konfiguriert ist.
    """
    if not _postgres_data_flag_on():
        return False
    if not pg_primary_db():
        raise RuntimeError(
            "USE_POSTGRES_DATA ist gesetzt: DATABASE_URL muss postgresql://… oder postgres://… sein "
            "(Schema scripts/postgres_bootstrap.sql, Daten scripts/migrate_sqlite_to_postgres.py)."
        )
    return True


def _pg_conn():
    """Gemeinsame Thread-lokale PG-Verbindung (core.pg_runtime)."""
    from core.pg_runtime import get_pg_connection

    return get_pg_connection()


_pg_saas_schema_lock = threading.Lock()
_pg_saas_schema_ready = False


def _pg_saas_backend() -> bool:
    """True: SaaS-/Metering-Tabellen liegen in PostgreSQL (dieselbe DATABASE_URL)."""
    return pg_primary_db()


def _pg_saas_ddl_statements() -> Tuple[str, ...]:
    """Idempotente DDL für Hilfstabellen (Outbox + SaaS), falls noch nicht aus Bootstrap."""
    return (
        """
        INSERT INTO kanzleien (id, name, email, plan, aktiv)
        VALUES ('default', 'Standard-Kanzlei', '', 'starter', 1)
        ON CONFLICT (id) DO NOTHING
        """,
        """
        CREATE TABLE IF NOT EXISTS email_outbox (
            id BIGSERIAL PRIMARY KEY,
            kanzlei_id TEXT NOT NULL REFERENCES kanzleien(id),
            mandant TEXT NOT NULL,
            to_email TEXT NOT NULL,
            subject TEXT NOT NULL,
            body_text TEXT NOT NULL,
            body_html TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 5,
            next_attempt_at TIMESTAMPTZ DEFAULT NOW(),
            last_error TEXT DEFAULT '',
            idempotency_key TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            sent_at TIMESTAMPTZ
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_email_outbox_idem
            ON email_outbox (kanzlei_id, idempotency_key)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_email_outbox_due
            ON email_outbox (status, next_attempt_at, kanzlei_id)
        """,
        """
        CREATE TABLE IF NOT EXISTS tenant_invite_records (
            id BIGSERIAL PRIMARY KEY,
            kanzlei_id TEXT NOT NULL REFERENCES kanzleien(id),
            jti TEXT NOT NULL UNIQUE,
            role TEXT NOT NULL DEFAULT 'assistent',
            email_lock TEXT,
            target_email TEXT,
            invited_by TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at BIGINT NOT NULL,
            revoked_at TIMESTAMPTZ,
            used_at TIMESTAMPTZ,
            used_email TEXT,
            email_outbox_id BIGINT,
            email_queued_at TIMESTAMPTZ,
            email_sent_at TIMESTAMPTZ
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_tenant_invite_records_kid ON tenant_invite_records (kanzlei_id, id DESC)",
        "ALTER TABLE tenant_invite_records ADD COLUMN IF NOT EXISTS email_queued_at TIMESTAMPTZ",
        """
        CREATE TABLE IF NOT EXISTS api_keys (
            id TEXT PRIMARY KEY,
            kanzlei_id TEXT NOT NULL REFERENCES kanzleien(id),
            name TEXT NOT NULL,
            key_hash TEXT NOT NULL,
            permissions_json TEXT NOT NULL DEFAULT '[]',
            aktiv INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_used_at TIMESTAMPTZ
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_api_keys_kid ON api_keys (kanzlei_id, aktiv)",
        """
        CREATE TABLE IF NOT EXISTS webhook_endpoints (
            id TEXT PRIMARY KEY,
            kanzlei_id TEXT NOT NULL REFERENCES kanzleien(id),
            url TEXT NOT NULL,
            secret TEXT NOT NULL,
            events_json TEXT NOT NULL DEFAULT '[]',
            aktiv INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_status TEXT DEFAULT '',
            last_error TEXT DEFAULT '',
            last_sent_at TIMESTAMPTZ
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_webhook_endpoints_kid ON webhook_endpoints (kanzlei_id, aktiv)",
        """
        CREATE TABLE IF NOT EXISTS webhook_queue (
            id BIGSERIAL PRIMARY KEY,
            kanzlei_id TEXT NOT NULL REFERENCES kanzleien(id),
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_error TEXT DEFAULT ''
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_webhook_queue_due ON webhook_queue (status, next_attempt_at, kanzlei_id)",
        """
        CREATE TABLE IF NOT EXISTS usage_metrics (
            kanzlei_id TEXT NOT NULL REFERENCES kanzleien(id),
            metric TEXT NOT NULL,
            day TEXT NOT NULL,
            value INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (kanzlei_id, metric, day)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_usage_metric_day ON usage_metrics (metric, day)",
        """
        CREATE TABLE IF NOT EXISTS agent_actions (
            id BIGSERIAL PRIMARY KEY,
            kanzlei_id TEXT NOT NULL REFERENCES kanzleien(id),
            action_key TEXT NOT NULL,
            mandant TEXT NOT NULL,
            aktion TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'planned',
            details TEXT DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (kanzlei_id, action_key)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_agent_actions_time ON agent_actions (kanzlei_id, created_at)",
        """
        CREATE TABLE IF NOT EXISTS agent_locks (
            name        TEXT PRIMARY KEY,
            owner       TEXT NOT NULL,
            expires_at  BIGINT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS einstellungen (
            kanzlei_id TEXT NOT NULL REFERENCES kanzleien(id),
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            geaendert_am TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (kanzlei_id, key)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS portal_records (
            id TEXT PRIMARY KEY,
            kanzlei_id TEXT NOT NULL REFERENCES kanzleien(id),
            typ TEXT NOT NULL,
            mandant TEXT NOT NULL,
            status TEXT DEFAULT '',
            data_json TEXT NOT NULL,
            erstellt_am TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            geaendert_am TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_portal_kid_typ
            ON portal_records (kanzlei_id, typ, mandant)
        """,
    )


def _init_db_postgresql() -> None:
    """Legt Hilfs-/SaaS-Tabellen in PostgreSQL an (ohne SQLite)."""
    global _pg_saas_schema_ready
    if not pg_primary_db():
        return
    with _pg_saas_schema_lock:
        if _pg_saas_schema_ready:
            return
        conn = _pg_conn()
        try:
            with conn.cursor() as cur:
                for stmt in _pg_saas_ddl_statements():
                    cur.execute(stmt)
            conn.commit()
            _pg_saas_schema_ready = True
            log.info("PostgreSQL SaaS-/Outbox-Tabellen geprüft bzw. angelegt.")
        except Exception:
            conn.rollback()
            raise


def _pg_normalize_row_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    for k, v in list(out.items()):
        if isinstance(v, (datetime, date)):
            out[k] = v.isoformat()
    return out


def _pg_ts_to_naive_datetime(val: Any) -> Optional[datetime]:
    """Für Tage-Berechnung: Postgres-Timestamp/date oder ISO-String → naive datetime."""
    if val is None:
        return None
    if isinstance(val, datetime):
        t = val
    elif isinstance(val, date):
        t = datetime.combine(val, datetime.min.time())
    else:
        s = str(val).replace("Z", "+00:00")
        t = datetime.fromisoformat(s)
    if t.tzinfo is not None:
        t = t.replace(tzinfo=None)
    return t


def _fehlende_dokumente_pg(kanzlei_id: str, mandant: str) -> List[str]:
    """Offene Dokumente aus PostgreSQL, falls Tabelle `dokumente` existiert; sonst []."""
    global _pg_dokumente_table_known
    conn = _pg_conn()
    with conn.cursor() as cur:
        if _pg_dokumente_table_known is None:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'dokumente'
                ) AS e
                """
            )
            _pg_dokumente_table_known = bool(cur.fetchone()["e"])
        if not _pg_dokumente_table_known:
            return []
        cur.execute(
            """
            SELECT name FROM dokumente
            WHERE kanzlei_id = %s AND mandant = %s AND status = 'ausstehend'
            """,
            (kanzlei_id, mandant),
        )
        return [r["name"] for r in cur.fetchall()]

_COMPAT_SECTION_DEFAULTS: Dict[str, Any] = {
    "belege": {},
    "rechnungen": {},
    "rechnungs_zaehler": {},
    "bot_fragen": {},
    "steuerfaelle": {},
    "finanzierungen": {},
    "workflow_regeln": {},
    "workflow_runs": {},
    "zeiterfassung": {"eintraege": {}, "laufend": {}},
    "lohnabrechnung": {"mitarbeiter": {}, "abrechnungen": {}, "zeitdaten": {}},
}


def get_connection(kanzlei_id: str = DEFAULT_KID) -> sqlite3.Connection:
    """Thread-lokale Connection. Jeder Thread hat seine eigene."""
    global _pg_sqlite_warned, _pg_hybrid_logged
    if (os.getenv("POSTGRES_ONLY_DATA") or "").strip().lower() in ("1", "true", "yes"):
        raise RuntimeError(
            "POSTGRES_ONLY_DATA=1: SQLite get_connection ist deaktiviert. "
            "Vollständige PostgreSQL-Migration für alle Domänen erforderlich (oder Flag entfernen)."
        )
    environment = (os.getenv("ENVIRONMENT") or os.getenv("APP_ENV") or "development").lower()
    if (
        environment == "production"
        and pg_primary_db()
        and not _allow_sqlite_fallback()
    ):
        raise RuntimeError(
            "Production mit DATABASE_URL=PostgreSQL: SQLite get_connection ist deaktiviert. "
            "Nur PostgreSQL-Datenpfad nutzen oder temporär ALLOW_SQLITE_FALLBACK=1 setzen."
        )
    if environment == "production" and not _pg_mandanten_mode():
        raise RuntimeError(
            "SQLite ist in Production deaktiviert. Setze USE_POSTGRES_DATA=1 und "
            "DATABASE_URL=postgresql://… (siehe docker-compose.yml beim Service api), oder "
            "für reine Test-Umgebungen ENVIRONMENT=development. "
            f"Aktuell: USE_POSTGRES_DATA={os.getenv('USE_POSTGRES_DATA')!r}, "
            f"DATABASE_URL ist Postgres-DSN: {pg_primary_db()!r}."
        )
    if _pg_mandanten_mode():
        if not _pg_hybrid_logged:
            log.warning(
                "Hybrid-Datenhaltung: Mandanten auf PostgreSQL, übrige Domänen auf SQLite (%s).",
                DB_PFAD,
            )
            _pg_hybrid_logged = True
    elif pg_primary_db() and not _pg_sqlite_warned:
        log.warning(
            "DATABASE_URL ist PostgreSQL: API-Keys/Webhooks/Outbox/Usage liegen auf Postgres; "
            "Mandanten/Belege ggf. weiter SQLite (%s) ohne vollständige Migration.",
            DB_PFAD,
        )
        _pg_sqlite_warned = True
    if not hasattr(_local, "conn") or _local.conn is None:
        os.makedirs(os.path.dirname(DB_PFAD), exist_ok=True)
        conn = sqlite3.connect(DB_PFAD, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            # Einige Runtime-Umgebungen erlauben kein Journal-Mode-Umschalten
            # (z. B. eingeschränkte Volume-Flags). In diesem Fall laufen wir
            # mit dem SQLite-Default weiter statt die komplette API zu blockieren.
            try:
                conn.execute("PRAGMA journal_mode=DELETE")
            except sqlite3.OperationalError:
                log.warning("SQLite journal_mode konnte nicht gesetzt werden (%s). Nutze Default.", DB_PFAD)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        _local.conn = conn
    return _local.conn


@contextmanager
def db_transaction(kanzlei_id: str = DEFAULT_KID):
    conn = get_connection(kanzlei_id)
    try:
        # In SQLite kann ein tenant-spezifischer Write an FK (kanzleien.id) scheitern,
        # wenn die Kanzlei-Zeile noch nicht existiert. Daher pro Transaktion idempotent absichern.
        conn.execute(
            "INSERT OR IGNORE INTO kanzleien (id, name, email, plan, aktiv) VALUES (?, ?, '', 'starter', 1)",
            (kanzlei_id, f"Kanzlei {kanzlei_id}"),
        )
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        log.error(f"DB Transaction Fehler: {e}")
        raise


def init_db():
    """Schema initialisieren — kanzlei_id in allen Tabellen."""
    if pg_primary_db():
        try:
            _init_db_postgresql()
        except Exception as e:
            # Bei mehreren Uvicorn-Workern kann PG-DDL beim parallelen Start kurz kollidieren.
            # API darf daran nicht scheitern; SQLite-Schema bleibt für Kern-Domänen Pflicht.
            log.warning("PG-Schema-Init übersprungen/fehlgeschlagen: %s", e)
        if (os.getenv("POSTGRES_ONLY_DATA") or "").strip().lower() in ("1", "true", "yes"):
            return

    environment = (os.getenv("ENVIRONMENT") or os.getenv("APP_ENV") or "development").lower()
    # Wie get_connection(): striktes Production + Postgres ohne ALLOW_SQLITE_FALLBACK → kein SQLite-DDL
    if (
        environment == "production"
        and pg_primary_db()
        and not _allow_sqlite_fallback()
    ):
        return
    if environment == "production" and not _postgres_data_flag_on():
        raise RuntimeError(
            "ENVIRONMENT=production: USE_POSTGRES_DATA muss 1/true/yes sein (Docker: "
            "docker-compose.yml setzt das beim api-Service). Prüfe eine veraltete compose-Datei "
            "oder entferne USE_POSTGRES_DATA=0 aus der Server-.env."
        )

    conn = get_connection()
    conn.executescript("""
        -- ── Kanzleien (Master-Tabelle) ──────────────────────
        CREATE TABLE IF NOT EXISTS kanzleien (
            id              TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            email           TEXT DEFAULT '',
            plan            TEXT DEFAULT 'starter',
            aktiv           INTEGER DEFAULT 1,
            erstellt_am     TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- Default-Kanzlei für Migration bestehender Daten
        INSERT OR IGNORE INTO kanzleien (id, name) VALUES ('default', 'Standard-Kanzlei');

        -- ── Benutzer ────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS benutzer (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            kanzlei_id      TEXT NOT NULL DEFAULT 'default' REFERENCES kanzleien(id),
            benutzername    TEXT NOT NULL,
            hash            TEXT NOT NULL,
            salt            TEXT NOT NULL,
            rolle           TEXT DEFAULT 'assistent' CHECK(rolle IN ('admin','steuerberater','assistent')),
            email           TEXT DEFAULT '',
            aktiv           INTEGER DEFAULT 1,
            erstellt_am     TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(kanzlei_id, benutzername)
        );

        -- ── Mandanten ───────────────────────────────────────
        CREATE TABLE IF NOT EXISTS mandanten (
            id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4)))),
            kanzlei_id      TEXT NOT NULL DEFAULT 'default' REFERENCES kanzleien(id),
            name            TEXT NOT NULL,
            email           TEXT DEFAULT '',
            telefon         TEXT DEFAULT '',
            branche         TEXT DEFAULT '',
            umsatz          REAL DEFAULT 0,
            notizen         TEXT DEFAULT '',
            steuer_id       TEXT DEFAULT '',
            adresse         TEXT DEFAULT '',
            letzte_antwort  TEXT,
            letzte_email    TEXT,
            erstellt_am     TEXT NOT NULL DEFAULT (datetime('now')),
            aktiv           INTEGER DEFAULT 1,
            UNIQUE(kanzlei_id, name)
        );

        -- ── Aufgaben ────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS aufgaben (
            id              TEXT PRIMARY KEY,
            kanzlei_id      TEXT NOT NULL DEFAULT 'default',
            mandant         TEXT NOT NULL,
            beschreibung    TEXT NOT NULL,
            frist           TEXT NOT NULL,
            frist_uhrzeit   TEXT DEFAULT '',
            prioritaet      TEXT DEFAULT 'normal' CHECK(prioritaet IN ('niedrig','normal','hoch','kritisch')),
            kategorie       TEXT DEFAULT 'allgemein',
            erledigt        INTEGER DEFAULT 0,
            erledigt_am     TEXT,
            zugewiesen_an   TEXT DEFAULT '',
            notiz           TEXT DEFAULT '',
            quelle          TEXT DEFAULT 'manuell',
            erstellt_am     TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- ── Dokumente ───────────────────────────────────────
        CREATE TABLE IF NOT EXISTS dokumente (
            id              TEXT PRIMARY KEY,
            kanzlei_id      TEXT NOT NULL DEFAULT 'default',
            mandant         TEXT NOT NULL,
            name            TEXT NOT NULL,
            typ             TEXT DEFAULT 'sonstiges',
            status          TEXT DEFAULT 'ausstehend',
            beschreibung    TEXT DEFAULT '',
            angefordert_am  TEXT,
            erhalten_am     TEXT,
            erstellt_am     TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- ── Kommunikation / Timeline ────────────────────────
        CREATE TABLE IF NOT EXISTS kommunikation (
            id              TEXT PRIMARY KEY,
            kanzlei_id      TEXT NOT NULL DEFAULT 'default',
            mandant         TEXT NOT NULL,
            typ             TEXT NOT NULL,
            text            TEXT NOT NULL,
            richtung        TEXT DEFAULT 'ausgehend',
            erstellt_am     TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- ── Belege ──────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS belege (
            id              TEXT PRIMARY KEY,
            kanzlei_id      TEXT NOT NULL DEFAULT 'default',
            mandant         TEXT NOT NULL,
            dateiname       TEXT NOT NULL,
            typ             TEXT DEFAULT 'ausgabe',
            status          TEXT DEFAULT 'neu',
            lieferant       TEXT DEFAULT '',
            betrag_brutto   REAL DEFAULT 0,
            betrag_netto    REAL DEFAULT 0,
            mwst_satz       INTEGER DEFAULT 19,
            mwst_betrag     REAL DEFAULT 0,
            kategorie       TEXT DEFAULT 'sonstiges',
            kategorie_name  TEXT DEFAULT '',
            skr03_konto     TEXT DEFAULT '',
            datum           TEXT DEFAULT '',
            ki_konfidenz    REAL DEFAULT 0,
            notiz           TEXT DEFAULT '',
            erstellt_am     TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- ── Rechnungen ──────────────────────────────────────
        CREATE TABLE IF NOT EXISTS rechnungen (
            id              TEXT PRIMARY KEY,
            kanzlei_id      TEXT NOT NULL DEFAULT 'default',
            mandant         TEXT NOT NULL,
            rechnungsnummer TEXT NOT NULL,
            status          TEXT DEFAULT 'offen',
            gesamt_netto    REAL DEFAULT 0,
            gesamt_brutto   REAL DEFAULT 0,
            mwst_betrag     REAL DEFAULT 0,
            datum           TEXT NOT NULL,
            faellig_bis     TEXT NOT NULL,
            bezahlt_am      TEXT,
            positionen      TEXT DEFAULT '[]',
            erstellt_am     TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(kanzlei_id, rechnungsnummer)
        );

        -- ── Audit Log (unveränderbar, alle Kanzleien) ───────
        CREATE TABLE IF NOT EXISTS audit_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            kanzlei_id      TEXT NOT NULL DEFAULT 'default',
            aktion          TEXT NOT NULL,
            benutzer        TEXT DEFAULT 'system',
            details         TEXT DEFAULT '',
            ip_adresse      TEXT DEFAULT '',
            zeitpunkt       TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- ── Einstellungen (pro Kanzlei) ─────────────────────
        CREATE TABLE IF NOT EXISTS einstellungen (
            kanzlei_id      TEXT NOT NULL DEFAULT 'default',
            key             TEXT NOT NULL,
            value           TEXT NOT NULL,
            geaendert_am    TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (kanzlei_id, key)
        );

        -- ── Portal (Uploads, Unterschriften, Freigaben) ───────
        CREATE TABLE IF NOT EXISTS portal_records (
            id              TEXT PRIMARY KEY,
            kanzlei_id      TEXT NOT NULL DEFAULT 'default',
            typ             TEXT NOT NULL,
            mandant         TEXT NOT NULL,
            status          TEXT DEFAULT '',
            data_json       TEXT NOT NULL,
            erstellt_am     TEXT NOT NULL DEFAULT (datetime('now')),
            geaendert_am    TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- ── Email Outbox (Retry/Backoff/Idempotenz) ──────────
        CREATE TABLE IF NOT EXISTS email_outbox (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            kanzlei_id      TEXT NOT NULL DEFAULT 'default',
            mandant         TEXT NOT NULL,
            to_email        TEXT NOT NULL,
            subject         TEXT NOT NULL,
            body_text       TEXT NOT NULL,
            body_html       TEXT DEFAULT '',
            status          TEXT NOT NULL DEFAULT 'pending',
            attempts        INTEGER NOT NULL DEFAULT 0,
            max_attempts    INTEGER NOT NULL DEFAULT 5,
            next_attempt_at TEXT DEFAULT (datetime('now')),
            last_error      TEXT DEFAULT '',
            idempotency_key TEXT NOT NULL,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            sent_at         TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_email_outbox_idem
            ON email_outbox(kanzlei_id, idempotency_key);
        CREATE INDEX IF NOT EXISTS idx_email_outbox_due
            ON email_outbox(status, next_attempt_at, kanzlei_id);

        -- ── Mandanten-Einladungen (Audit / Revoke) ───────────
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
        );
        CREATE INDEX IF NOT EXISTS idx_tenant_invite_records_kid
            ON tenant_invite_records(kanzlei_id, id DESC);

        -- ── Usage Metering (Quotas pro Tag) ─────────────────
        CREATE TABLE IF NOT EXISTS usage_metrics (
            kanzlei_id      TEXT NOT NULL,
            metric          TEXT NOT NULL,
            day             TEXT NOT NULL,
            value           INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (kanzlei_id, metric, day)
        );

        -- ── API Keys (Machine-to-Machine) ────────────────────
        CREATE TABLE IF NOT EXISTS api_keys (
            id              TEXT PRIMARY KEY,
            kanzlei_id      TEXT NOT NULL DEFAULT 'default',
            name            TEXT NOT NULL,
            key_hash        TEXT NOT NULL,
            permissions_json TEXT NOT NULL DEFAULT '[]',
            aktiv           INTEGER NOT NULL DEFAULT 1,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            last_used_at    TEXT
        );

        -- ── Webhooks (Tenant scoped) ─────────────────────────
        CREATE TABLE IF NOT EXISTS webhook_endpoints (
            id              TEXT PRIMARY KEY,
            kanzlei_id      TEXT NOT NULL DEFAULT 'default',
            url             TEXT NOT NULL,
            secret          TEXT NOT NULL,
            events_json     TEXT NOT NULL DEFAULT '[]',
            aktiv           INTEGER NOT NULL DEFAULT 1,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            last_status     TEXT DEFAULT '',
            last_error      TEXT DEFAULT '',
            last_sent_at    TEXT
        );
        CREATE TABLE IF NOT EXISTS webhook_queue (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            kanzlei_id      TEXT NOT NULL DEFAULT 'default',
            event_type      TEXT NOT NULL,
            payload_json    TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'pending',
            attempts        INTEGER NOT NULL DEFAULT 0,
            next_attempt_at TEXT DEFAULT (datetime('now')),
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            last_error      TEXT DEFAULT ''
        );

        -- ── Auto-Agent Action Log (Idempotenz) ───────────────
        CREATE TABLE IF NOT EXISTS agent_actions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            kanzlei_id      TEXT NOT NULL DEFAULT 'default',
            action_key      TEXT NOT NULL,
            mandant         TEXT NOT NULL,
            aktion          TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'planned',
            details         TEXT DEFAULT '',
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_action_key
            ON agent_actions(kanzlei_id, action_key);

        CREATE TABLE IF NOT EXISTS agent_locks (
            name        TEXT PRIMARY KEY,
            owner       TEXT NOT NULL,
            expires_at  INTEGER NOT NULL
        );

        -- ── Next Cut: Domain-Tabellen statt compat::* JSON ───
        CREATE TABLE IF NOT EXISTS workflow_rules_v2 (
            id              TEXT PRIMARY KEY,
            kanzlei_id      TEXT NOT NULL DEFAULT 'default',
            name            TEXT NOT NULL DEFAULT '',
            aktiv           INTEGER NOT NULL DEFAULT 1,
            trigger_type    TEXT DEFAULT '',
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
            data_json       TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS bot_questions_v2 (
            id              TEXT PRIMARY KEY,
            kanzlei_id      TEXT NOT NULL DEFAULT 'default',
            mandant         TEXT NOT NULL DEFAULT '',
            status          TEXT NOT NULL DEFAULT 'offen',
            frage_typ       TEXT DEFAULT 'sonstiges',
            erstellt_am     TEXT NOT NULL DEFAULT (datetime('now')),
            ablaeuft_am     TEXT DEFAULT '',
            data_json       TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS time_entries_v2 (
            id              TEXT PRIMARY KEY,
            kanzlei_id      TEXT NOT NULL DEFAULT 'default',
            mitarbeiter     TEXT NOT NULL DEFAULT '',
            mandant         TEXT NOT NULL DEFAULT '',
            start_at        TEXT NOT NULL DEFAULT '',
            end_at          TEXT DEFAULT '',
            status          TEXT NOT NULL DEFAULT 'closed',
            data_json       TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS time_running_v2 (
            kanzlei_id      TEXT NOT NULL DEFAULT 'default',
            mitarbeiter     TEXT NOT NULL,
            zeit_id         TEXT NOT NULL,
            started_at      TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (kanzlei_id, mitarbeiter)
        );

        CREATE TABLE IF NOT EXISTS steuerfaelle_v2 (
            id              TEXT PRIMARY KEY,
            kanzlei_id      TEXT NOT NULL DEFAULT 'default',
            mandant         TEXT NOT NULL DEFAULT '',
            jahr            INTEGER NOT NULL DEFAULT 0,
            steuerart       TEXT NOT NULL DEFAULT '',
            status          TEXT NOT NULL DEFAULT '',
            konfidenz_score REAL DEFAULT 0,
            erstellt_am     TEXT NOT NULL DEFAULT (datetime('now')),
            data_json       TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS finanzierungen_v2 (
            id              TEXT PRIMARY KEY,
            kanzlei_id      TEXT NOT NULL DEFAULT 'default',
            mandant         TEXT NOT NULL DEFAULT '',
            status          TEXT NOT NULL DEFAULT 'offen',
            steuerart       TEXT DEFAULT '',
            betrag          REAL DEFAULT 0,
            erstellt_am     TEXT NOT NULL DEFAULT (datetime('now')),
            data_json       TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS payroll_employees_v2 (
            id              TEXT PRIMARY KEY,
            kanzlei_id      TEXT NOT NULL DEFAULT 'default',
            mandant         TEXT NOT NULL DEFAULT '',
            name            TEXT NOT NULL DEFAULT '',
            aktiv           INTEGER NOT NULL DEFAULT 1,
            eintritt        TEXT DEFAULT '',
            erstellt_am     TEXT NOT NULL DEFAULT (datetime('now')),
            data_json       TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS payroll_time_v2 (
            id              TEXT PRIMARY KEY,
            kanzlei_id      TEXT NOT NULL DEFAULT 'default',
            ma_id           TEXT NOT NULL DEFAULT '',
            monat           TEXT NOT NULL DEFAULT '',
            importiert_am   TEXT NOT NULL DEFAULT (datetime('now')),
            data_json       TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS payroll_runs_v2 (
            id              TEXT PRIMARY KEY,
            kanzlei_id      TEXT NOT NULL DEFAULT 'default',
            ma_id           TEXT NOT NULL DEFAULT '',
            mandant         TEXT NOT NULL DEFAULT '',
            monat           TEXT NOT NULL DEFAULT '',
            status          TEXT NOT NULL DEFAULT 'berechnet',
            berechnet_am    TEXT NOT NULL DEFAULT (datetime('now')),
            data_json       TEXT NOT NULL
        );

        -- ── Performance-Indizes ──────────────────────────────
        CREATE INDEX IF NOT EXISTS idx_mandanten_kanzlei   ON mandanten(kanzlei_id);
        CREATE INDEX IF NOT EXISTS idx_aufgaben_kanzlei    ON aufgaben(kanzlei_id, mandant);
        CREATE INDEX IF NOT EXISTS idx_aufgaben_frist      ON aufgaben(frist);
        CREATE INDEX IF NOT EXISTS idx_aufgaben_erledigt   ON aufgaben(erledigt);
        CREATE INDEX IF NOT EXISTS idx_kommunikation_kid   ON kommunikation(kanzlei_id, mandant);
        CREATE INDEX IF NOT EXISTS idx_belege_kanzlei      ON belege(kanzlei_id, mandant);
        CREATE INDEX IF NOT EXISTS idx_rechnungen_kanzlei  ON rechnungen(kanzlei_id);
        CREATE INDEX IF NOT EXISTS idx_audit_kanzlei       ON audit_log(kanzlei_id, zeitpunkt);
        CREATE INDEX IF NOT EXISTS idx_portal_typ_mandant  ON portal_records(kanzlei_id, typ, mandant);
        CREATE INDEX IF NOT EXISTS idx_portal_status       ON portal_records(kanzlei_id, typ, status);
        CREATE INDEX IF NOT EXISTS idx_agent_actions_time  ON agent_actions(kanzlei_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_usage_metric_day    ON usage_metrics(metric, day);
        CREATE INDEX IF NOT EXISTS idx_api_keys_kid        ON api_keys(kanzlei_id, aktiv);
        CREATE INDEX IF NOT EXISTS idx_webhook_endpoints_kid ON webhook_endpoints(kanzlei_id, aktiv);
        CREATE INDEX IF NOT EXISTS idx_webhook_queue_due   ON webhook_queue(status, next_attempt_at, kanzlei_id);
        CREATE INDEX IF NOT EXISTS idx_workflow_rules_v2_kid   ON workflow_rules_v2(kanzlei_id, aktiv, trigger_type);
        CREATE INDEX IF NOT EXISTS idx_bot_questions_v2_kid    ON bot_questions_v2(kanzlei_id, mandant, status);
        CREATE INDEX IF NOT EXISTS idx_time_entries_v2_kid     ON time_entries_v2(kanzlei_id, mitarbeiter, mandant);
        CREATE INDEX IF NOT EXISTS idx_time_entries_v2_start    ON time_entries_v2(start_at);
        CREATE INDEX IF NOT EXISTS idx_steuerfaelle_v2_kid      ON steuerfaelle_v2(kanzlei_id, mandant, jahr, status);
        CREATE INDEX IF NOT EXISTS idx_finanzierungen_v2_kid    ON finanzierungen_v2(kanzlei_id, mandant, status);
        CREATE INDEX IF NOT EXISTS idx_payroll_employees_v2_kid ON payroll_employees_v2(kanzlei_id, mandant, aktiv);
        CREATE INDEX IF NOT EXISTS idx_payroll_time_v2_kid      ON payroll_time_v2(kanzlei_id, ma_id, monat);
        CREATE INDEX IF NOT EXISTS idx_payroll_runs_v2_kid      ON payroll_runs_v2(kanzlei_id, mandant, monat, status);
    """)
    _ensure_sqlite_column(conn, "aufgaben", "frist_uhrzeit", "TEXT DEFAULT ''")
    _ensure_sqlite_column(conn, "aufgaben", "erledigt_am", "TEXT")
    _ensure_sqlite_column(conn, "aufgaben", "portal_sichtbar", "INTEGER DEFAULT 1")
    conn.commit()
    log.info(f"DB initialisiert: {DB_PFAD}")


def _ensure_sqlite_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    """
    Fügt eine Spalte idempotent hinzu.
    `ADD COLUMN IF NOT EXISTS` ist nicht auf allen SQLite-Versionen verfügbar.
    """
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    existing = {str(r[1]).strip().lower() for r in rows if len(r) > 1}
    if column.strip().lower() in existing:
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


class DatenSpeicher:
    """
    Zentrale Datenzugriffsschicht — Multi-Kanzlei-fähig.
    ALLE Methoden filtern nach kanzlei_id.
    Keine Kanzlei sieht Daten einer anderen.
    """

    def __init__(self, kanzlei_id: str = DEFAULT_KID):
        self.kanzlei_id = kanzlei_id
        init_db()

    def _conn(self) -> sqlite3.Connection:
        return get_connection(self.kanzlei_id)

    # ══════════════════════════════════════════════════════════
    # MANDANTEN
    # ══════════════════════════════════════════════════════════

    def hole_mandanten(self) -> Dict[str, Dict]:
        """Nur Mandanten DIESER Kanzlei."""
        if _pg_mandanten_mode():
            conn = _pg_conn()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM mandanten WHERE kanzlei_id = %s AND aktiv = 1 ORDER BY name",
                    (self.kanzlei_id,),
                )
                rows = cur.fetchall()
            result: Dict[str, Dict] = {}
            for r in rows:
                m = _pg_normalize_row_dict(dict(r))
                m["fehlende_dokumente_liste"] = _fehlende_dokumente_pg(self.kanzlei_id, m["name"])
                result[m["name"]] = m
            return result
        rows = self._conn().execute(
            "SELECT * FROM mandanten WHERE kanzlei_id = ? AND aktiv = 1 ORDER BY name",
            (self.kanzlei_id,)
        ).fetchall()
        result = {}
        for r in rows:
            m = dict(r)
            m["fehlende_dokumente_liste"] = self._fehlende_dokumente(m["name"])
            result[m["name"]] = m
        return result


def email_outbox_enqueue(
    *,
    kanzlei_id: str,
    mandant: str,
    to_email: str,
    subject: str,
    body_text: str,
    body_html: str = "",
    idempotency_key: str,
    max_attempts: int = 5,
) -> Dict[str, Any]:
    """
    Legt eine Email in die Outbox.
    Idempotent via (kanzlei_id, idempotency_key).
    """
    if _pg_saas_backend():
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO email_outbox
                    (kanzlei_id, mandant, to_email, subject, body_text, body_html, max_attempts, idempotency_key)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (kanzlei_id, idempotency_key) DO NOTHING
                """,
                (
                    kanzlei_id,
                    mandant,
                    to_email,
                    subject,
                    body_text,
                    body_html or "",
                    max(1, int(max_attempts)),
                    idempotency_key,
                ),
            )
            inserted = cur.rowcount > 0
            cur.execute(
                """
                SELECT id, status, attempts, created_at
                FROM email_outbox
                WHERE kanzlei_id = %s AND idempotency_key = %s
                """,
                (kanzlei_id, idempotency_key),
            )
            row = cur.fetchone()
        conn.commit()
        return {
            "created": inserted,
            "id": int(row["id"]) if row else None,
            "status": row["status"] if row else None,
            "attempts": int(row["attempts"]) if row else 0,
            "created_at": row["created_at"] if row else None,
        }
    conn = get_connection()
    cur = conn.execute("""
        INSERT OR IGNORE INTO email_outbox
            (kanzlei_id, mandant, to_email, subject, body_text, body_html, max_attempts, idempotency_key)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        kanzlei_id, mandant, to_email, subject, body_text, body_html or "",
        max(1, int(max_attempts)), idempotency_key,
    ))
    conn.commit()
    row = conn.execute("""
        SELECT id, status, attempts, created_at
        FROM email_outbox
        WHERE kanzlei_id = ? AND idempotency_key = ?
    """, (kanzlei_id, idempotency_key)).fetchone()
    return {
        "created": cur.rowcount > 0,
        "id": int(row["id"]) if row else None,
        "status": row["status"] if row else None,
        "attempts": int(row["attempts"]) if row else 0,
        "created_at": row["created_at"] if row else None,
    }


def email_outbox_due(limit: int = 20) -> List[Dict[str, Any]]:
    if _pg_saas_backend():
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM email_outbox
                WHERE status IN ('pending', 'failed')
                  AND attempts < max_attempts
                  AND COALESCE(next_attempt_at, NOW()) <= NOW()
                ORDER BY created_at ASC
                LIMIT %s
                """,
                (max(1, int(limit)),),
            )
            rows = cur.fetchall()
        return [_pg_normalize_row_dict(dict(r)) for r in rows]
    conn = get_connection()
    rows = conn.execute("""
        SELECT *
        FROM email_outbox
        WHERE status IN ('pending', 'failed')
          AND attempts < max_attempts
          AND COALESCE(next_attempt_at, datetime('now')) <= datetime('now')
        ORDER BY created_at ASC
        LIMIT ?
    """, (max(1, int(limit)),)).fetchall()
    return [dict(r) for r in rows]


def email_outbox_claim(outbox_id: int) -> bool:
    if _pg_saas_backend():
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE email_outbox
                SET status = 'sending'
                WHERE id = %s
                  AND status IN ('pending', 'failed')
                  AND attempts < max_attempts
                """,
                (int(outbox_id),),
            )
            n = cur.rowcount
        conn.commit()
        return n > 0
    conn = get_connection()
    cur = conn.execute("""
        UPDATE email_outbox
        SET status = 'sending'
        WHERE id = ?
          AND status IN ('pending', 'failed')
          AND attempts < max_attempts
    """, (int(outbox_id),))
    conn.commit()
    return cur.rowcount > 0


def email_outbox_mark_sent(outbox_id: int) -> None:
    if _pg_saas_backend():
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE email_outbox
                SET status = 'sent',
                    sent_at = NOW(),
                    last_error = ''
                WHERE id = %s
                """,
                (int(outbox_id),),
            )
        conn.commit()
        return
    conn = get_connection()
    conn.execute("""
        UPDATE email_outbox
        SET status = 'sent',
            sent_at = datetime('now'),
            last_error = ''
        WHERE id = ?
    """, (int(outbox_id),))
    conn.commit()


def email_outbox_mark_failed(outbox_id: int, err: str) -> None:
    if _pg_saas_backend():
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE email_outbox
                SET attempts = attempts + 1,
                    status = CASE WHEN email_outbox.attempts + 1 >= max_attempts THEN 'dead' ELSE 'failed' END,
                    last_error = %s,
                    next_attempt_at = NOW() + (
                        CASE
                            WHEN email_outbox.attempts <= 0 THEN INTERVAL '1 minute'
                            WHEN email_outbox.attempts = 1 THEN INTERVAL '5 minutes'
                            WHEN email_outbox.attempts = 2 THEN INTERVAL '15 minutes'
                            ELSE INTERVAL '60 minutes'
                        END
                    )
                WHERE id = %s
                """,
                (str(err)[:500], int(outbox_id)),
            )
        conn.commit()
        return
    conn = get_connection()
    conn.execute("""
        UPDATE email_outbox
        SET attempts = attempts + 1,
            status = CASE WHEN attempts + 1 >= max_attempts THEN 'dead' ELSE 'failed' END,
            last_error = ?,
            next_attempt_at = datetime(
                'now',
                CASE
                    WHEN attempts <= 0 THEN '+1 minute'
                    WHEN attempts = 1 THEN '+5 minutes'
                    WHEN attempts = 2 THEN '+15 minutes'
                    ELSE '+60 minutes'
                END
            )
        WHERE id = ?
    """, (str(err)[:500], int(outbox_id)))
    conn.commit()


def email_outbox_recent(kanzlei_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    if _pg_saas_backend():
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, mandant, to_email, subject, status, attempts, max_attempts,
                       created_at, sent_at, last_error
                FROM email_outbox
                WHERE kanzlei_id = %s
                ORDER BY id DESC
                LIMIT %s
                """,
                (kanzlei_id, max(1, int(limit))),
            )
            rows = cur.fetchall()
        return [_pg_normalize_row_dict(dict(r)) for r in rows]
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, mandant, to_email, subject, status, attempts, max_attempts,
               created_at, sent_at, last_error
        FROM email_outbox
        WHERE kanzlei_id = ?
        ORDER BY id DESC
        LIMIT ?
    """, (kanzlei_id, max(1, int(limit)))).fetchall()
    return [dict(r) for r in rows]


def email_outbox_dead_24h_count(kanzlei_id: str) -> int:
    """Anzahl Outbox-Einträge mit Status dead in den letzten 24h (Readiness)."""
    if _pg_saas_backend():
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)::int AS n
                FROM email_outbox
                WHERE kanzlei_id = %s AND status = 'dead'
                  AND created_at >= NOW() - INTERVAL '24 hours'
                """,
                (kanzlei_id,),
            )
            row = cur.fetchone()
        return int(row["n"]) if row else 0
    conn = get_connection()
    row = conn.execute(
        """
        SELECT COUNT(*) AS n FROM email_outbox
        WHERE kanzlei_id = ? AND status = 'dead'
          AND created_at >= datetime('now', '-24 hours')
        """,
        (kanzlei_id,),
    ).fetchone()
    return int(row["n"]) if row else 0


def webhook_queue_failed_24h_count(kanzlei_id: str) -> int:
    """Fehlgeschlagene / tote Webhook-Queue-Einträge in 24h (Readiness)."""
    if _pg_saas_backend():
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)::int AS n
                FROM webhook_queue
                WHERE kanzlei_id = %s AND status IN ('failed', 'dead')
                  AND created_at >= NOW() - INTERVAL '24 hours'
                """,
                (kanzlei_id,),
            )
            row = cur.fetchone()
        return int(row["n"]) if row else 0
    conn = get_connection()
    row = conn.execute(
        """
        SELECT COUNT(*) AS n FROM webhook_queue
        WHERE kanzlei_id = ? AND status IN ('failed', 'dead')
          AND created_at >= datetime('now', '-24 hours')
        """,
        (kanzlei_id,),
    ).fetchone()
    return int(row["n"]) if row else 0


def agent_action_record(
    *,
    kanzlei_id: str,
    action_key: str,
    mandant: str,
    aktion: str,
    status: str = "planned",
    details: str = "",
) -> bool:
    """
    Idempotent: nur erste Erstellung mit action_key gewinnt.
    Rückgabe True = neu reserviert, False = bereits vorhanden.
    """
    if _pg_saas_backend():
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_actions
                    (kanzlei_id, action_key, mandant, aktion, status, details)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (kanzlei_id, action_key) DO NOTHING
                """,
                (kanzlei_id, action_key, mandant, aktion, status, details[:500]),
            )
            n = cur.rowcount
        conn.commit()
        return n > 0
    conn = get_connection()
    cur = conn.execute("""
        INSERT OR IGNORE INTO agent_actions
            (kanzlei_id, action_key, mandant, aktion, status, details)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (kanzlei_id, action_key, mandant, aktion, status, details[:500]))
    conn.commit()
    return cur.rowcount > 0


def agent_action_update(kanzlei_id: str, action_key: str, status: str, details: str = "") -> None:
    if _pg_saas_backend():
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE agent_actions
                SET status = %s, details = %s
                WHERE kanzlei_id = %s AND action_key = %s
                """,
                (status, details[:500], kanzlei_id, action_key),
            )
        conn.commit()
        return
    conn = get_connection()
    conn.execute("""
        UPDATE agent_actions
        SET status = ?, details = ?
        WHERE kanzlei_id = ? AND action_key = ?
    """, (status, details[:500], kanzlei_id, action_key))
    conn.commit()


def agent_actions_list(kanzlei_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Liste Auto-Agent-Aktionen für eine Kanzlei (PostgreSQL oder SQLite)."""
    lim = max(1, min(500, int(limit)))
    kid = str(kanzlei_id or "").strip() or DEFAULT_KID
    if _pg_saas_backend():
        _init_db_postgresql()
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT action_key, mandant, aktion, status, details, created_at
                FROM agent_actions
                WHERE kanzlei_id = %s
                ORDER BY id DESC
                LIMIT %s
                """,
                (kid, lim),
            )
            rows = cur.fetchall()
        return [_pg_normalize_row_dict(dict(r)) for r in rows]
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT action_key, mandant, aktion, status, details, created_at
        FROM agent_actions
        WHERE kanzlei_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (kid, lim),
    ).fetchall()
    return [dict(r) for r in rows]


def agent_lock_try_acquire(owner: str, ttl_seconds: int = 290, lock_name: str = "auto_agent") -> bool:
    """
    Prozessübergreifender Lock (SQLite oder PostgreSQL SaaS-Schema).
    Rückgabe True, wenn dieser ``owner`` die Sperre hält.
    """
    now = int(time.time())
    exp = now + max(30, int(ttl_seconds))
    name = (lock_name or "auto_agent").strip() or "auto_agent"
    own = (owner or "").strip() or "unknown"
    if _pg_saas_backend():
        try:
            _init_db_postgresql()
            conn = _pg_conn()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_locks (name, owner, expires_at)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (name) DO UPDATE SET
                        owner = EXCLUDED.owner,
                        expires_at = EXCLUDED.expires_at
                    WHERE agent_locks.expires_at < %s OR agent_locks.owner = %s
                    """,
                    (name, own, exp, now, own),
                )
            conn.commit()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT owner, expires_at FROM agent_locks WHERE name = %s",
                    (name,),
                )
                row = cur.fetchone()
            return bool(row and row["owner"] == own and int(row["expires_at"]) >= now)
        except Exception as exc:  # noqa: BLE001
            log.warning("agent_lock_try_acquire PG failed: %s", exc)
            try:
                _pg_conn().rollback()
            except Exception:
                pass
            return False
    try:
        conn = get_connection()
    except RuntimeError as exc:
        log.warning("agent_lock_try_acquire: kein SQLite (%s)", exc)
        return False
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_locks (
            name TEXT PRIMARY KEY,
            owner TEXT NOT NULL,
            expires_at INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO agent_locks (name, owner, expires_at)
        VALUES (?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            owner = excluded.owner,
            expires_at = excluded.expires_at
        WHERE agent_locks.expires_at < ? OR agent_locks.owner = ?
        """,
        (name, own, exp, now, own),
    )
    conn.commit()
    row = conn.execute(
        "SELECT owner, expires_at FROM agent_locks WHERE name = ?",
        (name,),
    ).fetchone()
    return bool(row and row["owner"] == own and int(row["expires_at"]) >= now)


def agent_lock_release(owner: str, lock_name: str = "auto_agent") -> None:
    """Lock für ``owner`` freigeben (Ablaufzeit auf 0)."""
    name = (lock_name or "auto_agent").strip() or "auto_agent"
    own = (owner or "").strip() or "unknown"
    if _pg_saas_backend():
        try:
            _init_db_postgresql()
            conn = _pg_conn()
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE agent_locks SET expires_at = 0 WHERE name = %s AND owner = %s",
                    (name, own),
                )
            conn.commit()
        except Exception as exc:  # noqa: BLE001
            log.warning("agent_lock_release PG failed: %s", exc)
            try:
                _pg_conn().rollback()
            except Exception:
                pass
        return
    try:
        conn = get_connection()
    except RuntimeError:
        return
    conn.execute(
        "UPDATE agent_locks SET expires_at = 0 WHERE name = ? AND owner = ?",
        (name, own),
    )
    conn.commit()


def usage_get(kanzlei_id: str, metric: str, day: Optional[str] = None) -> int:
    d = day or datetime.now().strftime("%Y-%m-%d")
    if _pg_saas_backend():
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT value FROM usage_metrics WHERE kanzlei_id = %s AND metric = %s AND day = %s",
                (kanzlei_id, metric, d),
            )
            row = cur.fetchone()
        return int(row["value"]) if row else 0
    conn = get_connection()
    row = conn.execute(
        "SELECT value FROM usage_metrics WHERE kanzlei_id = ? AND metric = ? AND day = ?",
        (kanzlei_id, metric, d),
    ).fetchone()
    return int(row["value"]) if row else 0


def usage_increment(kanzlei_id: str, metric: str, amount: int = 1, day: Optional[str] = None) -> int:
    d = day or datetime.now().strftime("%Y-%m-%d")
    if _pg_saas_backend():
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO usage_metrics (kanzlei_id, metric, day, value)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (kanzlei_id, metric, day) DO UPDATE SET
                    value = usage_metrics.value + EXCLUDED.value
                """,
                (kanzlei_id, metric, d, int(amount)),
            )
        conn.commit()
        return usage_get(kanzlei_id, metric, d)
    conn = get_connection()
    conn.execute("""
        INSERT INTO usage_metrics (kanzlei_id, metric, day, value)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(kanzlei_id, metric, day) DO UPDATE SET
            value = value + excluded.value
    """, (kanzlei_id, metric, d, int(amount)))
    conn.commit()
    return usage_get(kanzlei_id, metric, d)


def api_key_create(kanzlei_id: str, name: str, permissions: Optional[List[str]] = None) -> Dict[str, Any]:
    key_plain = f"ksk_{secrets.token_urlsafe(36)}"
    key_hash = hashlib.sha256(key_plain.encode("utf-8")).hexdigest()
    kid = str(uuid.uuid4())
    if _pg_saas_backend():
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO api_keys (id, kanzlei_id, name, key_hash, permissions_json, aktiv)
                VALUES (%s, %s, %s, %s, %s, 1)
                """,
                (kid, kanzlei_id, name[:120], key_hash, json.dumps(permissions or [])),
            )
        conn.commit()
        return {"id": kid, "key": key_plain}
    conn = get_connection()
    conn.execute("""
        INSERT INTO api_keys (id, kanzlei_id, name, key_hash, permissions_json, aktiv)
        VALUES (?, ?, ?, ?, ?, 1)
    """, (kid, kanzlei_id, name[:120], key_hash, json.dumps(permissions or [])))
    conn.commit()
    return {"id": kid, "key": key_plain}


def api_key_verify(key_plain: str) -> Optional[Dict[str, Any]]:
    if not key_plain:
        return None
    key_hash = hashlib.sha256(key_plain.encode("utf-8")).hexdigest()
    if _pg_saas_backend():
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, kanzlei_id, name, permissions_json
                FROM api_keys
                WHERE key_hash = %s AND aktiv = 1
                LIMIT 1
                """,
                (key_hash,),
            )
            row = cur.fetchone()
            if not row:
                return None
            cur.execute("UPDATE api_keys SET last_used_at = NOW() WHERE id = %s", (row["id"],))
        conn.commit()
        try:
            perms = json.loads(row["permissions_json"] or "[]")
        except Exception:
            perms = []
        return {
            "id": row["id"],
            "kanzlei_id": row["kanzlei_id"],
            "name": row["name"],
            "permissions": perms if isinstance(perms, list) else [],
        }
    conn = get_connection()
    row = conn.execute("""
        SELECT id, kanzlei_id, name, permissions_json
        FROM api_keys
        WHERE key_hash = ? AND aktiv = 1
        LIMIT 1
    """, (key_hash,)).fetchone()
    if not row:
        return None
    conn.execute("UPDATE api_keys SET last_used_at = datetime('now') WHERE id = ?", (row["id"],))
    conn.commit()
    try:
        perms = json.loads(row["permissions_json"] or "[]")
    except Exception:
        perms = []
    return {
        "id": row["id"],
        "kanzlei_id": row["kanzlei_id"],
        "name": row["name"],
        "permissions": perms if isinstance(perms, list) else [],
    }


def api_key_list(kanzlei_id: str) -> List[Dict[str, Any]]:
    if _pg_saas_backend():
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, permissions_json, aktiv, created_at, last_used_at
                FROM api_keys
                WHERE kanzlei_id = %s
                ORDER BY created_at DESC
                """,
                (kanzlei_id,),
            )
            rows = cur.fetchall()
        result = []
        for r in rows:
            rr = _pg_normalize_row_dict(dict(r))
            try:
                perms = json.loads(rr["permissions_json"] or "[]")
            except Exception:
                perms = []
            result.append({
                "id": rr["id"],
                "name": rr["name"],
                "permissions": perms if isinstance(perms, list) else [],
                "aktiv": bool(rr["aktiv"]),
                "created_at": rr["created_at"],
                "last_used_at": rr["last_used_at"],
            })
        return result
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, name, permissions_json, aktiv, created_at, last_used_at
        FROM api_keys
        WHERE kanzlei_id = ?
        ORDER BY created_at DESC
    """, (kanzlei_id,)).fetchall()
    result = []
    for r in rows:
        try:
            perms = json.loads(r["permissions_json"] or "[]")
        except Exception:
            perms = []
        result.append({
            "id": r["id"],
            "name": r["name"],
            "permissions": perms if isinstance(perms, list) else [],
            "aktiv": bool(r["aktiv"]),
            "created_at": r["created_at"],
            "last_used_at": r["last_used_at"],
        })
    return result


def api_key_deactivate(kanzlei_id: str, key_id: str) -> bool:
    if _pg_saas_backend():
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE api_keys SET aktiv = 0 WHERE kanzlei_id = %s AND id = %s",
                (kanzlei_id, key_id),
            )
            n = cur.rowcount
        conn.commit()
        return n > 0
    conn = get_connection()
    cur = conn.execute(
        "UPDATE api_keys SET aktiv = 0 WHERE kanzlei_id = ? AND id = ?",
        (kanzlei_id, key_id),
    )
    conn.commit()
    return cur.rowcount > 0


def api_key_rotate(kanzlei_id: str, key_id: str, new_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if _pg_saas_backend():
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT name, permissions_json
                FROM api_keys
                WHERE kanzlei_id = %s AND id = %s AND aktiv = 1
                """,
                (kanzlei_id, key_id),
            )
            row = cur.fetchone()
        if not row:
            return None
        try:
            perms = json.loads(row["permissions_json"] or "[]")
        except Exception:
            perms = []
        created = api_key_create(
            kanzlei_id=kanzlei_id,
            name=(new_name or row["name"]),
            permissions=perms if isinstance(perms, list) else [],
        )
        api_key_deactivate(kanzlei_id, key_id)
        return {"old_id": key_id, "new_id": created["id"], "key": created["key"]}
    conn = get_connection()
    row = conn.execute("""
        SELECT name, permissions_json
        FROM api_keys
        WHERE kanzlei_id = ? AND id = ? AND aktiv = 1
    """, (kanzlei_id, key_id)).fetchone()
    if not row:
        return None
    try:
        perms = json.loads(row["permissions_json"] or "[]")
    except Exception:
        perms = []
    created = api_key_create(
        kanzlei_id=kanzlei_id,
        name=(new_name or row["name"]),
        permissions=perms if isinstance(perms, list) else [],
    )
    api_key_deactivate(kanzlei_id, key_id)
    return {"old_id": key_id, "new_id": created["id"], "key": created["key"]}


def webhook_endpoint_create(kanzlei_id: str, url: str, events: List[str], secret: Optional[str] = None) -> Dict[str, Any]:
    wid = str(uuid.uuid4())
    sec = secret or secrets.token_urlsafe(24)
    if _pg_saas_backend():
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO webhook_endpoints (id, kanzlei_id, url, secret, events_json, aktiv)
                VALUES (%s, %s, %s, %s, %s, 1)
                """,
                (wid, kanzlei_id, url[:500], sec, json.dumps(events or [])),
            )
        conn.commit()
        return {"id": wid, "secret": sec}
    conn = get_connection()
    conn.execute("""
        INSERT INTO webhook_endpoints (id, kanzlei_id, url, secret, events_json, aktiv)
        VALUES (?, ?, ?, ?, ?, 1)
    """, (wid, kanzlei_id, url[:500], sec, json.dumps(events or [])))
    conn.commit()
    return {"id": wid, "secret": sec}


def webhook_endpoint_list(kanzlei_id: str) -> List[Dict[str, Any]]:
    if _pg_saas_backend():
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, url, events_json, aktiv, created_at, last_status, last_error, last_sent_at
                FROM webhook_endpoints
                WHERE kanzlei_id = %s
                ORDER BY created_at DESC
                """,
                (kanzlei_id,),
            )
            rows = cur.fetchall()
        result = []
        for r in rows:
            rr = _pg_normalize_row_dict(dict(r))
            try:
                ev = json.loads(rr["events_json"] or "[]")
            except Exception:
                ev = []
            result.append({
                "id": rr["id"],
                "url": rr["url"],
                "events": ev if isinstance(ev, list) else [],
                "aktiv": bool(rr["aktiv"]),
                "created_at": rr["created_at"],
                "last_status": rr["last_status"],
                "last_error": rr["last_error"],
                "last_sent_at": rr["last_sent_at"],
            })
        return result
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, url, events_json, aktiv, created_at, last_status, last_error, last_sent_at
        FROM webhook_endpoints
        WHERE kanzlei_id = ?
        ORDER BY created_at DESC
    """, (kanzlei_id,)).fetchall()
    result = []
    for r in rows:
        try:
            ev = json.loads(r["events_json"] or "[]")
        except Exception:
            ev = []
        result.append({
            "id": r["id"],
            "url": r["url"],
            "events": ev if isinstance(ev, list) else [],
            "aktiv": bool(r["aktiv"]),
            "created_at": r["created_at"],
            "last_status": r["last_status"],
            "last_error": r["last_error"],
            "last_sent_at": r["last_sent_at"],
        })
    return result


def webhook_endpoints_for_event(kanzlei_id: str, event_type: str) -> List[Dict[str, Any]]:
    if _pg_saas_backend():
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, url, secret, events_json, aktiv
                FROM webhook_endpoints
                WHERE kanzlei_id = %s AND aktiv = 1
                """,
                (kanzlei_id,),
            )
            rows = cur.fetchall()
        result = []
        for r in rows:
            try:
                ev = json.loads(r["events_json"] or "[]")
            except Exception:
                ev = []
            events = ev if isinstance(ev, list) else []
            if event_type in events or "*" in events:
                result.append({
                    "id": r["id"],
                    "url": r["url"],
                    "secret": r["secret"],
                })
        return result
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, url, secret, events_json, aktiv
        FROM webhook_endpoints
        WHERE kanzlei_id = ? AND aktiv = 1
    """, (kanzlei_id,)).fetchall()
    result = []
    for r in rows:
        try:
            ev = json.loads(r["events_json"] or "[]")
        except Exception:
            ev = []
        events = ev if isinstance(ev, list) else []
        if event_type in events or "*" in events:
            result.append({
                "id": r["id"],
                "url": r["url"],
                "secret": r["secret"],
            })
    return result


def webhook_endpoint_delete(kanzlei_id: str, webhook_id: str) -> bool:
    if _pg_saas_backend():
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM webhook_endpoints WHERE kanzlei_id = %s AND id = %s",
                (kanzlei_id, webhook_id),
            )
            n = cur.rowcount
        conn.commit()
        return n > 0
    conn = get_connection()
    cur = conn.execute(
        "DELETE FROM webhook_endpoints WHERE kanzlei_id = ? AND id = ?",
        (kanzlei_id, webhook_id),
    )
    conn.commit()
    return cur.rowcount > 0


def webhook_enqueue(kanzlei_id: str, event_type: str, payload: Dict[str, Any]) -> None:
    if _pg_saas_backend():
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO webhook_queue (kanzlei_id, event_type, payload_json, status)
                VALUES (%s, %s, %s, 'pending')
                """,
                (kanzlei_id, event_type, json.dumps(payload, ensure_ascii=False)),
            )
        conn.commit()
        return
    conn = get_connection()
    conn.execute("""
        INSERT INTO webhook_queue (kanzlei_id, event_type, payload_json, status)
        VALUES (?, ?, ?, 'pending')
    """, (kanzlei_id, event_type, json.dumps(payload, ensure_ascii=False)))
    conn.commit()


def webhook_due(limit: int = 25) -> List[Dict[str, Any]]:
    if _pg_saas_backend():
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM webhook_queue
                WHERE status IN ('pending', 'failed')
                  AND COALESCE(next_attempt_at, NOW()) <= NOW()
                ORDER BY id ASC
                LIMIT %s
                """,
                (max(1, int(limit)),),
            )
            rows = cur.fetchall()
        return [_pg_normalize_row_dict(dict(r)) for r in rows]
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM webhook_queue
        WHERE status IN ('pending', 'failed')
          AND COALESCE(next_attempt_at, datetime('now')) <= datetime('now')
        ORDER BY id ASC
        LIMIT ?
    """, (max(1, int(limit)),)).fetchall()
    return [dict(r) for r in rows]


def webhook_mark_sent(queue_id: int) -> None:
    if _pg_saas_backend():
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute("UPDATE webhook_queue SET status = 'sent' WHERE id = %s", (int(queue_id),))
        conn.commit()
        return
    conn = get_connection()
    conn.execute("UPDATE webhook_queue SET status = 'sent' WHERE id = ?", (int(queue_id),))
    conn.commit()


def webhook_mark_failed(queue_id: int, err: str) -> None:
    if _pg_saas_backend():
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE webhook_queue
                SET attempts = attempts + 1,
                    status = CASE WHEN webhook_queue.attempts + 1 >= 8 THEN 'dead' ELSE 'failed' END,
                    last_error = %s,
                    next_attempt_at = NOW() + (
                        CASE
                            WHEN webhook_queue.attempts <= 0 THEN INTERVAL '1 minute'
                            WHEN webhook_queue.attempts = 1 THEN INTERVAL '5 minutes'
                            WHEN webhook_queue.attempts = 2 THEN INTERVAL '15 minutes'
                            ELSE INTERVAL '60 minutes'
                        END
                    )
                WHERE id = %s
                """,
                (str(err)[:500], int(queue_id)),
            )
        conn.commit()
        return
    conn = get_connection()
    conn.execute("""
        UPDATE webhook_queue
        SET attempts = attempts + 1,
            status = CASE WHEN attempts + 1 >= 8 THEN 'dead' ELSE 'failed' END,
            last_error = ?,
            next_attempt_at = datetime(
                'now',
                CASE
                    WHEN attempts <= 0 THEN '+1 minute'
                    WHEN attempts = 1 THEN '+5 minutes'
                    WHEN attempts = 2 THEN '+15 minutes'
                    ELSE '+60 minutes'
                END
            )
        WHERE id = ?
    """, (str(err)[:500], int(queue_id)))
    conn.commit()


class DatenSpeicher(DatenSpeicher):
    def hole_mandant(self, name: str) -> Optional[Dict]:
        if _pg_mandanten_mode():
            conn = _pg_conn()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM mandanten WHERE kanzlei_id = %s AND name = %s AND aktiv = 1",
                    (self.kanzlei_id, name),
                )
                row = cur.fetchone()
            if not row:
                return None
            m = _pg_normalize_row_dict(dict(row))
            m["fehlende_dokumente_liste"] = _fehlende_dokumente_pg(self.kanzlei_id, name)
            return m
        row = self._conn().execute(
            "SELECT * FROM mandanten WHERE kanzlei_id = ? AND name = ? AND aktiv = 1",
            (self.kanzlei_id, name)
        ).fetchone()
        if not row:
            return None
        m = dict(row)
        m["fehlende_dokumente_liste"] = self._fehlende_dokumente(name)
        return m

    def mandant_existiert(self, name: str) -> bool:
        if _pg_mandanten_mode():
            conn = _pg_conn()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 AS x FROM mandanten WHERE kanzlei_id = %s AND name = %s AND aktiv = 1",
                    (self.kanzlei_id, name),
                )
                return cur.fetchone() is not None
        row = self._conn().execute(
            "SELECT 1 FROM mandanten WHERE kanzlei_id = ? AND name = ? AND aktiv = 1",
            (self.kanzlei_id, name)
        ).fetchone()
        return row is not None

    def mandant_speichern(self, name: str, daten: Dict) -> bool:
        if _pg_mandanten_mode():
            try:
                conn = _pg_conn()
                new_id = str(uuid.uuid4())
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO mandanten
                            (id, kanzlei_id, name, email, telefon, branche, umsatz,
                             notizen, steuer_id, adresse, letzte_antwort, letzte_email, aktiv)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
                        ON CONFLICT (kanzlei_id, name) DO UPDATE SET
                            email          = EXCLUDED.email,
                            telefon        = EXCLUDED.telefon,
                            branche        = EXCLUDED.branche,
                            umsatz         = EXCLUDED.umsatz,
                            notizen        = EXCLUDED.notizen,
                            steuer_id      = EXCLUDED.steuer_id,
                            adresse        = EXCLUDED.adresse,
                            letzte_antwort = EXCLUDED.letzte_antwort,
                            letzte_email   = EXCLUDED.letzte_email,
                            aktiv          = 1
                        """,
                        (
                            new_id,
                            self.kanzlei_id,
                            name,
                            daten.get("email", ""),
                            daten.get("telefon", ""),
                            daten.get("branche", ""),
                            float(daten.get("umsatz", 0) or 0),
                            daten.get("notizen", ""),
                            daten.get("steuer_id", ""),
                            daten.get("adresse", ""),
                            daten.get("letzte_antwort"),
                            daten.get("letzte_email"),
                        ),
                    )
                conn.commit()
                return True
            except Exception as e:
                log.error(f"mandant_speichern({name}) [pg]: {e}")
                try:
                    _pg_conn().rollback()
                except Exception:
                    pass
                return False
        try:
            with db_transaction(self.kanzlei_id) as conn:
                conn.execute("""
                    INSERT INTO mandanten
                        (kanzlei_id, name, email, telefon, branche, umsatz,
                         notizen, steuer_id, adresse, letzte_antwort, letzte_email, aktiv)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT(kanzlei_id, name) DO UPDATE SET
                        email          = excluded.email,
                        telefon        = excluded.telefon,
                        branche        = excluded.branche,
                        umsatz         = excluded.umsatz,
                        notizen        = excluded.notizen,
                        steuer_id      = excluded.steuer_id,
                        adresse        = excluded.adresse,
                        letzte_antwort = excluded.letzte_antwort,
                        letzte_email   = excluded.letzte_email,
                        aktiv          = 1
                """, (
                    self.kanzlei_id,
                    name,
                    daten.get("email", ""),
                    daten.get("telefon", ""),
                    daten.get("branche", ""),
                    float(daten.get("umsatz", 0) or 0),
                    daten.get("notizen", ""),
                    daten.get("steuer_id", ""),
                    daten.get("adresse", ""),
                    daten.get("letzte_antwort"),
                    daten.get("letzte_email"),
                ))
            return True
        except Exception as e:
            log.error(f"mandant_speichern({name}): {e}")
            return False

    def mandant_loeschen(self, name: str) -> bool:
        if _pg_mandanten_mode():
            try:
                conn = _pg_conn()
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE mandanten SET aktiv = 0 WHERE kanzlei_id = %s AND name = %s",
                        (self.kanzlei_id, name),
                    )
                conn.commit()
                return True
            except Exception as e:
                log.error(f"mandant_loeschen({name}) [pg]: {e}")
                try:
                    _pg_conn().rollback()
                except Exception:
                    pass
                return False
        try:
            with db_transaction(self.kanzlei_id) as conn:
                conn.execute(
                    "UPDATE mandanten SET aktiv = 0 WHERE kanzlei_id = ? AND name = ?",
                    (self.kanzlei_id, name)
                )
            return True
        except Exception as e:
            log.error(f"mandant_loeschen({name}): {e}")
            return False

    def _fehlende_dokumente(self, mandant: str) -> List[str]:
        if _pg_mandanten_mode():
            return _fehlende_dokumente_pg(self.kanzlei_id, mandant)
        rows = self._conn().execute(
            "SELECT name FROM dokumente WHERE kanzlei_id = ? AND mandant = ? AND status = 'ausstehend'",
            (self.kanzlei_id, mandant)
        ).fetchall()
        return [r["name"] for r in rows]

    # ══════════════════════════════════════════════════════════
    # AUFGABEN
    # ══════════════════════════════════════════════════════════

    def hole_fristen(self) -> Dict[str, Dict]:
        """Alle Aufgaben dieser Kanzlei als Dict {id: daten}."""
        rows = self._conn().execute(
            "SELECT * FROM aufgaben WHERE kanzlei_id = ? ORDER BY frist",
            (self.kanzlei_id,)
        ).fetchall()
        return {r["id"]: dict(r) for r in rows}

    def hole_aufgaben_fuer_mandant(self, mandant: str) -> List[Dict]:
        rows = self._conn().execute(
            "SELECT * FROM aufgaben WHERE kanzlei_id = ? AND mandant = ? ORDER BY frist",
            (self.kanzlei_id, mandant)
        ).fetchall()
        result = []
        for r in rows:
            a = dict(r)
            if a.get("frist"):
                try:
                    diff = (datetime.strptime(a["frist"], "%Y-%m-%d") - datetime.now()).days
                    a["tage_bis_frist"] = diff
                except Exception:
                    a["tage_bis_frist"] = None
            result.append(a)
        return result

    def hole_aufgaben_naechste_tage(self, tage: int = 7) -> List[Dict]:
        bis = (datetime.now().replace(hour=23,minute=59) +
               __import__("datetime").timedelta(days=tage)).strftime("%Y-%m-%d")
        rows = self._conn().execute(
            "SELECT * FROM aufgaben WHERE kanzlei_id = ? AND frist <= ? AND erledigt = 0 ORDER BY frist",
            (self.kanzlei_id, bis)
        ).fetchall()
        return [dict(r) for r in rows]

    def hole_ueberfaellige_aufgaben(self) -> List[Dict]:
        heute = datetime.now().strftime("%Y-%m-%d")
        rows = self._conn().execute(
            "SELECT * FROM aufgaben WHERE kanzlei_id = ? AND frist < ? AND erledigt = 0 ORDER BY frist",
            (self.kanzlei_id, heute)
        ).fetchall()
        return [dict(r) for r in rows]

    def aufgabe_speichern(self, aufgabe_id: str, daten: Dict) -> bool:
        try:
            with db_transaction(self.kanzlei_id) as conn:
                ps = daten.get("portal_sichtbar")
                portal_sichtbar = 1 if ps is not False and ps != 0 else 0
                conn.execute("""
                    INSERT INTO aufgaben
                        (id, kanzlei_id, mandant, beschreibung, frist, frist_uhrzeit, prioritaet,
                         kategorie, erledigt, erledigt_am, zugewiesen_an, notiz, quelle, portal_sichtbar)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        mandant       = excluded.mandant,
                        beschreibung  = excluded.beschreibung,
                        frist         = excluded.frist,
                        frist_uhrzeit = excluded.frist_uhrzeit,
                        prioritaet    = excluded.prioritaet,
                        kategorie     = excluded.kategorie,
                        erledigt      = excluded.erledigt,
                        erledigt_am   = excluded.erledigt_am,
                        zugewiesen_an = excluded.zugewiesen_an,
                        notiz         = excluded.notiz,
                        portal_sichtbar = excluded.portal_sichtbar
                """, (
                    aufgabe_id,
                    self.kanzlei_id,
                    daten.get("mandant", ""),
                    daten.get("beschreibung", ""),
                    daten.get("frist", ""),
                    daten.get("frist_uhrzeit", ""),
                    daten.get("prioritaet", "normal"),
                    daten.get("kategorie", "allgemein"),
                    1 if daten.get("erledigt") else 0,
                    (daten.get("erledigt_am") if daten.get("erledigt") else None),
                    daten.get("zugewiesen_an", ""),
                    daten.get("notiz", ""),
                    daten.get("quelle", "manuell"),
                    portal_sichtbar,
                ))
            return True
        except Exception as e:
            log.error(f"aufgabe_speichern({aufgabe_id}): {e}")
            return False

    def aufgabe_loeschen(self, aufgabe_id: str) -> bool:
        try:
            with db_transaction(self.kanzlei_id) as conn:
                conn.execute(
                    "DELETE FROM aufgaben WHERE id = ? AND kanzlei_id = ?",
                    (aufgabe_id, self.kanzlei_id)
                )
            return True
        except Exception as e:
            log.error(f"aufgabe_loeschen({aufgabe_id}): {e}")
            return False

    # ══════════════════════════════════════════════════════════
    # KOMMUNIKATION / TIMELINE
    # ══════════════════════════════════════════════════════════

    def hole_kommunikation(self, mandant: str, limit: int = 50) -> List[Dict]:
        rows = self._conn().execute(
            "SELECT * FROM kommunikation WHERE kanzlei_id = ? AND mandant = ? ORDER BY erstellt_am DESC LIMIT ?",
            (self.kanzlei_id, mandant, limit)
        ).fetchall()
        return [dict(r) for r in rows]

    def kommunikation_hinzufuegen(self, mandant: str, eintrag: Dict) -> bool:
        try:
            with db_transaction(self.kanzlei_id) as conn:
                conn.execute("""
                    INSERT INTO kommunikation (id, kanzlei_id, mandant, typ, text, richtung, erstellt_am)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    eintrag.get("id", str(uuid.uuid4())),
                    self.kanzlei_id,
                    mandant,
                    eintrag.get("typ", "notiz"),
                    eintrag.get("text", ""),
                    eintrag.get("richtung", "ausgehend"),
                    eintrag.get("timestamp", eintrag.get("erstellt_am", datetime.now().isoformat())),
                ))
            return True
        except Exception as e:
            log.error(f"kommunikation_hinzufuegen({mandant}): {e}")
            return False

    def timeline_laden(self, mandant: str) -> List[Dict]:
        return self.hole_kommunikation(mandant, 100)

    def timeline_speichern(self, mandant: str, eintrag: Dict) -> bool:
        return self.kommunikation_hinzufuegen(mandant, eintrag)

    # ══════════════════════════════════════════════════════════
    # AUDIT LOG
    # ══════════════════════════════════════════════════════════

    def log_eintrag(self, aktion: str, benutzer: str = "system",
                    details: str = "", ip: str = "") -> None:
        try:
            if _pg_mandanten_mode():
                conn = _pg_conn()
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO audit_log (kanzlei_id, aktion, benutzer, details, ip_adresse)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (self.kanzlei_id, aktion[:500], benutzer, details[:500], ip),
                    )
                conn.commit()
                return
            with db_transaction(self.kanzlei_id) as conn:
                conn.execute(
                    "INSERT INTO audit_log (kanzlei_id, aktion, benutzer, details, ip_adresse) VALUES (?,?,?,?,?)",
                    (self.kanzlei_id, aktion[:500], benutzer, details[:500], ip)
                )
        except Exception as e:
            log.error(f"log_eintrag Fehler: {e}")

    def hole_logs(self, limit: int = 100) -> List[Dict]:
        if _pg_mandanten_mode():
            conn = _pg_conn()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM audit_log
                    WHERE kanzlei_id = %s
                    ORDER BY zeitpunkt DESC
                    LIMIT %s
                    """,
                    (self.kanzlei_id, max(1, int(limit))),
                )
                rows = cur.fetchall()
            return [_pg_normalize_row_dict(dict(r)) for r in rows]
        rows = self._conn().execute(
            "SELECT * FROM audit_log WHERE kanzlei_id = ? ORDER BY zeitpunkt DESC LIMIT ?",
            (self.kanzlei_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]

    def log_decision(self, mandant: str, entscheidung: str, details: str = "") -> None:
        self.log_eintrag(f"DECISION | {mandant} | {entscheidung}", details=details)

    # ══════════════════════════════════════════════════════════
    # PORTAL RECORDS (SQL statt _load/_save JSON)
    # ══════════════════════════════════════════════════════════

    def portal_speichern(self, typ: str, record_id: str, mandant: str, payload: Dict) -> bool:
        try:
            status_s = str(payload.get("status", ""))[:40]
            dj = json.dumps(payload, ensure_ascii=False)
            ers = payload.get("erstellt_am")
            if ers is not None:
                es = str(ers).strip()
                if not es:
                    ers = None
                else:
                    try:
                        datetime.fromisoformat(es.replace("Z", "+00:00"))
                        ers = es
                    except ValueError:
                        ers = None
            if _pg_mandanten_mode():
                conn = _pg_conn()
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO portal_records
                            (id, kanzlei_id, typ, mandant, status, data_json, erstellt_am, geaendert_am)
                        VALUES (%s, %s, %s, %s, %s, %s, COALESCE(%s::timestamptz, NOW()), NOW())
                        ON CONFLICT(id) DO UPDATE SET
                            typ = EXCLUDED.typ,
                            mandant = EXCLUDED.mandant,
                            status = EXCLUDED.status,
                            data_json = EXCLUDED.data_json,
                            geaendert_am = NOW()
                        """,
                        (record_id, self.kanzlei_id, typ, mandant, status_s, dj, ers),
                    )
                conn.commit()
                return True
            with db_transaction(self.kanzlei_id) as conn:
                conn.execute("""
                    INSERT INTO portal_records
                        (id, kanzlei_id, typ, mandant, status, data_json, erstellt_am, geaendert_am)
                    VALUES (?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now')), datetime('now'))
                    ON CONFLICT(id) DO UPDATE SET
                        typ = excluded.typ,
                        mandant = excluded.mandant,
                        status = excluded.status,
                        data_json = excluded.data_json,
                        geaendert_am = datetime('now')
                """, (
                    record_id,
                    self.kanzlei_id,
                    typ,
                    mandant,
                    status_s,
                    dj,
                    ers,
                ))
            return True
        except Exception as e:
            log.error(f"portal_speichern({typ}, {record_id}): {e}")
            return False

    def portal_holen(self, typ: str, record_id: str) -> Optional[Dict]:
        if _pg_mandanten_mode():
            conn = _pg_conn()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT data_json FROM portal_records
                    WHERE kanzlei_id = %s AND typ = %s AND id = %s
                    """,
                    (self.kanzlei_id, typ, record_id),
                )
                row = cur.fetchone()
            if not row:
                return None
            raw = row.get("data_json") if isinstance(row, dict) else row[0]
        else:
            row = self._conn().execute(
                "SELECT data_json FROM portal_records WHERE kanzlei_id = ? AND typ = ? AND id = ?",
                (self.kanzlei_id, typ, record_id),
            ).fetchone()
            if not row:
                return None
            raw = row["data_json"]
        try:
            return json.loads(raw)
        except Exception:
            return None

    def portal_liste(self, typ: str, mandant: Optional[str] = None, status: Optional[str] = None) -> List[Dict]:
        if _pg_mandanten_mode():
            sql = "SELECT data_json FROM portal_records WHERE kanzlei_id = %s AND typ = %s"
            params: List[Any] = [self.kanzlei_id, typ]
            if mandant:
                sql += " AND mandant = %s"
                params.append(mandant)
            if status:
                sql += " AND status = %s"
                params.append(status)
            sql += " ORDER BY erstellt_am DESC"
            conn = _pg_conn()
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
            iter_rows = [r["data_json"] for r in rows]
        else:
            sql = "SELECT data_json FROM portal_records WHERE kanzlei_id = ? AND typ = ?"
            params = [self.kanzlei_id, typ]
            if mandant:
                sql += " AND mandant = ?"
                params.append(mandant)
            if status:
                sql += " AND status = ?"
                params.append(status)
            sql += " ORDER BY erstellt_am DESC"
            rows = self._conn().execute(sql, tuple(params)).fetchall()
            iter_rows = [r["data_json"] for r in rows]
        result = []
        for raw in iter_rows:
            try:
                result.append(json.loads(raw))
            except Exception:
                continue
        return result

    # ══════════════════════════════════════════════════════════
    # EINSTELLUNGEN
    # ══════════════════════════════════════════════════════════

    def setting_holen(self, key: str, default=None):
        if _pg_mandanten_mode():
            conn = _pg_conn()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT value FROM einstellungen WHERE kanzlei_id = %s AND key = %s",
                    (self.kanzlei_id, key),
                )
                row = cur.fetchone()
            if not row:
                return default
            val = row["value"] if isinstance(row, dict) else row[0]
        else:
            row = self._conn().execute(
                "SELECT value FROM einstellungen WHERE kanzlei_id = ? AND key = ?",
                (self.kanzlei_id, key)
            ).fetchone()
            if not row:
                return default
            val = row["value"]
        try:
            return json.loads(val)
        except Exception:
            return val

    def setting_setzen(self, key: str, value) -> bool:
        try:
            payload = json.dumps(value, ensure_ascii=False)
            if _pg_mandanten_mode():
                conn = _pg_conn()
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO einstellungen (kanzlei_id, key, value)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (kanzlei_id, key) DO UPDATE SET
                            value = EXCLUDED.value,
                            geaendert_am = NOW()
                        """,
                        (self.kanzlei_id, key, payload),
                    )
                conn.commit()
                return True
            with db_transaction(self.kanzlei_id) as conn:
                conn.execute("""
                    INSERT INTO einstellungen (kanzlei_id, key, value)
                    VALUES (?, ?, ?)
                    ON CONFLICT(kanzlei_id, key) DO UPDATE SET
                        value = excluded.value,
                        geaendert_am = datetime('now')
                """, (self.kanzlei_id, key, payload))
            return True
        except Exception as e:
            log.error(f"setting_setzen({key}): {e}")
            return False

    # ══════════════════════════════════════════════════════════
    # LEGACY-DOMAIN STORES (ohne _load/_save in Services)
    # ══════════════════════════════════════════════════════════

    def _section_holen(self, section: str, default: Any) -> Any:
        value = self.setting_holen(f"compat::{section}", deepcopy(default))
        if isinstance(default, dict) and not isinstance(value, dict):
            return deepcopy(default)
        if isinstance(default, list) and not isinstance(value, list):
            return deepcopy(default)
        return value

    def _section_setzen(self, section: str, value: Any) -> bool:
        return self.setting_setzen(f"compat::{section}", value)

    def _use_domain_tables_v2(self) -> bool:
        v = (os.getenv("USE_DOMAIN_TABLES_V2") or "0").strip().lower()
        return v in {"1", "true", "yes", "on"}

    def beleg_speichern(self, beleg_id: str, beleg: Dict[str, Any]) -> bool:
        belege = self._section_holen("belege", {})
        belege[beleg_id] = beleg
        return self._section_setzen("belege", belege)

    def belege_liste(self) -> List[Dict[str, Any]]:
        belege = self._section_holen("belege", {})
        out: List[Dict[str, Any]] = []
        for bid, b in belege.items():
            row = dict(b or {})
            if not row.get("beleg_id"):
                row["beleg_id"] = bid
            out.append(row)
        return out

    def beleg_holen(self, beleg_id: str) -> Optional[Dict[str, Any]]:
        belege = self._section_holen("belege", {})
        return belege.get(beleg_id)

    def beleg_loeschen(self, beleg_id: str) -> bool:
        belege = self._section_holen("belege", {})
        if beleg_id not in belege:
            return False
        del belege[beleg_id]
        return self._section_setzen("belege", belege)

    def rechnung_speichern(self, rechnung_id: str, rechnung: Dict[str, Any]) -> bool:
        rechnungen = self._section_holen("rechnungen", {})
        rechnungen[rechnung_id] = rechnung
        return self._section_setzen("rechnungen", rechnungen)

    def rechnungen_liste(self) -> List[Dict[str, Any]]:
        rechnungen = self._section_holen("rechnungen", {})
        return list(rechnungen.values())

    def rechnung_holen(self, rechnung_id: str) -> Optional[Dict[str, Any]]:
        rechnungen = self._section_holen("rechnungen", {})
        return rechnungen.get(rechnung_id)

    def rechnung_counter_next(self, jahr: int) -> int:
        zaehler = self._section_holen("rechnungs_zaehler", {})
        key = str(jahr)
        next_value = int(zaehler.get(key, 0)) + 1
        zaehler[key] = next_value
        self._section_setzen("rechnungs_zaehler", zaehler)
        return next_value

    def workflow_regeln_liste(self) -> Dict[str, Dict[str, Any]]:
        if self._use_domain_tables_v2():
            rows = self._conn().execute(
                "SELECT id, data_json FROM workflow_rules_v2 WHERE kanzlei_id = ?",
                (self.kanzlei_id,),
            ).fetchall()
            result: Dict[str, Dict[str, Any]] = {}
            for r in rows:
                try:
                    result[r["id"]] = json.loads(r["data_json"])
                except Exception:
                    continue
            if result:
                return result
        return self._section_holen("workflow_regeln", {})

    def workflow_regel_holen(self, regel_id: str) -> Optional[Dict[str, Any]]:
        return self.workflow_regeln_liste().get(regel_id)

    def workflow_regel_speichern(self, regel_id: str, regel: Dict[str, Any]) -> bool:
        regeln = self.workflow_regeln_liste()
        regeln[regel_id] = regel
        ok = self._section_setzen("workflow_regeln", regeln)
        if self._use_domain_tables_v2():
            try:
                with db_transaction(self.kanzlei_id) as conn:
                    conn.execute("""
                        INSERT INTO workflow_rules_v2
                            (id, kanzlei_id, name, aktiv, trigger_type, created_at, updated_at, data_json)
                        VALUES (?, ?, ?, ?, ?, COALESCE(?, datetime('now')), datetime('now'), ?)
                        ON CONFLICT(id) DO UPDATE SET
                            name = excluded.name,
                            aktiv = excluded.aktiv,
                            trigger_type = excluded.trigger_type,
                            updated_at = datetime('now'),
                            data_json = excluded.data_json
                    """, (
                        regel_id,
                        self.kanzlei_id,
                        regel.get("name", ""),
                        1 if regel.get("aktiv", True) else 0,
                        (regel.get("trigger") or {}).get("typ", ""),
                        regel.get("erstellt_am"),
                        json.dumps(regel, ensure_ascii=False),
                    ))
            except Exception as e:
                log.error(f"workflow_regel_speichern(v2): {e}")
                return False
        return ok

    def workflow_regel_loeschen(self, regel_id: str) -> bool:
        regeln = self.workflow_regeln_liste()
        regeln.pop(regel_id, None)
        ok = self._section_setzen("workflow_regeln", regeln)
        if self._use_domain_tables_v2():
            self._conn().execute(
                "DELETE FROM workflow_rules_v2 WHERE kanzlei_id = ? AND id = ?",
                (self.kanzlei_id, regel_id),
            )
            self._conn().commit()
        return ok

    def bot_fragen_liste(self) -> Dict[str, Dict[str, Any]]:
        if self._use_domain_tables_v2():
            rows = self._conn().execute(
                "SELECT id, data_json FROM bot_questions_v2 WHERE kanzlei_id = ?",
                (self.kanzlei_id,),
            ).fetchall()
            result: Dict[str, Dict[str, Any]] = {}
            for r in rows:
                try:
                    result[r["id"]] = json.loads(r["data_json"])
                except Exception:
                    continue
            if result:
                return result
        return self._section_holen("bot_fragen", {})

    def bot_frage_holen(self, frage_id: str) -> Optional[Dict[str, Any]]:
        return self.bot_fragen_liste().get(frage_id)

    def bot_frage_speichern(self, frage_id: str, frage: Dict[str, Any]) -> bool:
        fragen = self.bot_fragen_liste()
        fragen[frage_id] = frage
        ok = self._section_setzen("bot_fragen", fragen)
        if self._use_domain_tables_v2():
            try:
                with db_transaction(self.kanzlei_id) as conn:
                    conn.execute("""
                        INSERT INTO bot_questions_v2
                            (id, kanzlei_id, mandant, status, frage_typ, erstellt_am, ablaeuft_am, data_json)
                        VALUES (?, ?, ?, ?, ?, COALESCE(?, datetime('now')), ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            mandant = excluded.mandant,
                            status = excluded.status,
                            frage_typ = excluded.frage_typ,
                            ablaeuft_am = excluded.ablaeuft_am,
                            data_json = excluded.data_json
                    """, (
                        frage_id,
                        self.kanzlei_id,
                        frage.get("mandant", ""),
                        frage.get("status", "offen"),
                        frage.get("typ", "sonstiges"),
                        frage.get("erstellt_am"),
                        frage.get("ablaeuft_am", ""),
                        json.dumps(frage, ensure_ascii=False),
                    ))
            except Exception as e:
                log.error(f"bot_frage_speichern(v2): {e}")
                return False
        return ok

    def bot_fragen_setzen(self, fragen: Dict[str, Dict[str, Any]]) -> bool:
        payload = fragen if isinstance(fragen, dict) else {}
        ok = self._section_setzen("bot_fragen", payload)
        if self._use_domain_tables_v2():
            try:
                with db_transaction(self.kanzlei_id) as conn:
                    conn.execute("DELETE FROM bot_questions_v2 WHERE kanzlei_id = ?", (self.kanzlei_id,))
                    for qid, frage in payload.items():
                        conn.execute("""
                            INSERT INTO bot_questions_v2
                                (id, kanzlei_id, mandant, status, frage_typ, erstellt_am, ablaeuft_am, data_json)
                            VALUES (?, ?, ?, ?, ?, COALESCE(?, datetime('now')), ?, ?)
                        """, (
                            qid, self.kanzlei_id, frage.get("mandant", ""), frage.get("status", "offen"),
                            frage.get("typ", "sonstiges"), frage.get("erstellt_am"),
                            frage.get("ablaeuft_am", ""), json.dumps(frage, ensure_ascii=False),
                        ))
            except Exception as e:
                log.error(f"bot_fragen_setzen(v2): {e}")
                return False
        return ok

    def zeiterfassung_holen(self) -> Dict[str, Dict[str, Any]]:
        if self._use_domain_tables_v2():
            eintraege_rows = self._conn().execute(
                "SELECT id, data_json FROM time_entries_v2 WHERE kanzlei_id = ?",
                (self.kanzlei_id,),
            ).fetchall()
            running_rows = self._conn().execute(
                "SELECT mitarbeiter, zeit_id FROM time_running_v2 WHERE kanzlei_id = ?",
                (self.kanzlei_id,),
            ).fetchall()
            eintraege: Dict[str, Dict[str, Any]] = {}
            for r in eintraege_rows:
                try:
                    eintraege[r["id"]] = json.loads(r["data_json"])
                except Exception:
                    continue
            laufend = {r["mitarbeiter"]: r["zeit_id"] for r in running_rows}
            if eintraege or laufend:
                return {"eintraege": eintraege, "laufend": laufend}
        return self._section_holen("zeiterfassung", {"eintraege": {}, "laufend": {}})

    def zeiterfassung_speichern(self, zeiterfassung: Dict[str, Dict[str, Any]]) -> bool:
        ok = self._section_setzen("zeiterfassung", zeiterfassung)
        if self._use_domain_tables_v2():
            try:
                eintraege = (zeiterfassung or {}).get("eintraege", {})
                laufend = (zeiterfassung or {}).get("laufend", {})
                with db_transaction(self.kanzlei_id) as conn:
                    conn.execute("DELETE FROM time_entries_v2 WHERE kanzlei_id = ?", (self.kanzlei_id,))
                    conn.execute("DELETE FROM time_running_v2 WHERE kanzlei_id = ?", (self.kanzlei_id,))
                    for zid, eintrag in eintraege.items():
                        conn.execute("""
                            INSERT INTO time_entries_v2
                                (id, kanzlei_id, mitarbeiter, mandant, start_at, end_at, status, data_json)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            zid, self.kanzlei_id, eintrag.get("mitarbeiter", ""), eintrag.get("mandant", ""),
                            eintrag.get("start", ""), eintrag.get("ende", ""),
                            "running" if not eintrag.get("ende") else "closed",
                            json.dumps(eintrag, ensure_ascii=False),
                        ))
                    for ma, zid in laufend.items():
                        conn.execute("""
                            INSERT INTO time_running_v2 (kanzlei_id, mitarbeiter, zeit_id, started_at)
                            VALUES (?, ?, ?, datetime('now'))
                        """, (self.kanzlei_id, ma, zid))
            except Exception as e:
                log.error(f"zeiterfassung_speichern(v2): {e}")
                return False
        return ok

    def steuerfaelle_liste(self) -> Dict[str, Dict[str, Any]]:
        if self._use_domain_tables_v2():
            rows = self._conn().execute(
                "SELECT id, data_json FROM steuerfaelle_v2 WHERE kanzlei_id = ?",
                (self.kanzlei_id,),
            ).fetchall()
            result: Dict[str, Dict[str, Any]] = {}
            for r in rows:
                try:
                    payload = json.loads(r["data_json"])
                    if not isinstance(payload, dict):
                        payload = {}
                    if not payload.get("id"):
                        payload["id"] = r["id"]
                    result[r["id"]] = payload
                except Exception:
                    continue
            if result:
                return result
        raw = self._section_holen("steuerfaelle", {})
        out: Dict[str, Dict[str, Any]] = {}
        for fid, fall in raw.items():
            row = dict(fall or {})
            if not row.get("id"):
                row["id"] = fid
            out[fid] = row
        return out

    def steuerfall_holen(self, fall_id: str) -> Optional[Dict[str, Any]]:
        return self.steuerfaelle_liste().get(fall_id)

    def steuerfall_speichern(self, fall_id: str, fall: Dict[str, Any]) -> bool:
        faelle = self.steuerfaelle_liste()
        faelle[fall_id] = fall
        ok = self._section_setzen("steuerfaelle", faelle)
        if self._use_domain_tables_v2():
            try:
                with db_transaction(self.kanzlei_id) as conn:
                    conn.execute("""
                        INSERT INTO steuerfaelle_v2
                            (id, kanzlei_id, mandant, jahr, steuerart, status, konfidenz_score, erstellt_am, data_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now')), ?)
                        ON CONFLICT(id) DO UPDATE SET
                            mandant = excluded.mandant,
                            jahr = excluded.jahr,
                            steuerart = excluded.steuerart,
                            status = excluded.status,
                            konfidenz_score = excluded.konfidenz_score,
                            data_json = excluded.data_json
                    """, (
                        fall_id, self.kanzlei_id, fall.get("mandant", ""), int(fall.get("jahr", 0) or 0),
                        fall.get("steuerart", ""), fall.get("status", ""),
                        float(fall.get("konfidenz_score", 0) or 0), fall.get("erstellt_am"),
                        json.dumps(fall, ensure_ascii=False),
                    ))
            except Exception as e:
                log.error(f"steuerfall_speichern(v2): {e}")
                return False
        return ok

    def steuerfall_loeschen(self, fall_id: str) -> bool:
        faelle = dict(self.steuerfaelle_liste())
        if fall_id not in faelle:
            return False
        del faelle[fall_id]
        ok = self._section_setzen("steuerfaelle", faelle)
        if self._use_domain_tables_v2():
            try:
                with db_transaction(self.kanzlei_id) as conn:
                    conn.execute(
                        "DELETE FROM steuerfaelle_v2 WHERE id = ? AND kanzlei_id = ?",
                        (fall_id, self.kanzlei_id),
                    )
            except Exception as e:
                log.error(f"steuerfall_loeschen(v2): {e}")
                return False
        return ok

    def finanzierungen_liste(self) -> Dict[str, Dict[str, Any]]:
        if self._use_domain_tables_v2():
            rows = self._conn().execute(
                "SELECT id, data_json FROM finanzierungen_v2 WHERE kanzlei_id = ?",
                (self.kanzlei_id,),
            ).fetchall()
            result: Dict[str, Dict[str, Any]] = {}
            for r in rows:
                try:
                    result[r["id"]] = json.loads(r["data_json"])
                except Exception:
                    continue
            if result:
                return result
        return self._section_holen("finanzierungen", {})

    def finanzierung_speichern(self, angebot_id: str, angebot: Dict[str, Any]) -> bool:
        finanzierungen = self.finanzierungen_liste()
        finanzierungen[angebot_id] = angebot
        ok = self._section_setzen("finanzierungen", finanzierungen)
        if self._use_domain_tables_v2():
            try:
                with db_transaction(self.kanzlei_id) as conn:
                    conn.execute("""
                        INSERT INTO finanzierungen_v2
                            (id, kanzlei_id, mandant, status, steuerart, betrag, erstellt_am, data_json)
                        VALUES (?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now')), ?)
                        ON CONFLICT(id) DO UPDATE SET
                            mandant = excluded.mandant,
                            status = excluded.status,
                            steuerart = excluded.steuerart,
                            betrag = excluded.betrag,
                            data_json = excluded.data_json
                    """, (
                        angebot_id, self.kanzlei_id, angebot.get("mandant", ""),
                        angebot.get("status", "offen"), angebot.get("steuerart", ""),
                        float(angebot.get("betrag", 0) or 0), angebot.get("erstellt_am"),
                        json.dumps(angebot, ensure_ascii=False),
                    ))
            except Exception as e:
                log.error(f"finanzierung_speichern(v2): {e}")
                return False
        return ok

    def lohnabrechnung_holen(self) -> Dict[str, Dict[str, Any]]:
        if self._use_domain_tables_v2():
            ma_rows = self._conn().execute(
                "SELECT id, data_json FROM payroll_employees_v2 WHERE kanzlei_id = ?",
                (self.kanzlei_id,),
            ).fetchall()
            zeit_rows = self._conn().execute(
                "SELECT id, data_json FROM payroll_time_v2 WHERE kanzlei_id = ?",
                (self.kanzlei_id,),
            ).fetchall()
            run_rows = self._conn().execute(
                "SELECT id, data_json FROM payroll_runs_v2 WHERE kanzlei_id = ?",
                (self.kanzlei_id,),
            ).fetchall()
            mitarbeiter: Dict[str, Dict[str, Any]] = {}
            zeitdaten: Dict[str, Dict[str, Any]] = {}
            abrechnungen: Dict[str, Dict[str, Any]] = {}
            for rows, target in ((ma_rows, mitarbeiter), (zeit_rows, zeitdaten), (run_rows, abrechnungen)):
                for r in rows:
                    try:
                        target[r["id"]] = json.loads(r["data_json"])
                    except Exception:
                        continue
            if mitarbeiter or zeitdaten or abrechnungen:
                return {"mitarbeiter": mitarbeiter, "abrechnungen": abrechnungen, "zeitdaten": zeitdaten}
        return self._section_holen(
            "lohnabrechnung",
            {"mitarbeiter": {}, "abrechnungen": {}, "zeitdaten": {}},
        )

    def lohnabrechnung_speichern(self, lohnabrechnung: Dict[str, Dict[str, Any]]) -> bool:
        ok = self._section_setzen("lohnabrechnung", lohnabrechnung)
        if self._use_domain_tables_v2():
            try:
                mitarbeiter = (lohnabrechnung or {}).get("mitarbeiter", {})
                zeitdaten = (lohnabrechnung or {}).get("zeitdaten", {})
                abrechnungen = (lohnabrechnung or {}).get("abrechnungen", {})
                with db_transaction(self.kanzlei_id) as conn:
                    conn.execute("DELETE FROM payroll_employees_v2 WHERE kanzlei_id = ?", (self.kanzlei_id,))
                    conn.execute("DELETE FROM payroll_time_v2 WHERE kanzlei_id = ?", (self.kanzlei_id,))
                    conn.execute("DELETE FROM payroll_runs_v2 WHERE kanzlei_id = ?", (self.kanzlei_id,))
                    for mid, ma in mitarbeiter.items():
                        conn.execute("""
                            INSERT INTO payroll_employees_v2
                                (id, kanzlei_id, mandant, name, aktiv, eintritt, erstellt_am, data_json)
                            VALUES (?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now')), ?)
                        """, (
                            mid, self.kanzlei_id, ma.get("mandant", ""), ma.get("name", ""),
                            1 if ma.get("aktiv", True) else 0, ma.get("eintritt", ""),
                            ma.get("erstellt_am"), json.dumps(ma, ensure_ascii=False),
                        ))
                    for tid, td in zeitdaten.items():
                        conn.execute("""
                            INSERT INTO payroll_time_v2
                                (id, kanzlei_id, ma_id, monat, importiert_am, data_json)
                            VALUES (?, ?, ?, ?, COALESCE(?, datetime('now')), ?)
                        """, (
                            tid, self.kanzlei_id, td.get("ma_id", ""), td.get("monat", ""),
                            td.get("importiert_am"), json.dumps(td, ensure_ascii=False),
                        ))
                    for rid, run in abrechnungen.items():
                        conn.execute("""
                            INSERT INTO payroll_runs_v2
                                (id, kanzlei_id, ma_id, mandant, monat, status, berechnet_am, data_json)
                            VALUES (?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now')), ?)
                        """, (
                            rid, self.kanzlei_id, run.get("ma_id", ""), run.get("mandant", ""),
                            run.get("monat", ""), run.get("status", "berechnet"),
                            run.get("berechnet_am"), json.dumps(run, ensure_ascii=False),
                        ))
            except Exception as e:
                log.error(f"lohnabrechnung_speichern(v2): {e}")
                return False
        return ok

    # ══════════════════════════════════════════════════════════
    # HILFSMETHODEN
    # ══════════════════════════════════════════════════════════

    def berechne_tage_ohne_antwort(self, mandant: str) -> int:
        if _pg_mandanten_mode():
            conn = _pg_conn()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT letzte_antwort FROM mandanten WHERE kanzlei_id = %s AND name = %s",
                    (self.kanzlei_id, mandant),
                )
                row = cur.fetchone()
            if not row or row.get("letzte_antwort") is None:
                return 999
            try:
                letzte = _pg_ts_to_naive_datetime(row["letzte_antwort"])
                if letzte is None:
                    return 999
                return max(0, (datetime.now() - letzte).days)
            except Exception:
                return 0
        row = self._conn().execute(
            "SELECT letzte_antwort FROM mandanten WHERE kanzlei_id = ? AND name = ?",
            (self.kanzlei_id, mandant)
        ).fetchone()
        if not row or not row["letzte_antwort"]:
            return 999
        try:
            letzte = datetime.fromisoformat(row["letzte_antwort"])
            return max(0, (datetime.now() - letzte).days)
        except Exception:
            return 0

    def hole_statistiken(self) -> Dict:
        conn = self._conn()
        if _pg_mandanten_mode():
            pg = _pg_conn()
            with pg.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) AS n FROM mandanten WHERE kanzlei_id = %s AND aktiv = 1",
                    (self.kanzlei_id,),
                )
                mandanten_anz = cur.fetchone()["n"]
                cur.execute(
                    "SELECT COALESCE(SUM(umsatz), 0) AS s FROM mandanten WHERE kanzlei_id = %s AND aktiv = 1",
                    (self.kanzlei_id,),
                )
                umsatz = cur.fetchone()["s"]
        else:
            mandanten_anz = conn.execute(
                "SELECT COUNT(*) as n FROM mandanten WHERE kanzlei_id = ? AND aktiv = 1",
                (self.kanzlei_id,)
            ).fetchone()["n"]
            umsatz = conn.execute(
                "SELECT COALESCE(SUM(umsatz), 0) as s FROM mandanten WHERE kanzlei_id = ? AND aktiv = 1",
                (self.kanzlei_id,)
            ).fetchone()["s"]
        aufgaben_offen = conn.execute(
            "SELECT COUNT(*) as n FROM aufgaben WHERE kanzlei_id = ? AND erledigt = 0",
            (self.kanzlei_id,)
        ).fetchone()["n"]
        aufgaben_gesamt = conn.execute(
            "SELECT COUNT(*) as n FROM aufgaben WHERE kanzlei_id = ?",
            (self.kanzlei_id,)
        ).fetchone()["n"]

        return {
            "mandanten_gesamt":  mandanten_anz,
            "aufgaben_offen":    aufgaben_offen,
            "aufgaben_gesamt":   aufgaben_gesamt,
            "completion_rate":   round((1 - aufgaben_offen / max(aufgaben_gesamt, 1)) * 100),
            "gesamtumsatz":      umsatz,
            "kanzlei_id":        self.kanzlei_id,
        }

    def datenbank_info(self) -> Dict:
        try:
            groesse = os.path.getsize(DB_PFAD) // 1024
        except Exception:
            groesse = 0
        stats = self.hole_statistiken()
        return {
            **stats,
            "groesse_kb":    groesse,
            "db_pfad":       DB_PFAD,
            "backup_anzahl": 0,
            "letztes_backup": None,
        }

    def email_speichern(self, mandant: str, text: str) -> None:
        self.kommunikation_hinzufuegen(mandant, {
            "id":       str(uuid.uuid4()),
            "typ":      "email",
            "text":     text[:200],
            "richtung": "ausgehend",
        })

    # ── Kompatibilität mit altem JSON-Speicher ─────────────────
    def _load(self) -> Dict:
        """Kompatibilität: gibt DB-Daten als Dict zurück."""
        uploads = {x.get("id"): x for x in self.portal_liste("upload") if x.get("id")}
        unterschriften = {x.get("id"): x for x in self.portal_liste("unterschrift") if x.get("id")}
        freigaben = {x.get("id"): x for x in self.portal_liste("freigabe") if x.get("id")}
        result = {
            "mandanten":     self.hole_mandanten(),
            "fristen":       self.hole_fristen(),
            "portal": {
                "uploads": uploads,
                "unterschriften": unterschriften,
                "freigaben": freigaben,
            },
        }
        for section, default_value in _COMPAT_SECTION_DEFAULTS.items():
            loaded = self.setting_holen(f"compat::{section}", deepcopy(default_value))
            if isinstance(default_value, dict) and not isinstance(loaded, dict):
                loaded = deepcopy(default_value)
            result[section] = loaded
        return result

    def _save(self, data: Dict) -> bool:
        """Kompatibilität: persistiert Legacy-Sektionen in SQL-Einstellungen."""
        if not isinstance(data, dict):
            return False
        ok = True
        for section, default_value in _COMPAT_SECTION_DEFAULTS.items():
            value = data.get(section, deepcopy(default_value))
            if isinstance(default_value, dict) and not isinstance(value, dict):
                value = deepcopy(default_value)
            if not self.setting_setzen(f"compat::{section}", value):
                ok = False
        return ok

    def exportiere_json(self) -> Dict:
        uploads = {x.get("id"): x for x in self.portal_liste("upload") if x.get("id")}
        unterschriften = {x.get("id"): x for x in self.portal_liste("unterschrift") if x.get("id")}
        freigaben = {x.get("id"): x for x in self.portal_liste("freigabe") if x.get("id")}
        return {
            "mandanten": self.hole_mandanten(),
            "fristen": self.hole_fristen(),
            "belege": self._section_holen("belege", {}),
            "rechnungen": self._section_holen("rechnungen", {}),
            "rechnungs_zaehler": self._section_holen("rechnungs_zaehler", {}),
            "bot_fragen": self._section_holen("bot_fragen", {}),
            "steuerfaelle": self._section_holen("steuerfaelle", {}),
            "finanzierungen": self._section_holen("finanzierungen", {}),
            "workflow_regeln": self._section_holen("workflow_regeln", {}),
            "workflow_runs": self._section_holen("workflow_runs", {}),
            "zeiterfassung": self._section_holen("zeiterfassung", {"eintraege": {}, "laufend": {}}),
            "lohnabrechnung": self._section_holen(
                "lohnabrechnung",
                {"mitarbeiter": {}, "abrechnungen": {}, "zeitdaten": {}},
            ),
            "portal": {
                "uploads": uploads,
                "unterschriften": unterschriften,
                "freigaben": freigaben,
            },
        }

    def berechne_gesamtumsatz(self) -> float:
        if _pg_mandanten_mode():
            conn = _pg_conn()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COALESCE(SUM(umsatz), 0) AS s FROM mandanten WHERE kanzlei_id = %s AND aktiv = 1",
                    (self.kanzlei_id,),
                )
                row = cur.fetchone()
            return float(row["s"] if row else 0)
        row = self._conn().execute(
            "SELECT COALESCE(SUM(umsatz), 0) as s FROM mandanten WHERE kanzlei_id = ? AND aktiv = 1",
            (self.kanzlei_id,)
        ).fetchone()
        return float(row["s"] if row else 0)

    def berechne_tage_ohne_antwort_alle(self) -> Dict[str, int]:
        if _pg_mandanten_mode():
            conn = _pg_conn()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT name, letzte_antwort FROM mandanten WHERE kanzlei_id = %s AND aktiv = 1",
                    (self.kanzlei_id,),
                )
                rows = cur.fetchall()
            result: Dict[str, int] = {}
            for r in rows:
                la = r.get("letzte_antwort")
                if la is None:
                    result[r["name"]] = 999
                else:
                    try:
                        dt = _pg_ts_to_naive_datetime(la)
                        if dt is None:
                            result[r["name"]] = 999
                        else:
                            result[r["name"]] = max(0, (datetime.now() - dt).days)
                    except Exception:
                        result[r["name"]] = 0
            return result
        rows = self._conn().execute(
            "SELECT name, letzte_antwort FROM mandanten WHERE kanzlei_id = ? AND aktiv = 1",
            (self.kanzlei_id,)
        ).fetchall()
        result = {}
        for r in rows:
            if not r["letzte_antwort"]:
                result[r["name"]] = 999
            else:
                try:
                    d = (datetime.now() - datetime.fromisoformat(r["letzte_antwort"])).days
                    result[r["name"]] = max(0, d)
                except Exception:
                    result[r["name"]] = 0
        return result
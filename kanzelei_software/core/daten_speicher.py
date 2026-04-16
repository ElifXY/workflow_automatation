# ============================================================
# KANZLEI AI — DATENSPEICHER v4.0
# SQLite, Multi-Kanzlei-fähig, Thread-safe
#
# ARCHITEKTUR-ENTSCHEIDUNG:
#   Nicht: 1 DB pro User (unnötig komplex)
#   Sondern: 1 DB + kanzlei_id in jeder Tabelle
#   → Kanzlei A sieht niemals Daten von Kanzlei B
#   → Skaliert bis 10.000 Kanzleien auf einem Server
#   → Standard für alle SaaS-Produkte (Stripe, Slack, etc.)
#
# Migration:
#   Bestehende Daten bekommen kanzlei_id = 'default'
#   Neue Kanzleien bekommen eigene UUID
# ============================================================

import os
import sqlite3
import json
import logging
import threading
import uuid
import hashlib
import secrets
from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, List, Optional, Any

log = logging.getLogger("kanzlei_db")

DB_PFAD     = os.path.join("data", "kanzlei.db")
DEFAULT_KID = "default"   # Bestehende Daten

_local = threading.local()

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
    environment = (os.getenv("ENVIRONMENT") or os.getenv("APP_ENV") or "development").lower()
    if environment == "production":
        raise RuntimeError(
            "SQLite ist in Production deaktiviert. Nutze PostgreSQL Runtime-Backend."
        )
    if not hasattr(_local, "conn") or _local.conn is None:
        os.makedirs(os.path.dirname(DB_PFAD), exist_ok=True)
        conn = sqlite3.connect(DB_PFAD, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        _local.conn = conn
    return _local.conn


@contextmanager
def db_transaction(kanzlei_id: str = DEFAULT_KID):
    conn = get_connection(kanzlei_id)
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        log.error(f"DB Transaction Fehler: {e}")
        raise


def init_db():
    """Schema initialisieren — kanzlei_id in allen Tabellen."""
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
    conn.commit()
    log.info(f"DB initialisiert: {DB_PFAD}")


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
    conn = get_connection()
    cur = conn.execute("""
        INSERT OR IGNORE INTO agent_actions
            (kanzlei_id, action_key, mandant, aktion, status, details)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (kanzlei_id, action_key, mandant, aktion, status, details[:500]))
    conn.commit()
    return cur.rowcount > 0


def agent_action_update(kanzlei_id: str, action_key: str, status: str, details: str = "") -> None:
    conn = get_connection()
    conn.execute("""
        UPDATE agent_actions
        SET status = ?, details = ?
        WHERE kanzlei_id = ? AND action_key = ?
    """, (status, details[:500], kanzlei_id, action_key))
    conn.commit()


def usage_get(kanzlei_id: str, metric: str, day: Optional[str] = None) -> int:
    d = day or datetime.now().strftime("%Y-%m-%d")
    conn = get_connection()
    row = conn.execute(
        "SELECT value FROM usage_metrics WHERE kanzlei_id = ? AND metric = ? AND day = ?",
        (kanzlei_id, metric, d),
    ).fetchone()
    return int(row["value"]) if row else 0


def usage_increment(kanzlei_id: str, metric: str, amount: int = 1, day: Optional[str] = None) -> int:
    d = day or datetime.now().strftime("%Y-%m-%d")
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
    conn = get_connection()
    cur = conn.execute(
        "UPDATE api_keys SET aktiv = 0 WHERE kanzlei_id = ? AND id = ?",
        (kanzlei_id, key_id),
    )
    conn.commit()
    return cur.rowcount > 0


def api_key_rotate(kanzlei_id: str, key_id: str, new_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
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
    conn = get_connection()
    conn.execute("""
        INSERT INTO webhook_endpoints (id, kanzlei_id, url, secret, events_json, aktiv)
        VALUES (?, ?, ?, ?, ?, 1)
    """, (wid, kanzlei_id, url[:500], sec, json.dumps(events or [])))
    conn.commit()
    return {"id": wid, "secret": sec}


def webhook_endpoint_list(kanzlei_id: str) -> List[Dict[str, Any]]:
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
    conn = get_connection()
    cur = conn.execute(
        "DELETE FROM webhook_endpoints WHERE kanzlei_id = ? AND id = ?",
        (kanzlei_id, webhook_id),
    )
    conn.commit()
    return cur.rowcount > 0


def webhook_enqueue(kanzlei_id: str, event_type: str, payload: Dict[str, Any]) -> None:
    conn = get_connection()
    conn.execute("""
        INSERT INTO webhook_queue (kanzlei_id, event_type, payload_json, status)
        VALUES (?, ?, ?, 'pending')
    """, (kanzlei_id, event_type, json.dumps(payload, ensure_ascii=False)))
    conn.commit()


def webhook_due(limit: int = 25) -> List[Dict[str, Any]]:
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
    conn = get_connection()
    conn.execute("UPDATE webhook_queue SET status = 'sent' WHERE id = ?", (int(queue_id),))
    conn.commit()


def webhook_mark_failed(queue_id: int, err: str) -> None:
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
        row = self._conn().execute(
            "SELECT 1 FROM mandanten WHERE kanzlei_id = ? AND name = ? AND aktiv = 1",
            (self.kanzlei_id, name)
        ).fetchone()
        return row is not None

    def mandant_speichern(self, name: str, daten: Dict) -> bool:
        try:
            with db_transaction(self.kanzlei_id) as conn:
                conn.execute("""
                    INSERT INTO mandanten
                        (kanzlei_id, name, email, telefon, branche, umsatz,
                         notizen, steuer_id, adresse, letzte_antwort, letzte_email)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(kanzlei_id, name) DO UPDATE SET
                        email          = excluded.email,
                        telefon        = excluded.telefon,
                        branche        = excluded.branche,
                        umsatz         = excluded.umsatz,
                        notizen        = excluded.notizen,
                        steuer_id      = excluded.steuer_id,
                        adresse        = excluded.adresse,
                        letzte_antwort = excluded.letzte_antwort,
                        letzte_email   = excluded.letzte_email
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
                conn.execute("""
                    INSERT INTO aufgaben
                        (id, kanzlei_id, mandant, beschreibung, frist, prioritaet,
                         kategorie, erledigt, zugewiesen_an, notiz, quelle)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        beschreibung  = excluded.beschreibung,
                        frist         = excluded.frist,
                        prioritaet    = excluded.prioritaet,
                        erledigt      = excluded.erledigt,
                        erledigt_am   = CASE WHEN excluded.erledigt = 1 AND erledigt_am IS NULL
                                         THEN datetime('now') ELSE erledigt_am END,
                        zugewiesen_an = excluded.zugewiesen_an,
                        notiz         = excluded.notiz
                """, (
                    aufgabe_id,
                    self.kanzlei_id,
                    daten.get("mandant", ""),
                    daten.get("beschreibung", ""),
                    daten.get("frist", ""),
                    daten.get("prioritaet", "normal"),
                    daten.get("kategorie", "allgemein"),
                    1 if daten.get("erledigt") else 0,
                    daten.get("zugewiesen_an", ""),
                    daten.get("notiz", ""),
                    daten.get("quelle", "manuell"),
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
            with db_transaction(self.kanzlei_id) as conn:
                conn.execute(
                    "INSERT INTO audit_log (kanzlei_id, aktion, benutzer, details, ip_adresse) VALUES (?,?,?,?,?)",
                    (self.kanzlei_id, aktion[:500], benutzer, details[:500], ip)
                )
        except Exception as e:
            log.error(f"log_eintrag Fehler: {e}")

    def hole_logs(self, limit: int = 100) -> List[Dict]:
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
                    str(payload.get("status", ""))[:40],
                    json.dumps(payload, ensure_ascii=False),
                    payload.get("erstellt_am"),
                ))
            return True
        except Exception as e:
            log.error(f"portal_speichern({typ}, {record_id}): {e}")
            return False

    def portal_holen(self, typ: str, record_id: str) -> Optional[Dict]:
        row = self._conn().execute(
            "SELECT data_json FROM portal_records WHERE kanzlei_id = ? AND typ = ? AND id = ?",
            (self.kanzlei_id, typ, record_id),
        ).fetchone()
        if not row:
            return None
        try:
            return json.loads(row["data_json"])
        except Exception:
            return None

    def portal_liste(self, typ: str, mandant: Optional[str] = None, status: Optional[str] = None) -> List[Dict]:
        sql = "SELECT data_json FROM portal_records WHERE kanzlei_id = ? AND typ = ?"
        params: List[Any] = [self.kanzlei_id, typ]
        if mandant:
            sql += " AND mandant = ?"
            params.append(mandant)
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY erstellt_am DESC"
        rows = self._conn().execute(sql, tuple(params)).fetchall()
        result = []
        for r in rows:
            try:
                result.append(json.loads(r["data_json"]))
            except Exception:
                continue
        return result

    # ══════════════════════════════════════════════════════════
    # EINSTELLUNGEN
    # ══════════════════════════════════════════════════════════

    def setting_holen(self, key: str, default=None):
        row = self._conn().execute(
            "SELECT value FROM einstellungen WHERE kanzlei_id = ? AND key = ?",
            (self.kanzlei_id, key)
        ).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except Exception:
            return row["value"]

    def setting_setzen(self, key: str, value) -> bool:
        try:
            with db_transaction(self.kanzlei_id) as conn:
                conn.execute("""
                    INSERT INTO einstellungen (kanzlei_id, key, value)
                    VALUES (?, ?, ?)
                    ON CONFLICT(kanzlei_id, key) DO UPDATE SET
                        value = excluded.value,
                        geaendert_am = datetime('now')
                """, (self.kanzlei_id, key, json.dumps(value, ensure_ascii=False)))
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
        return list(belege.values())

    def beleg_holen(self, beleg_id: str) -> Optional[Dict[str, Any]]:
        belege = self._section_holen("belege", {})
        return belege.get(beleg_id)

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
                    result[r["id"]] = json.loads(r["data_json"])
                except Exception:
                    continue
            if result:
                return result
        return self._section_holen("steuerfaelle", {})

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
        mandanten_anz = conn.execute(
            "SELECT COUNT(*) as n FROM mandanten WHERE kanzlei_id = ? AND aktiv = 1",
            (self.kanzlei_id,)
        ).fetchone()["n"]
        aufgaben_offen = conn.execute(
            "SELECT COUNT(*) as n FROM aufgaben WHERE kanzlei_id = ? AND erledigt = 0",
            (self.kanzlei_id,)
        ).fetchone()["n"]
        aufgaben_gesamt = conn.execute(
            "SELECT COUNT(*) as n FROM aufgaben WHERE kanzlei_id = ?",
            (self.kanzlei_id,)
        ).fetchone()["n"]
        umsatz = conn.execute(
            "SELECT COALESCE(SUM(umsatz), 0) as s FROM mandanten WHERE kanzlei_id = ? AND aktiv = 1",
            (self.kanzlei_id,)
        ).fetchone()["s"]

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
        row = self._conn().execute(
            "SELECT COALESCE(SUM(umsatz), 0) as s FROM mandanten WHERE kanzlei_id = ? AND aktiv = 1",
            (self.kanzlei_id,)
        ).fetchone()
        return float(row["s"] if row else 0)

    def berechne_tage_ohne_antwort_alle(self) -> Dict[str, int]:
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
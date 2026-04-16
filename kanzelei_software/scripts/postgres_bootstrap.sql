-- Kanzlei AI PostgreSQL Bootstrap (Phase 1 SaaS)
-- Erstellt die Kern-Tabellen für produktiven Multi-Tenant-Betrieb.

CREATE TABLE IF NOT EXISTS kanzleien (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    email           TEXT DEFAULT '',
    plan            TEXT DEFAULT 'starter',
    aktiv           INTEGER DEFAULT 1,
    erstellt_am     TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS benutzer (
    id              BIGSERIAL PRIMARY KEY,
    kanzlei_id      TEXT NOT NULL REFERENCES kanzleien(id),
    benutzername    TEXT NOT NULL,
    hash            TEXT NOT NULL,
    salt            TEXT NOT NULL,
    rolle           TEXT DEFAULT 'assistent',
    email           TEXT DEFAULT '',
    aktiv           INTEGER DEFAULT 1,
    erstellt_am     TIMESTAMP DEFAULT NOW(),
    letzter_login   TIMESTAMP,
    UNIQUE (kanzlei_id, benutzername)
);

CREATE TABLE IF NOT EXISTS mandanten (
    id              TEXT PRIMARY KEY,
    kanzlei_id      TEXT NOT NULL REFERENCES kanzleien(id),
    name            TEXT NOT NULL,
    email           TEXT DEFAULT '',
    telefon         TEXT DEFAULT '',
    branche         TEXT DEFAULT '',
    umsatz          DOUBLE PRECISION DEFAULT 0,
    notizen         TEXT DEFAULT '',
    steuer_id       TEXT DEFAULT '',
    adresse         TEXT DEFAULT '',
    letzte_antwort  TEXT,
    letzte_email    TEXT,
    erstellt_am     TIMESTAMP DEFAULT NOW(),
    aktiv           INTEGER DEFAULT 1,
    UNIQUE (kanzlei_id, name)
);

CREATE TABLE IF NOT EXISTS aufgaben (
    id              TEXT PRIMARY KEY,
    kanzlei_id      TEXT NOT NULL REFERENCES kanzleien(id),
    mandant         TEXT NOT NULL,
    beschreibung    TEXT NOT NULL,
    frist           TEXT NOT NULL,
    prioritaet      TEXT DEFAULT 'normal',
    kategorie       TEXT DEFAULT '',
    erledigt        INTEGER DEFAULT 0,
    erledigt_am     TEXT,
    zugewiesen_an   TEXT DEFAULT '',
    notiz           TEXT DEFAULT '',
    quelle          TEXT DEFAULT 'manuell',
    erstellt_am     TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS kommunikation (
    id              TEXT PRIMARY KEY,
    kanzlei_id      TEXT NOT NULL REFERENCES kanzleien(id),
    mandant         TEXT NOT NULL,
    typ             TEXT NOT NULL,
    text            TEXT NOT NULL,
    richtung        TEXT DEFAULT 'ausgehend',
    erstellt_am     TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_log (
    id              BIGSERIAL PRIMARY KEY,
    kanzlei_id      TEXT NOT NULL REFERENCES kanzleien(id),
    aktion          TEXT NOT NULL,
    benutzer        TEXT DEFAULT 'system',
    details         TEXT DEFAULT '',
    ip_adresse      TEXT DEFAULT '',
    zeitpunkt       TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS email_outbox (
    id              BIGSERIAL PRIMARY KEY,
    kanzlei_id      TEXT NOT NULL REFERENCES kanzleien(id),
    mandant         TEXT NOT NULL,
    to_email        TEXT NOT NULL,
    subject         TEXT NOT NULL,
    body_text       TEXT NOT NULL,
    body_html       TEXT DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'pending',
    attempts        INTEGER NOT NULL DEFAULT 0,
    max_attempts    INTEGER NOT NULL DEFAULT 5,
    next_attempt_at TIMESTAMP DEFAULT NOW(),
    last_error      TEXT DEFAULT '',
    idempotency_key TEXT NOT NULL,
    created_at      TIMESTAMP DEFAULT NOW(),
    sent_at         TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_email_outbox_idem
    ON email_outbox (kanzlei_id, idempotency_key);

CREATE INDEX IF NOT EXISTS idx_mandanten_kid ON mandanten(kanzlei_id);
CREATE INDEX IF NOT EXISTS idx_aufgaben_kid ON aufgaben(kanzlei_id, mandant);
CREATE INDEX IF NOT EXISTS idx_audit_kid ON audit_log(kanzlei_id, zeitpunkt);

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

CREATE INDEX IF NOT EXISTS idx_email_outbox_due
    ON email_outbox (status, next_attempt_at, kanzlei_id);

CREATE INDEX IF NOT EXISTS idx_mandanten_kid ON mandanten(kanzlei_id);
CREATE INDEX IF NOT EXISTS idx_aufgaben_kid ON aufgaben(kanzlei_id, mandant);
CREATE INDEX IF NOT EXISTS idx_audit_kid ON audit_log(kanzlei_id, zeitpunkt);

-- Einstellungen / Portal (USE_POSTGRES_DATA=1: dieselbe DB wie Mandanten; ersetzt SQLite-Hybrid)
CREATE TABLE IF NOT EXISTS einstellungen (
    kanzlei_id TEXT NOT NULL REFERENCES kanzleien(id),
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    geaendert_am TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (kanzlei_id, key)
);

CREATE TABLE IF NOT EXISTS portal_records (
    id TEXT PRIMARY KEY,
    kanzlei_id TEXT NOT NULL REFERENCES kanzleien(id),
    typ TEXT NOT NULL,
    mandant TEXT NOT NULL,
    status TEXT DEFAULT '',
    data_json TEXT NOT NULL,
    erstellt_am TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    geaendert_am TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_portal_kid_typ ON portal_records(kanzlei_id, typ, mandant);

-- Default-Tenant (SQLite-kompatibel)
INSERT INTO kanzleien (id, name, email, plan, aktiv)
VALUES ('default', 'Standard-Kanzlei', '', 'starter', 1)
ON CONFLICT (id) DO NOTHING;

-- SaaS / Metering (kein SQLite mehr nötig für diese Domäne bei DATABASE_URL=postgresql)
CREATE TABLE IF NOT EXISTS api_keys (
    id               TEXT PRIMARY KEY,
    kanzlei_id       TEXT NOT NULL REFERENCES kanzleien(id),
    name             TEXT NOT NULL,
    key_hash         TEXT NOT NULL,
    permissions_json TEXT NOT NULL DEFAULT '[]',
    aktiv            INTEGER NOT NULL DEFAULT 1,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_api_keys_kid ON api_keys(kanzlei_id, aktiv);

CREATE TABLE IF NOT EXISTS webhook_endpoints (
    id           TEXT PRIMARY KEY,
    kanzlei_id   TEXT NOT NULL REFERENCES kanzleien(id),
    url          TEXT NOT NULL,
    secret       TEXT NOT NULL,
    events_json  TEXT NOT NULL DEFAULT '[]',
    aktiv        INTEGER NOT NULL DEFAULT 1,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_status  TEXT DEFAULT '',
    last_error   TEXT DEFAULT '',
    last_sent_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_webhook_endpoints_kid ON webhook_endpoints(kanzlei_id, aktiv);

CREATE TABLE IF NOT EXISTS webhook_queue (
    id              BIGSERIAL PRIMARY KEY,
    kanzlei_id      TEXT NOT NULL REFERENCES kanzleien(id),
    event_type      TEXT NOT NULL,
    payload_json    TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    attempts        INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_error      TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_webhook_queue_due ON webhook_queue(status, next_attempt_at, kanzlei_id);

CREATE TABLE IF NOT EXISTS usage_metrics (
    kanzlei_id TEXT NOT NULL REFERENCES kanzleien(id),
    metric     TEXT NOT NULL,
    day        TEXT NOT NULL,
    value      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (kanzlei_id, metric, day)
);
CREATE INDEX IF NOT EXISTS idx_usage_metric_day ON usage_metrics(metric, day);

CREATE TABLE IF NOT EXISTS agent_actions (
    id          BIGSERIAL PRIMARY KEY,
    kanzlei_id  TEXT NOT NULL REFERENCES kanzleien(id),
    action_key  TEXT NOT NULL,
    mandant     TEXT NOT NULL,
    aktion      TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'planned',
    details     TEXT DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (kanzlei_id, action_key)
);
CREATE INDEX IF NOT EXISTS idx_agent_actions_time ON agent_actions(kanzlei_id, created_at);

CREATE TABLE IF NOT EXISTS agent_locks (
    name        TEXT PRIMARY KEY,
    owner       TEXT NOT NULL,
    expires_at  BIGINT NOT NULL
);

-- Mandanten-Einladungen (Audit / Revoke; ergänzt HMAC-Token aus der API)
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
);
CREATE INDEX IF NOT EXISTS idx_tenant_invite_records_kid ON tenant_invite_records(kanzlei_id, id DESC);

-- Optional: SQLAlchemy-ORM-Tabelle ``users`` (parallel zu ``benutzer``; siehe backend/db/sqlalchemy_models.py)
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(512) NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    role VARCHAR(32) NOT NULL DEFAULT 'user',
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_users_tenant_id ON users(tenant_id);

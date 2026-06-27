CREATE DATABASE airflow;
CREATE DATABASE metabase;

\c condodata;

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS marts;
CREATE SCHEMA IF NOT EXISTS audit;
CREATE SCHEMA IF NOT EXISTS security;

-- ── Usuarios con privilegios mínimos ─────────────────────────────────────────

CREATE ROLE condodata_ingestion NOLOGIN;
CREATE ROLE condodata_api       NOLOGIN;
CREATE ROLE condodata_dbt       NOLOGIN;
CREATE ROLE condodata_readonly  NOLOGIN;

GRANT USAGE ON SCHEMA raw     TO condodata_ingestion;
GRANT USAGE ON SCHEMA audit   TO condodata_ingestion;
GRANT INSERT, SELECT ON ALL TABLES IN SCHEMA raw   TO condodata_ingestion;
GRANT INSERT, SELECT ON ALL TABLES IN SCHEMA audit TO condodata_ingestion;

GRANT USAGE ON SCHEMA staging TO condodata_api;
GRANT USAGE ON SCHEMA marts   TO condodata_api;
GRANT SELECT ON ALL TABLES IN SCHEMA staging TO condodata_api;
GRANT SELECT ON ALL TABLES IN SCHEMA marts   TO condodata_api;

GRANT USAGE ON SCHEMA raw     TO condodata_dbt;
GRANT USAGE ON SCHEMA staging TO condodata_dbt;
GRANT USAGE ON SCHEMA marts   TO condodata_dbt;
GRANT SELECT ON ALL TABLES IN SCHEMA raw     TO condodata_dbt;
GRANT ALL    ON ALL TABLES IN SCHEMA staging TO condodata_dbt;
GRANT ALL    ON ALL TABLES IN SCHEMA marts   TO condodata_dbt;

GRANT USAGE  ON SCHEMA marts TO condodata_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA marts TO condodata_readonly;

-- ── Tablas raw (bronze layer) ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS raw.bank_transactions (
    id              BIGSERIAL    PRIMARY KEY,
    source_file     TEXT         NOT NULL,
    source_hash     TEXT         NOT NULL,
    ingested_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    raw_date        TEXT,
    raw_description TEXT,
    raw_amount      TEXT,
    raw_reference   TEXT,
    page_number     INTEGER,
    row_number      INTEGER,
    condominio_id   INTEGER      NOT NULL
);

CREATE TABLE IF NOT EXISTS raw.cuotas (
    id              BIGSERIAL    PRIMARY KEY,
    source_file     TEXT         NOT NULL,
    source_hash     TEXT         NOT NULL,
    ingested_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    raw_unidad      TEXT,
    raw_propietario TEXT,
    raw_periodo     TEXT,
    raw_monto       TEXT,
    raw_fecha_pago  TEXT,
    raw_estado      TEXT,
    condominio_id   INTEGER      NOT NULL
);

CREATE TABLE IF NOT EXISTS raw.gastos (
    id              BIGSERIAL    PRIMARY KEY,
    source_file     TEXT         NOT NULL,
    source_hash     TEXT         NOT NULL,
    ingested_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    raw_fecha       TEXT,
    raw_proveedor   TEXT,
    raw_concepto    TEXT,
    raw_monto       TEXT,
    raw_categoria   TEXT,
    raw_comprobante TEXT,
    condominio_id   INTEGER      NOT NULL
);

-- ── Row-Level Security ────────────────────────────────────────────────────────

ALTER TABLE raw.bank_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE raw.cuotas            ENABLE ROW LEVEL SECURITY;
ALTER TABLE raw.gastos            ENABLE ROW LEVEL SECURITY;

CREATE POLICY bank_transactions_tenant ON raw.bank_transactions
    USING (condominio_id = current_setting('app.condominio_id', true)::integer);

CREATE POLICY cuotas_tenant ON raw.cuotas
    USING (condominio_id = current_setting('app.condominio_id', true)::integer);

CREATE POLICY gastos_tenant ON raw.gastos
    USING (condominio_id = current_setting('app.condominio_id', true)::integer);

-- ── Auditoría de ingesta ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS audit.ingestion_log (
    id              BIGSERIAL    PRIMARY KEY,
    run_id          UUID         NOT NULL DEFAULT gen_random_uuid(),
    source_type     TEXT         NOT NULL,
    source_file     TEXT,
    source_hash     TEXT,
    condominio_id   INTEGER,
    started_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    status          TEXT         NOT NULL DEFAULT 'running'
                                 CHECK (status IN ('running','success','failed')),
    records_read    INTEGER      CHECK (records_read >= 0),
    records_loaded  INTEGER      CHECK (records_loaded >= 0),
    records_failed  INTEGER      CHECK (records_failed >= 0),
    error_message   TEXT
);

-- ── Auditoría de accesos de la API ────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS security.access_log (
    id            BIGSERIAL   PRIMARY KEY,
    logged_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id       TEXT,
    condominio_id INTEGER,
    method        TEXT        NOT NULL,
    path          TEXT        NOT NULL,
    status_code   INTEGER     NOT NULL,
    ip_address    INET,
    duration_ms   NUMERIC(10,2)
);

-- ── Tabla de condominios ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS security.condominios (
    id            SERIAL      PRIMARY KEY,
    nombre        TEXT        NOT NULL,
    activo        BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Tabla de usuarios ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS security.users (
    id              SERIAL      PRIMARY KEY,
    username        TEXT        NOT NULL UNIQUE,
    hashed_password TEXT        NOT NULL,
    condominio_id   INTEGER     NOT NULL REFERENCES security.condominios(id),
    activo          BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login      TIMESTAMPTZ
);

-- ── Índices ───────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_bank_transactions_tenant
    ON raw.bank_transactions (condominio_id, ingested_at DESC);

CREATE INDEX IF NOT EXISTS idx_cuotas_tenant
    ON raw.cuotas (condominio_id, ingested_at DESC);

CREATE INDEX IF NOT EXISTS idx_gastos_tenant
    ON raw.gastos (condominio_id, ingested_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_bank_transactions_hash
    ON raw.bank_transactions (source_hash, condominio_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_cuotas_hash
    ON raw.cuotas (source_hash, condominio_id);

CREATE INDEX IF NOT EXISTS idx_access_log_user
    ON security.access_log (user_id, logged_at DESC);

CREATE INDEX IF NOT EXISTS idx_ingestion_log_run
    ON audit.ingestion_log (run_id, started_at DESC);

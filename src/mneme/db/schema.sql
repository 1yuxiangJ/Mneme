-- mneme database schema (PostgreSQL 17+ with pgvector)
--
-- Apply once at setup time:
--   psql mneme -f src/mneme/db/schema.sql
--
-- Idempotent: safe to re-run.

CREATE EXTENSION IF NOT EXISTS vector;


-- =============================================================
-- core_blocks: structured large-grained user model blocks.
--
-- ACCESS POLICY (Letta read-only primary):
--   - Awake agent: READ ONLY
--   - Sleep agent: SOLE WRITER (via promote / consolidate / reflect)
--
-- The `last_writer` column is a self-check; application layer
-- must reject writes from non-sleep actors and log to memory_ops_log.
-- =============================================================
CREATE TABLE IF NOT EXISTS core_blocks (
    label         TEXT PRIMARY KEY,
    value         TEXT NOT NULL,
    char_limit    INT  NOT NULL DEFAULT 2000,
    version       INT  NOT NULL DEFAULT 1,
    last_writer   TEXT NOT NULL DEFAULT 'sleep_agent',
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Pre-seed empty core blocks (5 fixed labels for MVP).
INSERT INTO core_blocks (label, value) VALUES
    ('background',      ''),
    ('preferences',     ''),
    ('habits',          ''),
    ('skills',          ''),
    ('lessons_learned', '')
ON CONFLICT (label) DO NOTHING;


-- =============================================================
-- archival_facts: small-grained facts with vector embedding.
-- Awake writes during `remember`. Sleep writes during consolidate / demote.
-- =============================================================
CREATE TABLE IF NOT EXISTS archival_facts (
    id            BIGSERIAL PRIMARY KEY,
    content       TEXT NOT NULL,
    tags          TEXT[],
    confidence    SMALLINT NOT NULL DEFAULT 2,  -- 1=low 2=med 3=high
    source        TEXT,                          -- session id / origin tag
    embedding     vector(1024),                  -- 阿里通义 text-embedding-v3
    is_deleted    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at  TIMESTAMPTZ,
    use_count     INT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_archival_embedding
    ON archival_facts
    USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_archival_tags
    ON archival_facts USING GIN (tags);

CREATE INDEX IF NOT EXISTS idx_archival_active
    ON archival_facts (is_deleted, created_at DESC)
    WHERE is_deleted = FALSE;


-- =============================================================
-- memory_ops_log: append-only audit log of every memory mutation.
-- Sleep agent uses this for diff review. User can inspect manually.
-- =============================================================
CREATE TABLE IF NOT EXISTS memory_ops_log (
    id            BIGSERIAL PRIMARY KEY,
    op_type       TEXT NOT NULL,  -- remember / recall / forget / sleep_consolidate / sleep_promote / sleep_demote / sleep_resolve / sleep_reflect / policy_violation
    actor         TEXT NOT NULL,  -- 'awake_agent' / 'sleep_agent'
    target_kind   TEXT,           -- 'core' / 'archival'
    target_id     TEXT,           -- core label or archival id (cast to text)
    before_value  TEXT,
    after_value   TEXT,
    reason        TEXT,           -- LLM rationale (free text)
    ts            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ops_log_ts    ON memory_ops_log(ts DESC);
CREATE INDEX IF NOT EXISTS idx_ops_log_actor ON memory_ops_log(actor, ts DESC);


-- =============================================================
-- staging tables (built on-the-fly by Sleep agent each cycle).
-- Defined here for reference only:
--   CREATE TABLE core_blocks_staging      (LIKE core_blocks      INCLUDING ALL);
--   CREATE TABLE archival_facts_staging   (LIKE archival_facts   INCLUDING ALL);
-- See sleep/agent.py for atomic swap logic.
-- =============================================================

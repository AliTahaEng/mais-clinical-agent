-- ─────────────────────────────────────────────────────────────────────────────
-- PostgreSQL Schema Migration 001 — Audit Log + LangGraph Checkpoints
-- Run with: psql -U mais_user -d mais_db -f 001_postgres_schema.sql
-- ─────────────────────────────────────────────────────────────────────────────

-- ── Audit log (append-only) ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_log (
    id               BIGSERIAL PRIMARY KEY,
    event_type       VARCHAR(100) NOT NULL,
    agent_id         VARCHAR(100) NOT NULL,
    session_id       VARCHAR(128) NOT NULL,
    payload          JSONB        NOT NULL DEFAULT '{}',
    timestamp        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    idempotency_key  VARCHAR(256) NOT NULL DEFAULT '',

    CONSTRAINT audit_log_idempotency_key_unique
        UNIQUE (idempotency_key)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX IF NOT EXISTS audit_log_session_idx
    ON audit_log (session_id);

CREATE INDEX IF NOT EXISTS audit_log_event_type_idx
    ON audit_log (event_type);

CREATE INDEX IF NOT EXISTS audit_log_timestamp_idx
    ON audit_log (timestamp DESC);

-- Row-level security: only the application role can insert
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY audit_log_insert_policy ON audit_log
    FOR INSERT TO mais_user WITH CHECK (TRUE);

CREATE POLICY audit_log_select_policy ON audit_log
    FOR SELECT TO mais_user USING (TRUE);

-- Prevent updates and deletes (audit trail is immutable)
CREATE RULE no_update_audit AS ON UPDATE TO audit_log DO INSTEAD NOTHING;
CREATE RULE no_delete_audit AS ON DELETE TO audit_log DO INSTEAD NOTHING;


-- ── LangGraph checkpointer tables ─────────────────────────────────────────
-- These are created automatically by AsyncPostgresSaver.setup()
-- but are listed here for documentation purposes.
--
-- checkpoints    — stores graph state snapshots
-- checkpoint_blobs — stores large state blobs
-- checkpoint_writes — stores pending writes

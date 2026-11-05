-- Migration 0002: Phase 1 schema extensions
-- Adds hash chain fields to audit_log, authorization and roe to engagements,
-- and composite indexes for task scheduling queries.

-- ---------------------------------------------------------------------------
-- Engagements: add client, auth_reference, and roe policy JSON
-- ---------------------------------------------------------------------------
ALTER TABLE engagements ADD COLUMN client TEXT NOT NULL DEFAULT '';
ALTER TABLE engagements ADD COLUMN auth_reference TEXT NOT NULL DEFAULT '';
ALTER TABLE engagements ADD COLUMN roe TEXT NOT NULL DEFAULT '{}';

-- ---------------------------------------------------------------------------
-- Audit log: add cryptographic chaining hashes
-- ---------------------------------------------------------------------------
ALTER TABLE audit_log ADD COLUMN prev_hash TEXT NOT NULL DEFAULT '0000000000000000000000000000000000000000000000000000000000000000';
ALTER TABLE audit_log ADD COLUMN entry_hash TEXT NOT NULL DEFAULT '';

-- ---------------------------------------------------------------------------
-- Tasks: composite index for scheduler queries and unique task_uuid column
-- ---------------------------------------------------------------------------
ALTER TABLE tasks ADD COLUMN task_uuid TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_uuid
    ON tasks (task_uuid);

CREATE INDEX IF NOT EXISTS idx_tasks_engagement_status
    ON tasks (engagement_id, status);

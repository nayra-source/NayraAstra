-- Migration 0001: initial schema
-- All timestamps are TEXT in ISO-8601 UTC format: YYYY-MM-DDTHH:MM:SSZ
-- Foreign keys must be enabled before connecting (PRAGMA foreign_keys=ON).

-- ---------------------------------------------------------------------------
-- Engagements
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS engagements (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'paused', 'completed', 'archived'))
);

-- ---------------------------------------------------------------------------
-- Scope entries (allowlist / denylist)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scope_entries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id   TEXT    NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    entry_type      TEXT    NOT NULL CHECK (entry_type IN ('allow', 'deny')),
    value           TEXT    NOT NULL,
    description     TEXT    NOT NULL DEFAULT '',
    created_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scope_entries_engagement
    ON scope_entries (engagement_id);

-- ---------------------------------------------------------------------------
-- Hosts
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hosts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id   TEXT    NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    address         TEXT    NOT NULL,
    hostname        TEXT,
    os_guess        TEXT,
    first_seen      TEXT    NOT NULL,
    last_seen       TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_hosts_engagement
    ON hosts (engagement_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_hosts_engagement_address
    ON hosts (engagement_id, address);

-- ---------------------------------------------------------------------------
-- Tasks
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id   TEXT    NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    workflow_run_id INTEGER REFERENCES workflow_runs(id) ON DELETE SET NULL,
    module_name     TEXT    NOT NULL,
    adapter_name    TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'pending'
                    CHECK (status IN (
                        'pending','running','succeeded',
                        'failed','skipped','blocked','cancelled'
                    )),
    intrusiveness   TEXT    NOT NULL DEFAULT 'passive'
                    CHECK (intrusiveness IN (
                        'passive','active-safe','active-intrusive','disruptive'
                    )),
    args            TEXT    NOT NULL DEFAULT '{}',   -- JSON blob
    started_at      TEXT,
    finished_at     TEXT,
    exit_code       INTEGER,
    error_message   TEXT,
    created_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_engagement
    ON tasks (engagement_id);

CREATE INDEX IF NOT EXISTS idx_tasks_status
    ON tasks (status);

-- ---------------------------------------------------------------------------
-- Artifacts
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS artifacts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    engagement_id   TEXT    NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    artifact_type   TEXT    NOT NULL,  -- e.g. 'raw_output', 'pcap', 'screenshot'
    mime_type       TEXT    NOT NULL DEFAULT 'application/octet-stream',
    path            TEXT    NOT NULL,  -- relative to engagement workspace
    size_bytes      INTEGER NOT NULL DEFAULT 0,
    sha256          TEXT,
    created_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_artifacts_task
    ON artifacts (task_id);

CREATE INDEX IF NOT EXISTS idx_artifacts_engagement
    ON artifacts (engagement_id);

-- ---------------------------------------------------------------------------
-- Observations  (raw, structured output from a single task)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS observations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    engagement_id   TEXT    NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    host_id         INTEGER REFERENCES hosts(id) ON DELETE SET NULL,
    observation_key TEXT    NOT NULL,  -- e.g. 'open_port', 'banner', 'cve'
    value           TEXT    NOT NULL,  -- JSON blob
    observed_at     TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_observations_task
    ON observations (task_id);

CREATE INDEX IF NOT EXISTS idx_observations_engagement
    ON observations (engagement_id);

-- ---------------------------------------------------------------------------
-- Findings
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS findings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id   TEXT    NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    host_id         INTEGER REFERENCES hosts(id) ON DELETE SET NULL,
    title           TEXT    NOT NULL,
    description     TEXT    NOT NULL DEFAULT '',
    severity        TEXT    NOT NULL
                    CHECK (severity IN ('info','low','medium','high','critical')),
    confidence      TEXT    NOT NULL
                    CHECK (confidence IN ('tentative','likely','confirmed')),
    status          TEXT    NOT NULL DEFAULT 'new'
                    CHECK (status IN ('new','validated','false_positive','accepted_risk')),
    cve             TEXT,
    cvss_score      REAL,
    remediation     TEXT    NOT NULL DEFAULT '',
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_findings_engagement
    ON findings (engagement_id);

CREATE INDEX IF NOT EXISTS idx_findings_severity
    ON findings (severity);

-- ---------------------------------------------------------------------------
-- Finding evidence (links findings to observations and artifacts)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS finding_evidence (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id      INTEGER NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    observation_id  INTEGER REFERENCES observations(id) ON DELETE SET NULL,
    artifact_id     INTEGER REFERENCES artifacts(id) ON DELETE SET NULL,
    note            TEXT    NOT NULL DEFAULT '',
    added_at        TEXT    NOT NULL,
    CHECK (observation_id IS NOT NULL OR artifact_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_finding_evidence_finding
    ON finding_evidence (finding_id);

-- ---------------------------------------------------------------------------
-- Workflow runs
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS workflow_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id   TEXT    NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    workflow_name   TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'pending'
                    CHECK (status IN (
                        'pending','running','succeeded',
                        'failed','cancelled'
                    )),
    dry_run         INTEGER NOT NULL DEFAULT 0 CHECK (dry_run IN (0, 1)),
    started_at      TEXT,
    finished_at     TEXT,
    created_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_engagement
    ON workflow_runs (engagement_id);

-- ---------------------------------------------------------------------------
-- Audit log  (append-only via triggers)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT    NOT NULL,  -- e.g. 'task.start', 'finding.created'
    actor       TEXT    NOT NULL DEFAULT 'system',
    entity_type TEXT    NOT NULL,
    entity_id   TEXT    NOT NULL,
    payload     TEXT    NOT NULL DEFAULT '{}',  -- JSON blob
    logged_at   TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_log_entity
    ON audit_log (entity_type, entity_id);

CREATE INDEX IF NOT EXISTS idx_audit_log_logged_at
    ON audit_log (logged_at);

-- Immutability: prevent UPDATE and DELETE on audit_log rows.
CREATE TRIGGER IF NOT EXISTS audit_log_no_update
BEFORE UPDATE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log rows are immutable: UPDATE is not allowed');
END;

CREATE TRIGGER IF NOT EXISTS audit_log_no_delete
BEFORE DELETE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log rows are immutable: DELETE is not allowed');
END;


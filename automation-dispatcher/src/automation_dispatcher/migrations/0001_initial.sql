CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY CHECK (version > 0),
    name TEXT NOT NULL UNIQUE,
    checksum TEXT NOT NULL CHECK (length(checksum) = 64),
    applied_at TEXT NOT NULL
);

CREATE TABLE dispatchers (
    dispatcher_id TEXT PRIMARY KEY,
    cadence_class TEXT NOT NULL CHECK (cadence_class IN ('daily', 'weekly')),
    automation_id TEXT,
    expected_task_id TEXT,
    expected_working_directory TEXT,
    expected_harness TEXT,
    expected_host TEXT,
    default_reporting_task_id TEXT,
    heartbeat_schedule_json TEXT NOT NULL DEFAULT '{}',
    timezone TEXT NOT NULL DEFAULT 'UTC',
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    installed_skill_version TEXT,
    source_revision TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE dispatcher_routes (
    route_id TEXT PRIMARY KEY,
    dispatcher_id TEXT NOT NULL REFERENCES dispatchers(dispatcher_id),
    revision INTEGER NOT NULL CHECK (revision > 0),
    destination_task_id TEXT NOT NULL,
    expected_working_directory TEXT,
    expected_harness TEXT,
    expected_host TEXT,
    required_identity_json TEXT NOT NULL DEFAULT '{}',
    effective_at TEXT NOT NULL,
    actor TEXT,
    reason TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (dispatcher_id, revision)
);

CREATE TABLE workflows (
    workflow_id TEXT PRIMARY KEY,
    dispatcher_id TEXT NOT NULL REFERENCES dispatchers(dispatcher_id),
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    definition_path TEXT NOT NULL,
    definition_revision TEXT NOT NULL,
    definition_hash TEXT NOT NULL CHECK (length(definition_hash) = 64),
    normalized_definition_json TEXT NOT NULL,
    timezone TEXT NOT NULL,
    schedule_json TEXT NOT NULL,
    next_due_at TEXT,
    max_lateness_seconds INTEGER NOT NULL CHECK (max_lateness_seconds >= 0),
    catch_up_policy TEXT NOT NULL,
    max_lookback_seconds INTEGER NOT NULL CHECK (max_lookback_seconds >= 0),
    retry_policy_json TEXT NOT NULL,
    claim_lease_seconds INTEGER NOT NULL CHECK (claim_lease_seconds > 0),
    procedure_kind TEXT NOT NULL,
    procedure_reference TEXT NOT NULL,
    external_effect_mode TEXT NOT NULL,
    reconciliation_reference TEXT,
    authority_references_json TEXT NOT NULL DEFAULT '[]',
    reporting_task_id TEXT NOT NULL,
    receipt_template_json TEXT NOT NULL DEFAULT '{}',
    data_sensitivity TEXT NOT NULL DEFAULT 'internal',
    evidence_retention_json TEXT NOT NULL DEFAULT '{}',
    current_revision INTEGER NOT NULL CHECK (current_revision > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE workflow_revisions (
    workflow_id TEXT NOT NULL REFERENCES workflows(workflow_id),
    revision INTEGER NOT NULL CHECK (revision > 0),
    dispatcher_id TEXT NOT NULL REFERENCES dispatchers(dispatcher_id),
    definition_path TEXT NOT NULL,
    definition_revision TEXT NOT NULL,
    normalized_definition_json TEXT NOT NULL,
    definition_hash TEXT NOT NULL CHECK (length(definition_hash) = 64),
    actor TEXT,
    reason TEXT,
    effective_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workflow_id, revision)
);

CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES workflows(workflow_id),
    workflow_revision INTEGER NOT NULL,
    scheduled_for TEXT NOT NULL,
    occurrence_key TEXT NOT NULL UNIQUE,
    discovered_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    state TEXT NOT NULL CHECK (
        state IN (
            'claimed', 'running', 'succeeded', 'failed', 'skipped',
            'abandoned', 'effect_unknown', 'recovered'
        )
    ),
    claim_owner TEXT,
    claim_time TEXT,
    lease_expires_at TEXT,
    attempt INTEGER NOT NULL DEFAULT 1 CHECK (attempt > 0),
    recovery_of_run_id TEXT REFERENCES runs(run_id),
    prior_claim_owner TEXT,
    external_effect_key TEXT,
    reconciliation_state TEXT,
    reconciliation_evidence_json TEXT,
    configured_identity_json TEXT,
    observed_identity_json TEXT,
    output_summary TEXT,
    evidence_json TEXT,
    error_class TEXT,
    receipt_hash TEXT,
    UNIQUE (workflow_id, scheduled_for),
    FOREIGN KEY (workflow_id, workflow_revision)
        REFERENCES workflow_revisions(workflow_id, revision)
);

CREATE TABLE audit_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    dispatcher_id TEXT NOT NULL REFERENCES dispatchers(dispatcher_id),
    workflow_id TEXT REFERENCES workflows(workflow_id),
    run_id TEXT REFERENCES runs(run_id),
    event_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    actor TEXT,
    observed_identity_json TEXT,
    payload_json TEXT NOT NULL,
    previous_event_hash TEXT,
    event_hash TEXT NOT NULL UNIQUE CHECK (length(event_hash) = 64)
);

CREATE INDEX audit_events_dispatcher_chain
    ON audit_events(dispatcher_id, event_id);
CREATE INDEX audit_events_run
    ON audit_events(run_id, event_id);

CREATE TABLE receipts (
    receipt_id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES runs(run_id),
    workflow_id TEXT REFERENCES workflows(workflow_id),
    dispatcher_id TEXT NOT NULL REFERENCES dispatchers(dispatcher_id),
    destination_task_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'posting', 'posted', 'failed')),
    rendered_content TEXT NOT NULL,
    content_hash TEXT NOT NULL CHECK (length(content_hash) = 64),
    created_at TEXT NOT NULL,
    posted_at TEXT,
    external_message_id TEXT,
    delivery_attempt INTEGER NOT NULL DEFAULT 0 CHECK (delivery_attempt >= 0),
    last_attempt_at TEXT
);

CREATE INDEX receipts_dispatcher_status
    ON receipts(dispatcher_id, status, created_at);
CREATE UNIQUE INDEX receipts_one_per_run
    ON receipts(run_id) WHERE run_id IS NOT NULL;

CREATE TRIGGER dispatcher_routes_no_update
BEFORE UPDATE ON dispatcher_routes
BEGIN
    SELECT RAISE(ABORT, 'dispatcher_routes are immutable');
END;

CREATE TRIGGER dispatcher_routes_no_delete
BEFORE DELETE ON dispatcher_routes
BEGIN
    SELECT RAISE(ABORT, 'dispatcher_routes are immutable');
END;

CREATE TRIGGER workflow_revisions_no_update
BEFORE UPDATE ON workflow_revisions
BEGIN
    SELECT RAISE(ABORT, 'workflow_revisions are immutable');
END;

CREATE TRIGGER workflow_revisions_no_delete
BEFORE DELETE ON workflow_revisions
BEGIN
    SELECT RAISE(ABORT, 'workflow_revisions are immutable');
END;

CREATE TRIGGER audit_events_no_update
BEFORE UPDATE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'audit_events are immutable');
END;

CREATE TRIGGER audit_events_no_delete
BEFORE DELETE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'audit_events are immutable');
END;

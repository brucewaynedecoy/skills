ALTER TABLE dispatchers
    ADD COLUMN name TEXT NOT NULL DEFAULT '';

ALTER TABLE dispatchers
    ADD COLUMN description TEXT NOT NULL DEFAULT '';

ALTER TABLE dispatchers
    ADD COLUMN current_revision INTEGER NOT NULL DEFAULT 1
        CHECK (current_revision > 0);

ALTER TABLE dispatchers
    ADD COLUMN schedule_json TEXT NOT NULL DEFAULT '{}';

ALTER TABLE dispatchers
    ADD COLUMN max_lateness_seconds INTEGER NOT NULL DEFAULT 0
        CHECK (max_lateness_seconds >= 0);

ALTER TABLE dispatchers
    ADD COLUMN catch_up_policy TEXT NOT NULL DEFAULT 'none';

ALTER TABLE dispatchers
    ADD COLUMN max_lookback_seconds INTEGER NOT NULL DEFAULT 0
        CHECK (max_lookback_seconds >= 0);

UPDATE dispatchers
SET name = dispatcher_id,
    schedule_json = canonical_collection_schedule_json((
        SELECT schedule_json
        FROM workflows
        WHERE workflows.dispatcher_id = dispatchers.dispatcher_id
        ORDER BY workflow_id
        LIMIT 1
    )),
    timezone = trim((
        SELECT timezone
        FROM workflows
        WHERE workflows.dispatcher_id = dispatchers.dispatcher_id
        ORDER BY workflow_id
        LIMIT 1
    )),
    max_lateness_seconds = (
        SELECT max_lateness_seconds
        FROM workflows
        WHERE workflows.dispatcher_id = dispatchers.dispatcher_id
        ORDER BY workflow_id
        LIMIT 1
    ),
    catch_up_policy = lower(trim((
        SELECT catch_up_policy
        FROM workflows
        WHERE workflows.dispatcher_id = dispatchers.dispatcher_id
        ORDER BY workflow_id
        LIMIT 1
    ))),
    max_lookback_seconds = (
        SELECT max_lookback_seconds
        FROM workflows
        WHERE workflows.dispatcher_id = dispatchers.dispatcher_id
        ORDER BY workflow_id
        LIMIT 1
    );

ALTER TABLE dispatchers DROP COLUMN cadence_class;

CREATE TABLE dispatcher_revisions (
    dispatcher_id TEXT NOT NULL REFERENCES dispatchers(dispatcher_id),
    revision INTEGER NOT NULL CHECK (revision > 0),
    normalized_config_json TEXT NOT NULL,
    config_hash TEXT NOT NULL CHECK (length(config_hash) = 64),
    actor TEXT,
    reason TEXT,
    effective_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (dispatcher_id, revision)
);

INSERT INTO dispatcher_revisions (
    dispatcher_id,
    revision,
    normalized_config_json,
    config_hash,
    actor,
    reason,
    effective_at,
    created_at
)
SELECT dispatcher_id,
       current_revision,
       normalized_config_json,
       sha256_hex(normalized_config_json),
       'migration-0002',
       'deterministic upgrade from workflow-owned timing',
       created_at,
       created_at
FROM (
    SELECT dispatcher_id,
           current_revision,
           created_at,
           canonical_dispatcher_configuration_json(
               dispatcher_id,
               name,
               description,
               timezone,
               schedule_json,
               max_lateness_seconds,
               catch_up_policy,
               max_lookback_seconds,
               heartbeat_schedule_json,
               enabled
           ) AS normalized_config_json
    FROM dispatchers
);

CREATE TRIGGER dispatcher_revisions_no_update
BEFORE UPDATE ON dispatcher_revisions
BEGIN
    SELECT RAISE(ABORT, 'dispatcher_revisions are immutable');
END;

CREATE TRIGGER dispatcher_revisions_no_delete
BEFORE DELETE ON dispatcher_revisions
BEGIN
    SELECT RAISE(ABORT, 'dispatcher_revisions are immutable');
END;

CREATE TRIGGER dispatchers_current_revision_valid
BEFORE UPDATE OF current_revision ON dispatchers
WHEN NOT EXISTS (
    SELECT 1
    FROM dispatcher_revisions
    WHERE dispatcher_id = NEW.dispatcher_id
      AND revision = NEW.current_revision
)
BEGIN
    SELECT RAISE(ABORT, 'dispatcher current revision does not exist');
END;

ALTER TABLE workflows DROP COLUMN timezone;
ALTER TABLE workflows DROP COLUMN schedule_json;
ALTER TABLE workflows DROP COLUMN next_due_at;
ALTER TABLE workflows DROP COLUMN max_lateness_seconds;
ALTER TABLE workflows DROP COLUMN catch_up_policy;
ALTER TABLE workflows DROP COLUMN max_lookback_seconds;

CREATE TRIGGER workflows_dispatcher_no_update
BEFORE UPDATE OF dispatcher_id ON workflows
WHEN NEW.dispatcher_id <> OLD.dispatcher_id
BEGIN
    SELECT RAISE(ABORT, 'workflow dispatcher ownership is immutable');
END;

ALTER TABLE runs
    ADD COLUMN dispatcher_revision INTEGER NOT NULL DEFAULT 1
        CHECK (dispatcher_revision > 0);

CREATE TRIGGER runs_dispatcher_revision_valid_insert
BEFORE INSERT ON runs
WHEN NOT EXISTS (
    SELECT 1
    FROM workflows AS workflow
    JOIN dispatcher_revisions AS revision
      ON revision.dispatcher_id = workflow.dispatcher_id
     AND revision.revision = NEW.dispatcher_revision
    WHERE workflow.workflow_id = NEW.workflow_id
)
BEGIN
    SELECT RAISE(ABORT, 'run dispatcher revision does not exist for workflow collection');
END;

CREATE TRIGGER runs_dispatcher_revision_valid_update
BEFORE UPDATE OF workflow_id, dispatcher_revision ON runs
WHEN NOT EXISTS (
    SELECT 1
    FROM workflows AS workflow
    JOIN dispatcher_revisions AS revision
      ON revision.dispatcher_id = workflow.dispatcher_id
     AND revision.revision = NEW.dispatcher_revision
    WHERE workflow.workflow_id = NEW.workflow_id
)
BEGIN
    SELECT RAISE(ABORT, 'run dispatcher revision does not exist for workflow collection');
END;

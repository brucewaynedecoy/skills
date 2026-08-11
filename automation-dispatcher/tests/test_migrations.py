from __future__ import annotations

from hashlib import sha256
from importlib import resources
import json
import sqlite3

import pytest

from automation_dispatcher.database import (
    BUSY_TIMEOUT_MS,
    MigrationError,
    connect,
    initialize_database,
    migrate,
)
from automation_dispatcher.registry import dispatcher_configuration_from_row


EXPECTED_TABLES = {
    "schema_migrations",
    "dispatchers",
    "dispatcher_revisions",
    "dispatcher_routes",
    "workflows",
    "workflow_revisions",
    "runs",
    "audit_events",
    "receipts",
}

NOW = "2026-01-01T00:00:00Z"


def _initialize_v1(path, *, workflows=("workflow-a",), second_schedule=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    migration = resources.files("automation_dispatcher.migrations").joinpath(
        "0001_initial.sql"
    )
    content = migration.read_bytes()
    conn = sqlite3.connect(path)
    conn.executescript(content.decode("utf-8"))
    conn.execute(
        "INSERT INTO schema_migrations(version, name, checksum, applied_at) "
        "VALUES (1, '0001_initial.sql', ?, ?)",
        (sha256(content).hexdigest(), NOW),
    )
    conn.execute(
        "INSERT INTO dispatchers (dispatcher_id, cadence_class, timezone, created_at, "
        "updated_at) VALUES ('ops-collection', 'daily', 'UTC', ?, ?)",
        (NOW, NOW),
    )
    for index, workflow_id in enumerate(workflows):
        schedule = (
            second_schedule
            if index == 1 and second_schedule is not None
            else '{"version":1,"frequency":"daily","time":"06:00:00","weekdays":[]}'
        )
        definition = f'{{"workflow_id":"{workflow_id}"}}'
        conn.execute(
            "INSERT INTO workflows ("
            "workflow_id, dispatcher_id, name, definition_path, definition_revision, "
            "definition_hash, normalized_definition_json, timezone, schedule_json, "
            "max_lateness_seconds, catch_up_policy, max_lookback_seconds, "
            "retry_policy_json, claim_lease_seconds, procedure_kind, procedure_reference, "
            "external_effect_mode, reporting_task_id, current_revision, created_at, updated_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                workflow_id,
                "ops-collection",
                workflow_id,
                f"/tmp/{workflow_id}.json",
                "v1",
                chr(ord("a") + index) * 64,
                definition,
                "America/Chicago",
                schedule,
                900,
                "bounded",
                86400,
                "{}",
                60,
                "script",
                f"/tmp/{workflow_id}.py",
                "none",
                "task-1",
                1,
                NOW,
                NOW,
            ),
        )
        conn.execute(
            "INSERT INTO workflow_revisions ("
            "workflow_id, revision, dispatcher_id, definition_path, definition_revision, "
            "normalized_definition_json, definition_hash, effective_at, created_at"
            ") VALUES (?,1,'ops-collection',?,'v1',?,?,?,?)",
            (
                workflow_id,
                f"/tmp/{workflow_id}.json",
                definition,
                chr(ord("a") + index) * 64,
                NOW,
                NOW,
            ),
        )
    conn.commit()
    conn.close()


def test_fresh_and_repeated_initialization(tmp_path):
    path = tmp_path / "state" / "daily.sqlite3"

    first = initialize_database(path)
    second = initialize_database(path)

    assert [item["version"] for item in first["applied_migrations"]] == [1, 2]
    assert second["applied_migrations"] == []
    assert first["schema_version"] == second["schema_version"] == 2
    assert first["verification"]["ok"] is True

    conn = connect(path)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert EXPECTED_TABLES <= tables
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == BUSY_TIMEOUT_MS
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    finally:
        conn.close()


def test_every_connect_enforces_foreign_keys(tmp_path):
    path = tmp_path / "daily.sqlite3"
    initialize_database(path)

    for _ in range(2):
        conn = connect(path)
        try:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO workflows ("
                    "workflow_id, dispatcher_id, name, definition_path, "
                    "definition_revision, definition_hash, normalized_definition_json, "
                    "retry_policy_json, claim_lease_seconds, "
                    "procedure_kind, procedure_reference, external_effect_mode, "
                    "reporting_task_id, current_revision, created_at, updated_at"
                    ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        "missing-parent", "no-dispatcher", "Missing", "/tmp/x", "v1",
                        "a" * 64, "{}", "{}", 60,
                        "script", "/tmp/x", "none", "task", 1, "2026-01-01T00:00:00Z",
                        "2026-01-01T00:00:00Z",
                    ),
                )
            conn.rollback()
        finally:
            conn.close()


def test_migration_checksum_mismatch_fails_closed(tmp_path):
    path = tmp_path / "daily.sqlite3"
    initialize_database(path)
    conn = connect(path)
    try:
        conn.execute("UPDATE schema_migrations SET checksum = ? WHERE version = 1", ("0" * 64,))
        conn.commit()
        with pytest.raises(MigrationError, match="checksum mismatch"):
            migrate(conn)
    finally:
        conn.close()


def test_migrate_refuses_to_take_over_an_active_transaction(tmp_path):
    path = tmp_path / "daily.sqlite3"
    initialize_database(path)
    conn = connect(path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        with pytest.raises(MigrationError, match="active transaction"):
            migrate(conn)
        conn.rollback()
    finally:
        conn.close()


def test_v1_upgrade_moves_equal_timing_to_immutable_collection_revision(tmp_path):
    path = tmp_path / "ops.sqlite3"
    _initialize_v1(path, workflows=("workflow-a", "workflow-b"))
    conn = connect(path)
    try:
        conn.execute(
            "INSERT INTO runs (run_id, workflow_id, workflow_revision, scheduled_for, "
            "occurrence_key, discovered_at, state) "
            "VALUES ('legacy-run','workflow-a',1,?,'legacy-occurrence',?,'succeeded')",
            (NOW, NOW),
        )
        conn.commit()
        result = migrate(conn)
        assert [item["version"] for item in result] == [2]
        dispatcher = conn.execute(
            "SELECT * FROM dispatchers WHERE dispatcher_id = 'ops-collection'"
        ).fetchone()
        assert dispatcher["name"] == "ops-collection"
        assert dispatcher["timezone"] == "America/Chicago"
        assert dispatcher["schedule_json"] == (
            '{"expression":"0 6 * * *","kind":"cron","version":2}'
        )
        assert dispatcher["max_lateness_seconds"] == 900
        assert dispatcher["catch_up_policy"] == "bounded"
        assert dispatcher["max_lookback_seconds"] == 86400

        dispatcher_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(dispatchers)")
        }
        workflow_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(workflows)")
        }
        assert "cadence_class" not in dispatcher_columns
        assert {
            "timezone",
            "schedule_json",
            "next_due_at",
            "max_lateness_seconds",
            "catch_up_policy",
            "max_lookback_seconds",
        }.isdisjoint(workflow_columns)

        revision = conn.execute(
            "SELECT * FROM dispatcher_revisions WHERE dispatcher_id = 'ops-collection'"
        ).fetchone()
        assert revision["revision"] == 1
        assert revision["config_hash"] == sha256(
            revision["normalized_config_json"].encode("utf-8")
        ).hexdigest()
        assert json.loads(revision["normalized_config_json"]) == (
            dispatcher_configuration_from_row(dispatcher)
        )
        assert conn.execute(
            "SELECT dispatcher_revision FROM runs WHERE run_id = 'legacy-run'"
        ).fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute(
                "UPDATE dispatcher_revisions SET reason = 'rewrite' "
                "WHERE dispatcher_id = 'ops-collection' AND revision = 1"
            )
        conn.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute(
                "DELETE FROM dispatcher_revisions "
                "WHERE dispatcher_id = 'ops-collection' AND revision = 1"
            )
        conn.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="current revision"):
            conn.execute(
                "UPDATE dispatchers SET current_revision = 2 "
                "WHERE dispatcher_id = 'ops-collection'"
            )
        conn.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="ownership is immutable"):
            conn.execute(
                "UPDATE workflows SET dispatcher_id = 'other-collection' "
                "WHERE workflow_id = 'workflow-a'"
            )
        conn.rollback()
    finally:
        conn.close()


def test_v1_upgrade_fails_closed_on_missing_or_mixed_timing(tmp_path):
    missing_path = tmp_path / "missing.sqlite3"
    _initialize_v1(missing_path, workflows=())
    missing = connect(missing_path)
    try:
        with pytest.raises(MigrationError, match="requires legacy timing evidence"):
            migrate(missing)
        assert missing.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] == 1
    finally:
        missing.close()

    mixed_path = tmp_path / "mixed.sqlite3"
    _initialize_v1(
        mixed_path,
        workflows=("workflow-a", "workflow-b"),
        second_schedule=(
            '{"version":1,"frequency":"daily","time":"07:00:00","weekdays":[]}'
        ),
    )
    mixed = connect(mixed_path)
    try:
        with pytest.raises(MigrationError, match="mixed legacy timing"):
            migrate(mixed)
        assert mixed.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] == 1
    finally:
        mixed.close()


def test_runs_require_a_dispatcher_revision_for_the_workflow_collection(tmp_path):
    path = tmp_path / "ops.sqlite3"
    _initialize_v1(path)
    conn = connect(path)
    try:
        migrate(conn)
        with pytest.raises(sqlite3.IntegrityError, match="dispatcher revision"):
            conn.execute(
                "INSERT INTO runs (run_id, workflow_id, workflow_revision, "
                "dispatcher_revision, scheduled_for, occurrence_key, discovered_at, state) "
                "VALUES ('run-1','workflow-a',1,99,?,'occurrence-1',?,'claimed')",
                (NOW, NOW),
            )
        conn.rollback()
        conn.execute(
            "INSERT INTO runs (run_id, workflow_id, workflow_revision, "
            "dispatcher_revision, scheduled_for, occurrence_key, discovered_at, state) "
            "VALUES ('run-1','workflow-a',1,1,?,'occurrence-1',?,'claimed')",
            (NOW, NOW),
        )
        assert conn.execute(
            "SELECT dispatcher_revision FROM runs WHERE run_id = 'run-1'"
        ).fetchone()[0] == 1
    finally:
        conn.close()

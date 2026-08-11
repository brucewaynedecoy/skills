from __future__ import annotations

import json
import sqlite3

import pytest

from automation_dispatcher.audit import append_event, canonical_json, verify_audit_chain
from automation_dispatcher.database import connect, initialize_database
from automation_dispatcher.registry import (
    dispatcher_configuration_hash,
    normalize_dispatcher_configuration,
)


NOW = "2026-08-10T12:00:00.000000Z"


def _dispatcher(conn, dispatcher_id="daily"):
    config = normalize_dispatcher_configuration(
        {
            "dispatcher_id": dispatcher_id,
            "name": "Audit collection",
            "description": "Audit test collection",
            "timezone": "America/Chicago",
            "schedule": "0 6 * * *",
            "max_lateness_seconds": 3600,
            "catch_up": {"policy": "latest", "max_lookback_seconds": 86400},
            "heartbeat_schedule": {"verified": True, "schedule": "0 6 * * *"},
            "enabled": True,
        }
    )
    conn.execute(
        """INSERT INTO dispatchers (
               dispatcher_id, name, description, schedule_json,
               heartbeat_schedule_json, timezone, max_lateness_seconds,
               catch_up_policy, max_lookback_seconds, created_at, updated_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            dispatcher_id, config["name"], config["description"],
            json.dumps(config["schedule"], sort_keys=True, separators=(",", ":")),
            json.dumps(config["heartbeat_schedule"], sort_keys=True, separators=(",", ":")),
            config["timezone"], config["max_lateness_seconds"],
            config["catch_up"]["policy"], config["catch_up"]["max_lookback_seconds"],
            NOW, NOW,
        ),
    )
    normalized = json.dumps(config, sort_keys=True, separators=(",", ":"))
    conn.execute(
        """INSERT INTO dispatcher_revisions (
               dispatcher_id, revision, normalized_config_json, config_hash,
               actor, reason, effective_at, created_at
           ) VALUES (?, 1, ?, ?, 'test', 'fixture setup', ?, ?)""",
        (dispatcher_id, normalized, dispatcher_configuration_hash(config), NOW, NOW),
    )
    conn.commit()


def test_append_is_transaction_neutral_and_chain_verifies(tmp_path):
    path = tmp_path / "daily.sqlite3"
    initialize_database(path)
    conn = connect(path)
    try:
        _dispatcher(conn)
        conn.execute("BEGIN IMMEDIATE")
        discarded = append_event(
            conn,
            dispatcher_id="daily",
            event_type="dry_event",
            payload={"b": 2, "a": 1},
            occurred_at=NOW,
        )
        assert conn.in_transaction is True
        assert discarded["hash"] == discarded["event_hash"]
        conn.rollback()
        assert conn.execute("SELECT count(*) FROM audit_events").fetchone()[0] == 0

        conn.execute("BEGIN IMMEDIATE")
        first = append_event(
            conn,
            dispatcher_id="daily",
            event_type="route_verified",
            payload={"task": "task-1", "assurance": "attested"},
            occurred_at=NOW,
            actor="test",
        )
        second = append_event(
            conn,
            dispatcher_id="daily",
            event_type="no_due_work",
            payload={"count": 0},
            occurred_at="2026-08-10T12:01:00.000000Z",
            observed_identity={"host": "test-host"},
        )
        conn.commit()

        assert first["previous_event_hash"] is None
        assert second["previous_event_hash"] == first["event_hash"]
        assert verify_audit_chain(conn, "daily") == {
            "dispatcher_id": "daily",
            "valid": True,
            "event_count": 2,
            "last_event_id": second["event_id"],
            "last_event_hash": second["event_hash"],
            "errors": [],
        }
        assert conn.execute("SELECT payload_json FROM audit_events WHERE event_id = 1").fetchone()[0] == canonical_json(
            {"task": "task-1", "assurance": "attested"}
        )
    finally:
        conn.close()


def test_immutable_audit_events_reject_update_and_delete(tmp_path):
    path = tmp_path / "daily.sqlite3"
    initialize_database(path)
    conn = connect(path)
    try:
        _dispatcher(conn)
        append_event(conn, "daily", "created", {}, occurred_at=NOW)
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute("UPDATE audit_events SET payload_json = '{}' WHERE event_id = 1")
        conn.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute("DELETE FROM audit_events WHERE event_id = 1")
        conn.rollback()
    finally:
        conn.close()


def test_verifier_detects_tampered_canonical_payload(tmp_path):
    path = tmp_path / "daily.sqlite3"
    initialize_database(path)
    conn = connect(path)
    try:
        _dispatcher(conn)
        append_event(conn, "daily", "created", {"value": 1}, occurred_at=NOW)
        conn.commit()

        # Simulate an administrator bypassing the ordinary immutability guard.
        conn.execute("DROP TRIGGER audit_events_no_update")
        conn.execute("UPDATE audit_events SET payload_json = ? WHERE event_id = 1", ('{"value":2}',))
        conn.commit()

        result = verify_audit_chain(conn, "daily")
        assert result["valid"] is False
        assert "event_hash_mismatch" in {error["error"] for error in result["errors"]}
    finally:
        conn.close()


def test_workflow_revisions_are_immutable(tmp_path):
    path = tmp_path / "daily.sqlite3"
    initialize_database(path)
    conn = connect(path)
    try:
        _dispatcher(conn)
        conn.execute(
            "INSERT INTO workflows ("
            "workflow_id, dispatcher_id, name, definition_path, definition_revision, "
            "definition_hash, normalized_definition_json, retry_policy_json, "
            "claim_lease_seconds, procedure_kind, procedure_reference, external_effect_mode, "
            "reporting_task_id, current_revision, created_at, updated_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "example", "daily", "Example", "/tmp/example.json", "v1", "a" * 64,
                "{}", "{}", 60, "script", "/tmp/run",
                "none", "task-1", 1, NOW, NOW,
            ),
        )
        conn.execute(
            "INSERT INTO workflow_revisions ("
            "workflow_id, revision, dispatcher_id, definition_path, definition_revision, "
            "normalized_definition_json, definition_hash, effective_at, created_at"
            ") VALUES (?,?,?,?,?,?,?,?,?)",
            ("example", 1, "daily", "/tmp/example.json", "v1", "{}", "a" * 64, NOW, NOW),
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute(
                "UPDATE workflow_revisions SET reason = 'rewritten' "
                "WHERE workflow_id = 'example' AND revision = 1"
            )
        conn.rollback()
    finally:
        conn.close()

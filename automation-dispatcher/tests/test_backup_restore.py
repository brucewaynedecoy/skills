from __future__ import annotations

from hashlib import sha256
import json

import pytest

from automation_dispatcher.audit import append_event
from automation_dispatcher.backup import create_backup, export_sanitized, verify_backup
from automation_dispatcher.database import (
    assert_runtime_path_is_external,
    connect,
    initialize_database,
)


NOW = "2026-08-10T12:00:00.000000Z"


def _seed(path):
    initialize_database(path)
    conn = connect(path)
    try:
        conn.execute(
            "INSERT INTO dispatchers ("
            "dispatcher_id, name, description, current_revision, schedule_json, timezone, "
            "max_lateness_seconds, catch_up_policy, max_lookback_seconds, expected_task_id, "
            "default_reporting_task_id, created_at, updated_at"
            ") VALUES ('daily', 'Morning reviews', 'Shared morning work', 1, ?, "
            "'America/Chicago', 900, 'bounded', 86400, 'task-1', 'task-1', ?, ?)",
            ('{"version":2,"kind":"cron","expression":"0 6 * * *"}', NOW, NOW),
        )
        normalized = json.dumps(
            {
                "dispatcher_id": "daily",
                "name": "Morning reviews",
                "schedule_json": {
                    "version": 2,
                    "kind": "cron",
                    "expression": "0 6 * * *",
                },
                "timezone": "America/Chicago",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        conn.execute(
            "INSERT INTO dispatcher_revisions ("
            "dispatcher_id, revision, normalized_config_json, config_hash, actor, reason, "
            "effective_at, created_at) VALUES ('daily',1,?,?,?, ?,?,?)",
            (
                normalized,
                sha256(normalized.encode("utf-8")).hexdigest(),
                "test",
                "seed",
                NOW,
                NOW,
            ),
        )
        append_event(
            conn,
            "daily",
            "dispatcher_created",
            {
                "safe": "value",
                "api_token": "should-not-export",
                "artifact_url": "https://example.test/report?signature=temporary",
            },
            occurred_at=NOW,
        )
        conn.commit()
    finally:
        conn.close()


def test_backup_uses_snapshot_and_verifies_temporary_restore(tmp_path):
    source = tmp_path / "daily.sqlite3"
    backup = tmp_path / "backups" / "daily.sqlite3"
    _seed(source)

    result = create_backup(source, backup)

    assert result["verified"] is True
    assert result["verification"]["restore_verified"] is True
    assert result["verification"]["integrity"]["integrity_ok"] is True
    assert result["verification"]["integrity"]["foreign_keys_ok"] is True
    assert len(result["sha256"]) == 64
    assert result["last_audit_event_id"] == 1

    conn = connect(source)
    try:
        append_event(conn, "daily", "source_changed", {}, occurred_at=NOW)
        conn.commit()
    finally:
        conn.close()
    assert verify_backup(backup)["audit_chains"][0]["event_count"] == 1


def test_verify_backup_fails_closed_for_non_database(tmp_path):
    broken = tmp_path / "broken.sqlite3"
    broken.write_bytes(b"not a sqlite database")

    result = verify_backup(broken)

    assert result["ok"] is False
    assert result["restore_verified"] is False
    assert result["errors"]


def test_sanitized_export_redacts_payloads_and_omits_receipt_body(tmp_path):
    source = tmp_path / "daily.sqlite3"
    export = tmp_path / "exports" / "daily.json"
    _seed(source)
    conn = connect(source)
    try:
        conn.execute(
            "INSERT INTO receipts ("
            "receipt_id, dispatcher_id, destination_task_id, status, rendered_content, "
            "content_hash, created_at"
            ") VALUES ('receipt-1', 'daily', 'task-1', 'pending', ?, ?, ?)",
            ("private receipt body", "b" * 64, NOW),
        )
        conn.commit()
    finally:
        conn.close()

    result = export_sanitized(source, export)
    document = json.loads(export.read_text(encoding="utf-8"))

    assert result["sanitized"] is True
    assert document["manifest"]["format"] == "automation-dispatcher-sanitized-export-v2"
    assert document["dispatchers"][0]["schedule"]["kind"] == "cron"
    assert document["dispatcher_revisions"][0]["revision"] == 1
    assert document["dispatcher_revisions"][0]["normalized_config"]["name"] == "Morning reviews"
    assert document["audit_events"][0]["payload"]["api_token"] == "[REDACTED]"
    assert document["audit_events"][0]["payload"]["artifact_url"] == "https://example.test/report"
    assert "rendered_content" not in document["receipts"][0]
    assert "should-not-export" not in export.read_text(encoding="utf-8")
    assert "private receipt body" not in export.read_text(encoding="utf-8")


def test_runtime_and_backup_paths_reject_configured_skill_roots(tmp_path, monkeypatch):
    skill_root = tmp_path / "installed-skill"
    skill_root.mkdir()
    source = skill_root / "runtime.sqlite3"
    _seed(source)
    external = tmp_path / "external.sqlite3"
    _seed(external)
    monkeypatch.setenv("AUTOMATION_DISPATCHER_FORBIDDEN_ROOTS", str(skill_root))

    with pytest.raises(ValueError, match="outside the installed/source skill"):
        initialize_database(skill_root / "another.sqlite3")
    with pytest.raises(ValueError, match="outside the installed/source skill"):
        create_backup(source, tmp_path / "backup.sqlite3")
    with pytest.raises(ValueError, match="outside the installed/source skill"):
        export_sanitized(source, tmp_path / "export.json")
    with pytest.raises(ValueError, match="outside the installed/source skill"):
        create_backup(external, skill_root / "backup.sqlite3")


def test_default_codex_skill_root_is_always_forbidden(tmp_path, monkeypatch):
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    with pytest.raises(ValueError, match="outside the installed/source skill"):
        assert_runtime_path_is_external(
            codex_home / "skills" / "automation-dispatcher" / "runtime.sqlite3"
        )

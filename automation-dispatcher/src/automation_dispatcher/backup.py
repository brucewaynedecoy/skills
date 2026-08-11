"""Verified SQLite backups and privacy-bounded JSON exports."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

from .audit import audit_tip, canonical_json, verify_audit_chain
from .database import (
    BUSY_TIMEOUT_MS,
    assert_runtime_path_is_external,
    connect,
    integrity_check,
    schema_version,
    utc_now,
)


_SENSITIVE_KEY = re.compile(
    r"(^|_)(authorization|cookie|credential|password|private_key|secret|signed_url|token)($|_)",
    re.IGNORECASE,
)


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_only_connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        f"{path.as_uri()}?mode=ro",
        uri=True,
        timeout=BUSY_TIMEOUT_MS / 1_000,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _metadata(path: Path) -> dict[str, Any]:
    connection = _read_only_connection(path)
    try:
        return {
            "schema_version": schema_version(connection),
            "audit_tip": audit_tip(connection),
        }
    finally:
        connection.close()


def _resolved_backup_path(source: Path, destination: str | Path) -> Path:
    target = assert_runtime_path_is_external(destination)
    if target.is_dir():
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        target = target / f"{source.stem}-{timestamp}.sqlite3"
    if target == source:
        raise ValueError("backup destination must differ from the source database")
    if target.exists():
        raise FileExistsError(f"refusing to overwrite existing backup: {target}")
    return target


def create_backup(path: str | Path, destination: str | Path) -> dict[str, Any]:
    """Create a transactionally safe snapshot using SQLite's backup API."""

    source_path = assert_runtime_path_is_external(path)
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    backup_path = _resolved_backup_path(source_path, destination)
    backup_path.parent.mkdir(parents=True, exist_ok=True)

    source = connect(source_path)
    target = sqlite3.connect(backup_path)
    try:
        source.backup(target)
        target.commit()
    except Exception:
        target.close()
        source.close()
        if backup_path.exists():
            backup_path.unlink()
        raise
    else:
        target.close()
        source.close()

    verification = verify_backup(backup_path)
    if not verification["ok"]:
        raise sqlite3.DatabaseError(f"backup failed restore verification: {verification}")
    metadata = _metadata(backup_path)
    return {
        "source_path": str(source_path),
        "backup_path": str(backup_path),
        "size_bytes": backup_path.stat().st_size,
        "sha256": _sha256_file(backup_path),
        "schema_version": metadata["schema_version"],
        "last_audit_event_id": metadata["audit_tip"]["event_id"],
        "last_audit_event_hash": metadata["audit_tip"]["event_hash"],
        "verified": True,
        "verification": verification,
    }


def verify_backup(path: str | Path) -> dict[str, Any]:
    """Restore a backup to a temporary file, then verify DB, FKs, and audit chains."""

    backup_path = assert_runtime_path_is_external(path)
    base: dict[str, Any] = {
        "backup_path": str(backup_path),
        "ok": False,
        "restore_verified": False,
    }
    if not backup_path.is_file():
        return {**base, "errors": ["backup file does not exist"]}

    try:
        checksum = _sha256_file(backup_path)
        size = backup_path.stat().st_size
        with tempfile.TemporaryDirectory(prefix="automation-dispatcher-restore-") as temp_dir:
            restored_path = Path(temp_dir) / "restored.sqlite3"
            source = _read_only_connection(backup_path)
            restored = sqlite3.connect(restored_path)
            try:
                source.backup(restored)
                restored.commit()
            finally:
                restored.close()
                source.close()

            checks = integrity_check(restored_path)
            audit_connection = _read_only_connection(restored_path)
            try:
                dispatcher_ids = [
                    row[0]
                    for row in audit_connection.execute(
                        "SELECT dispatcher_id FROM dispatchers ORDER BY dispatcher_id"
                    )
                ]
                audit_chains = [
                    verify_audit_chain(audit_connection, dispatcher_id)
                    for dispatcher_id in dispatcher_ids
                ]
                version = schema_version(audit_connection)
                tip = audit_tip(audit_connection)
            finally:
                audit_connection.close()

        audit_ok = all(chain["valid"] for chain in audit_chains)
        ok = bool(checks["ok"] and audit_ok)
        return {
            **base,
            "ok": ok,
            "restore_verified": ok,
            "size_bytes": size,
            "sha256": checksum,
            "schema_version": version,
            "last_audit_event_id": tip["event_id"],
            "last_audit_event_hash": tip["event_hash"],
            "integrity": checks,
            "audit_chains": audit_chains,
            "errors": [] if ok else ["restored backup verification failed"],
        }
    except (OSError, sqlite3.Error, ValueError) as error:
        return {**base, "errors": [str(error)]}


def _sanitize_string(value: str) -> str:
    if value.lower().startswith(("bearer ", "basic ")):
        return "[REDACTED]"
    if value.startswith(("http://", "https://")):
        parsed = urlsplit(value)
        if parsed.query or parsed.fragment:
            return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    return value


def _sanitize(value: Any, *, key: str = "") -> Any:
    if key and _SENSITIVE_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {item_key: _sanitize(item, key=item_key) for item_key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        return _sanitize_string(value)
    return value


def _parse_json(value: str | None) -> Any:
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return "[INVALID JSON OMITTED]"


def _rows(connection: sqlite3.Connection, query: str) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(query)]


def _sanitize_json_columns(
    rows: Iterable[dict[str, Any]], json_columns: Iterable[str]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        clean = dict(row)
        for column in json_columns:
            if column in clean:
                clean[column.removesuffix("_json")] = _sanitize(_parse_json(clean.pop(column)))
        result.append(_sanitize(clean))
    return result


def export_sanitized(path: str | Path, destination: str | Path) -> dict[str, Any]:
    """Export bounded operational summaries with secret-like fields redacted."""

    database_path = assert_runtime_path_is_external(path)
    destination_path = assert_runtime_path_is_external(destination)
    if not database_path.is_file():
        raise FileNotFoundError(database_path)
    if destination_path == database_path:
        raise ValueError("export destination must differ from the database")
    if destination_path.exists():
        raise FileExistsError(f"refusing to overwrite existing export: {destination_path}")
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    verification = integrity_check(database_path)
    if not verification["ok"]:
        raise sqlite3.DatabaseError(f"cannot export invalid database: {verification}")

    connection = _read_only_connection(database_path)
    try:
        dispatchers = _rows(
            connection,
            "SELECT dispatcher_id, name, description, current_revision, schedule_json, "
            "timezone, max_lateness_seconds, catch_up_policy, max_lookback_seconds, "
            "heartbeat_schedule_json, automation_id, expected_task_id, "
            "expected_working_directory, expected_harness, expected_host, "
            "default_reporting_task_id, enabled, installed_skill_version, "
            "source_revision, created_at, updated_at FROM dispatchers ORDER BY dispatcher_id",
        )
        dispatchers = _sanitize_json_columns(
            dispatchers,
            ["schedule_json", "heartbeat_schedule_json"],
        )
        dispatcher_revisions = _sanitize_json_columns(
            _rows(
                connection,
                "SELECT * FROM dispatcher_revisions ORDER BY dispatcher_id, revision",
            ),
            ["normalized_config_json"],
        )
        routes = _sanitize_json_columns(
            _rows(
                connection,
                "SELECT route_id, dispatcher_id, revision, destination_task_id, "
                "expected_working_directory, expected_harness, expected_host, "
                "required_identity_json, effective_at, actor, reason, created_at "
                "FROM dispatcher_routes ORDER BY dispatcher_id, revision",
            ),
            ["required_identity_json"],
        )
        workflows = _sanitize_json_columns(
            _rows(connection, "SELECT * FROM workflows ORDER BY workflow_id"),
            [
                "normalized_definition_json",
                "retry_policy_json",
                "authority_references_json",
                "receipt_template_json",
                "evidence_retention_json",
            ],
        )
        revisions = _sanitize_json_columns(
            _rows(
                connection,
                "SELECT * FROM workflow_revisions ORDER BY workflow_id, revision",
            ),
            ["normalized_definition_json"],
        )
        runs = _sanitize_json_columns(
            _rows(
                connection,
                "SELECT run_id, workflow_id, workflow_revision, dispatcher_revision, scheduled_for, "
                "occurrence_key, discovered_at, started_at, finished_at, state, "
                "claim_owner, claim_time, lease_expires_at, attempt, recovery_of_run_id, "
                "prior_claim_owner, external_effect_key, reconciliation_state, "
                "reconciliation_evidence_json, configured_identity_json, "
                "observed_identity_json, output_summary, evidence_json, error_class, "
                "receipt_hash FROM runs ORDER BY scheduled_for, workflow_id",
            ),
            [
                "reconciliation_evidence_json",
                "configured_identity_json",
                "observed_identity_json",
                "evidence_json",
            ],
        )
        receipts = _rows(
            connection,
            "SELECT receipt_id, run_id, dispatcher_id, destination_task_id, status, "
            "content_hash, created_at, posted_at, external_message_id "
            "FROM receipts ORDER BY created_at, receipt_id",
        )
        events = _sanitize_json_columns(
            _rows(
                connection,
                "SELECT event_id, dispatcher_id, workflow_id, run_id, event_type, "
                "occurred_at, actor, observed_identity_json, payload_json, "
                "previous_event_hash, event_hash FROM audit_events ORDER BY event_id",
            ),
            ["observed_identity_json", "payload_json"],
        )
        version = schema_version(connection)
        tip = audit_tip(connection)
    finally:
        connection.close()

    sections: dict[str, Any] = {
        "dispatchers": _sanitize(dispatchers),
        "dispatcher_revisions": dispatcher_revisions,
        "dispatcher_routes": routes,
        "workflows": workflows,
        "workflow_revisions": revisions,
        "runs": runs,
        "receipts": _sanitize(receipts),
        "audit_events": events,
    }
    section_checksums = {
        name: sha256(canonical_json(value).encode("utf-8")).hexdigest()
        for name, value in sections.items()
    }
    document = {
        "manifest": {
            "format": "automation-dispatcher-sanitized-export-v2",
            "exported_at": utc_now(),
            "database_name": database_path.name,
            "schema_version": version,
            "dispatcher_ids": [item["dispatcher_id"] for item in dispatchers],
            "last_audit_event_id": tip["event_id"],
            "last_audit_event_hash": tip["event_hash"],
            "section_sha256": section_checksums,
        },
        **sections,
    }
    encoded = (canonical_json(document) + "\n").encode("utf-8")
    with tempfile.NamedTemporaryFile(
        mode="wb", prefix=f".{destination_path.name}.", dir=destination_path.parent, delete=False
    ) as temporary:
        temporary.write(encoded)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, destination_path)
    return {
        "database_path": str(database_path),
        "export_path": str(destination_path),
        "size_bytes": destination_path.stat().st_size,
        "sha256": _sha256_file(destination_path),
        "schema_version": version,
        "dispatcher_ids": document["manifest"]["dispatcher_ids"],
        "last_audit_event_id": tip["event_id"],
        "last_audit_event_hash": tip["event_hash"],
        "sanitized": True,
    }

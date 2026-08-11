"""Canonical, append-only hash-chained audit events."""

from __future__ import annotations

from hashlib import sha256
import hmac
import json
import sqlite3
from typing import Any

from .database import utc_now


def _validate_json_keys(value: Any) -> None:
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("canonical JSON object keys must be strings")
        for item in value.values():
            _validate_json_keys(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _validate_json_keys(item)


def canonical_json(value: Any) -> str:
    """Serialize JSON deterministically for persistence and hashing."""

    _validate_json_keys(value)
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _hash_material(
    *,
    dispatcher_id: str,
    workflow_id: str | None,
    run_id: str | None,
    event_type: str,
    occurred_at: str,
    actor: str | None,
    observed_identity: Any,
    payload: Any,
    previous_event_hash: str | None,
) -> str:
    material = {
        "actor": actor,
        "dispatcher_id": dispatcher_id,
        "event_type": event_type,
        "observed_identity": observed_identity,
        "occurred_at": occurred_at,
        "payload": payload,
        "previous_event_hash": previous_event_hash,
        "run_id": run_id,
        "workflow_id": workflow_id,
    }
    return sha256(canonical_json(material).encode("utf-8")).hexdigest()


def append_event(
    connection: sqlite3.Connection,
    dispatcher_id: str,
    event_type: str,
    payload: Any,
    *,
    workflow_id: str | None = None,
    run_id: str | None = None,
    occurred_at: str | None = None,
    actor: str | None = None,
    observed_identity: Any = None,
) -> dict[str, Any]:
    """Append one event without beginning, committing, or rolling back a transaction.

    Callers performing a projection transition should acquire their write
    transaction first (normally ``BEGIN IMMEDIATE``), update the projection,
    append the event, and commit both together.
    """

    if not dispatcher_id:
        raise ValueError("dispatcher_id is required")
    if not event_type:
        raise ValueError("event_type is required")

    timestamp = occurred_at or utc_now()
    payload_json = canonical_json(payload)
    identity_json = None if observed_identity is None else canonical_json(observed_identity)
    previous_row = connection.execute(
        "SELECT event_hash FROM audit_events "
        "WHERE dispatcher_id = ? ORDER BY event_id DESC LIMIT 1",
        (dispatcher_id,),
    ).fetchone()
    previous_hash = previous_row[0] if previous_row is not None else None
    event_hash = _hash_material(
        dispatcher_id=dispatcher_id,
        workflow_id=workflow_id,
        run_id=run_id,
        event_type=event_type,
        occurred_at=timestamp,
        actor=actor,
        observed_identity=observed_identity,
        payload=payload,
        previous_event_hash=previous_hash,
    )
    cursor = connection.execute(
        "INSERT INTO audit_events("
        "dispatcher_id, workflow_id, run_id, event_type, occurred_at, actor, "
        "observed_identity_json, payload_json, previous_event_hash, event_hash"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            dispatcher_id,
            workflow_id,
            run_id,
            event_type,
            timestamp,
            actor,
            identity_json,
            payload_json,
            previous_hash,
            event_hash,
        ),
    )
    return {
        "event_id": cursor.lastrowid,
        "dispatcher_id": dispatcher_id,
        "workflow_id": workflow_id,
        "run_id": run_id,
        "event_type": event_type,
        "occurred_at": timestamp,
        "actor": actor,
        "observed_identity": observed_identity,
        "payload": payload,
        "previous_event_hash": previous_hash,
        "event_hash": event_hash,
        "hash": event_hash,
    }


def verify_audit_chain(
    connection: sqlite3.Connection, dispatcher_id: str
) -> dict[str, Any]:
    """Verify canonical storage, links, and hashes for one dispatcher chain."""

    rows = connection.execute(
        "SELECT event_id, dispatcher_id, workflow_id, run_id, event_type, "
        "occurred_at, actor, observed_identity_json, payload_json, "
        "previous_event_hash, event_hash "
        "FROM audit_events WHERE dispatcher_id = ? ORDER BY event_id",
        (dispatcher_id,),
    ).fetchall()
    errors: list[dict[str, Any]] = []
    expected_previous: str | None = None

    for row in rows:
        event_id = row["event_id"]
        try:
            payload = json.loads(row["payload_json"])
            if canonical_json(payload) != row["payload_json"]:
                errors.append({"event_id": event_id, "error": "payload_not_canonical"})
        except (TypeError, ValueError, json.JSONDecodeError):
            errors.append({"event_id": event_id, "error": "payload_invalid_json"})
            payload = None

        identity_raw = row["observed_identity_json"]
        try:
            identity = None if identity_raw is None else json.loads(identity_raw)
            if identity_raw is not None and canonical_json(identity) != identity_raw:
                errors.append({"event_id": event_id, "error": "identity_not_canonical"})
        except (TypeError, ValueError, json.JSONDecodeError):
            errors.append({"event_id": event_id, "error": "identity_invalid_json"})
            identity = None

        if row["previous_event_hash"] != expected_previous:
            errors.append(
                {
                    "event_id": event_id,
                    "error": "previous_hash_mismatch",
                    "expected": expected_previous,
                    "actual": row["previous_event_hash"],
                }
            )

        expected_hash = _hash_material(
            dispatcher_id=row["dispatcher_id"],
            workflow_id=row["workflow_id"],
            run_id=row["run_id"],
            event_type=row["event_type"],
            occurred_at=row["occurred_at"],
            actor=row["actor"],
            observed_identity=identity,
            payload=payload,
            previous_event_hash=row["previous_event_hash"],
        )
        if not hmac.compare_digest(expected_hash, row["event_hash"]):
            errors.append(
                {
                    "event_id": event_id,
                    "error": "event_hash_mismatch",
                    "expected": expected_hash,
                    "actual": row["event_hash"],
                }
            )
        expected_previous = row["event_hash"]

    return {
        "dispatcher_id": dispatcher_id,
        "valid": not errors,
        "event_count": len(rows),
        "last_event_id": rows[-1]["event_id"] if rows else None,
        "last_event_hash": rows[-1]["event_hash"] if rows else None,
        "errors": errors,
    }


def audit_tip(connection: sqlite3.Connection) -> dict[str, Any]:
    """Return the globally latest event marker for backup/export manifests."""

    row = connection.execute(
        "SELECT event_id, dispatcher_id, event_hash "
        "FROM audit_events ORDER BY event_id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return {"event_id": None, "dispatcher_id": None, "event_hash": None}
    return {
        "event_id": row["event_id"],
        "dispatcher_id": row["dispatcher_id"],
        "event_hash": row["event_hash"],
    }

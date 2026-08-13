"""Command-line interface for durable automation dispatch."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from . import __version__
from .audit import append_event, audit_tip, verify_audit_chain
from .backup import create_backup, export_sanitized, verify_backup
from .claims import (
    ClaimError,
    claim_occurrence,
    complete_run,
    fail_run,
    mark_effect_started,
    mark_running,
    recover_run,
)
from .database import (
    assert_runtime_path_is_external,
    connect,
    initialize_database,
    integrity_check,
    migrate,
    schema_version,
)
from .definitions import normalize_definition
from .lifecycle_artifacts import (
    ARTIFACT_MODELS,
    LifecycleArtifact,
    load_artifact,
)
from .lifecycle_contracts import LifecycleContractError, seal_artifact, validate_artifact
from .lifecycle_engine import lifecycle_status, plan_step, semantic_drift_report
from .receipts import (
    acknowledge_receipt,
    create_receipt,
    prepare_receipt_post,
)
from .registry import (
    RegistryError,
    dispatcher_configuration_from_row,
    dispatcher_configuration_hash,
    heartbeat_reconciliation,
    list_workflows,
    normalize_dispatcher_configuration,
    register_workflow,
    revise_dispatcher_schedule,
    revise_workflow,
    set_workflow_enabled,
)
from .routing import check_route
from .runner import ProcedureError, execute_procedure
from .scheduling import collection_occurrences_between


class CliError(RuntimeError):
    """A user-facing deterministic CLI failure."""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _utc_datetime(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CliError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise CliError(f"{field} must include a timezone")
    return parsed.astimezone(UTC)


def _json_value(value: str | None, *, default: Any) -> Any:
    if value is None:
        return default
    if value.startswith("@"):
        value = Path(value[1:]).expanduser().resolve(strict=True).read_text(encoding="utf-8")
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid JSON: {exc}") from exc


def _open_existing(path: str | Path) -> sqlite3.Connection:
    resolved = assert_runtime_path_is_external(path)
    if not resolved.is_file():
        raise CliError(f"dispatcher database does not exist: {resolved}")
    return connect(resolved)


def _database_path(args: argparse.Namespace) -> str:
    if not getattr(args, "database", None):
        raise CliError("--database is required")
    return str(Path(args.database).expanduser().resolve())


def _dispatcher(conn: sqlite3.Connection, dispatcher_id: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM dispatchers WHERE dispatcher_id = ?", (dispatcher_id,)
    ).fetchone()
    if row is None:
        raise CliError(f"unknown dispatcher: {dispatcher_id}")
    return row


def _route_material(
    conn: sqlite3.Connection, dispatcher_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    dispatcher = _dispatcher(conn, dispatcher_id)
    route = conn.execute(
        "SELECT * FROM dispatcher_routes WHERE dispatcher_id = ? ORDER BY revision DESC LIMIT 1",
        (dispatcher_id,),
    ).fetchone()
    if route is None:
        raise CliError("dispatcher has no configured route revision")
    configured = {
        "task_id": {"value": route["destination_task_id"], "source": "verified_config", "assurance": "verified_config"},
        "working_directory": {"value": route["expected_working_directory"], "source": "verified_config", "assurance": "verified_config"},
        "harness": {"value": route["expected_harness"], "source": "verified_config", "assurance": "verified_config"},
        "host": {"value": route["expected_host"], "source": "verified_config", "assurance": "verified_config"},
    }
    requirements = json.loads(route["required_identity_json"])
    return configured, requirements


def _route_check(
    conn: sqlite3.Connection,
    dispatcher_id: str,
    observed: Mapping[str, Any],
    *,
    actor: str,
    audit_failure: bool = True,
) -> dict[str, Any]:
    configured, requirements = _route_material(conn, dispatcher_id)
    result = check_route(configured, observed, requirements)
    result["configured_identity"] = configured
    if not result["ok"] and audit_failure:
        # Detach the persisted payload before attaching the returned event to
        # ``result``; otherwise event.payload.result would form a reference
        # cycle in machine-readable CLI output.
        audit_result = json.loads(json.dumps(result, sort_keys=True))
        conn.execute("BEGIN IMMEDIATE")
        try:
            event = append_event(
                conn,
                dispatcher_id,
                result["outcome"],
                {"configured": configured, "observed": observed, "result": audit_result},
                actor=actor,
                observed_identity=observed,
            )
            destination = configured["task_id"]["value"]
            content = (
                f"### Dispatcher route attention needed\n"
                f"- Dispatcher: `{dispatcher_id}`\n"
                f"- Outcome: **{result['outcome']}**\n"
                f"- Audit: `{event['event_id']}/{event['event_hash'][:12]}`\n"
                "- Attention needed: correct or attest the invocation route before dispatch."
            )
            receipt = create_receipt(
                conn,
                dispatcher_id=dispatcher_id,
                destination_task_id=destination,
                content=content,
            )
            append_event(
                conn,
                dispatcher_id,
                "receipt_pending",
                {"receipt_id": receipt["receipt_id"], "content_hash": receipt["content_hash"]},
                actor=actor,
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        result["event"] = event
        result["receipt"] = receipt
    return result


def _verification(conn: sqlite3.Connection, database_path: str) -> dict[str, Any]:
    physical = integrity_check(database_path)
    chains = {
        row["dispatcher_id"]: verify_audit_chain(conn, row["dispatcher_id"])
        for row in conn.execute("SELECT dispatcher_id FROM dispatchers ORDER BY dispatcher_id")
    }
    return {
        "ok": bool(physical["ok"]) and all(chain["valid"] for chain in chains.values()),
        "database": physical,
        "audit_chains": chains,
    }


def _verified_current_definition(
    conn: sqlite3.Connection, workflow_id: str
) -> tuple[sqlite3.Row, sqlite3.Row, dict[str, Any], Path]:
    workflow = conn.execute(
        "SELECT * FROM workflows WHERE workflow_id = ?", (workflow_id,)
    ).fetchone()
    if workflow is None:
        raise CliError(f"unknown workflow: {workflow_id}")
    dispatcher = _dispatcher(conn, workflow["dispatcher_id"])
    active_route = dispatcher["default_reporting_task_id"] or dispatcher["expected_task_id"]
    if workflow["reporting_task_id"] != active_route:
        raise CliError(
            "workflow reporting route does not match the current dispatcher route; "
            "revise the workflow before dispatch"
        )
    revision = conn.execute(
        """SELECT * FROM workflow_revisions
            WHERE workflow_id = ? AND revision = ?""",
        (workflow_id, workflow["current_revision"]),
    ).fetchone()
    if revision is None:
        raise CliError("current workflow revision snapshot is missing")
    definition_path = Path(revision["definition_path"]).expanduser().resolve(strict=True)
    current = normalize_definition(json.loads(definition_path.read_text(encoding="utf-8")))
    snapshot = normalize_definition(json.loads(revision["normalized_definition_json"]))
    if current["content_hash"] != revision["definition_hash"]:
        raise CliError("current definition bytes do not match the registered revision hash")
    if snapshot["content_hash"] != revision["definition_hash"]:
        raise CliError("stored revision snapshot does not match its registered hash")
    return workflow, revision, snapshot, definition_path


def _workflow_attention(
    conn: sqlite3.Connection,
    workflow: sqlite3.Row,
    *,
    event_type: str,
    message: str,
    actor: str,
) -> dict[str, Any]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        dispatcher = _dispatcher(conn, workflow["dispatcher_id"])
        destination_task_id = (
            dispatcher["default_reporting_task_id"] or dispatcher["expected_task_id"]
        )
        if not destination_task_id:
            raise CliError("dispatcher has no active reporting route")
        event = append_event(
            conn,
            workflow["dispatcher_id"],
            event_type,
            {"message": message, "definition_hash": workflow["definition_hash"]},
            workflow_id=workflow["workflow_id"],
            actor=actor,
        )
        content = (
            f"### Workflow attention needed\n"
            f"- Workflow: `{workflow['workflow_id']}`\n"
            f"- Outcome: **{event_type}**\n"
            f"- Audit: `{event['event_id']}/{event['event_hash'][:12]}`\n"
            f"- Attention needed: {message}"
        )
        receipt = create_receipt(
            conn,
            dispatcher_id=workflow["dispatcher_id"],
            destination_task_id=destination_task_id,
            content=content,
            workflow_id=workflow["workflow_id"],
        )
        append_event(
            conn,
            workflow["dispatcher_id"],
            "receipt_pending",
            {"receipt_id": receipt["receipt_id"], "content_hash": receipt["content_hash"]},
            workflow_id=workflow["workflow_id"],
            actor=actor,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {
        "status": event_type,
        "ok": False,
        "dispatcher_id": workflow["dispatcher_id"],
        "workflow_id": workflow["workflow_id"],
        "event": event,
        "receipt": receipt,
        "message": message,
    }


def _cmd_init(args: argparse.Namespace) -> dict[str, Any]:
    path = _database_path(args)
    now = _utc_now()
    requirements = _json_value(args.required_identity, default={
        "task_id": {"required": True, "minimum_assurance": "verified_config"},
        "working_directory": {"required": True, "minimum_assurance": "verified_config"},
        "harness": {"required": False, "minimum_assurance": "unknown", "allow_unknown": True},
        "host": {"required": False, "minimum_assurance": "unknown", "allow_unknown": True},
    })
    if not isinstance(requirements, Mapping):
        raise CliError("required identity must be a JSON object")
    heartbeat_schedule = _json_value(args.heartbeat_schedule, default={})
    if not isinstance(heartbeat_schedule, Mapping):
        raise CliError("heartbeat schedule must be a JSON object")
    catch_up = _json_value(args.catch_up, default={})
    if not isinstance(catch_up, Mapping):
        raise CliError("catch-up policy must be a JSON object")
    schedule = _json_value(args.schedule, default={})
    config = normalize_dispatcher_configuration(
        {
            "dispatcher_id": args.dispatcher_id,
            "name": args.name,
            "description": args.description,
            "timezone": args.timezone,
            "schedule": schedule,
            "max_lateness_seconds": args.max_lateness_seconds,
            "catch_up": catch_up,
            "heartbeat_schedule": heartbeat_schedule,
            "enabled": True,
        }
    )
    reconciliation = heartbeat_reconciliation(config)
    config_hash = dispatcher_configuration_hash(config)
    result = initialize_database(path)
    conn = connect(path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT * FROM dispatchers WHERE dispatcher_id = ?", (args.dispatcher_id,)
        ).fetchone()
        if existing:
            expected_directory = str(
                Path(args.expected_working_directory).expanduser().resolve(strict=True)
            )
            if dispatcher_configuration_from_row(existing) != config:
                raise CliError(
                    "existing dispatcher configuration differs; use schedule-revise "
                    "or initialize a different collection"
                )
            if (
                existing["expected_task_id"] != args.expected_task_id
                or existing["expected_working_directory"] != expected_directory
            ):
                raise CliError("existing dispatcher route differs; use route-revise")
            conn.rollback()
            return {
                **result,
                "dispatcher_id": args.dispatcher_id,
                "status": "already_initialized",
                "configuration": config,
                "heartbeat_reconciliation": reconciliation,
            }
        working_directory = str(Path(args.expected_working_directory).expanduser().resolve(strict=True))
        conn.execute(
            """
            INSERT INTO dispatchers (
                dispatcher_id, name, description, current_revision, schedule_json,
                automation_id, expected_task_id,
                expected_working_directory, expected_harness, expected_host,
                default_reporting_task_id, heartbeat_schedule_json, timezone,
                max_lateness_seconds, catch_up_policy, max_lookback_seconds, enabled,
                installed_skill_version, source_revision, created_at, updated_at
            ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
            """,
            (
                config["dispatcher_id"], config["name"], config["description"],
                json.dumps(config["schedule"], sort_keys=True, separators=(",", ":")),
                args.automation_id, args.expected_task_id, working_directory, args.expected_harness,
                args.expected_host, args.expected_task_id,
                json.dumps(config["heartbeat_schedule"], sort_keys=True, separators=(",", ":")),
                config["timezone"], config["max_lateness_seconds"],
                config["catch_up"]["policy"], config["catch_up"]["max_lookback_seconds"],
                args.skill_version or __version__, args.source_revision, now, now,
            ),
        )
        conn.execute(
            """
            INSERT INTO dispatcher_revisions (
                dispatcher_id, revision, normalized_config_json, config_hash,
                actor, reason, effective_at, created_at
            ) VALUES (?, 1, ?, ?, ?, ?, ?, ?)
            """,
            (
                config["dispatcher_id"],
                json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
                config_hash,
                args.actor,
                args.reason,
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO dispatcher_routes (
                route_id, dispatcher_id, revision, destination_task_id,
                expected_working_directory, expected_harness, expected_host,
                required_identity_json, effective_at, actor, reason, created_at
            ) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()), args.dispatcher_id, args.expected_task_id,
                working_directory, args.expected_harness, args.expected_host,
                json.dumps(requirements, sort_keys=True, separators=(",", ":")),
                now, args.actor, args.reason, now,
            ),
        )
        event = append_event(
            conn,
            args.dispatcher_id,
            "dispatcher_initialized",
            {
                "task_id": args.expected_task_id,
                "collection_name": config["name"],
                "dispatcher_revision": 1,
                "schedule": config["schedule"],
                "route_revision": 1,
                "heartbeat_schedule_verified": bool(heartbeat_schedule.get("verified", False)),
                "heartbeat_reconciliation": reconciliation,
            },
            actor=args.actor,
        )
        content = (
            "### Dispatcher initialized\n"
            f"- Dispatcher: `{args.dispatcher_id}`\n"
            f"- Collection: `{config['name']}`\n"
            f"- Schedule revision: `1`\n"
            f"- Audit: `{event['event_id']}/{event['event_hash'][:12]}`"
        )
        receipt = create_receipt(
            conn,
            dispatcher_id=args.dispatcher_id,
            destination_task_id=args.expected_task_id,
            content=content,
        )
        append_event(
            conn,
            args.dispatcher_id,
            "receipt_pending",
            {
                "receipt_id": receipt["receipt_id"],
                "content_hash": receipt["content_hash"],
                "action": "dispatcher_initialized",
            },
            actor=args.actor,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {
        **result,
        "dispatcher_id": args.dispatcher_id,
        "status": "initialized",
        "configuration": config,
        "heartbeat_reconciliation": reconciliation,
        "event": event,
        "receipt": receipt,
    }


def _cmd_status(args: argparse.Namespace) -> dict[str, Any]:
    path = _database_path(args)
    conn = _open_existing(path)
    try:
        verification = _verification(conn, path)
        dispatchers = [dict(row) for row in conn.execute("SELECT * FROM dispatchers ORDER BY dispatcher_id")]
        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("workflows", "runs", "receipts", "audit_events")
        }
        return {
            "status": "ok" if verification["ok"] else "failed",
            "ok": verification["ok"],
            "database_path": path,
            "schema_version": schema_version(conn),
            "dispatchers": dispatchers,
            "counts": counts,
            "audit_tip": audit_tip(conn),
            "integrity": verification,
            "cli_version": __version__,
        }
    finally:
        conn.close()


def _cmd_route_check(args: argparse.Namespace) -> dict[str, Any]:
    conn = _open_existing(_database_path(args))
    try:
        result = _route_check(
            conn,
            args.dispatcher_id,
            _json_value(args.observed, default={}),
            actor=args.actor,
        )
        result["status"] = "ok" if result["ok"] else result["outcome"]
        return result
    finally:
        conn.close()


def _cmd_route_revise(args: argparse.Namespace) -> dict[str, Any]:
    requirements = _json_value(args.required_identity, default={
        "task_id": {"required": True, "minimum_assurance": "verified_config"},
        "working_directory": {"required": True, "minimum_assurance": "verified_config"},
        "harness": {"required": False, "minimum_assurance": "unknown", "allow_unknown": True},
        "host": {"required": False, "minimum_assurance": "unknown", "allow_unknown": True},
    })
    if not isinstance(requirements, Mapping):
        raise CliError("required identity must be a JSON object")
    working_directory = str(Path(args.expected_working_directory).expanduser().resolve(strict=True))
    now = _utc_now()
    conn = _open_existing(_database_path(args))
    try:
        conn.execute("BEGIN IMMEDIATE")
        dispatcher = _dispatcher(conn, args.dispatcher_id)
        revision = int(conn.execute(
            "SELECT COALESCE(MAX(revision), 0) FROM dispatcher_routes WHERE dispatcher_id = ?",
            (args.dispatcher_id,),
        ).fetchone()[0]) + 1
        conn.execute(
            """
            INSERT INTO dispatcher_routes (
                route_id, dispatcher_id, revision, destination_task_id,
                expected_working_directory, expected_harness, expected_host,
                required_identity_json, effective_at, actor, reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()), args.dispatcher_id, revision, args.destination_task_id,
                working_directory, args.expected_harness, args.expected_host,
                json.dumps(requirements, sort_keys=True, separators=(",", ":")),
                now, args.actor, args.reason, now,
            ),
        )
        conn.execute(
            """
            UPDATE dispatchers
            SET expected_task_id = ?, expected_working_directory = ?,
                expected_harness = ?, expected_host = ?,
                default_reporting_task_id = ?, updated_at = ?
            WHERE dispatcher_id = ?
            """,
            (
                args.destination_task_id, working_directory, args.expected_harness,
                args.expected_host, args.destination_task_id, now, args.dispatcher_id,
            ),
        )
        affected_workflows = [
            row[0]
            for row in conn.execute(
                """SELECT workflow_id FROM workflows
                     WHERE dispatcher_id = ? AND enabled = 1 AND reporting_task_id <> ?
                     ORDER BY workflow_id""",
                (args.dispatcher_id, args.destination_task_id),
            )
        ]
        event = append_event(
            conn,
            args.dispatcher_id,
            "dispatcher_route_revised",
            {
                "revision": revision,
                "previous_task_id": dispatcher["expected_task_id"],
                "destination_task_id": args.destination_task_id,
                "reason": args.reason,
                "workflow_reconciliation_required": affected_workflows,
            },
            actor=args.actor,
        )
        content = (
            "### Dispatcher route revised\n"
            f"- Dispatcher: `{args.dispatcher_id}`\n"
            f"- Route revision: `{revision}`\n"
            f"- Destination task: `{args.destination_task_id}`\n"
            f"- Audit: `{event['event_id']}/{event['event_hash'][:12]}`"
        )
        receipt = create_receipt(
            conn,
            dispatcher_id=args.dispatcher_id,
            destination_task_id=args.destination_task_id,
            content=content,
        )
        append_event(
            conn,
            args.dispatcher_id,
            "receipt_pending",
            {"receipt_id": receipt["receipt_id"], "content_hash": receipt["content_hash"], "action": "route_revised"},
            actor=args.actor,
        )
        conn.commit()
        return {
            "status": "route_revised",
            "dispatcher_id": args.dispatcher_id,
            "route_revision": revision,
            "workflow_reconciliation_required": affected_workflows,
            "event": event,
            "receipt": receipt,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _cmd_schedule_revise(args: argparse.Namespace) -> dict[str, Any]:
    schedule = _json_value(args.schedule, default={})
    catch_up = _json_value(args.catch_up, default={})
    heartbeat_schedule = _json_value(args.heartbeat_schedule, default={})
    if not isinstance(catch_up, Mapping):
        raise CliError("catch-up policy must be a JSON object")
    if not isinstance(heartbeat_schedule, Mapping):
        raise CliError("heartbeat schedule must be a JSON object")
    conn = _open_existing(_database_path(args))
    try:
        return revise_dispatcher_schedule(
            conn,
            args.dispatcher_id,
            schedule=schedule,
            timezone=args.timezone,
            max_lateness_seconds=args.max_lateness_seconds,
            catch_up=catch_up,
            heartbeat_schedule=heartbeat_schedule,
            actor=args.actor,
            reason=args.reason,
        )
    finally:
        conn.close()


def _cmd_register(args: argparse.Namespace, *, revise: bool = False) -> dict[str, Any]:
    conn = _open_existing(_database_path(args))
    try:
        operation = revise_workflow if revise else register_workflow
        result = operation(
            conn,
            args.definition,
            actor=args.actor,
            reason=args.reason,
            dry_run=args.dry_run,
        )
        return result
    finally:
        conn.close()


def _cmd_enabled(args: argparse.Namespace, *, enabled: bool) -> dict[str, Any]:
    conn = _open_existing(_database_path(args))
    try:
        result = set_workflow_enabled(
            conn, args.workflow_id, enabled=enabled, actor=args.actor, reason=args.reason
        )
        return result
    finally:
        conn.close()


def _cmd_list(args: argparse.Namespace) -> dict[str, Any]:
    conn = _open_existing(_database_path(args))
    try:
        return {"status": "ok", "workflows": list_workflows(conn, args.dispatcher_id)}
    finally:
        conn.close()


def _due_for_dispatcher(
    conn: sqlite3.Connection,
    dispatcher_id: str,
    now: str,
    start: str | None,
    max_occurrences: int | None,
) -> list[dict[str, Any]]:
    dispatcher = _dispatcher(conn, dispatcher_id)
    now_utc = _utc_datetime(now, "at")
    supplied_start = _utc_datetime(start, "start") if start is not None else None
    if max_occurrences is not None and (
        isinstance(max_occurrences, bool) or max_occurrences < 0
    ):
        raise CliError("max-occurrences must be a non-negative integer")

    revision_rows = conn.execute(
        """SELECT revision, normalized_config_json, effective_at
             FROM dispatcher_revisions
            WHERE dispatcher_id = ? AND revision <= ?
            ORDER BY effective_at, revision""",
        (dispatcher_id, dispatcher["current_revision"]),
    ).fetchall()
    if not revision_rows:
        raise CliError("dispatcher revision history is missing")
    collection_occurrences: list[dict[str, Any]] = []
    inclusive_now = now_utc + timedelta(microseconds=1)
    for index, revision_row in enumerate(revision_rows):
        effective_at = _utc_datetime(revision_row["effective_at"], "revision effective_at")
        next_effective_at = (
            _utc_datetime(revision_rows[index + 1]["effective_at"], "revision effective_at")
            if index + 1 < len(revision_rows)
            else inclusive_now
        )
        config = json.loads(revision_row["normalized_config_json"])
        window_seconds = min(
            config["max_lateness_seconds"],
            config["catch_up"]["max_lookback_seconds"],
        )
        beginning = now_utc - timedelta(seconds=window_seconds)
        if supplied_start is not None:
            beginning = max(beginning, supplied_start)
        segment_start = max(beginning, effective_at)
        segment_end = min(inclusive_now, next_effective_at)
        if segment_start >= segment_end:
            continue
        revision_occurrences = collection_occurrences_between(config, segment_start, segment_end)
        for occurrence in revision_occurrences:
            scheduled = _utc_datetime(occurrence["scheduled_for"], "scheduled_for")
            collection_occurrences.append(
                {
                    **occurrence,
                    "dispatcher_revision": int(revision_row["revision"]),
                    "_catch_up_policy": config["catch_up"]["policy"],
                    "lateness_seconds": int((now_utc - scheduled).total_seconds()),
                }
            )
    collection_occurrences.sort(key=lambda item: item["scheduled_for"])

    workflows = conn.execute(
        """SELECT workflows.*,
                  COALESCE(
                      (SELECT MAX(audit_events.occurred_at)
                         FROM audit_events
                        WHERE audit_events.workflow_id = workflows.workflow_id
                          AND audit_events.event_type IN ('workflow_registered', 'workflow_enabled')),
                      workflows.created_at
                  ) AS activation_effective_at
             FROM workflows
            WHERE dispatcher_id = ? AND enabled = 1
            ORDER BY workflow_id""",
        (dispatcher_id,),
    ).fetchall()
    existing = {
        (row["workflow_id"], row["scheduled_for"])
        for row in conn.execute(
            """SELECT runs.workflow_id, runs.scheduled_for
                 FROM runs JOIN workflows USING (workflow_id)
                WHERE workflows.dispatcher_id = ?""",
            (dispatcher_id,),
        )
    }
    output: list[dict[str, Any]] = []
    for occurrence in collection_occurrences:
        for workflow in workflows:
            if _utc_datetime(occurrence["scheduled_for"], "scheduled_for") < _utc_datetime(
                workflow["activation_effective_at"], "workflow activation effective_at"
            ):
                continue
            key = (workflow["workflow_id"], occurrence["scheduled_for"])
            if key in existing:
                continue
            output.append(
                {
                    "workflow_id": workflow["workflow_id"],
                    **occurrence,
                }
            )
    latest_by_revision: dict[int, str] = {}
    for item in output:
        if item["_catch_up_policy"] in {"none", "latest"}:
            revision = int(item["dispatcher_revision"])
            latest_by_revision[revision] = max(
                latest_by_revision.get(revision, item["scheduled_for"]),
                item["scheduled_for"],
            )
    output = [
        item
        for item in output
        if item["_catch_up_policy"] not in {"none", "latest"}
        or item["scheduled_for"] == latest_by_revision[int(item["dispatcher_revision"])]
    ]
    for item in output:
        del item["_catch_up_policy"]
    output.sort(key=lambda item: (item["scheduled_for"], item["workflow_id"]))
    if max_occurrences is not None:
        scheduled_times = sorted({item["scheduled_for"] for item in output})
        selected = set(scheduled_times[-max_occurrences:] if max_occurrences else [])
        output = [item for item in output if item["scheduled_for"] in selected]
    return output


def _cmd_due(args: argparse.Namespace) -> dict[str, Any]:
    conn = _open_existing(_database_path(args))
    try:
        due = _due_for_dispatcher(
            conn, args.dispatcher_id, args.at or _utc_now(), args.start, args.max_occurrences
        )
        return {"status": "due" if due else "no_due", "dispatcher_id": args.dispatcher_id, "occurrences": due}
    finally:
        conn.close()


def _cmd_claim(args: argparse.Namespace) -> dict[str, Any]:
    conn = _open_existing(_database_path(args))
    try:
        workflow, revision, _, _ = _verified_current_definition(conn, args.workflow_id)
        route = _route_check(
            conn,
            workflow["dispatcher_id"],
            _json_value(args.observed, default={}),
            actor=args.owner,
        )
        if not route["ok"]:
            return {"status": route["outcome"], "ok": False, "route": route}
        return claim_occurrence(
            conn,
            args.workflow_id,
            args.scheduled_for,
            claim_owner=args.owner,
            observed_identity=_json_value(args.observed, default={}),
            expected_revision=revision["revision"],
            expected_definition_hash=revision["definition_hash"],
            expected_route_task_id=route["configured_identity"]["task_id"]["value"],
            occurrence_metadata=_json_value(args.occurrence_metadata, default={}),
        )
    finally:
        conn.close()


def _cmd_complete(args: argparse.Namespace) -> dict[str, Any]:
    conn = _open_existing(_database_path(args))
    try:
        transition = complete_run(
            conn,
            args.run_id,
            actor=args.actor,
            summary=args.summary,
            evidence=list(args.evidence or []),
            persist_receipt=True,
        )
        return transition
    finally:
        conn.close()


def _cmd_fail(args: argparse.Namespace) -> dict[str, Any]:
    conn = _open_existing(_database_path(args))
    try:
        transition = fail_run(
            conn,
            args.run_id,
            actor=args.actor,
            error_class=args.error_class,
            summary=args.summary,
            effect_unknown=args.effect_unknown,
            persist_receipt=True,
        )
        return transition
    finally:
        conn.close()


def _cmd_recover(args: argparse.Namespace) -> dict[str, Any]:
    conn = _open_existing(_database_path(args))
    try:
        return recover_run(
            conn,
            args.run_id,
            new_owner=args.owner,
            reason=args.reason,
            reconciliation_outcome=args.reconciliation_outcome,
            reconciliation_evidence=_json_value(args.reconciliation_evidence, default=None),
            persist_receipt=True,
        )
    finally:
        conn.close()


def _cmd_run(args: argparse.Namespace) -> dict[str, Any]:
    database_path = _database_path(args)
    conn = _open_existing(database_path)
    observed = _json_value(args.observed, default={})
    try:
        preflight = _verification(conn, database_path)
        if not preflight["ok"]:
            return {"status": "integrity_failed", "ok": False, "preflight": preflight, "runs": []}
        route = _route_check(conn, args.dispatcher_id, observed, actor=args.owner)
        if not route["ok"]:
            return {"status": route["outcome"], "route": route, "runs": []}
        heartbeat = heartbeat_reconciliation(_dispatcher(conn, args.dispatcher_id))
        if not heartbeat.get("covered"):
            return {
                "status": "reconciliation_required",
                "ok": False,
                "dispatcher_id": args.dispatcher_id,
                "route": route,
                "heartbeat_reconciliation": heartbeat,
                "runs": [],
            }
        due = _due_for_dispatcher(
            conn, args.dispatcher_id, args.at or _utc_now(), args.start, args.max_occurrences
        )
        results: list[dict[str, Any]] = []
        for occurrence in due:
            try:
                workflow, revision, definition, definition_path = _verified_current_definition(
                    conn, occurrence["workflow_id"]
                )
            except (CliError, OSError, ValueError, json.JSONDecodeError) as exc:
                workflow = conn.execute(
                    "SELECT * FROM workflows WHERE workflow_id = ?",
                    (occurrence["workflow_id"],),
                ).fetchone()
                if workflow is None:
                    raise
                results.append(
                    _workflow_attention(
                        conn,
                        workflow,
                        event_type="definition_invalid",
                        message=str(exc),
                        actor=args.owner,
                    )
                )
                continue
            claim = claim_occurrence(
                conn,
                occurrence["workflow_id"],
                occurrence["scheduled_for"],
                claim_owner=args.owner,
                observed_identity=observed,
                expected_revision=revision["revision"],
                expected_dispatcher_revision=occurrence["dispatcher_revision"],
                expected_definition_hash=revision["definition_hash"],
                expected_route_task_id=route["configured_identity"]["task_id"]["value"],
                occurrence_metadata=occurrence,
            )
            if claim["status"] != "claimed":
                results.append(claim)
                continue
            run = claim["run"]
            mark_running(conn, run["run_id"], claim_owner=args.owner)
            if definition["procedure"]["external_effect"]["mode"] != "none":
                mark_effect_started(conn, run["run_id"], actor=args.owner)
            try:
                procedure = execute_procedure(
                    definition,
                    occurrence_key=run["occurrence_key"],
                    run_id=run["run_id"],
                    approved_roots=args.approved_root or [definition_path.parent],
                    base_dir=definition_path.parent,
                    timeout_seconds=args.timeout,
                )
            except ProcedureError as exc:
                failed = fail_run(
                    conn,
                    run["run_id"],
                    actor=args.owner,
                    error_class="procedure_error",
                    summary=str(exc),
                    effect_unknown=definition["procedure"]["external_effect"]["mode"] != "none",
                    persist_receipt=True,
                )
                results.append(failed)
                continue
            if procedure.status == "action_required":
                results.append({"status": "action_required", "run_id": run["run_id"], "host_action": procedure.host_action})
            elif procedure.status == "succeeded":
                completed = complete_run(
                    conn,
                    run["run_id"],
                    actor=args.owner,
                    summary=procedure.summary,
                    evidence=procedure.evidence,
                    persist_receipt=True,
                )
                results.append(completed)
            else:
                failed = fail_run(
                    conn,
                    run["run_id"],
                    actor=args.owner,
                    error_class=f"procedure_exit_{procedure.returncode}",
                    summary=procedure.summary,
                    effect_unknown=definition["procedure"]["external_effect"]["mode"] != "none",
                    persist_receipt=True,
                )
                results.append(failed)
        failed = any(
            result.get("status")
            in {"failed", "effect_unknown", "abandoned", "definition_invalid"}
            for result in results
        )
        return {
            "status": "failed" if failed else ("processed" if results else "no_due"),
            "ok": not failed,
            "dispatcher_id": args.dispatcher_id,
            "route": route,
            "heartbeat_reconciliation": heartbeat,
            "runs": results,
        }
    finally:
        conn.close()


def _cmd_receipt_ack(args: argparse.Namespace) -> dict[str, Any]:
    conn = _open_existing(_database_path(args))
    try:
        conn.execute("BEGIN IMMEDIATE")
        result = acknowledge_receipt(
            conn, args.receipt_id, external_message_id=args.external_message_id
        )
        row = conn.execute(
            "SELECT dispatcher_id, run_id FROM receipts WHERE receipt_id = ?", (args.receipt_id,)
        ).fetchone()
        event = None
        if not result["already_posted"]:
            event = append_event(
                conn,
                row["dispatcher_id"],
                "receipt_acknowledged",
                {"receipt_id": args.receipt_id, "external_message_id": args.external_message_id},
                run_id=row["run_id"],
                actor=args.actor,
            )
        conn.commit()
        result["dispatcher_id"] = row["dispatcher_id"]
        result["run_id"] = row["run_id"]
        if event:
            result["event"] = event
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _cmd_receipt_retry(args: argparse.Namespace) -> dict[str, Any]:
    conn = _open_existing(_database_path(args))
    try:
        return prepare_receipt_post(
            conn,
            args.receipt_id,
            actor=args.actor,
            confirm_not_posted=args.confirm_not_posted,
        )
    finally:
        conn.close()


def _cmd_audit(args: argparse.Namespace) -> dict[str, Any]:
    conn = _open_existing(_database_path(args))
    try:
        events = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM audit_events WHERE dispatcher_id = ? ORDER BY event_id",
                (args.dispatcher_id,),
            )
        ]
        result = {"status": "ok", "dispatcher_id": args.dispatcher_id, "events": events}
        if args.verify:
            result["verification"] = verify_audit_chain(conn, args.dispatcher_id)
        return result
    finally:
        conn.close()


def _cmd_integrity(args: argparse.Namespace) -> dict[str, Any]:
    path = _database_path(args)
    conn = _open_existing(path)
    try:
        result = _verification(conn, path)
        result["status"] = "ok" if result["ok"] else "failed"
        return result
    finally:
        conn.close()


def _cmd_backup(args: argparse.Namespace) -> dict[str, Any]:
    return create_backup(
        _database_path(args), assert_runtime_path_is_external(args.destination)
    )


def _cmd_restore_verify(args: argparse.Namespace) -> dict[str, Any]:
    return verify_backup(args.backup_path)


def _cmd_export(args: argparse.Namespace) -> dict[str, Any]:
    return export_sanitized(
        _database_path(args), assert_runtime_path_is_external(args.destination)
    )


def _cmd_migrate(args: argparse.Namespace) -> dict[str, Any]:
    conn = _open_existing(_database_path(args))
    try:
        applied = migrate(conn)
        return {"status": "migrated" if applied else "current", "applied_migrations": applied, "schema_version": schema_version(conn)}
    finally:
        conn.close()


def _lifecycle_source_revision() -> str:
    return os.environ.get("AUTOMATION_DISPATCHER_SOURCE_REVISION", "unknown")


def _lifecycle_result(
    command: str,
    status: str,
    *,
    identity: Mapping[str, Any] | None = None,
    warnings: Sequence[str] = (),
    next_action: Mapping[str, Any] | None = None,
    error: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    value = seal_artifact(
        {
            "schema_version": 1,
            "artifact_type": "command_result",
            "command": command,
            "status": status,
            "identity": {
                "cli_version": __version__,
                **dict(identity or {}),
            },
            "database_path": None,
            "source_revision": _lifecycle_source_revision(),
            "event": None,
            "warnings": list(warnings),
            "next_action": dict(next_action) if next_action is not None else None,
            "error": dict(error) if error is not None else None,
        }
    )
    return validate_artifact("command_result", value)


def _lifecycle_load(
    args: argparse.Namespace, path: str, artifact_type: str
) -> LifecycleArtifact:
    source_controlled = artifact_type == "collection_manifest"
    return load_artifact(
        path,
        artifact_type,
        storage_owner="source_controlled" if source_controlled else "external_state",
        explicit_root=(args.repository_root if source_controlled else args.state_root),
        source_root=None if source_controlled else args.source_root,
        installed_roots=tuple(args.installed_root or ()),
    )


def _lifecycle_progress(args: argparse.Namespace) -> list[dict[str, Any]]:
    return [
        _lifecycle_load(args, path, "progress_record").as_dict()
        for path in (args.progress or ())
    ]


def _lifecycle_command_request(
    args: argparse.Namespace, plan: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    command = args.lifecycle_command
    input_path = getattr(args, "input", None) or getattr(args, "plan", None)
    request = seal_artifact(
        {
            "schema_version": 1,
            "artifact_type": "lifecycle_command",
            "command": command,
            "actor": args.actor,
            "reason": args.reason,
            "database_path": None,
            "plan_id": plan.get("plan_id") if plan is not None else None,
            "plan_hash": plan.get("content_hash") if plan is not None else None,
            "input_path": (
                str(Path(input_path).expanduser().resolve(strict=False)) if input_path else None
            ),
        }
    )
    return validate_artifact("lifecycle_command", request)


def _cmd_lifecycle(args: argparse.Namespace) -> dict[str, Any]:
    command = args.lifecycle_command
    request: dict[str, Any] | None = None
    try:
        request = _lifecycle_command_request(args)
        if command == "plan":
            artifact = _lifecycle_load(args, args.input, args.artifact_type)
            return _lifecycle_result(
                command,
                "completed",
                identity={
                    "artifact_type": args.artifact_type,
                    "command_request_hash": request["content_hash"],
                    "content_hash": artifact.content_hash,
                    "input_path": str(Path(args.input).expanduser().resolve(strict=False)),
                    "normalized": artifact.as_dict(),
                },
                next_action={"type": "review_artifact", "artifact_type": args.artifact_type},
            )
        plan = _lifecycle_load(args, args.plan, "lifecycle_plan").as_dict()
        request = _lifecycle_command_request(args, plan)
        progress = _lifecycle_progress(args)
        if command == "explain":
            blocked = bool(plan["unresolved_decisions"])
            return _lifecycle_result(
                command,
                "blocked" if blocked else "completed",
                identity={
                    "plan_id": plan["plan_id"],
                    "command_request_hash": request["content_hash"],
                    "plan_hash": plan["content_hash"],
                    "collections": plan["collections"],
                    "workflow_mappings": plan["workflow_mappings"],
                    "approved_scope": plan["approved_scope"],
                    "expected_cli_operations": plan["expected_cli_operations"],
                    "expected_host_operations": plan["expected_host_operations"],
                    "rollback_steps": plan["rollback_steps"],
                    "unresolved_decisions": plan["unresolved_decisions"],
                },
                next_action=(
                    {"type": "resolve_decisions", "items": plan["unresolved_decisions"]}
                    if blocked
                    else {"type": "review_plan"}
                ),
            )
        if command == "status":
            status = lifecycle_status(plan, progress)
            recovery_required = any(
                disposition == "reconciliation_required"
                for disposition in status["recovery"].values()
            )
            return _lifecycle_result(
                command,
                status["status"],
                identity={**status, "command_request_hash": request["content_hash"]},
                next_action={
                    "type": "reconcile_progress" if recovery_required else "resume_or_review",
                    "plan_id": plan["plan_id"],
                },
            )
        if command == "verify":
            observed = _lifecycle_load(args, args.observed, args.observed_type).as_dict()
            report = semantic_drift_report(plan, observed).as_dict()
            drifted = report["status"] != "unchanged"
            return _lifecycle_result(
                command,
                "conflict" if drifted else "completed",
                identity={
                    "plan_id": plan["plan_id"],
                    "command_request_hash": request["content_hash"],
                    "plan_hash": plan["content_hash"],
                    "drift_report": report,
                },
                next_action=(
                    {"type": "rediscover_and_replan"}
                    if drifted
                    else {"type": "continue_review"}
                ),
            )
        if command == "apply":
            if not args.dry_run:
                raise LifecycleContractError(
                    "dry_run_required",
                    "Phase 2 lifecycle apply is planning-only and requires --dry-run",
                )
            step = plan_step(
                plan,
                stage=args.stage,
                action=args.action,
                collection_id=args.collection_id,
                progress=progress,
            )
            if step.writes:
                dry_run = {
                    **step.as_dict(),
                    "writes_prevented": list(step.writes),
                    "host_requests_prevented": list(step.host_requests),
                    "mutation_count": 0,
                }
            else:
                dry_run = {**step.as_dict(), "mutation_count": 0}
            if step.step_id in {item["step_id"] for item in progress if item["status"] == "completed"}:
                result_status = "no_op"
            elif step.blockers:
                result_status = "blocked"
            else:
                result_status = "completed"
            return _lifecycle_result(
                command,
                result_status,
                identity={
                    "plan_id": plan["plan_id"],
                    "command_request_hash": request["content_hash"],
                    "plan_hash": plan["content_hash"],
                    "dry_run": True,
                    "step_plan": dry_run,
                },
                next_action=step.next_action,
            )
        raise LifecycleContractError(
            "unsupported_lifecycle_command", f"unsupported lifecycle command: {command}"
        )
    except LifecycleContractError as exc:
        status = {
            "optimistic_concurrency_conflict": "conflict",
            "source_snapshot_drift": "conflict",
            "unsupported_future": "blocked",
            "migration_required": "blocked",
            "forbidden_artifact_path": "blocked",
            "symlink_artifact_path": "blocked",
            "blocked_prerequisite": "blocked",
        }.get(exc.code, "failed")
        return _lifecycle_result(
            command,
            status,
            identity={
                "plan_id": getattr(args, "plan_id", None),
                "input_path": getattr(args, "input", None) or getattr(args, "plan", None),
                "command_request_hash": request.get("content_hash") if request else None,
                "exit_code": 2 if status == "failed" else 1,
            },
            next_action={"type": "correct_or_reconcile", "reason": exc.code},
            error={"code": exc.code, "message": str(exc), "details": exc.details},
        )


def _add_lifecycle_path_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--state-root")
    command.add_argument("--repository-root")
    command.add_argument("--source-root", required=True)
    command.add_argument("--installed-root", action="append")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="automation-dispatcher")
    parser.add_argument("--database", "--db", dest="database", help="External dispatcher SQLite database")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("--dispatcher-id", required=True)
    init.add_argument("--name", required=True)
    init.add_argument("--description", required=True)
    init.add_argument("--schedule", required=True, help="Collection cron schedule or preset JSON")
    init.add_argument("--max-lateness-seconds", type=int, required=True)
    init.add_argument("--catch-up", required=True, help="Collection catch-up policy JSON")
    init.add_argument("--expected-task-id", required=True)
    init.add_argument("--expected-working-directory", required=True)
    init.add_argument("--automation-id")
    init.add_argument("--expected-harness")
    init.add_argument("--expected-host")
    init.add_argument("--timezone", required=True)
    init.add_argument("--required-identity")
    init.add_argument(
        "--heartbeat-schedule",
        required=True,
        help="Verified heartbeat schedule JSON used for coverage checks",
    )
    init.add_argument("--skill-version")
    init.add_argument("--source-revision")
    init.add_argument("--actor", required=True)
    init.add_argument("--reason", required=True)
    init.set_defaults(handler=_cmd_init)

    status = sub.add_parser("status")
    status.set_defaults(handler=_cmd_status)
    route = sub.add_parser("route-check")
    route.add_argument("--dispatcher-id", required=True)
    route.add_argument("--observed", required=True)
    route.add_argument("--actor", required=True)
    route.set_defaults(handler=_cmd_route_check)
    route_revise = sub.add_parser("route-revise")
    route_revise.add_argument("--dispatcher-id", required=True)
    route_revise.add_argument("--destination-task-id", required=True)
    route_revise.add_argument("--expected-working-directory", required=True)
    route_revise.add_argument("--expected-harness")
    route_revise.add_argument("--expected-host")
    route_revise.add_argument("--required-identity")
    route_revise.add_argument("--actor", required=True)
    route_revise.add_argument("--reason", required=True)
    route_revise.set_defaults(handler=_cmd_route_revise)
    schedule_revise = sub.add_parser("schedule-revise")
    schedule_revise.add_argument("--dispatcher-id", required=True)
    schedule_revise.add_argument("--schedule", required=True)
    schedule_revise.add_argument("--timezone", required=True)
    schedule_revise.add_argument("--max-lateness-seconds", type=int, required=True)
    schedule_revise.add_argument("--catch-up", required=True)
    schedule_revise.add_argument("--heartbeat-schedule", required=True)
    schedule_revise.add_argument("--actor", required=True)
    schedule_revise.add_argument("--reason", required=True)
    schedule_revise.set_defaults(handler=_cmd_schedule_revise)

    for name, revise in (("register", False), ("revise", True)):
        command = sub.add_parser(name)
        command.add_argument("--definition", required=True)
        command.add_argument("--actor", required=True)
        command.add_argument("--reason", required=True)
        command.add_argument("--dry-run", action="store_true")
        command.set_defaults(handler=lambda a, r=revise: _cmd_register(a, revise=r))
    for name, enabled in (("enable", True), ("disable", False)):
        command = sub.add_parser(name)
        command.add_argument("workflow_id")
        command.add_argument("--actor", required=True)
        command.add_argument("--reason", required=True)
        command.set_defaults(handler=lambda a, e=enabled: _cmd_enabled(a, enabled=e))
    listing = sub.add_parser("list")
    listing.add_argument("--dispatcher-id")
    listing.set_defaults(handler=_cmd_list)

    due = sub.add_parser("due")
    due.add_argument("--dispatcher-id", required=True)
    due.add_argument("--at")
    due.add_argument("--start")
    due.add_argument("--max-occurrences", type=int)
    due.set_defaults(handler=_cmd_due)
    claim = sub.add_parser("claim")
    claim.add_argument("--workflow-id", required=True)
    claim.add_argument("--scheduled-for", required=True)
    claim.add_argument("--owner", required=True)
    claim.add_argument("--observed", required=True)
    claim.add_argument("--occurrence-metadata")
    claim.set_defaults(handler=_cmd_claim)
    run = sub.add_parser("run")
    run.add_argument("--dispatcher-id", required=True)
    run.add_argument("--owner", required=True)
    run.add_argument("--observed", required=True)
    run.add_argument("--at")
    run.add_argument("--start")
    run.add_argument("--max-occurrences", type=int)
    run.add_argument("--approved-root", action="append")
    run.add_argument("--timeout", type=int, default=900)
    run.set_defaults(handler=_cmd_run)

    complete = sub.add_parser("complete")
    complete.add_argument("run_id")
    complete.add_argument("--actor", required=True)
    complete.add_argument("--summary", required=True)
    complete.add_argument("--evidence", action="append")
    complete.set_defaults(handler=_cmd_complete)
    fail = sub.add_parser("fail")
    fail.add_argument("run_id")
    fail.add_argument("--actor", required=True)
    fail.add_argument("--error-class", required=True)
    fail.add_argument("--summary", required=True)
    fail.add_argument("--effect-unknown", action="store_true")
    fail.set_defaults(handler=_cmd_fail)
    recover = sub.add_parser("recover")
    recover.add_argument("run_id")
    recover.add_argument("--owner", required=True)
    recover.add_argument("--reason", required=True)
    recover.add_argument("--reconciliation-outcome", choices=("completed", "not_completed"))
    recover.add_argument("--reconciliation-evidence")
    recover.set_defaults(handler=_cmd_recover)

    ack = sub.add_parser("receipt-ack")
    ack.add_argument("receipt_id")
    ack.add_argument("--external-message-id")
    ack.add_argument("--actor", required=True)
    ack.set_defaults(handler=_cmd_receipt_ack)
    retry = sub.add_parser("receipt-retry")
    retry.add_argument("receipt_id")
    retry.add_argument("--actor", required=True)
    retry.add_argument("--confirm-not-posted", action="store_true")
    retry.set_defaults(handler=_cmd_receipt_retry)
    audit = sub.add_parser("audit")
    audit.add_argument("--dispatcher-id", required=True)
    audit.add_argument("--verify", action="store_true")
    audit.set_defaults(handler=_cmd_audit)
    integrity = sub.add_parser("integrity-check")
    integrity.set_defaults(handler=_cmd_integrity)
    backup = sub.add_parser("backup")
    backup.add_argument("--destination", required=True)
    backup.set_defaults(handler=_cmd_backup)
    restore = sub.add_parser("restore-verify")
    restore.add_argument("backup_path")
    restore.set_defaults(handler=_cmd_restore_verify)
    export = sub.add_parser("export")
    export.add_argument("--destination", required=True)
    export.set_defaults(handler=_cmd_export)
    migration = sub.add_parser("migrate")
    migration.set_defaults(handler=_cmd_migrate)

    lifecycle = sub.add_parser("lifecycle")
    lifecycle_sub = lifecycle.add_subparsers(dest="lifecycle_command", required=True)

    lifecycle_plan = lifecycle_sub.add_parser("plan")
    lifecycle_plan.add_argument("--artifact-type", required=True, choices=tuple(ARTIFACT_MODELS))
    lifecycle_plan.add_argument("--input", required=True)
    lifecycle_plan.add_argument("--actor", required=True)
    lifecycle_plan.add_argument("--reason", required=True)
    _add_lifecycle_path_arguments(lifecycle_plan)
    lifecycle_plan.set_defaults(handler=_cmd_lifecycle)

    for name in ("explain", "status", "verify", "apply"):
        command = lifecycle_sub.add_parser(name)
        command.add_argument("--plan", required=True)
        command.add_argument("--progress", action="append")
        command.add_argument("--actor", required=True)
        command.add_argument("--reason", required=True)
        _add_lifecycle_path_arguments(command)
        if name == "verify":
            command.add_argument("--observed", required=True)
            command.add_argument(
                "--observed-type", required=True, choices=tuple(ARTIFACT_MODELS)
            )
        if name == "apply":
            command.add_argument("--stage", required=True)
            command.add_argument("--action", required=True)
            command.add_argument("--collection-id")
            command.add_argument("--dry-run", action="store_true")
        command.set_defaults(handler=_cmd_lifecycle)
    return parser


def _human(result: Any) -> str:
    if isinstance(result, Mapping):
        status = result.get("status", "ok")
        if result.get("artifact_type") == "command_result":
            identity = result.get("identity") if isinstance(result.get("identity"), Mapping) else {}
            next_action = result.get("next_action")
            error = result.get("error")
            parts = [str(status)]
            if identity.get("plan_id"):
                parts.append(f"plan_id={identity['plan_id']}")
            if isinstance(next_action, Mapping) and next_action.get("type"):
                parts.append(f"next_action={next_action['type']}")
            if isinstance(error, Mapping) and error.get("code"):
                parts.append(f"blocker={error['code']}")
            return " ".join(parts)
        identifiers = [
            f"{key}={result[key]}"
            for key in ("dispatcher_id", "workflow_id", "run_id", "receipt_id")
            if result.get(key) is not None
        ]
        return " ".join([str(status), *identifiers])
    return str(result)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.handler(args)
        if isinstance(result, dict) and result.get("artifact_type") != "command_result":
            result.setdefault("database_path", _database_path(args) if getattr(args, "database", None) else None)
            result.setdefault("cli_version", __version__)
            result.setdefault(
                "source_revision",
                os.environ.get("AUTOMATION_DISPATCHER_SOURCE_REVISION", "unknown"),
            )
            event = result.get("event")
            if isinstance(event, Mapping):
                result.setdefault("event_id", event.get("event_id"))
                result.setdefault("event_hash", event.get("event_hash"))
        if args.json:
            print(json.dumps(result, sort_keys=True, ensure_ascii=False, default=str))
        else:
            print(_human(result))
        if isinstance(result, Mapping) and result.get("artifact_type") == "command_result":
            identity = result.get("identity")
            if isinstance(identity, Mapping) and identity.get("exit_code") in {1, 2}:
                return int(identity["exit_code"])
        if isinstance(result, Mapping) and (
            result.get("ok") is False
            or result.get("status") in {
                "failed", "route_mismatch", "route_unattested", "effect_unknown", "error",
                "blocked", "conflict"
            }
        ):
            return 1
        return 0
    except (CliError, RegistryError, ClaimError, ProcedureError, OSError, ValueError, sqlite3.Error) as exc:
        raw_database = getattr(args, "database", None)
        error = {
            "status": "error",
            "error_class": type(exc).__name__,
            "message": str(exc),
            "command": getattr(args, "command", None),
            "database_path": (
                str(Path(raw_database).expanduser().resolve()) if raw_database else None
            ),
            "cli_version": __version__,
            "source_revision": os.environ.get(
                "AUTOMATION_DISPATCHER_SOURCE_REVISION", "unknown"
            ),
        }
        for key in ("dispatcher_id", "workflow_id", "run_id", "receipt_id"):
            value = getattr(args, key, None)
            if value is not None:
                error[key] = value
        if getattr(args, "json", False):
            print(json.dumps(error, sort_keys=True), file=sys.stderr)
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

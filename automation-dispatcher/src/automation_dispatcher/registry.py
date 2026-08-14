"""Workflow registry projection and immutable revision operations."""

from __future__ import annotations

import json
import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .audit import append_event
from . import __version__
from .database import connect, initialize_database
from .definitions import (
    DefinitionError,
    load_definition,
    normalize_definition,
    normalize_dispatcher_id,
    validate_definition,
)
from .scheduling import normalize_collection_schedule
from .receipts import create_receipt


class RegistryError(RuntimeError):
    """Raised when a registry mutation violates dispatcher policy."""


_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _non_negative_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise RegistryError(f"{field} must be a non-negative integer")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise RegistryError(f"{field} must be a non-negative integer") from exc
    if normalized < 0 or str(value).strip() != str(normalized):
        raise RegistryError(f"{field} must be a non-negative integer")
    return normalized


def _canonical_catch_up(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RegistryError("catch_up must be a JSON object")
    policy = str(value.get("policy", "")).strip().lower()
    if policy not in {"none", "latest", "bounded", "all"}:
        raise RegistryError("catch_up.policy must be none, latest, bounded, or all")
    return {
        "policy": policy,
        "max_lookback_seconds": _non_negative_int(
            value.get("max_lookback_seconds"), "catch_up.max_lookback_seconds"
        ),
    }


def normalize_dispatcher_configuration(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return canonical durable configuration for one workflow collection."""

    if not isinstance(value, Mapping):
        raise RegistryError("dispatcher configuration must be a JSON object")
    try:
        dispatcher_id = normalize_dispatcher_id(value.get("dispatcher_id"))
        schedule = normalize_collection_schedule(value.get("schedule", value.get("schedule_json")))
    except DefinitionError as exc:
        raise RegistryError(str(exc)) from exc
    name = value.get("name")
    description = value.get("description")
    if not isinstance(name, str) or not name.strip():
        raise RegistryError("dispatcher name must be a non-empty string")
    if not isinstance(description, str):
        raise RegistryError("dispatcher description must be a string")
    timezone_name = value.get("timezone")
    if not isinstance(timezone_name, str) or not timezone_name.strip():
        raise RegistryError("timezone must be an IANA timezone name")
    timezone_name = timezone_name.strip()
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise RegistryError(f"unknown IANA timezone: {timezone_name}") from exc
    max_lateness = _non_negative_int(
        value.get("max_lateness_seconds"), "max_lateness_seconds"
    )
    catch_up = _canonical_catch_up(value.get("catch_up"))
    heartbeat = value.get("heartbeat_schedule")
    if not isinstance(heartbeat, Mapping):
        raise RegistryError("heartbeat_schedule must be a JSON object")
    enabled = value.get("enabled", True)
    if enabled not in (True, False, 0, 1):
        raise RegistryError("dispatcher enabled must be a boolean")
    return {
        "schema_version": 2,
        "dispatcher_id": dispatcher_id,
        "name": name.strip(),
        "description": description.strip(),
        "timezone": timezone_name,
        "schedule": schedule,
        "max_lateness_seconds": max_lateness,
        "catch_up": catch_up,
        "heartbeat_schedule": dict(heartbeat),
        "enabled": bool(enabled),
    }


def dispatcher_configuration_hash(config: Mapping[str, Any]) -> str:
    return hashlib.sha256(_json(config).encode("utf-8")).hexdigest()


def _workflow_configuration_receipt(
    conn: Any,
    workflow: Mapping[str, Any],
    *,
    action: str,
    actor: str,
    event: Mapping[str, Any],
) -> dict[str, Any]:
    workflow_id = str(workflow["workflow_id"])
    content = (
        f"### Workflow {action}\n"
        f"- Workflow: `{workflow_id}`\n"
        f"- Dispatcher: `{workflow['dispatcher_id']}`\n"
        f"- Definition hash: `{str(workflow['definition_hash'])[:12]}`\n"
        f"- Audit: `{event['event_id']}/{str(event['event_hash'])[:12]}`"
    )
    receipt = create_receipt(
        conn,
        dispatcher_id=workflow["dispatcher_id"],
        destination_task_id=workflow["reporting_task_id"],
        content=content,
        workflow_id=workflow_id,
    )
    append_event(
        conn,
        workflow["dispatcher_id"],
        "receipt_pending",
        {
            "receipt_id": receipt["receipt_id"],
            "content_hash": receipt["content_hash"],
            "action": action,
        },
        workflow_id=workflow_id,
        actor=actor,
    )
    return receipt


def dispatcher_configuration_from_row(dispatcher: Any) -> dict[str, Any]:
    row = dict(dispatcher)
    return normalize_dispatcher_configuration(
        {
            "dispatcher_id": row["dispatcher_id"],
            "name": row["name"],
            "description": row["description"],
            "timezone": row["timezone"],
            "schedule_json": json.loads(row["schedule_json"]),
            "max_lateness_seconds": row["max_lateness_seconds"],
            "catch_up": {
                "policy": row["catch_up_policy"],
                "max_lookback_seconds": row["max_lookback_seconds"],
            },
            "heartbeat_schedule": json.loads(row["heartbeat_schedule_json"] or "{}"),
            "enabled": row["enabled"],
        }
    )


def _fixed_weekly_slots(schedule: Mapping[str, Any]) -> list[int] | None:
    minute_text, hour_text, day_of_month, month, day_of_week = str(
        schedule["expression"]
    ).split()
    if not minute_text.isdigit() or not hour_text.isdigit():
        return None
    if day_of_month != "*" or month != "*":
        return None
    minute = int(hour_text) * 60 + int(minute_text)
    if day_of_week == "*":
        cron_days = range(7)
    else:
        parts = day_of_week.split(",")
        if not all(part.isdigit() and 0 <= int(part) <= 6 for part in parts):
            return None
        cron_days = [int(part) for part in parts]
    return sorted({((day - 1) % 7) * 1440 + minute for day in cron_days})


def heartbeat_reconciliation(dispatcher: Any) -> dict[str, Any]:
    """Verify that the configured host heartbeat covers the collection schedule."""

    source = dict(dispatcher)
    collection = (
        normalize_dispatcher_configuration(source)
        if "schedule" in source and "heartbeat_schedule" in source
        else dispatcher_configuration_from_row(source)
    )
    configured = collection["heartbeat_schedule"]
    if not isinstance(configured, Mapping) or not configured.get("verified"):
        return {
            "status": "reconciliation_required",
            "verified": False,
            "covered": None,
            "reason": "dispatcher heartbeat schedule has not been verified",
        }
    max_lateness = collection["max_lateness_seconds"]
    if "interval_seconds" in configured:
        interval = _non_negative_int(configured["interval_seconds"], "heartbeat interval_seconds")
        if interval == 0:
            raise RegistryError("heartbeat interval_seconds must be positive")
        if interval > max_lateness:
            raise RegistryError("verified heartbeat interval does not cover collection maximum lateness")
        return {
            "status": "covered",
            "verified": True,
            "covered": True,
            "mode": "interval",
            "worst_delay_seconds": interval,
            "max_lateness_seconds": max_lateness,
        }
    if "schedule" in configured:
        try:
            heartbeat_schedule = normalize_collection_schedule(configured["schedule"])
        except DefinitionError as exc:
            raise RegistryError(str(exc)) from exc
        if heartbeat_schedule != collection["schedule"]:
            raise RegistryError(
                "verified heartbeat schedule differs from the collection schedule; "
                "use an exact schedule or a verified interval"
            )
        return {
            "status": "covered",
            "verified": True,
            "covered": True,
            "mode": "exact_schedule",
            "worst_delay_seconds": 0,
            "max_lateness_seconds": max_lateness,
        }
    raw_slots = configured.get("slots")
    if not isinstance(raw_slots, list) or not raw_slots:
        raise RegistryError(
            "verified heartbeat schedule must contain schedule, interval_seconds, or non-empty slots"
        )
    due_slots = _fixed_weekly_slots(collection["schedule"])
    if not due_slots:
        raise RegistryError(
            "legacy heartbeat slots can cover only a fixed daily/weekly collection schedule; "
            "use an exact schedule or verified interval"
        )
    heartbeat_slots: list[int] = []
    for slot in raw_slots:
        if not isinstance(slot, Mapping):
            raise RegistryError("heartbeat slots must be objects")
        weekdays = slot.get("weekdays", list(_WEEKDAYS))
        if not isinstance(weekdays, list) or not weekdays:
            raise RegistryError("heartbeat slot weekdays must be a non-empty list")
        time_text = str(slot.get("time", ""))
        try:
            hour_text, minute_text, *rest = time_text.split(":")
            hour, minute = int(hour_text), int(minute_text)
        except (TypeError, ValueError) as exc:
            raise RegistryError(f"invalid heartbeat time: {time_text!r}") from exc
        if rest or not (0 <= hour < 24 and 0 <= minute < 60):
            raise RegistryError(f"invalid heartbeat time: {time_text!r}")
        minute = hour * 60 + minute
        for weekday in weekdays:
            name = str(weekday).lower()
            if name not in _WEEKDAYS:
                raise RegistryError(f"invalid heartbeat weekday: {weekday!r}")
            heartbeat_slots.append(_WEEKDAYS.index(name) * 1440 + minute)

    uncovered: list[dict[str, Any]] = []
    worst_delay = 0
    for due_slot in due_slots:
        delays = [((heartbeat - due_slot) % (7 * 1440)) for heartbeat in heartbeat_slots]
        delay = min(delays)
        worst_delay = max(worst_delay, delay)
        if delay * 60 > max_lateness:
            uncovered.append({"slot": due_slot, "delay_seconds": delay * 60})
    result = {
        "status": "covered" if not uncovered else "uncovered",
        "verified": True,
        "covered": not uncovered,
        "worst_delay_seconds": worst_delay * 60,
        "mode": "legacy_slots",
        "max_lateness_seconds": max_lateness,
        "uncovered": uncovered,
    }
    if uncovered:
        raise RegistryError("verified heartbeat schedule does not cover collection maximum lateness")
    return result


def revise_dispatcher_schedule(
    conn: Any,
    dispatcher_id: str,
    *,
    schedule: Any,
    timezone: str,
    max_lateness_seconds: int,
    catch_up: Mapping[str, Any],
    heartbeat_schedule: Mapping[str, Any],
    actor: str,
    reason: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Append a dispatcher configuration revision and update its projection."""

    current = conn.execute(
        "SELECT * FROM dispatchers WHERE dispatcher_id = ?", (dispatcher_id,)
    ).fetchone()
    if current is None:
        raise RegistryError(f"unknown dispatcher: {dispatcher_id}")
    config = normalize_dispatcher_configuration(
        {
            "dispatcher_id": dispatcher_id,
            "name": current["name"],
            "description": current["description"],
            "timezone": timezone,
            "schedule": schedule,
            "max_lateness_seconds": max_lateness_seconds,
            "catch_up": catch_up,
            "heartbeat_schedule": heartbeat_schedule,
            "enabled": current["enabled"],
        }
    )
    reconciliation = heartbeat_reconciliation(config)
    revision = int(current["current_revision"]) + 1
    config_hash = dispatcher_configuration_hash(config)
    current_revision = conn.execute(
        """SELECT config_hash FROM dispatcher_revisions
             WHERE dispatcher_id = ? AND revision = ?""",
        (dispatcher_id, current["current_revision"]),
    ).fetchone()
    if current_revision is None:
        raise RegistryError("current dispatcher revision snapshot is missing")
    if current_revision["config_hash"] == config_hash:
        raise RegistryError("dispatcher schedule configuration is unchanged")
    result = {
        "status": "valid",
        "dispatcher_id": dispatcher_id,
        "revision": revision,
        "configuration": config,
        "config_hash": config_hash,
        "heartbeat_reconciliation": reconciliation,
    }
    if dry_run:
        return {**result, "dry_run": True}

    timestamp = _now()
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            """
            INSERT INTO dispatcher_revisions (
                dispatcher_id, revision, normalized_config_json, config_hash,
                actor, reason, effective_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dispatcher_id,
                revision,
                _json(config),
                config_hash,
                actor,
                reason,
                timestamp,
                timestamp,
            ),
        )
        conn.execute(
            """
            UPDATE dispatchers
               SET current_revision = ?, schedule_json = ?, timezone = ?,
                   max_lateness_seconds = ?, catch_up_policy = ?,
                   max_lookback_seconds = ?, heartbeat_schedule_json = ?, updated_at = ?
             WHERE dispatcher_id = ?
            """,
            (
                revision,
                _json(config["schedule"]),
                config["timezone"],
                config["max_lateness_seconds"],
                config["catch_up"]["policy"],
                config["catch_up"]["max_lookback_seconds"],
                _json(config["heartbeat_schedule"]),
                timestamp,
                dispatcher_id,
            ),
        )
        event = append_event(
            conn,
            dispatcher_id=dispatcher_id,
            event_type="dispatcher_schedule_revised",
            payload={
                "revision": revision,
                "previous_revision": int(current["current_revision"]),
                "config_hash": config_hash,
                "reason": reason,
                "heartbeat_reconciliation": reconciliation,
            },
            actor=actor,
        )
        destination_task_id = current["default_reporting_task_id"] or current["expected_task_id"]
        content = (
            "### Dispatcher schedule revised\n"
            f"- Dispatcher: `{dispatcher_id}`\n"
            f"- Schedule revision: `{revision}`\n"
            f"- Schedule: `{config['schedule']['expression']}`\n"
            f"- Audit: `{event['event_id']}/{event['event_hash'][:12]}`"
        )
        receipt = create_receipt(
            conn,
            dispatcher_id=dispatcher_id,
            destination_task_id=destination_task_id,
            content=content,
        )
        append_event(
            conn,
            dispatcher_id=dispatcher_id,
            event_type="receipt_pending",
            payload={
                "receipt_id": receipt["receipt_id"],
                "content_hash": receipt["content_hash"],
                "action": "schedule_revised",
            },
            actor=actor,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {
        **result,
        "status": "schedule_revised",
        "event": event,
        "receipt": receipt,
    }


def initialize_dispatcher(
    database_path: str | Path,
    *,
    dispatcher_id: str,
    name: str,
    description: str,
    schedule: Any,
    timezone: str,
    max_lateness_seconds: int,
    catch_up: Mapping[str, Any],
    heartbeat_schedule: Mapping[str, Any],
    expected_task_id: str,
    expected_working_directory: str | Path,
    actor: str,
    reason: str,
    required_identity: Mapping[str, Any],
    automation_id: str | None = None,
    expected_harness: str | None = None,
    expected_host: str | None = None,
    skill_version: str | None = None,
    source_revision: str | None = None,
    timestamp: str | None = None,
    route_id: str | None = None,
    receipt_creator: Callable[..., dict[str, Any]] = create_receipt,
) -> dict[str, Any]:
    """Initialize or verify one collection through the canonical registry path."""

    config = normalize_dispatcher_configuration(
        {
            "dispatcher_id": dispatcher_id,
            "name": name,
            "description": description,
            "timezone": timezone,
            "schedule": schedule,
            "max_lateness_seconds": max_lateness_seconds,
            "catch_up": catch_up,
            "heartbeat_schedule": heartbeat_schedule,
            "enabled": True,
        }
    )
    reconciliation = heartbeat_reconciliation(config)
    config_hash = dispatcher_configuration_hash(config)
    initialized = initialize_database(database_path)
    working_directory = str(
        Path(expected_working_directory).expanduser().resolve(strict=True)
    )
    now = timestamp or _now()
    conn = connect(database_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT * FROM dispatchers WHERE dispatcher_id = ?", (dispatcher_id,)
        ).fetchone()
        if existing:
            if dispatcher_configuration_from_row(existing) != config:
                raise RegistryError(
                    "existing dispatcher configuration differs; use schedule-revise "
                    "or initialize a different collection"
                )
            if (
                existing["expected_task_id"] != expected_task_id
                or existing["expected_working_directory"] != working_directory
            ):
                raise RegistryError("existing dispatcher route differs; use route-revise")
            if source_revision is not None and existing["source_revision"] != source_revision:
                raise RegistryError("existing dispatcher source revision differs")
            conn.rollback()
            return {
                **initialized,
                "dispatcher_id": dispatcher_id,
                "status": "already_initialized",
                "configuration": config,
                "heartbeat_reconciliation": reconciliation,
            }
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
                _json(config["schedule"]), automation_id, expected_task_id,
                working_directory, expected_harness, expected_host, expected_task_id,
                _json(config["heartbeat_schedule"]), config["timezone"],
                config["max_lateness_seconds"], config["catch_up"]["policy"],
                config["catch_up"]["max_lookback_seconds"], skill_version or __version__,
                source_revision, now, now,
            ),
        )
        conn.execute(
            """
            INSERT INTO dispatcher_revisions (
                dispatcher_id, revision, normalized_config_json, config_hash,
                actor, reason, effective_at, created_at
            ) VALUES (?, 1, ?, ?, ?, ?, ?, ?)
            """,
            (dispatcher_id, _json(config), config_hash, actor, reason, now, now),
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
                route_id or str(uuid.uuid4()), dispatcher_id, expected_task_id,
                working_directory, expected_harness, expected_host,
                _json(required_identity), now, actor, reason, now,
            ),
        )
        event = append_event(
            conn,
            dispatcher_id,
            "dispatcher_initialized",
            {
                "task_id": expected_task_id,
                "collection_name": config["name"],
                "dispatcher_revision": 1,
                "schedule": config["schedule"],
                "route_revision": 1,
                "heartbeat_schedule_verified": bool(heartbeat_schedule.get("verified", False)),
                "heartbeat_reconciliation": reconciliation,
            },
            actor=actor,
        )
        content = (
            "### Dispatcher initialized\n"
            f"- Dispatcher: `{dispatcher_id}`\n"
            f"- Collection: `{config['name']}`\n"
            "- Schedule revision: `1`\n"
            f"- Audit: `{event['event_id']}/{event['event_hash'][:12]}`"
        )
        receipt = receipt_creator(
            conn,
            dispatcher_id=dispatcher_id,
            destination_task_id=expected_task_id,
            content=content,
        )
        append_event(
            conn,
            dispatcher_id,
            "receipt_pending",
            {
                "receipt_id": receipt["receipt_id"],
                "content_hash": receipt["content_hash"],
                "action": "dispatcher_initialized",
            },
            actor=actor,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {
        **initialized,
        "dispatcher_id": dispatcher_id,
        "status": "initialized",
        "configuration": config,
        "heartbeat_reconciliation": reconciliation,
        "event": event,
        "receipt": receipt,
    }


def _projection(normalized: Mapping[str, Any], definition_path: Path) -> dict[str, Any]:
    procedure = normalized["procedure"]
    external = procedure.get("external_effect", {})
    reporting = normalized["reporting"]
    retry = normalized["retry"]
    retention = normalized["evidence_retention"]
    return {
        "workflow_id": normalized["workflow_id"],
        "dispatcher_id": normalized["dispatcher_id"],
        "name": normalized["name"],
        "description": normalized.get("description", ""),
        "enabled": int(normalized.get("enabled", True)),
        "definition_path": str(definition_path),
        "definition_revision": str(normalized["revision"]),
        "definition_hash": normalized["content_hash"],
        "normalized_definition_json": _json(normalized),
        "retry_policy_json": _json(retry),
        "claim_lease_seconds": int(normalized["claim_lease_seconds"]),
        "procedure_kind": procedure["kind"],
        "procedure_reference": procedure["reference"],
        "external_effect_mode": external.get("mode", "none"),
        "reconciliation_reference": external.get("reconciliation_reference"),
        "authority_references_json": _json(normalized["authority_refs"]),
        "reporting_task_id": reporting["task_id"],
        "receipt_template_json": _json({"fields": reporting.get("receipt_fields", [])}),
        "data_sensitivity": normalized["data_sensitivity"],
        "evidence_retention_json": _json(retention),
    }


def prepare_definition(path: str | Path) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    resolved = Path(path).expanduser().resolve(strict=True)
    normalized = normalize_definition(load_definition(resolved), base_dir=resolved.parent)
    return resolved, normalized, _projection(normalized, resolved)


def register_workflow(
    conn: Any,
    definition_path: str | Path,
    *,
    actor: str,
    reason: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    resolved, normalized, projection = prepare_definition(definition_path)
    dispatcher = conn.execute(
        "SELECT * FROM dispatchers WHERE dispatcher_id = ?",
        (projection["dispatcher_id"],),
    ).fetchone()
    if dispatcher is None:
        raise RegistryError(f"unknown dispatcher: {projection['dispatcher_id']}")
    allowed_route = dispatcher["default_reporting_task_id"] or dispatcher["expected_task_id"]
    if not allowed_route or projection["reporting_task_id"] != allowed_route:
        raise RegistryError("workflow reporting task is outside the dispatcher route")
    errors = validate_definition(
        normalized,
        base_dir=resolved.parent,
        allowed_reporting_tasks=[allowed_route],
        require_existing_refs=True,
    )
    if errors:
        raise RegistryError("invalid workflow definition: " + "; ".join(errors))
    heartbeat_status = heartbeat_reconciliation(dispatcher)
    if conn.execute(
        "SELECT 1 FROM workflows WHERE workflow_id = ?", (projection["workflow_id"],)
    ).fetchone():
        raise RegistryError("workflow already exists; use revise")

    result = {
        "status": "valid",
        "revision": 1,
        "heartbeat_reconciliation": heartbeat_status,
        **projection,
    }
    if dry_run:
        return {**result, "dry_run": True, "normalized_definition": normalized}

    timestamp = _now()
    conn.execute("BEGIN IMMEDIATE")
    try:
        columns = list(projection) + ["current_revision", "created_at", "updated_at"]
        values = list(projection.values()) + [1, timestamp, timestamp]
        conn.execute(
            f"INSERT INTO workflows ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
            values,
        )
        conn.execute(
            """
            INSERT INTO workflow_revisions (
                workflow_id, revision, dispatcher_id, definition_path, definition_revision,
                normalized_definition_json, definition_hash, actor, reason,
                effective_at, created_at
            ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                projection["workflow_id"], projection["dispatcher_id"], projection["definition_path"],
                projection["definition_revision"], projection["normalized_definition_json"],
                projection["definition_hash"], actor, reason, timestamp, timestamp,
            ),
        )
        event = append_event(
            conn,
            dispatcher_id=projection["dispatcher_id"],
            workflow_id=projection["workflow_id"],
            event_type="workflow_registered",
            payload={
                "definition_hash": projection["definition_hash"],
                "revision": 1,
                "reason": reason,
                "heartbeat_reconciliation": heartbeat_status,
            },
            actor=actor,
        )
        receipt = _workflow_configuration_receipt(
            conn,
            projection,
            action="registered",
            actor=actor,
            event=event,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {
        **result,
        "status": "registered",
        "event": event,
        "receipt": receipt,
        "definition_path": str(resolved),
    }


def revise_workflow(
    conn: Any,
    definition_path: str | Path,
    *,
    actor: str,
    reason: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    resolved, normalized, projection = prepare_definition(definition_path)
    current = conn.execute(
        "SELECT * FROM workflows WHERE workflow_id = ?", (projection["workflow_id"],)
    ).fetchone()
    if current is None:
        raise RegistryError("workflow does not exist; use register")
    if current["dispatcher_id"] != projection["dispatcher_id"]:
        raise RegistryError("a workflow cannot move between dispatchers")
    dispatcher = conn.execute(
        "SELECT * FROM dispatchers WHERE dispatcher_id = ?", (current["dispatcher_id"],)
    ).fetchone()
    allowed_route = dispatcher["default_reporting_task_id"] or dispatcher["expected_task_id"]
    if projection["reporting_task_id"] != allowed_route:
        raise RegistryError("workflow reporting task is outside the dispatcher route")
    errors = validate_definition(
        normalized,
        base_dir=resolved.parent,
        allowed_reporting_tasks=[allowed_route],
        require_existing_refs=True,
    )
    if errors:
        raise RegistryError("invalid workflow definition: " + "; ".join(errors))
    heartbeat_status = heartbeat_reconciliation(dispatcher)
    revision = int(current["current_revision"]) + 1
    if int(projection["definition_revision"]) <= int(current["definition_revision"]):
        raise RegistryError("definition revision must increase monotonically")
    if current["definition_hash"] == projection["definition_hash"]:
        raise RegistryError("definition bytes are unchanged")
    if dry_run:
        return {
            "status": "valid",
            "dry_run": True,
            "revision": revision,
            "previous_hash": current["definition_hash"],
            "heartbeat_reconciliation": heartbeat_status,
            **projection,
            "normalized_definition": normalized,
        }

    timestamp = _now()
    conn.execute("BEGIN IMMEDIATE")
    try:
        assignments = ",".join(f"{column} = ?" for column in projection if column != "workflow_id")
        conn.execute(
            f"UPDATE workflows SET {assignments}, current_revision = ?, updated_at = ? WHERE workflow_id = ?",
            [value for key, value in projection.items() if key != "workflow_id"]
            + [revision, timestamp, projection["workflow_id"]],
        )
        conn.execute(
            """
            INSERT INTO workflow_revisions (
                workflow_id, revision, dispatcher_id, definition_path, definition_revision,
                normalized_definition_json, definition_hash, actor, reason,
                effective_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                projection["workflow_id"], revision, projection["dispatcher_id"], projection["definition_path"],
                projection["definition_revision"], projection["normalized_definition_json"],
                projection["definition_hash"], actor, reason, timestamp, timestamp,
            ),
        )
        event = append_event(
            conn,
            dispatcher_id=projection["dispatcher_id"],
            workflow_id=projection["workflow_id"],
            event_type="workflow_revised",
            payload={
                "definition_hash": projection["definition_hash"],
                "previous_hash": current["definition_hash"],
                "revision": revision,
                "reason": reason,
                "heartbeat_reconciliation": heartbeat_status,
            },
            actor=actor,
        )
        receipt = _workflow_configuration_receipt(
            conn,
            projection,
            action="revised",
            actor=actor,
            event=event,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {
        "status": "revised",
        "revision": revision,
        "heartbeat_reconciliation": heartbeat_status,
        **projection,
        "event": event,
        "receipt": receipt,
        "definition_path": str(resolved),
    }


def set_workflow_enabled(
    conn: Any, workflow_id: str, *, enabled: bool, actor: str, reason: str
) -> dict[str, Any]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            """SELECT workflow_id, dispatcher_id, enabled, definition_hash, reporting_task_id
                 FROM workflows WHERE workflow_id = ?""",
            (workflow_id,),
        ).fetchone()
        if row is None:
            raise RegistryError(f"unknown workflow: {workflow_id}")
        if bool(row["enabled"]) == enabled:
            conn.rollback()
            return {
                "workflow_id": workflow_id,
                "enabled": enabled,
                "status": "already_enabled" if enabled else "already_disabled",
            }
        conn.execute(
            "UPDATE workflows SET enabled = ?, updated_at = ? WHERE workflow_id = ?",
            (int(enabled), _now(), workflow_id),
        )
        event = append_event(
            conn,
            dispatcher_id=row["dispatcher_id"],
            workflow_id=workflow_id,
            event_type="workflow_enabled" if enabled else "workflow_disabled",
            payload={"previous": bool(row["enabled"]), "enabled": enabled, "reason": reason},
            actor=actor,
        )
        receipt = _workflow_configuration_receipt(
            conn,
            row,
            action="enabled" if enabled else "disabled",
            actor=actor,
            event=event,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {
        "workflow_id": workflow_id,
        "enabled": enabled,
        "status": "updated",
        "event": event,
        "receipt": receipt,
    }


def list_workflows(conn: Any, dispatcher_id: str | None = None) -> list[dict[str, Any]]:
    if dispatcher_id:
        rows = conn.execute(
            "SELECT * FROM workflows WHERE dispatcher_id = ? ORDER BY workflow_id",
            (dispatcher_id,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM workflows ORDER BY dispatcher_id, workflow_id").fetchall()
    return [dict(row) for row in rows]

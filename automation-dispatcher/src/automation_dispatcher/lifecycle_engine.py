"""Durable, resumable, idempotent lifecycle state-machine primitives."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable, Mapping, Sequence

from .audit import append_event
from .lifecycle_artifacts import (
    LifecycleArtifact,
    ProgressRecordArtifact,
    SemanticDriftReportArtifact,
    atomic_write_artifact,
    load_artifact,
)
from .lifecycle_contracts import (
    HOST_ADAPTER_OPERATIONS,
    LIFECYCLE_STAGES,
    LifecycleContractError,
    canonical_json_bytes,
    content_hash,
    seal_artifact,
    validate_artifact,
    validate_transition,
)


class RecoveryDisposition(StrEnum):
    SAFE_RETRY = "safe_retry"
    ALREADY_APPLIED = "already_applied"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    INVALIDATED_PLAN = "invalidated_plan"
    BLOCKED_PREREQUISITE = "blocked_prerequisite"
    OPERATOR_DECISION_REQUIRED = "operator_decision_required"


@dataclass(frozen=True)
class StepPlan:
    operation_id: str
    step_id: str
    stage: str
    action: str
    collection_id: str | None
    reads: tuple[str, ...]
    writes: tuple[str, ...]
    host_requests: tuple[str, ...]
    approval_required: bool
    blockers: tuple[str, ...]
    next_action: dict[str, Any] | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "step_id": self.step_id,
            "stage": self.stage,
            "action": self.action,
            "collection_id": self.collection_id,
            "reads": list(self.reads),
            "writes": list(self.writes),
            "host_requests": list(self.host_requests),
            "approval_required": self.approval_required,
            "blockers": list(self.blockers),
            "next_action": self.next_action,
        }


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _stable_identifier(prefix: str, material: Mapping[str, Any]) -> str:
    digest = sha256(canonical_json_bytes(material)).hexdigest()
    return f"{prefix}-{digest[:32]}"


def deterministic_operation_id(plan_hash: str, stage: str) -> str:
    if stage not in LIFECYCLE_STAGES:
        raise LifecycleContractError(
            "unsupported_lifecycle_stage", f"unsupported lifecycle stage: {stage}"
        )
    return _stable_identifier("op", {"plan_hash": plan_hash, "stage": stage})


def deterministic_step_id(
    plan_hash: str, stage: str, action: str, collection_id: str | None = None
) -> str:
    if not action:
        raise LifecycleContractError("invalid_step_action", "lifecycle step action is required")
    return _stable_identifier(
        "step",
        {
            "plan_hash": plan_hash,
            "stage": stage,
            "action": action,
            "collection_id": collection_id,
        },
    )


def classify_recovery(
    *,
    status: str,
    plan_current: bool,
    prerequisites_satisfied: bool,
    effect_may_have_occurred: bool = False,
    observed_applied: bool = False,
    conflicting_observation: bool = False,
) -> RecoveryDisposition:
    if not plan_current:
        return RecoveryDisposition.INVALIDATED_PLAN
    if not prerequisites_satisfied:
        return RecoveryDisposition.BLOCKED_PREREQUISITE
    if conflicting_observation:
        return RecoveryDisposition.OPERATOR_DECISION_REQUIRED
    if observed_applied or status == "completed":
        return RecoveryDisposition.ALREADY_APPLIED
    if effect_may_have_occurred or status == "running":
        return RecoveryDisposition.RECONCILIATION_REQUIRED
    return RecoveryDisposition.SAFE_RETRY


_SEMANTIC_KEYS = frozenset(
    {
        "schedule",
        "schedule_json",
        "timezone",
        "timezone_name",
        "workflow_id",
        "workflow_ids",
        "definition_hash",
        "definition_id",
        "procedure_ref",
        "procedure_path",
        "authority",
        "authorities",
        "route",
        "route_hash",
        "destination_task_id",
        "expected_task_id",
        "expected_working_directory",
        "heartbeat_target",
        "heartbeat_schedule",
        "automation_id",
        "automation_state",
        "host_automation_state",
    }
)
_STAGE_PREREQUISITES = {
    "discover": (),
    "propose": ("discover",),
    "initialize": ("propose",),
    "shadow_validate": ("initialize",),
    "cut_over": ("shadow_validate",),
    "operate_evolve": ("cut_over",),
}


def _semantic_projection(value: Any) -> dict[str, list[Any]]:
    collected: dict[str, list[bytes]] = {}

    def visit(child_value: Any) -> None:
        if isinstance(child_value, Mapping):
            for key in sorted(child_value):
                child = child_value[key]
                if key in _SEMANTIC_KEYS:
                    encoded = canonical_json_bytes({"value": child})
                    collected.setdefault(key, []).append(encoded)
                visit(child)
        elif isinstance(child_value, list):
            for child in child_value:
                visit(child)

    visit(value)
    projected: dict[str, list[Any]] = {}
    for key, values in collected.items():
        projected[key] = [json.loads(item)["value"] for item in sorted(set(values))]
    return projected


def semantic_drift_report(
    plan: Mapping[str, Any],
    observed: Mapping[str, Any],
    *,
    generated_at: str | None = None,
) -> LifecycleArtifact:
    validate_artifact("lifecycle_plan", plan)
    observed_hash = str(observed.get("content_hash") or content_hash(observed))
    expected_projection = _semantic_projection(plan)
    observed_projection = _semantic_projection(observed)
    changes = []
    for field in sorted(set(expected_projection) | set(observed_projection)):
        expected_value = expected_projection.get(field)
        observed_value = observed_projection.get(field)
        if expected_value != observed_value:
            changes.append(
                {
                    "path": field,
                    "expected": expected_value,
                    "observed": observed_value,
                    "classification": (
                        "missing" if field not in observed_projection else
                        "unexpected" if field not in expected_projection else "changed"
                    ),
                }
            )
    report = seal_artifact(
        {
            "schema_version": 1,
            "artifact_type": "semantic_drift_report",
            "report_id": _stable_identifier(
                "drift",
                {
                    "plan_hash": plan["content_hash"],
                    "observed_source_hash": observed_hash,
                    "changes": changes,
                },
            ),
            "plan_id": plan["plan_id"],
            "plan_hash": plan["content_hash"],
            "expected_source_hash": plan["source_snapshot_hash"],
            "observed_source_hash": observed_hash,
            "changes": changes,
            "status": "drifted" if changes or plan["source_snapshot_hash"] != observed_hash else "unchanged",
            "generated_at": generated_at or utc_now(),
        }
    )
    return SemanticDriftReportArtifact.from_mapping(report)


def lifecycle_status(
    plan: Mapping[str, Any], progress: Sequence[Mapping[str, Any]] = ()
) -> dict[str, Any]:
    validate_artifact("lifecycle_plan", plan)
    validated = [validate_artifact("progress_record", item) for item in progress]
    for record in validated:
        if record["plan_id"] != plan["plan_id"] or record["plan_hash"] != plan["content_hash"]:
            raise LifecycleContractError(
                "progress_plan_conflict", "progress is not bound to the supplied plan"
            )
    by_step = {record["step_id"]: record for record in validated}
    statuses = [record["status"] for record in by_step.values()]
    if any(status == "blocked" for status in statuses):
        status = "blocked"
    elif any(status == "failed" for status in statuses):
        status = "failed"
    elif any(status == "running" for status in statuses):
        status = "in_progress"
    elif statuses and all(item == "completed" for item in statuses):
        status = "completed"
    else:
        status = "no_op"
    return {
        "status": status,
        "plan_id": plan["plan_id"],
        "plan_hash": plan["content_hash"],
        "steps": [by_step[key] for key in sorted(by_step)],
        "recovery": {
            key: classify_recovery(
                status=record["status"],
                plan_current=True,
                prerequisites_satisfied=True,
            ).value
            for key, record in sorted(by_step.items())
        },
        "stage_status": plan["stage_status"],
        "unresolved_decisions": list(plan["unresolved_decisions"]),
    }


def plan_step(
    plan: Mapping[str, Any],
    *,
    stage: str,
    action: str,
    collection_id: str | None = None,
    progress: Sequence[Mapping[str, Any]] = (),
) -> StepPlan:
    validate_artifact("lifecycle_plan", plan)
    if stage not in LIFECYCLE_STAGES:
        raise LifecycleContractError(
            "unsupported_lifecycle_stage", f"unsupported lifecycle stage: {stage}"
        )
    operation_id = deterministic_operation_id(plan["content_hash"], stage)
    step_id = deterministic_step_id(plan["content_hash"], stage, action, collection_id)
    completed = {
        item["step_id"]
        for item in progress
        if validate_artifact("progress_record", item)["status"] == "completed"
    }
    blockers = list(plan["unresolved_decisions"])
    blockers.extend(
        f"stage_prerequisite_incomplete:{required}"
        for required in _STAGE_PREREQUISITES[stage]
        if plan["stage_status"].get(required) not in {"completed", "reconciled"}
    )
    host_requests = tuple(
        operation.get("operation", "unknown")
        for operation in plan["expected_host_operations"]
        if isinstance(operation, Mapping)
    )
    unsupported = sorted(set(host_requests) - set(HOST_ADAPTER_OPERATIONS))
    blockers.extend(f"unsupported_host_operation:{item}" for item in unsupported)
    blockers.extend(
        f"host_capability_snapshot_required:{item}"
        for item in host_requests
        if item in HOST_ADAPTER_OPERATIONS
    )
    approval_required = stage in {"initialize", "cut_over"} or bool(host_requests)
    next_action = None
    if step_id in completed:
        next_action = {"type": "none", "reason": "step_already_completed"}
    elif blockers:
        next_action = {"type": "resolve_blockers", "count": len(blockers)}
    elif approval_required:
        next_action = {"type": "request_exact_approval", "stage": stage}
    else:
        next_action = {"type": "execute_local_step", "stage": stage}
    return StepPlan(
        operation_id=operation_id,
        step_id=step_id,
        stage=stage,
        action=action,
        collection_id=collection_id,
        reads=("plan", "progress", "source_and_host_assumptions"),
        writes=("progress_record",) if step_id not in completed else (),
        host_requests=host_requests,
        approval_required=approval_required,
        blockers=tuple(blockers),
        next_action=next_action,
    )


def make_progress_record(
    plan: Mapping[str, Any],
    *,
    stage: str,
    action: str,
    actor: str,
    status: str,
    collection_id: str | None = None,
    started_at: str | None = None,
    updated_at: str | None = None,
    evidence: Sequence[str] = (),
    dispatcher_id: str | None = None,
    workflow_id: str | None = None,
    event_id: int | None = None,
    receipt_id: str | None = None,
) -> LifecycleArtifact:
    validate_artifact("lifecycle_plan", plan)
    instant = started_at or utc_now()
    record = seal_artifact(
        {
            "schema_version": 1,
            "artifact_type": "progress_record",
            "operation_id": deterministic_operation_id(plan["content_hash"], stage),
            "plan_id": plan["plan_id"],
            "plan_hash": plan["content_hash"],
            "stage": stage,
            "step_id": deterministic_step_id(plan["content_hash"], stage, action, collection_id),
            "status": status,
            "started_at": instant,
            "updated_at": updated_at or instant,
            "actor": actor,
            "evidence": list(evidence),
            "dispatcher_id": dispatcher_id,
            "workflow_id": workflow_id,
            "event_id": event_id,
            "receipt_id": receipt_id,
        }
    )
    return ProgressRecordArtifact.from_mapping(record)


def persist_progress(
    path: str | Path,
    record: LifecycleArtifact,
    *,
    plan: Mapping[str, Any],
    actor: str,
    connection: sqlite3.Connection,
    dispatcher_id: str,
    expected_dispatcher_revision: int,
    expected_dispatcher_config_hash: str,
    source_root: str | Path,
    installed_roots: tuple[str | Path, ...] = (),
    expected_content_hash: str | None = None,
    before_replace: Callable[[Path], None] | None = None,
) -> dict[str, Any]:
    """Persist audited progress inside an active caller-owned SQLite transaction.

    The helper is transaction-neutral: the caller must commit after success or roll back
    after failure. A savepoint removes the newly appended event if the external atomic
    write fails. A completed replay resolves the original event and never appends again.
    """

    validate_artifact("lifecycle_plan", plan)
    validate_artifact("progress_record", record.data)
    if record.data["plan_id"] != plan["plan_id"] or record.data["plan_hash"] != plan["content_hash"]:
        raise LifecycleContractError(
            "progress_plan_conflict", "progress is not bound to the supplied plan"
        )
    if record.data["dispatcher_id"] not in {None, dispatcher_id}:
        raise LifecycleContractError(
            "progress_dispatcher_conflict", "progress is bound to another dispatcher"
        )
    if not connection.in_transaction:
        raise LifecycleContractError(
            "audit_transaction_required",
            "audited progress persistence requires an active caller-owned transaction",
        )
    assert_registry_progress_current(
        connection,
        dispatcher_id,
        expected_revision=expected_dispatcher_revision,
        expected_config_hash=expected_dispatcher_config_hash,
    )
    resolved = Path(path).expanduser().resolve(strict=False)
    if resolved.exists():
        current = load_artifact(
            resolved,
            "progress_record",
            source_root=source_root,
            installed_roots=installed_roots,
        )
        if current.data["step_id"] != record.data["step_id"]:
            raise LifecycleContractError(
                "progress_step_conflict", "progress path already belongs to another step"
            )
        if current.data["status"] == "completed":
            audit_material = dict(current.data)
            audit_material["event_id"] = None
            audit_material = seal_artifact(audit_material)
            event = _progress_event(
                connection,
                dispatcher_id=dispatcher_id,
                plan_id=plan["plan_id"],
                step_id=current.data["step_id"],
                progress_hash=audit_material["content_hash"],
                event_id=current.data["event_id"],
            )
            if event is None:
                raise LifecycleContractError(
                    "progress_audit_missing",
                    "completed progress has no matching immutable audit event",
                    step_id=current.data["step_id"],
                    progress_hash=current.content_hash,
                )
            return {
                "status": "already_applied",
                "record": current.as_dict(),
                "event_id": event["event_id"],
                "event_hash": event["event_hash"],
            }
        if expected_content_hash is None:
            raise LifecycleContractError(
                "optimistic_concurrency_required",
                "updating progress requires the previously observed content hash",
            )
    savepoint = "lifecycle_progress_persist"
    connection.execute(f"SAVEPOINT {savepoint}")
    try:
        event = append_lifecycle_event(
            connection,
            dispatcher_id=dispatcher_id,
            plan=plan,
            record=record.data,
            actor=actor,
        )
        audited_data = dict(record.data)
        audited_data["event_id"] = event["event_id"]
        audited_record = ProgressRecordArtifact.from_mapping(seal_artifact(audited_data))
        atomic_write_artifact(
            resolved,
            audited_record,
            source_root=source_root,
            installed_roots=installed_roots,
            expected_content_hash=expected_content_hash,
            before_replace=before_replace,
        )
        connection.execute(f"RELEASE SAVEPOINT {savepoint}")
    except Exception:
        connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        connection.execute(f"RELEASE SAVEPOINT {savepoint}")
        raise
    return {
        "status": "persisted",
        "record": audited_record.as_dict(),
        "event_id": event["event_id"],
        "event_hash": event["event_hash"],
        "transaction_pending": True,
    }


def _progress_event(
    connection: sqlite3.Connection,
    *,
    dispatcher_id: str,
    plan_id: str,
    step_id: str,
    progress_hash: str,
    event_id: int | None,
) -> dict[str, Any] | None:
    if event_id is not None:
        rows = connection.execute(
            "SELECT event_id, event_hash, payload_json FROM audit_events "
            "WHERE dispatcher_id = ? AND event_type = 'lifecycle_transition' "
            "AND event_id = ?",
            (dispatcher_id, event_id),
        ).fetchall()
    else:
        rows = connection.execute(
            "SELECT event_id, event_hash, payload_json FROM audit_events "
            "WHERE dispatcher_id = ? AND event_type = 'lifecycle_transition' "
            "ORDER BY event_id DESC",
            (dispatcher_id,),
        ).fetchall()
    for row in rows:
        payload = json.loads(row["payload_json"])
        if (
            payload.get("plan_id") == plan_id
            and payload.get("step_id") == step_id
            and payload.get("progress_hash") == progress_hash
        ):
            return {"event_id": row["event_id"], "event_hash": row["event_hash"]}
    return None


def verify_progress_audit_binding(
    connection: sqlite3.Connection,
    progress: Mapping[str, Any],
    *,
    dispatcher_id: str,
) -> dict[str, Any]:
    """Verify a sealed progress record against its exact immutable audit event."""

    try:
        record = validate_artifact("progress_record", progress)
    except LifecycleContractError as exc:
        return {
            "valid": False,
            "errors": [{"error": exc.code, "message": str(exc)}],
            "event_id": progress.get("event_id"),
            "event_hash": None,
            "progress_hash": None,
        }
    errors: list[dict[str, Any]] = []
    if record["dispatcher_id"] != dispatcher_id:
        errors.append({
            "error": "dispatcher_mismatch",
            "expected": dispatcher_id,
            "observed": record["dispatcher_id"],
        })
    event_id = record["event_id"]
    if event_id is None:
        errors.append({"error": "event_id_missing"})
        row = None
    else:
        row = connection.execute(
            "SELECT event_id,event_hash,workflow_id,actor,payload_json "
            "FROM audit_events WHERE dispatcher_id = ? "
            "AND event_type = 'lifecycle_transition' AND event_id = ?",
            (dispatcher_id, event_id),
        ).fetchone()
        if row is None:
            errors.append({"error": "audit_event_missing", "event_id": event_id})
    audit_material = dict(record)
    audit_material["event_id"] = None
    progress_hash = seal_artifact(audit_material)["content_hash"]
    event_hash = None
    if row is not None:
        event_hash = row["event_hash"]
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError):
            payload = None
            errors.append({"error": "audit_payload_invalid"})
        expected_payload = {
            "plan_id": record["plan_id"],
            "plan_hash": record["plan_hash"],
            "operation_id": record["operation_id"],
            "step_id": record["step_id"],
            "stage": record["stage"],
            "status": record["status"],
            "progress_hash": progress_hash,
        }
        if payload != expected_payload:
            errors.append({
                "error": "audit_payload_mismatch",
                "expected": expected_payload,
                "observed": payload,
            })
        if row["workflow_id"] != record["workflow_id"]:
            errors.append({"error": "audit_workflow_mismatch"})
        if row["actor"] != record["actor"]:
            errors.append({"error": "audit_actor_mismatch"})
    return {
        "valid": not errors,
        "errors": errors,
        "event_id": event_id,
        "event_hash": event_hash,
        "progress_hash": progress_hash,
    }


def assert_registry_progress_current(
    connection: sqlite3.Connection,
    dispatcher_id: str,
    *,
    expected_revision: int,
    expected_config_hash: str,
) -> None:
    """Fence progress writes to the currently observed immutable dispatcher revision."""

    row = connection.execute(
        "SELECT dispatcher.current_revision, revision.config_hash "
        "FROM dispatchers AS dispatcher "
        "JOIN dispatcher_revisions AS revision "
        "ON revision.dispatcher_id = dispatcher.dispatcher_id "
        "AND revision.revision = dispatcher.current_revision "
        "WHERE dispatcher.dispatcher_id = ?",
        (dispatcher_id,),
    ).fetchone()
    if row is None:
        raise LifecycleContractError(
            "registry_dispatcher_missing", "dispatcher registry state is missing"
        )
    if row["current_revision"] != expected_revision or row["config_hash"] != expected_config_hash:
        raise LifecycleContractError(
            "registry_progress_conflict",
            "dispatcher registry state changed after progress was planned",
            expected_revision=expected_revision,
            observed_revision=row["current_revision"],
            expected_config_hash=expected_config_hash,
            observed_config_hash=row["config_hash"],
        )


def append_lifecycle_event(
    connection: sqlite3.Connection,
    *,
    dispatcher_id: str,
    plan: Mapping[str, Any],
    record: Mapping[str, Any],
    actor: str,
) -> dict[str, Any]:
    """Bind one material lifecycle transition to the immutable runtime audit chain."""

    validate_artifact("lifecycle_plan", plan)
    validate_artifact("progress_record", record)
    if record["plan_id"] != plan["plan_id"] or record["plan_hash"] != plan["content_hash"]:
        raise LifecycleContractError(
            "progress_plan_conflict", "progress is not bound to the supplied plan"
        )
    return append_event(
        connection,
        dispatcher_id,
        "lifecycle_transition",
        {
            "plan_id": plan["plan_id"],
            "plan_hash": plan["content_hash"],
            "operation_id": record["operation_id"],
            "step_id": record["step_id"],
            "stage": record["stage"],
            "status": record["status"],
            "progress_hash": record["content_hash"],
        },
        workflow_id=record["workflow_id"],
        actor=actor,
    )


def assert_stage_transition(current: str, target: str, *, blocked: bool = False) -> None:
    if blocked:
        raise LifecycleContractError(
            "blocked_prerequisite", "blocked lifecycle state cannot advance"
        )
    validate_transition(current, target)

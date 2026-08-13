from __future__ import annotations

import json
from pathlib import Path

import pytest

from automation_dispatcher.audit import verify_audit_chain
from automation_dispatcher.cli import main
from automation_dispatcher.database import connect
from automation_dispatcher.lifecycle_artifacts import (
    ARTIFACT_MODELS,
    SchemaDisposition,
    atomic_write_artifact,
    classify_schema_version,
    load_artifact,
    model_for,
    sanitized_export,
)
from automation_dispatcher.lifecycle_contracts import (
    LifecycleContractError,
    contract_schema,
    seal_artifact,
)
from automation_dispatcher.lifecycle_engine import (
    RecoveryDisposition,
    assert_registry_progress_current,
    assert_stage_transition,
    classify_recovery,
    deterministic_operation_id,
    deterministic_step_id,
    lifecycle_status,
    make_progress_record,
    persist_progress,
    plan_step,
    semantic_drift_report,
)


HASH = "0" * 64
NOW = "2026-08-13T12:00:00Z"
SOURCE_ROOT = Path(__file__).parents[1]


def _minimal(schema: dict) -> object:
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    declared = schema.get("type", "object")
    kind = declared[0] if isinstance(declared, list) else declared
    if kind == "object":
        properties = schema.get("properties", {})
        return {name: _minimal(properties[name]) for name in schema.get("required", ())}
    if kind == "array":
        return [_minimal(schema.get("items", {}))] if schema.get("minItems", 0) else []
    if kind == "boolean":
        return True
    if kind in {"integer", "number"}:
        return 1
    if kind == "null":
        return None
    if schema.get("format") == "date-time":
        return NOW
    if schema.get("pattern") == "^[0-9a-f]{64}$":
        return HASH
    return "value"


def _artifact(artifact_type: str) -> dict:
    value = _minimal(contract_schema(artifact_type))
    assert isinstance(value, dict)
    return seal_artifact(value)


def _snapshot(**scope: object) -> dict:
    snapshot = _artifact("discovery_snapshot")
    snapshot.update(
        snapshot_id="snapshot-p2",
        scope={
            "schedule": "0 6 * * *",
            "timezone": "America/Chicago",
            "route": "task-1",
            **scope,
        },
        tasks=[{"workflow_id": "workflow-1", "definition_hash": HASH}],
    )
    return seal_artifact(snapshot)


def _plan(snapshot: dict | None = None) -> dict:
    source = snapshot or _snapshot()
    plan = _artifact("lifecycle_plan")
    plan.update(
        plan_id="plan-p2",
        source_snapshot_id=source["snapshot_id"],
        source_snapshot_hash=source["content_hash"],
        collections=[
            {
                "collection_id": "collection-1",
                "schedule": "0 6 * * *",
                "timezone": "America/Chicago",
                "route": "task-1",
            }
        ],
        workflow_mappings=[{"workflow_id": "workflow-1", "definition_hash": HASH}],
        unresolved_decisions=[],
        expected_cli_operations=[{"operation": "init"}],
        expected_host_operations=[],
        stage_status={"discover": "completed", "propose": "completed"},
    )
    return seal_artifact(plan)


def _invoke(capsys, *arguments: str) -> tuple[int, dict, str]:
    code = main(list(arguments))
    captured = capsys.readouterr()
    raw = captured.out or captured.err
    return code, json.loads(raw), raw


def _write(path: Path, artifact: dict) -> None:
    path.write_text(json.dumps(artifact), encoding="utf-8")


def _initialize_registry(tmp_path: Path, capsys) -> tuple[Path, dict]:
    database = tmp_path / "dispatcher.sqlite3"
    schedule = {"version": 2, "kind": "cron", "expression": "0 6 * * *"}
    code, _, _ = _invoke(
        capsys,
        "--database", str(database), "--json", "init",
        "--dispatcher-id", "collection-1", "--name", "Collection",
        "--description", "Lifecycle audit fixture", "--schedule", json.dumps(schedule),
        "--max-lateness-seconds", "3600",
        "--catch-up", json.dumps({"policy": "latest", "max_lookback_seconds": 86400}),
        "--expected-task-id", "task-1", "--expected-working-directory", str(tmp_path),
        "--timezone", "America/Chicago",
        "--heartbeat-schedule", json.dumps({"verified": True, "schedule": schedule}),
        "--actor", "test", "--reason", "audit fixture",
    )
    assert code == 0
    connection = connect(database)
    try:
        row = connection.execute(
            "SELECT dispatcher.current_revision, revision.config_hash "
            "FROM dispatchers AS dispatcher JOIN dispatcher_revisions AS revision "
            "ON revision.dispatcher_id = dispatcher.dispatcher_id "
            "AND revision.revision = dispatcher.current_revision "
            "WHERE dispatcher.dispatcher_id = 'collection-1'"
        ).fetchone()
        return database, dict(row)
    finally:
        connection.close()


def test_all_contracts_have_typed_versioned_models() -> None:
    assert set(ARTIFACT_MODELS) == set(json.loads(
        (SOURCE_ROOT / "src/automation_dispatcher/contracts/v1/catalog.json").read_text()
    )["artifacts"])
    for artifact_type in ARTIFACT_MODELS:
        artifact = _artifact(artifact_type)
        typed = model_for(artifact_type).from_mapping(artifact)
        assert typed.as_dict() == artifact
        assert typed.content_hash == artifact["content_hash"]


def test_schema_evolution_classifies_current_future_older_and_corrupt() -> None:
    assert classify_schema_version({"schema_version": 1}).disposition is SchemaDisposition.CURRENT
    future = classify_schema_version({"schema_version": 2})
    assert future.disposition is SchemaDisposition.UNSUPPORTED_FUTURE
    older = classify_schema_version({"schema_version": 0})
    assert older.disposition is SchemaDisposition.MIGRATION_REQUIRED
    assert older.migration_supported is False
    supported = classify_schema_version(
        {"schema_version": 0}, supported_upgrade_versions=frozenset({0})
    )
    assert supported.disposition is SchemaDisposition.UPGRADE_SUPPORTED
    assert supported.migration_supported is True
    assert classify_schema_version({"schema_version": "1"}).disposition is SchemaDisposition.CORRUPT


def test_atomic_io_round_trip_permissions_and_optimistic_concurrency(tmp_path: Path) -> None:
    plan = model_for("lifecycle_plan").from_mapping(_plan())
    destination = tmp_path / "plan.json"
    atomic_write_artifact(destination, plan, source_root=SOURCE_ROOT)
    assert load_artifact(destination, "lifecycle_plan", source_root=SOURCE_ROOT).as_dict() == plan.as_dict()
    assert destination.stat().st_mode & 0o777 == 0o600

    changed = dict(plan.data)
    changed["actor"] = "new-actor"
    changed = model_for("lifecycle_plan").from_mapping(seal_artifact(changed))
    with pytest.raises(LifecycleContractError, match="changed since") as caught:
        atomic_write_artifact(
            destination,
            changed,
            source_root=SOURCE_ROOT,
            expected_content_hash=HASH,
        )
    assert caught.value.code == "optimistic_concurrency_conflict"
    assert load_artifact(destination, "lifecycle_plan", source_root=SOURCE_ROOT).content_hash == plan.content_hash


def test_atomic_io_injected_failure_never_publishes_partial_file(tmp_path: Path) -> None:
    destination = tmp_path / "plan.json"

    def fail_before_replace(_: Path) -> None:
        raise RuntimeError("injected crash")

    with pytest.raises(RuntimeError, match="injected crash"):
        atomic_write_artifact(
            destination,
            model_for("lifecycle_plan").from_mapping(_plan()),
            source_root=SOURCE_ROOT,
            before_replace=fail_before_replace,
        )
    assert not destination.exists()
    assert not list(tmp_path.glob(".*.tmp"))

    original = model_for("lifecycle_plan").from_mapping(_plan())
    atomic_write_artifact(destination, original, source_root=SOURCE_ROOT)
    changed = dict(original.data)
    changed["actor"] = "changed"
    changed = model_for("lifecycle_plan").from_mapping(seal_artifact(changed))
    with pytest.raises(RuntimeError):
        atomic_write_artifact(
            destination,
            changed,
            source_root=SOURCE_ROOT,
            expected_content_hash=original.content_hash,
            before_replace=fail_before_replace,
        )
    assert load_artifact(destination, "lifecycle_plan", source_root=SOURCE_ROOT).content_hash == original.content_hash

    def fail_after_replace(_: Path) -> None:
        raise RuntimeError("injected post-write crash")

    with pytest.raises(RuntimeError, match="post-write"):
        atomic_write_artifact(
            destination,
            changed,
            source_root=SOURCE_ROOT,
            expected_content_hash=original.content_hash,
            after_replace=fail_after_replace,
        )
    assert load_artifact(destination, "lifecycle_plan", source_root=SOURCE_ROOT).content_hash == changed.content_hash


def test_atomic_io_rejects_forbidden_and_symlink_paths(tmp_path: Path) -> None:
    plan = model_for("lifecycle_plan").from_mapping(_plan())
    with pytest.raises(LifecycleContractError) as forbidden:
        atomic_write_artifact(SOURCE_ROOT / "unsafe-plan.json", plan, source_root=SOURCE_ROOT)
    assert forbidden.value.code == "forbidden_artifact_path"

    external = tmp_path / "external"
    external.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(external, target_is_directory=True)
    with pytest.raises(LifecycleContractError) as symlinked:
        atomic_write_artifact(linked / "plan.json", plan, source_root=SOURCE_ROOT)
    assert symlinked.value.code == "symlink_artifact_path"


def test_sanitized_exports_are_allowlisted_and_redact_local_paths(tmp_path: Path) -> None:
    report = _artifact("readiness_report")
    report.update(
        report_id="report-1",
        plan_id="plan-p2",
        collection_id="collection-1",
        checks=[
            {
                "check_id": "path",
                "paths": [
                    str(tmp_path / "private.json"),
                    r"C:\Users\operator\private.json",
                    r"\\server\share\private.json",
                    "~/private.json",
                ],
            }
        ],
        blockers=[],
        unresolved_decisions=[],
        tested_occurrence_boundary={"scheduled_for": NOW},
        status="ready",
    )
    report = seal_artifact(report)
    exported = sanitized_export(report).as_dict()
    assert set(exported) == {
        "schema_version", "artifact_type", "report_id", "plan_id", "plan_hash",
        "collection_id", "generated_at", "checks", "blockers", "unresolved_decisions",
        "tested_occurrence_boundary", "status", "content_hash",
    }
    assert str(tmp_path) not in json.dumps(exported)
    assert all(
        value.startswith("[local-path:")
        for value in exported["checks"][0]["paths"]
    )
    with pytest.raises(LifecycleContractError) as unavailable:
        sanitized_export(_plan())
    assert unavailable.value.code == "artifact_not_exportable"


def test_deterministic_ids_and_recovery_classification() -> None:
    plan_hash = _plan()["content_hash"]
    assert deterministic_operation_id(plan_hash, "initialize") == deterministic_operation_id(
        plan_hash, "initialize"
    )
    assert deterministic_step_id(plan_hash, "initialize", "create", "c1") != deterministic_step_id(
        plan_hash, "initialize", "create", "c2"
    )
    assert classify_recovery(status="failed", plan_current=False, prerequisites_satisfied=True) is RecoveryDisposition.INVALIDATED_PLAN
    assert classify_recovery(status="blocked", plan_current=True, prerequisites_satisfied=False) is RecoveryDisposition.BLOCKED_PREREQUISITE
    assert classify_recovery(status="completed", plan_current=True, prerequisites_satisfied=True) is RecoveryDisposition.ALREADY_APPLIED
    assert classify_recovery(status="running", plan_current=True, prerequisites_satisfied=True) is RecoveryDisposition.RECONCILIATION_REQUIRED
    assert classify_recovery(status="failed", plan_current=True, prerequisites_satisfied=True) is RecoveryDisposition.SAFE_RETRY


def test_progress_is_resumable_idempotent_and_hash_fenced(tmp_path: Path, capsys) -> None:
    database, revision = _initialize_registry(tmp_path, capsys)
    plan = _plan()
    path = tmp_path / "progress.json"
    running = make_progress_record(
        plan, stage="initialize", action="create-state", actor="agent", status="running",
        started_at=NOW,
    )
    connection = connect(database)
    try:
        common = {
            "plan": plan,
            "actor": "agent",
            "connection": connection,
            "dispatcher_id": "collection-1",
            "expected_dispatcher_revision": revision["current_revision"],
            "expected_dispatcher_config_hash": revision["config_hash"],
            "source_root": SOURCE_ROOT,
        }
        with pytest.raises(LifecycleContractError) as transaction:
            persist_progress(path, running, **common)
        assert transaction.value.code == "audit_transaction_required"

        connection.execute("BEGIN IMMEDIATE")
        persisted = persist_progress(path, running, **common)
        connection.commit()
        assert persisted["status"] == "persisted"
        assert persisted["event_id"]
        assert persisted["event_hash"]
        assert persisted["record"]["event_id"] == persisted["event_id"]

        completed = make_progress_record(
            plan, stage="initialize", action="create-state", actor="agent", status="completed",
            started_at=NOW, updated_at="2026-08-13T12:01:00Z",
        )
        connection.execute("BEGIN IMMEDIATE")
        with pytest.raises(LifecycleContractError) as missing_fence:
            persist_progress(path, completed, **common)
        assert missing_fence.value.code == "optimistic_concurrency_required"
        connection.rollback()

        current = load_artifact(path, "progress_record", source_root=SOURCE_ROOT)
        connection.execute("BEGIN IMMEDIATE")
        completed_result = persist_progress(
            path, completed, expected_content_hash=current.content_hash, **common
        )
        connection.commit()
        assert completed_result["event_id"] != persisted["event_id"]
        assert completed_result["record"]["event_id"] == completed_result["event_id"]

        event_count = connection.execute(
            "SELECT COUNT(*) FROM audit_events WHERE dispatcher_id = 'collection-1'"
        ).fetchone()[0]
        connection.execute("BEGIN IMMEDIATE")
        replay = persist_progress(path, running, **common)
        connection.commit()
        assert replay["status"] == "already_applied"
        assert replay["event_id"] == completed_result["event_id"]
        assert connection.execute(
            "SELECT COUNT(*) FROM audit_events WHERE dispatcher_id = 'collection-1'"
        ).fetchone()[0] == event_count
    finally:
        connection.close()


def test_lifecycle_state_machine_status_step_planning_and_transitions() -> None:
    plan = _plan()
    completed = make_progress_record(
        plan, stage="propose", action="normalize", actor="agent", status="completed", started_at=NOW
    ).as_dict()
    assert lifecycle_status(plan, [completed])["status"] == "completed"
    step = plan_step(plan, stage="propose", action="normalize", progress=[completed])
    assert step.writes == ()
    assert step.next_action == {"type": "none", "reason": "step_already_completed"}
    assert_stage_transition("discover", "propose")
    with pytest.raises(LifecycleContractError) as skip:
        assert_stage_transition("discover", "cut_over")
    assert skip.value.code == "illegal_lifecycle_transition"
    with pytest.raises(LifecycleContractError) as blocked:
        assert_stage_transition("propose", "initialize", blocked=True)
    assert blocked.value.code == "blocked_prerequisite"

    prerequisite_plan = dict(plan)
    prerequisite_plan["stage_status"] = {"discover": "completed"}
    prerequisite_plan = seal_artifact(prerequisite_plan)
    prerequisite = plan_step(
        prerequisite_plan, stage="shadow_validate", action="validate"
    )
    assert "stage_prerequisite_incomplete:initialize" in prerequisite.blockers

    host_plan = dict(plan)
    host_plan["expected_host_operations"] = [{"operation": "tasks.read"}]
    host_plan = seal_artifact(host_plan)
    host_step = plan_step(host_plan, stage="cut_over", action="host-cutover")
    assert "host_capability_snapshot_required:tasks.read" in host_step.blockers


def test_semantic_drift_is_deterministic_and_stale_changes_block() -> None:
    snapshot = _snapshot()
    plan = _plan(snapshot)
    unchanged = semantic_drift_report(plan, snapshot, generated_at=NOW).as_dict()
    repeated = semantic_drift_report(plan, snapshot, generated_at=NOW).as_dict()
    assert repeated == unchanged
    assert unchanged["status"] == "unchanged"
    changed_snapshot = _snapshot(timezone="UTC")
    changed = semantic_drift_report(plan, changed_snapshot, generated_at=NOW).as_dict()
    assert changed["status"] == "drifted"
    assert changed["changes"]


def test_material_lifecycle_transition_is_audit_chained(tmp_path: Path, capsys) -> None:
    database, revision = _initialize_registry(tmp_path, capsys)
    plan = _plan()
    record = make_progress_record(
        plan, stage="initialize", action="create-state", actor="agent", status="completed",
        started_at=NOW, dispatcher_id="collection-1",
    )
    progress_path = tmp_path / "audited-progress.json"
    connection = connect(database)
    try:
        connection.execute("BEGIN IMMEDIATE")
        persisted = persist_progress(
            progress_path,
            record,
            plan=plan,
            actor="agent",
            connection=connection,
            dispatcher_id="collection-1",
            expected_dispatcher_revision=revision["current_revision"],
            expected_dispatcher_config_hash=revision["config_hash"],
            source_root=SOURCE_ROOT,
        )
        connection.commit()
        assert persisted["event_id"]
        assert persisted["event_hash"]
        persisted_record = load_artifact(
            progress_path, "progress_record", source_root=SOURCE_ROOT
        )
        assert persisted_record.data["event_id"] == persisted["event_id"]
        assert persisted_record.content_hash == persisted["record"]["content_hash"]
        verification = verify_audit_chain(connection, "collection-1")
        assert verification["valid"] is True
        assert verification["event_count"] >= 2
        assert_registry_progress_current(
            connection,
            "collection-1",
            expected_revision=revision["current_revision"],
            expected_config_hash=revision["config_hash"],
        )
        with pytest.raises(LifecycleContractError) as stale_registry:
            assert_registry_progress_current(
                connection,
                "collection-1",
                expected_revision=revision["current_revision"] + 1,
                expected_config_hash=revision["config_hash"],
            )
        assert stale_registry.value.code == "registry_progress_conflict"

        failure_path = tmp_path / "failed-progress.json"
        failed_record = make_progress_record(
            plan, stage="initialize", action="failing-write", actor="agent", status="running",
            started_at=NOW, dispatcher_id="collection-1",
        )
        before_failure = connection.execute(
            "SELECT COUNT(*) FROM audit_events WHERE dispatcher_id = 'collection-1'"
        ).fetchone()[0]
        connection.execute("BEGIN IMMEDIATE")
        with pytest.raises(RuntimeError, match="injected"):
            persist_progress(
                failure_path,
                failed_record,
                plan=plan,
                actor="agent",
                connection=connection,
                dispatcher_id="collection-1",
                expected_dispatcher_revision=revision["current_revision"],
                expected_dispatcher_config_hash=revision["config_hash"],
                source_root=SOURCE_ROOT,
                before_replace=lambda _: (_ for _ in ()).throw(RuntimeError("injected")),
            )
        assert connection.execute(
            "SELECT COUNT(*) FROM audit_events WHERE dispatcher_id = 'collection-1'"
        ).fetchone()[0] == before_failure
        connection.rollback()
        assert not failure_path.exists()

        rollback_path = tmp_path / "rolled-back-progress.json"
        rollback_record = make_progress_record(
            plan, stage="initialize", action="caller-rollback", actor="agent",
            status="completed", started_at=NOW, dispatcher_id="collection-1",
        )
        connection.execute("BEGIN IMMEDIATE")
        persist_progress(
            rollback_path,
            rollback_record,
            plan=plan,
            actor="agent",
            connection=connection,
            dispatcher_id="collection-1",
            expected_dispatcher_revision=revision["current_revision"],
            expected_dispatcher_config_hash=revision["config_hash"],
            source_root=SOURCE_ROOT,
        )
        connection.rollback()
        assert rollback_path.exists()
        connection.execute("BEGIN IMMEDIATE")
        with pytest.raises(LifecycleContractError) as missing_audit:
            persist_progress(
                rollback_path,
                rollback_record,
                plan=plan,
                actor="agent",
                connection=connection,
                dispatcher_id="collection-1",
                expected_dispatcher_revision=revision["current_revision"],
                expected_dispatcher_config_hash=revision["config_hash"],
                source_root=SOURCE_ROOT,
            )
        assert missing_audit.value.code == "progress_audit_missing"
        connection.rollback()
    finally:
        connection.close()


def test_lifecycle_cli_success_no_op_stale_invalid_partial_and_dry_run(
    tmp_path: Path, capsys
) -> None:
    snapshot = _snapshot()
    plan = _plan(snapshot)
    plan_path = tmp_path / "plan.json"
    snapshot_path = tmp_path / "snapshot.json"
    _write(plan_path, plan)
    _write(snapshot_path, snapshot)
    common = ("--json", "lifecycle")
    path_args = ("--source-root", str(SOURCE_ROOT), "--state-root", str(tmp_path))

    code, validated, _ = _invoke(
        capsys, *common, "plan", "--artifact-type", "lifecycle_plan", "--input", str(plan_path),
        "--actor", "agent", "--reason", "validate", *path_args,
    )
    assert code == 0
    assert validated["status"] == "completed"
    assert validated["identity"]["normalized"] == plan

    code, explained, _ = _invoke(
        capsys, *common, "explain", "--plan", str(plan_path), "--actor", "agent",
        "--reason", "explain", *path_args,
    )
    assert code == 0
    assert explained["identity"]["plan_id"] == "plan-p2"

    completed = make_progress_record(
        plan, stage="propose", action="normalize", actor="agent", status="completed", started_at=NOW
    ).as_dict()
    progress_path = tmp_path / "progress.json"
    _write(progress_path, completed)
    before_dry_run = {
        path.name: path.read_bytes() for path in tmp_path.iterdir() if path.is_file()
    }
    code, applied, _ = _invoke(
        capsys, *common, "apply", "--plan", str(plan_path), "--progress", str(progress_path),
        "--stage", "propose", "--action", "normalize", "--dry-run", "--actor", "agent",
        "--reason", "plan apply", *path_args,
    )
    assert code == 0
    assert applied["status"] == "no_op"
    assert applied["identity"]["step_plan"]["mutation_count"] == 0
    assert {
        path.name: path.read_bytes() for path in tmp_path.iterdir() if path.is_file()
    } == before_dry_run

    running = make_progress_record(
        plan, stage="initialize", action="create-state", actor="agent", status="running",
        started_at=NOW,
    ).as_dict()
    running_path = tmp_path / "running-progress.json"
    _write(running_path, running)
    code, partial, _ = _invoke(
        capsys, *common, "status", "--plan", str(plan_path), "--progress", str(running_path),
        "--actor", "agent", "--reason", "resume status", *path_args,
    )
    assert code == 0
    assert partial["status"] == "in_progress"
    assert partial["next_action"]["type"] == "reconcile_progress"
    assert "reconciliation_required" in partial["identity"]["recovery"].values()

    changed_snapshot = _snapshot(timezone="UTC")
    changed_snapshot_path = tmp_path / "changed-snapshot.json"
    _write(changed_snapshot_path, changed_snapshot)
    code, stale, _ = _invoke(
        capsys, *common, "verify", "--plan", str(plan_path), "--observed", str(changed_snapshot_path),
        "--observed-type", "discovery_snapshot", "--actor", "agent", "--reason", "verify",
        *path_args,
    )
    assert code == 1
    assert stale["status"] == "conflict"
    assert stale["next_action"]["type"] == "rediscover_and_replan"

    code, invalid_apply, _ = _invoke(
        capsys, *common, "apply", "--plan", str(plan_path), "--stage", "propose",
        "--action", "normalize", "--actor", "agent", "--reason", "must be dry", *path_args,
    )
    assert code == 2
    assert invalid_apply["error"]["code"] == "dry_run_required"

    tampered = dict(plan)
    tampered["actor"] = "tampered"
    _write(plan_path, tampered)
    code, invalid, _ = _invoke(
        capsys, *common, "status", "--plan", str(plan_path), "--actor", "agent",
        "--reason", "status", *path_args,
    )
    assert code == 2
    assert invalid["error"]["code"] == "content_hash_mismatch"
    assert invalid["artifact_type"] == "command_result"
    assert invalid["identity"]["cli_version"]


def test_lifecycle_cli_unsupported_and_forbidden_paths_are_structured(tmp_path: Path, capsys) -> None:
    future = _plan()
    future["schema_version"] = 2
    future_path = tmp_path / "future.json"
    _write(future_path, future)
    common = ("--json", "lifecycle", "status", "--plan", str(future_path), "--actor", "agent", "--reason", "status")
    code, unsupported, _ = _invoke(
        capsys, *common, "--source-root", str(SOURCE_ROOT), "--state-root", str(tmp_path)
    )
    assert code == 1
    assert unsupported["status"] == "blocked"
    assert unsupported["error"]["code"] == "unsupported_future"

    source_root = tmp_path / "source"
    source_root.mkdir()
    plan_path = source_root / "forbidden-plan.json"
    _write(plan_path, _plan())
    try:
        code, forbidden, _ = _invoke(
            capsys, "--json", "lifecycle", "status", "--plan", str(plan_path),
            "--actor", "agent", "--reason", "status", "--source-root", str(source_root),
            "--state-root", str(tmp_path),
        )
        assert code == 1
        assert forbidden["status"] == "blocked"
        assert forbidden["error"]["code"] == "forbidden_artifact_path"
    finally:
        plan_path.unlink(missing_ok=True)


def test_human_lifecycle_output_mentions_blocker_and_next_action(tmp_path: Path, capsys) -> None:
    plan = _plan()
    plan["unresolved_decisions"] = ["choose exact state root"]
    plan = seal_artifact(plan)
    path = tmp_path / "plan.json"
    _write(path, plan)
    code = main([
        "lifecycle", "explain", "--plan", str(path), "--actor", "agent", "--reason", "explain",
        "--source-root", str(SOURCE_ROOT), "--state-root", str(tmp_path),
    ])
    output = capsys.readouterr().out
    assert code == 1
    assert "blocked" in output
    assert "resolve_decisions" in output

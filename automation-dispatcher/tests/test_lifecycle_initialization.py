from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from automation_dispatcher.backup import create_backup, verify_backup
from automation_dispatcher.cli import main
from automation_dispatcher.database import connect
from automation_dispatcher.lifecycle_artifacts import model_for
from automation_dispatcher.lifecycle_contracts import seal_artifact
from automation_dispatcher.lifecycle_discovery import (
    build_accepted_plan,
    discover_host_state,
    propose_collections,
)
from automation_dispatcher.lifecycle_initialization import (
    InitializationPaths,
    LifecycleInitializationError,
    initialize_from_plan,
    shadow_validate_from_plan,
)
from automation_dispatcher.scheduling import collection_occurrences_between


NOW = "2026-08-14T12:00:00Z"
EXPIRY = "2026-08-20T12:00:00Z"


def _capabilities() -> dict:
    return model_for("host_capability_snapshot").seal(
        {
            "schema_version": 1,
            "artifact_type": "host_capability_snapshot",
            "environment_id": "p4-fixture",
            "observed_at": NOW,
            "capabilities": [
                {
                    "name": name,
                    "supported": True,
                    "surface": f"fixture.{name}",
                    "reason": "offline fixture only",
                }
                for name in (
                    "tasks.list",
                    "tasks.read",
                    "automations.list",
                    "automations.read",
                )
            ],
        }
    ).as_dict()


def _observations(
    state_root: Path,
    schedule: dict | None = None,
) -> dict:
    return {
        "environment_id": "p4-fixture",
        "observed_at": NOW,
        "input_reference": "fixture://p4-source",
        "tasks": [],
        "automations": [
            {
                "id": "legacy-daily",
                "title": "Legacy daily",
                "enabled": True,
                "schedule": schedule
                or {"version": 2, "kind": "cron", "expression": "0 6 * * *"},
                "timezone": "America/Chicago",
                "target_task_id": "task-p4",
                "route_identity": "route-p4",
                "host_target": "task-p4",
                "authority_boundary": "ops",
                "approved_working_roots": [str(state_root)],
                "execution_constraints": {"network": "approved-only"},
                "revision": "7",
                "raw_reference": "fixture://legacy-daily",
                "prompt_summary": "Run the approved daily procedure.",
                "procedure": {
                    "kind": "documented",
                    "reference": "procedures/legacy-daily.md",
                    "external_effect": {
                        "mode": "idempotency_key",
                        "idempotency_key": "occurrence",
                    },
                },
                "authority_refs": ["authorities/legacy-daily.md"],
                "reporting": {
                    "task_id": "task-p4",
                    "receipt_fields": ["run_id", "status"],
                },
                "receipt": {"required_fields": ["run_id", "status"]},
                "data_sensitivity": "internal",
                "evidence_retention": {"policy": "references-only", "days": 30},
                "retry": {"max_attempts": 1, "backoff_seconds": 0},
                "claim_lease_seconds": 900,
            }
        ],
        "existing_manifests": [],
    }


def _fixture(tmp_path: Path, *, schedule: dict | None = None) -> dict:
    state_root = tmp_path / "state"
    repository_root = tmp_path / "repository"
    source_root = tmp_path / "installed"
    source_directory = repository_root / "collections" / "daily"
    for path in (state_root, source_directory, source_root):
        path.mkdir(parents=True)
    paths = InitializationPaths(
        database=state_root / "dispatcher.sqlite3",
        source_directory=source_directory,
        manifest=source_directory / "collection-manifest.json",
        heartbeat_template=source_directory / "heartbeat.txt",
        backup=state_root / "pre-cutover.sqlite3",
        progress=state_root / "initialization-progress.json",
        readiness=state_root / "readiness.json",
    )
    snapshot = discover_host_state(
        _observations(state_root, schedule),
        capability_snapshot=_capabilities(),
        actor="approver",
    ).snapshot.as_dict()
    proposal = propose_collections(snapshot)
    plan = build_accepted_plan(
        snapshot,
        proposal,
        actor="approver",
        accepted=True,
        accepted_at=NOW,
        expires_at=EXPIRY,
        selected_alternatives=("accept-compatible-groups",),
        state_paths=(
            paths.database,
            paths.backup,
            paths.progress,
            paths.readiness,
        ),
        source_paths=(paths.manifest,),
        state_root=state_root,
        repository_root=repository_root,
        source_root=source_root,
    ).as_dict()
    collection = plan["collections"][0]
    definition = collection["workflow_drafts"][0]["definition"]
    authority = source_directory / "definitions" / definition["authority_refs"][0]
    authority.parent.mkdir(parents=True)
    authority.write_text("# Approved authority\n", encoding="utf-8")
    current_source_path = state_root / "current-source.json"
    current_source_path.write_text(json.dumps(snapshot), encoding="utf-8")
    plan_path = state_root / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    return {
        "state_root": state_root,
        "repository_root": repository_root,
        "source_root": source_root,
        "paths": paths,
        "snapshot": snapshot,
        "snapshot_path": current_source_path,
        "plan": plan,
        "plan_path": plan_path,
        "collection": collection,
    }


def _multi_collection_fixture(tmp_path: Path) -> dict:
    state_root = tmp_path / "state"
    repository_root = tmp_path / "repository"
    source_root = tmp_path / "installed"
    source_directory = repository_root / "collections" / "selected"
    for path in (state_root, source_directory, source_root):
        path.mkdir(parents=True)
    selected_paths = InitializationPaths(
        database=state_root / "selected.sqlite3",
        source_directory=source_directory,
        manifest=source_directory / "selected-manifest.json",
        heartbeat_template=source_directory / "heartbeat.txt",
        backup=state_root / "selected-backup.sqlite3",
        progress=state_root / "selected-progress.json",
        readiness=state_root / "selected-readiness.json",
    )
    sibling_paths = {
        "database": state_root / "sibling.sqlite3",
        "manifest": source_directory / "sibling-manifest.json",
        "backup": state_root / "sibling-backup.sqlite3",
        "progress": state_root / "sibling-progress.json",
        "readiness": state_root / "sibling-readiness.json",
    }
    observations = _observations(state_root)
    sibling = json.loads(json.dumps(observations["automations"][0]))
    sibling.update(
        {
            "id": "legacy-weekly",
            "title": "Legacy weekly",
            "schedule": {"version": 2, "kind": "cron", "expression": "30 7 * * 1"},
            "target_task_id": "task-p4-sibling",
            "route_identity": "route-p4-sibling",
            "host_target": "task-p4-sibling",
            "authority_boundary": "ops-sibling",
            "revision": "3",
            "raw_reference": "fixture://legacy-weekly",
            "procedure": {
                "kind": "documented",
                "reference": "procedures/legacy-weekly.md",
                "external_effect": {
                    "mode": "idempotency_key",
                    "idempotency_key": "occurrence",
                },
            },
            "authority_refs": ["authorities/legacy-weekly.md"],
            "reporting": {
                "task_id": "task-p4-sibling",
                "receipt_fields": ["run_id", "status"],
            },
        }
    )
    observations["automations"].append(sibling)
    snapshot = discover_host_state(
        observations,
        capability_snapshot=_capabilities(),
        actor="approver",
    ).snapshot.as_dict()
    proposal = propose_collections(snapshot)
    assert len(proposal["collections"]) == 2
    plan = build_accepted_plan(
        snapshot,
        proposal,
        actor="approver",
        accepted=True,
        accepted_at=NOW,
        expires_at=EXPIRY,
        selected_alternatives=("accept-compatible-groups",),
        state_paths=(
            selected_paths.database,
            selected_paths.backup,
            selected_paths.progress,
            selected_paths.readiness,
            sibling_paths["database"],
            sibling_paths["backup"],
            sibling_paths["progress"],
            sibling_paths["readiness"],
        ),
        source_paths=(selected_paths.manifest, sibling_paths["manifest"]),
        state_root=state_root,
        repository_root=repository_root,
        source_root=source_root,
    ).as_dict()
    collections = plan["collections"]
    selected = collections[0]
    sibling_collection = collections[1]
    for collection in collections:
        for draft in collection["workflow_drafts"]:
            definition = draft["definition"]
            for reference in definition["authority_refs"]:
                authority = source_directory / "definitions" / reference
                authority.parent.mkdir(parents=True, exist_ok=True)
                authority.write_text("# Approved authority\n", encoding="utf-8")
    return {
        "state_root": state_root,
        "repository_root": repository_root,
        "source_root": source_root,
        "paths": selected_paths,
        "sibling_paths": sibling_paths,
        "snapshot": snapshot,
        "plan": plan,
        "collection": selected,
        "sibling_collection": sibling_collection,
    }


def _initialize(fixture: dict, **overrides: object) -> dict:
    values = {
        "collection_id": fixture["collection"]["dispatcher_id"],
        "expected_plan_hash": fixture["plan"]["content_hash"],
        "expected_source_state_hash": fixture["snapshot"]["content_hash"],
        "actor": "approver",
        "reason": "P4 initialization fixture",
        "paths": fixture["paths"],
        "repository_root": fixture["repository_root"],
        "state_root": fixture["state_root"],
        "source_root": fixture["source_root"],
        "source_revision": "38745487",
        "now": datetime(2026, 8, 14, 13, tzinfo=UTC),
    }
    values.update(overrides)
    return initialize_from_plan(fixture["plan"], fixture["snapshot"], **values)


def _canonical_source_occurrences(
    fixture: dict, window_start: str, window_end: str
) -> list[dict]:
    occurrences = collection_occurrences_between(
        {
            "schedule": fixture["collection"]["schedule"],
            "timezone": fixture["collection"]["timezone"],
            "enabled": True,
        },
        window_start,
        window_end,
    )
    source_id = fixture["collection"]["workflow_drafts"][0]["source_id"]
    return [{"source_id": source_id, **item} for item in occurrences]


def _shadow(
    fixture: dict,
    occurrences: list[dict],
    *,
    window_start: str,
    window_end: str,
) -> dict:
    return shadow_validate_from_plan(
        fixture["plan"],
        fixture["snapshot"],
        occurrences,
        collection_id=fixture["collection"]["dispatcher_id"],
        expected_plan_hash=fixture["plan"]["content_hash"],
        expected_source_state_hash=fixture["snapshot"]["content_hash"],
        actor="approver",
        paths=fixture["paths"],
        repository_root=fixture["repository_root"],
        state_root=fixture["state_root"],
        source_root=fixture["source_root"],
        window_start=window_start,
        window_end=window_end,
        now=datetime(2026, 8, 14, 13, tzinfo=UTC),
    )


def test_initialization_generates_registers_backs_up_and_replays_as_no_op(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    first = _initialize(fixture)
    assert first["status"] == "completed"
    assert first["workflow_execution_count"] == 0
    assert first["host_mutation_count"] == 0
    assert Path(first["manifest_path"]).is_file()
    assert Path(first["heartbeat_template_path"]).is_file()
    assert verify_backup(fixture["paths"].backup)["ok"] is True
    heartbeat = fixture["paths"].heartbeat_template.read_text(encoding="utf-8")
    for required in (
        "Required CLI version:",
        "Pinned command prefix:",
        "Dispatcher:",
        "Manifest:",
        "Database:",
        "fresh route-observation JSON",
        " status`",
        " integrity-check`",
        " route-check --dispatcher-id ",
        " due --dispatcher-id ",
        " run --dispatcher-id ",
        "action_required, completed, or failed receipt",
        "complete <run-id>",
        "fail <run-id>",
        "receipt-ack <receipt-id>",
        "receipt-retry <receipt-id>",
        "Stay silent when no occurrence is due",
        "Existing sources remain authoritative",
        "cutover requires separate explicit approval",
    ):
        assert required in heartbeat
    connection = connect(fixture["paths"].database)
    try:
        assert connection.execute("SELECT COUNT(*) FROM workflows").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
        initial_receipts = connection.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]
    finally:
        connection.close()

    repeated = _initialize(fixture)
    assert repeated["status"] == "no_op"
    assert repeated["mutation_count"] == 0
    connection = connect(fixture["paths"].database)
    try:
        assert connection.execute("SELECT COUNT(*) FROM workflows").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] == initial_receipts
    finally:
        connection.close()


def test_multi_collection_plan_initializes_only_selected_collection(tmp_path: Path) -> None:
    fixture = _multi_collection_fixture(tmp_path)
    result = _initialize(fixture)
    selected = fixture["collection"]
    sibling = fixture["sibling_collection"]
    selected_workflows = {
        draft["definition"]["workflow_id"] for draft in selected["workflow_drafts"]
    }
    sibling_workflows = {
        draft["definition"]["workflow_id"] for draft in sibling["workflow_drafts"]
    }
    assert result["manifest"]["dispatcher_id"] == selected["dispatcher_id"]
    assert set(result["workflow_hashes"]) == selected_workflows
    assert sibling_workflows.isdisjoint(result["workflow_hashes"])
    assert not fixture["sibling_paths"]["manifest"].exists()
    assert not fixture["sibling_paths"]["database"].exists()
    assert not fixture["sibling_paths"]["backup"].exists()
    assert not fixture["sibling_paths"]["progress"].exists()
    assert not fixture["sibling_paths"]["readiness"].exists()
    for workflow_id in sibling_workflows:
        assert not (
            fixture["paths"].source_directory
            / "definitions"
            / f"{workflow_id}.json"
        ).exists()
    connection = connect(fixture["paths"].database)
    try:
        assert {
            row["dispatcher_id"]
            for row in connection.execute("SELECT dispatcher_id FROM dispatchers")
        } == {selected["dispatcher_id"]}
        assert {
            row["workflow_id"]
            for row in connection.execute("SELECT workflow_id FROM workflows")
        } == selected_workflows
    finally:
        connection.close()


@pytest.mark.parametrize(
    "boundary",
    [
        "source_generation",
        "database_initialization",
        "workflow_registration",
        "manifest",
        "heartbeat_template",
        "backup",
        "progress_persist",
        "progress",
    ],
)
def test_initialization_resumes_after_injected_crash_without_duplicates(
    tmp_path: Path, boundary: str
) -> None:
    fixture = _fixture(tmp_path)
    with pytest.raises(RuntimeError, match="injected lifecycle crash"):
        _initialize(fixture, crash_after_step=boundary)
    resumed = _initialize(fixture)
    assert resumed["status"] in {"completed", "no_op"}
    connection = connect(fixture["paths"].database)
    try:
        assert connection.execute("SELECT COUNT(*) FROM workflows").fetchone()[0] == 1
        receipt_count = connection.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]
        assert receipt_count == 2
        assert connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM audit_events WHERE event_type = 'lifecycle_transition'"
        ).fetchone()[0] == 1
    finally:
        connection.close()


@pytest.mark.parametrize("corruption", ["route", "revision", "audit"])
def test_resume_rejects_corrupted_partial_projection_before_artifacts(
    tmp_path: Path, corruption: str
) -> None:
    fixture = _fixture(tmp_path)
    with pytest.raises(RuntimeError, match="workflow_registration"):
        _initialize(fixture, crash_after_step="workflow_registration")
    connection = connect(fixture["paths"].database)
    try:
        if corruption == "route":
            connection.execute("DROP TRIGGER dispatcher_routes_no_delete")
            connection.execute("DELETE FROM dispatcher_routes")
        elif corruption == "revision":
            connection.execute("DROP TRIGGER dispatcher_revisions_no_update")
            connection.execute("UPDATE dispatcher_revisions SET config_hash = ?", ("0" * 64,))
        else:
            connection.execute("DROP TRIGGER audit_events_no_delete")
            connection.execute("DELETE FROM audit_events")
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(LifecycleInitializationError) as caught:
        _initialize(fixture)
    assert caught.value.code == "initialization_projection_invalid"
    assert not fixture["paths"].manifest.exists()
    assert not fixture["paths"].heartbeat_template.exists()
    assert not fixture["paths"].backup.exists()
    assert not fixture["paths"].progress.exists()


def test_initialization_rejects_matching_backup_without_audit_tip(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    with pytest.raises(RuntimeError, match="workflow_registration"):
        _initialize(fixture, crash_after_step="workflow_registration")
    candidate = fixture["state_root"] / "candidate.sqlite3"
    create_backup(fixture["paths"].database, candidate)
    connection = connect(candidate)
    try:
        connection.execute("DROP TRIGGER audit_events_no_delete")
        connection.execute("DELETE FROM audit_events")
        connection.commit()
    finally:
        connection.close()
    create_backup(candidate, fixture["paths"].backup)
    with pytest.raises(LifecycleInitializationError) as caught:
        _initialize(fixture)
    assert caught.value.code == "backup_provenance_mismatch"


def test_initialization_rejects_hash_actor_expiry_source_and_byte_conflicts(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    for overrides, code in (
        ({"expected_plan_hash": "0" * 64}, "plan_hash_mismatch"),
        ({"actor": "different-actor"}, "plan_actor_mismatch"),
        ({"expected_source_state_hash": "0" * 64}, "source_snapshot_drift"),
        ({"now": datetime(2026, 8, 21, tzinfo=UTC)}, "plan_expired"),
    ):
        with pytest.raises(LifecycleInitializationError) as caught:
            _initialize(fixture, **overrides)
        assert caught.value.code == code

    _initialize(fixture)
    definition_path = Path(_initialize(fixture)["definitions"][0])
    definition_path.write_text("user-owned conflicting bytes\n", encoding="utf-8")
    with pytest.raises(LifecycleInitializationError) as conflict:
        _initialize(fixture)
    assert conflict.value.code == "source_conflict"
    assert conflict.value.details["observed_size"] > 0


def test_initialization_rejects_unapproved_external_path_before_mutation(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    paths = fixture["paths"]
    conflicting = InitializationPaths(
        database=fixture["state_root"] / "not-approved.sqlite3",
        source_directory=paths.source_directory,
        manifest=paths.manifest,
        heartbeat_template=paths.heartbeat_template,
        backup=paths.backup,
        progress=paths.progress,
        readiness=paths.readiness,
    )
    with pytest.raises(LifecycleInitializationError) as caught:
        _initialize(fixture, paths=conflicting)
    assert caught.value.code == "unapproved_state_path"
    assert not conflicting.database.exists()


def test_initialization_rejects_unplanned_source_sibling(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    paths = fixture["paths"]
    sibling = paths.source_directory / "sibling.txt"
    unapproved = InitializationPaths(
        database=paths.database,
        source_directory=paths.source_directory,
        manifest=paths.manifest,
        heartbeat_template=sibling,
        backup=paths.backup,
        progress=paths.progress,
        readiness=paths.readiness,
    )
    with pytest.raises(LifecycleInitializationError) as caught:
        _initialize(fixture, paths=unapproved)
    assert caught.value.code == "unapproved_source_path"
    assert not sibling.exists()


def test_initialization_rejects_preplanted_valid_unrelated_backup(tmp_path: Path) -> None:
    other = _fixture(tmp_path / "other")
    _initialize(other)
    fixture = _fixture(tmp_path / "target")
    create_backup(other["paths"].database, fixture["paths"].backup)
    with pytest.raises(LifecycleInitializationError) as caught:
        _initialize(fixture)
    assert caught.value.code == "backup_provenance_mismatch"


def test_shadow_validation_matches_occurrences_without_runs_and_blocks_q003(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    _initialize(fixture)
    window_start = "2026-08-14T00:00:00Z"
    window_end = "2026-08-17T00:00:00Z"
    source_occurrences = _canonical_source_occurrences(
        fixture, window_start, window_end
    )
    database_bytes = fixture["paths"].database.read_bytes()
    connection = connect(fixture["paths"].database)
    try:
        before_rows = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("runs", "receipts", "audit_events", "workflows", "workflow_revisions")
        }
        before_tip = connection.execute(
            "SELECT event_id,event_hash FROM audit_events ORDER BY event_id DESC LIMIT 1"
        ).fetchone()
        before_tip = tuple(before_tip)
    finally:
        connection.close()
    result = shadow_validate_from_plan(
        fixture["plan"],
        fixture["snapshot"],
        source_occurrences,
        collection_id=fixture["collection"]["dispatcher_id"],
        expected_plan_hash=fixture["plan"]["content_hash"],
        expected_source_state_hash=fixture["snapshot"]["content_hash"],
        actor="approver",
        paths=fixture["paths"],
        repository_root=fixture["repository_root"],
        state_root=fixture["state_root"],
        source_root=fixture["source_root"],
        window_start=window_start,
        window_end=window_end,
        now=datetime(2026, 8, 14, 13, tzinfo=UTC),
    )
    assert result["status"] == "blocked"
    assert result["workflow_execution_count"] == 0
    assert result["claim_count"] == 0
    assert result["receipt_post_count"] == 0
    assert result["host_mutation_count"] == 0
    checks = {item["name"]: item for item in result["readiness"]["checks"]}
    assert checks["occurrence_equivalence"]["passed"] is True
    assert checks["host_capability_coverage"]["passed"] is False
    assert any("Q-003" in blocker for blocker in result["readiness"]["blockers"])
    assert result["readiness"]["tested_occurrence_boundary"]["existing_sources_authoritative"] is True
    progress = json.loads(fixture["paths"].progress.read_text(encoding="utf-8"))
    backup_hash = checks["backup_restore"]["sha256"]
    assert f"backup_restore_verified:sha256:{backup_hash}" in progress["evidence"]
    connection = connect(fixture["paths"].database)
    try:
        after_rows = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("runs", "receipts", "audit_events", "workflows", "workflow_revisions")
        }
        after_tip = connection.execute(
            "SELECT event_id,event_hash FROM audit_events ORDER BY event_id DESC LIMIT 1"
        ).fetchone()
        after_tip = tuple(after_tip)
    finally:
        connection.close()
    assert fixture["paths"].database.read_bytes() == database_bytes
    assert after_rows == before_rows
    assert after_tip == before_tip


def test_shadow_rejects_swapped_valid_unrelated_backup(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path / "target")
    _initialize(fixture)
    unrelated = _fixture(tmp_path / "unrelated")
    _initialize(unrelated)
    fixture["paths"].backup.unlink()
    create_backup(unrelated["paths"].database, fixture["paths"].backup)
    window_start = "2026-08-14T00:00:00Z"
    window_end = "2026-08-17T00:00:00Z"
    result = _shadow(
        fixture,
        _canonical_source_occurrences(fixture, window_start, window_end),
        window_start=window_start,
        window_end=window_end,
    )
    checks = {item["name"]: item for item in result["readiness"]["checks"]}
    assert checks["backup_restore"]["passed"] is True
    assert checks["backup_provenance"]["passed"] is False
    assert checks["backup_progress_binding"]["passed"] is False
    assert any(
        "backup provenance invalid" in blocker
        for blocker in result["readiness"]["blockers"]
    )
    assert any("Q-003" in blocker for blocker in result["readiness"]["blockers"])


def test_shadow_rejects_resealed_progress_not_bound_to_immutable_event(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    _initialize(fixture)
    progress = json.loads(fixture["paths"].progress.read_text(encoding="utf-8"))
    original_event_id = progress["event_id"]
    progress["evidence"] = [
        progress["evidence"][0],
        f"backup_restore_verified:sha256:{'0' * 64}",
    ]
    tampered = seal_artifact(progress)
    assert tampered["event_id"] == original_event_id
    fixture["paths"].progress.write_text(json.dumps(tampered), encoding="utf-8")
    window_start = "2026-08-14T00:00:00Z"
    window_end = "2026-08-17T00:00:00Z"
    result = _shadow(
        fixture,
        _canonical_source_occurrences(fixture, window_start, window_end),
        window_start=window_start,
        window_end=window_end,
    )
    checks = {item["name"]: item for item in result["readiness"]["checks"]}
    assert checks["audit_chain"]["passed"] is True
    assert checks["backup_restore"]["passed"] is True
    assert checks["backup_provenance"]["passed"] is True
    assert checks["backup_progress_binding"]["passed"] is False
    assert checks["progress_audit_binding"]["passed"] is False
    assert any(
        error["error"] == "audit_payload_mismatch"
        for error in checks["progress_audit_binding"]["evidence"]["errors"]
    )
    assert any(
        "immutable lifecycle audit event" in blocker
        for blocker in result["readiness"]["blockers"]
    )


def test_shadow_mismatch_reports_semantic_guidance(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    _initialize(fixture)
    result = shadow_validate_from_plan(
        fixture["plan"],
        fixture["snapshot"],
        [],
        collection_id=fixture["collection"]["dispatcher_id"],
        expected_plan_hash=fixture["plan"]["content_hash"],
        expected_source_state_hash=fixture["snapshot"]["content_hash"],
        actor="approver",
        paths=fixture["paths"],
        repository_root=fixture["repository_root"],
        state_root=fixture["state_root"],
        source_root=fixture["source_root"],
        window_start="2026-08-14T00:00:00Z",
        window_end="2026-08-17T00:00:00Z",
        now=datetime(2026, 8, 14, 13, tzinfo=UTC),
    )
    assert any(item["field"] == "occurrences" for item in result["semantic_changes"])
    assert "accept a new lifecycle plan" in result["semantic_changes"][0]["guidance"]


@pytest.mark.parametrize(
    ("expression", "window_start", "window_end", "tamper"),
    [
        ("30 2 * * *", "2026-03-08T06:00:00Z", "2026-03-08T10:00:00Z", "drop-gap"),
        ("30 1 * * *", "2026-11-01T05:00:00Z", "2026-11-01T09:00:00Z", "invent-fold"),
    ],
)
def test_shadow_compares_dst_adjustment_identity(
    tmp_path: Path,
    expression: str,
    window_start: str,
    window_end: str,
    tamper: str,
) -> None:
    fixture = _fixture(
        tmp_path,
        schedule={"version": 2, "kind": "cron", "expression": expression},
    )
    _initialize(fixture)
    occurrences = _canonical_source_occurrences(fixture, window_start, window_end)
    assert len(occurrences) == 1
    if tamper == "drop-gap":
        assert occurrences[0]["adjustment"]["kind"] == "gap_advanced"
        occurrences[0]["adjustment"] = None
    else:
        assert occurrences[0]["adjustment"] is None
        occurrences[0]["adjustment"] = {
            "kind": "gap_advanced",
            "from_local": occurrences[0]["intended_local"],
            "to_local": occurrences[0]["effective_local"],
        }
    result = _shadow(
        fixture,
        occurrences,
        window_start=window_start,
        window_end=window_end,
    )
    check = next(
        item for item in result["readiness"]["checks"]
        if item["name"] == "occurrence_equivalence"
    )
    assert check["passed"] is False
    assert check["missing"] and check["unexpected"]


def test_shadow_rejects_incomplete_source_occurrence_schema(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    _initialize(fixture)
    with pytest.raises(LifecycleInitializationError) as caught:
        _shadow(
            fixture,
            [{"source_id": fixture["collection"]["workflow_drafts"][0]["source_id"],
              "scheduled_for": "2026-08-14T11:00:00Z"}],
            window_start="2026-08-14T00:00:00Z",
            window_end="2026-08-17T00:00:00Z",
        )
    assert caught.value.code == "invalid_source_occurrences"


def test_shadow_rejects_timezone_naive_window_and_occurrence(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    _initialize(fixture)
    with pytest.raises(LifecycleInitializationError) as naive_window:
        _shadow(
            fixture,
            [],
            window_start="2026-08-14T00:00:00",
            window_end="2026-08-17T00:00:00Z",
        )
    assert naive_window.value.code == "invalid_occurrence_window"
    window_start = "2026-08-14T00:00:00Z"
    window_end = "2026-08-17T00:00:00Z"
    occurrences = _canonical_source_occurrences(fixture, window_start, window_end)
    occurrences[0]["scheduled_for"] = occurrences[0]["scheduled_for"].removesuffix("Z")
    with pytest.raises(LifecycleInitializationError) as naive_occurrence:
        _shadow(
            fixture,
            occurrences,
            window_start=window_start,
            window_end=window_end,
        )
    assert naive_occurrence.value.code == "invalid_source_occurrences"


@pytest.mark.parametrize("drift", ["route", "config", "definition"])
def test_shadow_reports_independent_projection_drift(
    tmp_path: Path, drift: str
) -> None:
    fixture = _fixture(tmp_path)
    initialized = _initialize(fixture)
    connection = connect(fixture["paths"].database)
    try:
        if drift == "route":
            connection.execute("DROP TRIGGER dispatcher_routes_no_delete")
            connection.execute(
                "DELETE FROM dispatcher_routes WHERE dispatcher_id = ?",
                (fixture["collection"]["dispatcher_id"],),
            )
        elif drift == "config":
            connection.execute("DROP TRIGGER dispatcher_revisions_no_update")
            connection.execute(
                "UPDATE dispatcher_revisions SET config_hash = ? WHERE dispatcher_id = ? AND revision = 1",
                ("0" * 64, fixture["collection"]["dispatcher_id"]),
            )
        connection.commit()
    finally:
        connection.close()
    if drift == "definition":
        Path(initialized["definitions"][0]).write_text("{}\n", encoding="utf-8")
    window_start = "2026-08-14T00:00:00Z"
    window_end = "2026-08-17T00:00:00Z"
    result = _shadow(
        fixture,
        _canonical_source_occurrences(fixture, window_start, window_end),
        window_start=window_start,
        window_end=window_end,
    )
    blockers = "\n".join(result["readiness"]["blockers"])
    assert result["status"] == "blocked"
    assert {
        "route": "route projection",
        "config": "configuration drifted",
        "definition": "definition path or bytes drifted",
    }[drift] in blockers
    assert "Q-003" in blockers


def test_shadow_readiness_write_resumes_after_injected_crash(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    _initialize(fixture)
    common = {
        "collection_id": fixture["collection"]["dispatcher_id"],
        "expected_plan_hash": fixture["plan"]["content_hash"],
        "expected_source_state_hash": fixture["snapshot"]["content_hash"],
        "actor": "approver",
        "paths": fixture["paths"],
        "repository_root": fixture["repository_root"],
        "state_root": fixture["state_root"],
        "source_root": fixture["source_root"],
        "window_start": "2026-08-14T00:00:00Z",
        "window_end": "2026-08-17T00:00:00Z",
        "now": datetime(2026, 8, 14, 13, tzinfo=UTC),
    }
    with pytest.raises(RuntimeError, match="readiness"):
        shadow_validate_from_plan(
            fixture["plan"], fixture["snapshot"], [], crash_after_step="readiness", **common
        )
    resumed = shadow_validate_from_plan(
        fixture["plan"], fixture["snapshot"], [], **common
    )
    assert resumed["status"] == "blocked"
    assert resumed["mutation_count"] == 0


def test_legacy_lifecycle_apply_dry_run_shape_and_zero_writes_are_unchanged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture = _fixture(tmp_path)
    before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    code = main(
        [
            "--json", "lifecycle", "apply", "--plan", str(fixture["plan_path"]),
            "--stage", "propose", "--action", "normalize", "--dry-run", "--actor", "approver",
            "--reason", "legacy P2 dry run", "--repository-root", str(fixture["repository_root"]),
            "--state-root", str(fixture["state_root"]), "--source-root", str(fixture["source_root"]),
        ]
    )
    result = json.loads(capsys.readouterr().out)
    assert code == 1
    assert result["status"] == "blocked"
    assert result["identity"]["dry_run"] is True
    assert result["identity"]["step_plan"]["mutation_count"] == 0
    assert result["database_path"] is None
    assert {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    } == before


def test_cli_non_dry_run_requires_current_observation_and_keeps_host_unchanged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture = _fixture(tmp_path)
    paths = fixture["paths"]
    arguments = [
        "--json",
        "lifecycle",
        "apply",
        "--plan",
        str(fixture["plan_path"]),
        "--stage",
        "initialize",
        "--action",
        "anything",
        "--collection-id",
        fixture["collection"]["dispatcher_id"],
        "--expected-plan-hash",
        fixture["plan"]["content_hash"],
        "--expected-source-state-hash",
        fixture["snapshot"]["content_hash"],
        "--current-source-observation",
        str(fixture["snapshot_path"]),
        "--database-path",
        str(paths.database),
        "--source-directory",
        str(paths.source_directory),
        "--manifest-path",
        str(paths.manifest),
        "--heartbeat-template-path",
        str(paths.heartbeat_template),
        "--backup-path",
        str(paths.backup),
        "--progress-output",
        str(paths.progress),
        "--repository-root",
        str(fixture["repository_root"]),
        "--state-root",
        str(fixture["state_root"]),
        "--source-root",
        str(fixture["source_root"]),
        "--actor",
        "approver",
        "--reason",
        "P4 CLI fixture",
    ]
    assert main(arguments) == 2
    rejected = json.loads(capsys.readouterr().out)
    assert rejected["error"]["code"] == "invalid_lifecycle_action"
    assert not paths.database.exists()
    arguments[arguments.index("anything")] = "apply"
    assert main(arguments) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "completed"
    assert result["database_path"] == str(paths.database)
    assert result["identity"]["host_mutation_count"] == 0

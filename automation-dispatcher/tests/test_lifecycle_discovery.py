from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest

from automation_dispatcher.cli import main
from automation_dispatcher.definitions import normalize_definition
from automation_dispatcher.lifecycle_artifacts import load_artifact, model_for
from automation_dispatcher.lifecycle_contracts import LifecycleContractError
from automation_dispatcher.lifecycle_discovery import (
    build_accepted_plan,
    discover_host_state,
    propose_collections,
    route_lifecycle_request,
)


NOW = "2026-08-13T18:00:00Z"
SOURCE_ROOT = Path(__file__).parents[1]


def _capabilities(*, supported: bool = True, environment_id: str = "codex-fixture") -> dict:
    return model_for("host_capability_snapshot").seal(
        {
            "schema_version": 1,
            "artifact_type": "host_capability_snapshot",
            "environment_id": environment_id,
            "observed_at": NOW,
            "capabilities": [
                {
                    "name": name,
                    "supported": supported,
                    "surface": f"fixture.{name}" if supported else None,
                    "reason": "fixture observation" if supported else "Q-003 unavailable",
                }
                for name in ("tasks.list", "tasks.read", "automations.list", "automations.read")
            ],
        }
    ).as_dict()


def _item(stable_id: str, expression: str = "0 6 * * *", **overrides: object) -> dict:
    value = {
        "id": stable_id,
        "title": "Daily Automations",
        "enabled": True,
        "schedule": {"version": 2, "kind": "cron", "expression": expression},
        "timezone": "America/Chicago",
        "target_task_id": "task-target-1",
        "route_identity": "route-1",
        "host_target": "task-target-1",
        "authority_boundary": "team-ops",
        "approved_working_roots": ["/approved/ops"],
        "execution_constraints": {"network": "approved-only"},
        "revision": "7",
        "raw_reference": f"fixture://{stable_id}",
        "prompt": "sensitive prompt body that must not be retained",
        "prompt_summary": f"Run {stable_id}.",
        "procedure": {
            "kind": "documented",
            "reference": f"procedures/{stable_id}.md",
            "external_effect": {"mode": "idempotency_key", "idempotency_key": "occurrence"},
        },
        "authority_refs": [f"authorities/{stable_id}.md"],
        "reporting": {"task_id": "task-target-1", "receipt_fields": ["run_id", "status"]},
        "receipt": {"required_fields": ["run_id", "status"]},
        "data_sensitivity": "internal",
        "evidence_retention": {"policy": "references-only", "days": 30},
        "retry": {"max_attempts": 2, "backoff_seconds": 60},
        "claim_lease_seconds": 900,
    }
    value.update(overrides)
    return value


def _observations(*items: dict) -> dict:
    return {
        "environment_id": "codex-fixture",
        "observed_at": NOW,
        "input_reference": "fixture://host-observations",
        "tasks": [],
        "automations": list(items),
        "existing_manifests": [],
    }


def _discover(*items: dict):
    return discover_host_state(
        _observations(*items), capability_snapshot=_capabilities(), actor="test-agent"
    ).snapshot.as_dict()


def _acceptance_paths(tmp_path: Path) -> dict:
    state_root = tmp_path / "external-state"
    repository_root = tmp_path / "repository"
    source_root = tmp_path / "installed-source"
    state_root.mkdir()
    repository_root.mkdir()
    source_root.mkdir()
    return {
        "accepted_at": NOW,
        "state_paths": (state_root / "plan.json",),
        "source_paths": (repository_root / "collections" / "daily.json",),
        "state_root": state_root,
        "repository_root": repository_root,
        "source_root": source_root,
    }


@pytest.mark.parametrize(
    ("prompt", "operation"),
    [
        ("Consolidate my daily tasks", "consolidate"),
        ("Add a workflow to the collection", "add_workflow"),
        ("Create a new collection", "create_collection"),
        ("Resume the setup", "resume"),
        ("Inspect lifecycle status", "inspect"),
        ("Change schedule to Fridays", "schedule_change"),
    ],
)
def test_natural_language_routes_to_lifecycle_operation(prompt: str, operation: str) -> None:
    assert route_lifecycle_request(prompt) == operation


def test_discovery_is_deterministic_bounded_read_only_and_keeps_nonactive_items() -> None:
    observations = _observations(
        _item("automation-b", paused=True, enabled=False),
        _item("automation-a"),
        _item("automation-c", accessible=False),
    )
    first = discover_host_state(
        observations,
        capability_snapshot=_capabilities(),
        actor="test-agent",
        cursor=0,
        page_size=2,
    )
    repeated = discover_host_state(
        observations,
        capability_snapshot=_capabilities(),
        actor="test-agent",
        cursor=0,
        page_size=2,
    )
    assert first.snapshot.as_dict() == repeated.snapshot.as_dict()
    assert first.next_cursor == 2
    assert first.total_candidates == 3
    visible = first.snapshot.data["automations"]
    assert [item["stable_id"] for item in visible] == ["automation-a", "automation-b"]
    assert visible[1]["status"] == "paused"
    assert visible[0]["title"] == "Daily Automations"
    serialized = json.dumps(first.snapshot.as_dict())
    assert "sensitive prompt body" not in serialized
    assert first.snapshot.data["scope"]["read_only"] is True


def test_discovery_fail_closes_live_access_and_records_missing_capabilities() -> None:
    page = discover_host_state(
        _observations(_item("automation-a")),
        capability_snapshot=None,
        actor="test-agent",
    )
    assert page.snapshot.data["unsupported_capabilities"] == [
        "tasks.list", "tasks.read", "automations.list", "automations.read"
    ]
    assert any("Q-003" in warning for warning in page.snapshot.data["warnings"])
    live = _observations(_item("automation-a"))
    live["live"] = True
    with pytest.raises(LifecycleContractError) as caught:
        discover_host_state(live, capability_snapshot=_capabilities(), actor="test-agent")
    assert caught.value.code == "host_capability_unavailable"
    with pytest.raises(LifecycleContractError) as environment_drift:
        discover_host_state(
            _observations(_item("automation-a")),
            capability_snapshot=_capabilities(environment_id="other-environment"),
            actor="test-agent",
        )
    assert environment_drift.value.code == "host_environment_drift"


def test_discovery_marks_existing_manifests_and_never_hides_missing_selection() -> None:
    observations = _observations(_item("managed-a"), _item("unmanaged-b"))
    observations["existing_manifests"] = [
        {
            "manifest_id": "manifest-1",
            "source_ids": ["managed-a", "stale-source"],
        }
    ]
    page = discover_host_state(
        observations,
        capability_snapshot=_capabilities(),
        actor="test-agent",
        selected_ids=("managed-a", "missing-source"),
    )
    item = page.snapshot.data["automations"][0]
    assert item["stable_id"] == "managed-a"
    assert item["status"] == "already_managed"
    assert item["lifecycle_state"] == "active"
    assert item["management_classification"] == "managed"
    assert item["managed_manifest_id"] == "manifest-1"
    assert any("missing-source" in warning for warning in page.snapshot.data["warnings"])
    assert any("stale-source" in warning for warning in page.snapshot.data["warnings"])
    proposal = propose_collections(page.snapshot.as_dict())
    assert proposal["exclusions"] == [
        {"source_id": "managed-a", "reason": "already_managed"}
    ]


def test_discovery_preserves_paused_lifecycle_state_but_managed_sources_are_excluded() -> None:
    snapshot = _discover(
        _item(
            "managed-paused",
            enabled=False,
            paused=True,
            managed_manifest_id="manifest-direct",
        )
    )
    item = snapshot["automations"][0]
    assert item["lifecycle_state"] == "paused"
    assert item["management_classification"] == "managed"
    assert item["status"] == "already_managed"
    proposal = propose_collections(snapshot)
    assert proposal["collections"] == []
    assert {entry["source_id"] for entry in proposal["exclusions"]} == {
        "managed-paused"
    }


def test_discovery_rejects_ambiguous_manifest_claims_and_duplicate_host_ids() -> None:
    observations = _observations(_item("shared-source"))
    observations["existing_manifests"] = [
        {"manifest_id": "manifest-a", "source_ids": ["shared-source"]},
        {"manifest_id": "manifest-b", "automation_ids": ["shared-source"]},
    ]
    with pytest.raises(LifecycleContractError) as ambiguous:
        discover_host_state(
            observations, capability_snapshot=_capabilities(), actor="test-agent"
        )
    assert ambiguous.value.code == "ambiguous_managed_source"

    duplicated = _observations(_item("duplicate"), _item("duplicate"))
    with pytest.raises(LifecycleContractError) as within_kind:
        discover_host_state(
            duplicated, capability_snapshot=_capabilities(), actor="test-agent"
        )
    assert within_kind.value.code == "duplicate_host_identity"

    across_kinds = _observations(_item("duplicate"))
    across_kinds["tasks"] = [_item("duplicate")]
    with pytest.raises(LifecycleContractError) as across:
        discover_host_state(
            across_kinds, capability_snapshot=_capabilities(), actor="test-agent"
        )
    assert across.value.code == "duplicate_host_identity"


def test_proposal_groups_only_compatible_schedules_and_normalizes_v2_definitions() -> None:
    snapshot = _discover(
        _item("daily-a"),
        _item("daily-b"),
        _item("weekly-a", "0 6 * * 1"),
        _item("paused-daily", paused=True, enabled=False),
    )
    proposal = propose_collections(snapshot)
    assert len(proposal["collections"]) == 2
    assert proposal["mutation_count"] == 0
    groups = {
        collection["schedule"]["expression"]: collection
        for collection in proposal["collections"]
    }
    assert len(groups["0 6 * * *"]["workflow_drafts"]) == 3
    assert len(groups["0 6 * * 1"]["workflow_drafts"]) == 1
    for collection in proposal["collections"]:
        assert collection["cutover_candidate"]["authorized"] is False
        for draft in collection["workflow_drafts"]:
            normalized = normalize_definition(draft["definition"])
            assert normalized["schema_version"] == 2
            assert "schedule" not in normalized
            assert "timezone" not in normalized
    paused = next(item for item in proposal["workflow_mappings"] if item["source_id"] == "paused-daily")
    assert paused["source_status"] == "paused"
    assert proposal["inclusion_decisions"] == [
        {
            "source_id": "paused-daily",
            "reason": "source is paused and unmanaged",
            "choices": ["include", "exclude"],
        }
    ]
    assert "decide whether to include paused source paused-daily" in proposal[
        "unresolved_decisions"
    ]
    daily_decision = next(
        item
        for item in proposal["grouping_decisions"]
        if item["collection_id"] == groups["0 6 * * *"]["dispatcher_id"]
    )
    assert daily_decision["decision"] == "grouped"
    assert daily_decision["compatible_on"] == {
        "schedule": {"version": 2, "kind": "cron", "expression": "0 6 * * *"},
        "timezone": "America/Chicago",
        "authority_boundary": "team-ops",
        "approved_working_roots": ["/approved/ops"],
        "route_identity": "route-1",
        "host_target": "task-target-1",
        "execution_constraints": {"network": "approved-only"},
    }
    assert "same canonical schedule" in daily_decision["rationale"]
    assert {
        risk["code"] for risk in proposal["risks"]
    } == {
        "cutover_requires_separate_approval",
        "mixed_schedule_split",
        "unresolved_decision",
    }
    split = next(
        item for item in proposal["grouping_decisions"] if item["decision"] == "split"
    )
    assert split["differing_fields"] == ["schedule"]
    boundary = groups["0 6 * * *"]["cutover_candidate"]
    assert boundary["status"] == "computed"
    assert boundary["last_source_scheduled_for"] == "2026-08-13T11:00:00Z"
    assert boundary["first_dispatcher_scheduled_for"] == "2026-08-14T11:00:00Z"
    assert boundary["disable_source_before"] == "2026-08-14T11:00:00Z"
    assert boundary["authorized"] is False


def test_proposal_exposes_inaccessible_unsafe_and_incomplete_candidates() -> None:
    unsafe = _item("unsafe")
    unsafe["procedure"] = {
        "kind": "documented",
        "reference": "procedures/unsafe.md",
        "external_effect": {"mode": "unknown"},
    }
    incomplete = _item("incomplete", timezone=None)
    inaccessible = _item("gone", accessible=False)
    proposal = propose_collections(_discover(unsafe, incomplete, inaccessible))
    assert {item["reason"] for item in proposal["exclusions"]} == {
        "incomplete_compatibility_evidence", "inaccessible"
    }
    assert any("unsafe" in item for item in proposal["unresolved_decisions"])
    assert any("incomplete" in item for item in proposal["unresolved_decisions"])


def test_proposal_exposes_route_target_splits_and_unknown_cutover_boundaries() -> None:
    proposal = propose_collections(
        _discover(
            _item("route-a"),
            _item(
                "route-b",
                route_identity="route-2",
                target_task_id="task-target-2",
                host_target="task-target-2",
            ),
        )
    )
    split = next(
        item for item in proposal["grouping_decisions"] if item["decision"] == "split"
    )
    assert split["differing_fields"] == ["route_identity", "host_target"]
    assert any(risk["code"] == "route_target_conflict" for risk in proposal["risks"])

    unknown = propose_collections(_discover(_item("bad-zone", timezone="Mars/Olympus")))
    boundary = unknown["collections"][0]["cutover_candidate"]
    assert boundary["status"] == "unknown"
    assert boundary["boundary_id"] is None
    assert boundary["authorized"] is False
    assert "unknown IANA timezone" in boundary["reason"]
    assert any(
        risk["code"] == "cutover_boundary_unknown"
        and risk["severity"] == "blocking"
        for risk in unknown["risks"]
    )
    assert any("resolve cutover boundary" in item for item in unknown["unresolved_decisions"])


def test_acceptance_topology_and_paused_decisions_materially_change_the_plan(
    tmp_path: Path,
) -> None:
    snapshot = _discover(
        _item("daily-a"),
        _item("daily-b"),
        _item("paused-daily", enabled=False, paused=True),
    )
    proposal = propose_collections(snapshot)
    paths = _acceptance_paths(tmp_path)
    compatible = build_accepted_plan(
        snapshot,
        proposal,
        actor="approver",
        accepted=True,
        expires_at="2026-08-14T18:00:00Z",
        paused_source_decisions={"paused-daily": True},
        selected_alternatives=("accept-compatible-groups",),
        **paths,
    ).as_dict()
    assert len(compatible["collections"]) == 1
    assert len(compatible["collections"][0]["workflow_drafts"]) == 3
    assert compatible["unresolved_decisions"] == []

    separate = build_accepted_plan(
        snapshot,
        proposal,
        actor="approver",
        accepted=True,
        expires_at="2026-08-14T18:00:00Z",
        paused_source_decisions={"paused-daily": False},
        selected_alternatives=("keep-separate",),
        **paths,
    ).as_dict()
    assert len(separate["collections"]) == 2
    assert all(len(item["workflow_drafts"]) == 1 for item in separate["collections"])
    assert {item["source_id"] for item in separate["workflow_mappings"]} == {
        "daily-a",
        "daily-b",
    }
    assert {
        item["dispatcher_id"] for item in separate["workflow_mappings"]
    } == {item["dispatcher_id"] for item in separate["collections"]}
    assert {
        item["reason"] for item in separate["exclusions"]
    } == {"paused_source_excluded_by_acceptance"}
    assert all(
        "one collection per source" in item["grouping_rationale"]
        for item in separate["collections"]
    )
    assert "alternative:keep-separate" in separate["approved_scope"]

    with pytest.raises(LifecycleContractError) as missing_paused:
        build_accepted_plan(
            snapshot,
            proposal,
            actor="approver",
            accepted=True,
            expires_at="2026-08-14T18:00:00Z",
            **paths,
        )
    assert missing_paused.value.code == "paused_source_decision_required"
    with pytest.raises(LifecycleContractError) as multiple_topologies:
        build_accepted_plan(
            snapshot,
            proposal,
            actor="approver",
            accepted=True,
            expires_at="2026-08-14T18:00:00Z",
            selected_alternatives=("keep-separate", "accept-compatible-groups"),
            **paths,
        )
    assert multiple_topologies.value.code == "invalid_selected_alternative"


@pytest.mark.parametrize(
    "alternatives",
    [
        [
            {
                "id": "arbitrary-topology",
                "kind": "topology",
                "description": "A recomputed hash does not make this implementation-owned.",
            }
        ],
        [
            {
                "id": "keep-separate",
                "kind": "topology",
                "description": "Create one proposed collection per selected source.",
            }
        ],
        [
            {
                "id": "keep-separate",
                "kind": "topology",
                "description": "tampered description",
            },
            {
                "id": "keep-separate",
                "kind": "topology",
                "description": "Create one proposed collection per selected source.",
            },
        ],
    ],
)
def test_acceptance_rejects_rehashed_tampered_topology_contract(
    alternatives: list[dict],
) -> None:
    snapshot = _discover(_item("daily-a"))
    proposal = propose_collections(snapshot)
    proposal["alternatives"] = alternatives
    proposal["proposal_hash"] = sha256(
        json.dumps(
            {key: value for key, value in proposal.items() if key != "proposal_hash"},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    with pytest.raises(LifecycleContractError) as tampered:
        build_accepted_plan(
            snapshot,
            proposal,
            actor="approver",
            accepted=True,
            accepted_at=NOW,
            expires_at="2026-08-14T18:00:00Z",
            selected_alternatives=(str(alternatives[0]["id"]),),
        )
    assert tampered.value.code == "invalid_selected_alternative"


def test_plan_requires_explicit_acceptance_and_is_bound_to_snapshot_proposal_and_expiry(
    tmp_path: Path,
) -> None:
    snapshot = _discover(_item("daily-a"))
    proposal = propose_collections(snapshot)
    paths = _acceptance_paths(tmp_path)
    with pytest.raises(LifecycleContractError) as caught:
        build_accepted_plan(
            snapshot, proposal, actor="approver", accepted=False, expires_at="2026-08-14T18:00:00Z"
        )
    assert caught.value.code == "proposal_acceptance_required"
    plan = build_accepted_plan(
        snapshot,
        proposal,
        actor="approver",
        accepted=True,
        expires_at="2026-08-14T18:00:00Z",
        selected_alternatives=("accept-compatible-groups",),
        **paths,
    ).as_dict()
    assert plan["source_snapshot_hash"] == snapshot["content_hash"]
    assert f"proposal_hash:{proposal['proposal_hash']}" in plan["approved_scope"]
    assert "expires_at:2026-08-14T18:00:00Z" in plan["approved_scope"]
    assert plan["stage_status"]["initialize"] == "pending"
    assert {item["operation"] for item in plan["expected_cli_operations"]} == {
        "init", "register"
    }
    assert {item["operation"] for item in plan["expected_host_operations"]} == {
        "automations.create_or_update_heartbeat", "automations.disable_legacy"
    }
    assert all(item["authorized"] is False for item in plan["expected_host_operations"])
    changed = deepcopy(snapshot)
    changed["content_hash"] = "0" * 64
    with pytest.raises(LifecycleContractError) as drifted:
        build_accepted_plan(
            changed, proposal, actor="approver", accepted=True, expires_at="2026-08-14T18:00:00Z"
        )
    assert drifted.value.code in {"content_hash_mismatch", "source_snapshot_drift"}


def test_plan_expiry_is_relative_to_acceptance_time_not_discovery_time() -> None:
    snapshot = _discover(_item("daily-a"))
    proposal = propose_collections(snapshot)
    with pytest.raises(LifecycleContractError) as expired:
        build_accepted_plan(
            snapshot,
            proposal,
            actor="approver",
            accepted=True,
            accepted_at="2026-08-15T18:00:00Z",
            expires_at="2026-08-14T18:00:00Z",
        )
    assert expired.value.code == "invalid_plan_expiry"


def test_plan_paths_are_normalized_and_fenced(
    tmp_path: Path,
) -> None:
    snapshot = _discover(_item("daily-a"))
    proposal = propose_collections(snapshot)
    roots = _acceptance_paths(tmp_path)
    plan = build_accepted_plan(
        snapshot,
        proposal,
        actor="approver",
        accepted=True,
        expires_at="2026-08-14T18:00:00Z",
        **roots,
    ).as_dict()
    assert plan["state_paths"] == [str(Path(roots["state_paths"][0]).resolve())]
    assert plan["source_paths"] == [str(Path(roots["source_paths"][0]).resolve())]

    cases = [
        ({"state_paths": ("../escape.json",)}, "state_path_outside_root"),
        ({"source_paths": ("../escape.json",)}, "source_path_outside_root"),
        (
            {"source_paths": (Path(roots["repository_root"]) / ".automation-dispatcher" / "x",)},
            "forbidden_artifact_path",
        ),
        ({"state_root": Path("/")}, "forbidden_plan_root"),
        ({"repository_root": Path("/")}, "forbidden_plan_root"),
    ]
    for overrides, code in cases:
        arguments = {**roots, **overrides}
        with pytest.raises(LifecycleContractError) as caught:
            build_accepted_plan(
                snapshot,
                proposal,
                actor="approver",
                accepted=True,
                expires_at="2026-08-14T18:00:00Z",
                **arguments,
            )
        assert caught.value.code == code

    state_link_target = tmp_path / "state-link-target"
    state_link_target.mkdir()
    state_link = Path(roots["state_root"]) / "linked"
    state_link.symlink_to(state_link_target, target_is_directory=True)
    with pytest.raises(LifecycleContractError) as symlinked:
        build_accepted_plan(
            snapshot,
            proposal,
            actor="approver",
            accepted=True,
            expires_at="2026-08-14T18:00:00Z",
            **{**roots, "state_paths": (state_link / "plan.json",)},
        )
    assert symlinked.value.code == "symlink_artifact_path"

    installed = Path(roots["state_root"]) / "installed"
    installed.mkdir()
    with pytest.raises(LifecycleContractError) as installed_path:
        build_accepted_plan(
            snapshot,
            proposal,
            actor="approver",
            accepted=True,
            expires_at="2026-08-14T18:00:00Z",
            **{
                **roots,
                "state_paths": (installed / "plan.json",),
                "installed_roots": (installed,),
            },
        )
    assert installed_path.value.code == "forbidden_artifact_path"

    with pytest.raises(LifecycleContractError) as source_owned_state:
        build_accepted_plan(
            snapshot,
            proposal,
            actor="approver",
            accepted=True,
            expires_at="2026-08-14T18:00:00Z",
            **{**roots, "state_paths": (Path(roots["source_root"]) / "state.json",)},
        )
    assert source_owned_state.value.code == "forbidden_artifact_path"


def test_resume_after_rediscovery_is_no_op_or_requires_reproposal_on_change() -> None:
    observations = _observations(_item("daily-a"))
    first = discover_host_state(
        observations, capability_snapshot=_capabilities(), actor="test-agent"
    ).snapshot.as_dict()
    repeated = discover_host_state(
        observations, capability_snapshot=_capabilities(), actor="test-agent"
    ).snapshot.as_dict()
    proposal = propose_collections(first)
    assert repeated == first
    assert propose_collections(repeated) == proposal

    changed_observations = _observations(_item("daily-a", "30 6 * * *"))
    changed = discover_host_state(
        changed_observations, capability_snapshot=_capabilities(), actor="test-agent"
    ).snapshot.as_dict()
    assert changed["content_hash"] != first["content_hash"]
    with pytest.raises(LifecycleContractError) as drifted:
        build_accepted_plan(
            changed,
            proposal,
            actor="approver",
            accepted=True,
            expires_at="2026-08-14T18:00:00Z",
        )
    assert drifted.value.code == "source_snapshot_drift"


def test_lifecycle_plan_cli_proposes_then_writes_only_explicitly_accepted_plan(
    tmp_path: Path, capsys
) -> None:
    repository = tmp_path / "fixture-repository"
    state = tmp_path / "external-state"
    repository.mkdir()
    state.mkdir()
    observations_path = repository / "observations.json"
    observations_path.write_text(json.dumps(_observations(_item("daily-a"))), encoding="utf-8")
    capabilities_path = state / "capabilities.json"
    capabilities_path.write_text(json.dumps(_capabilities()), encoding="utf-8")
    common = [
        "--json", "lifecycle", "plan",
        "--host-observations", str(observations_path),
        "--host-capabilities", str(capabilities_path),
        "--actor", "test-agent", "--reason", "scenario fixture",
        "--repository-root", str(repository),
        "--state-root", str(state),
        "--source-root", str(SOURCE_ROOT),
    ]
    assert main(common) == 0
    proposal_result = json.loads(capsys.readouterr().out)
    assert proposal_result["status"] == "completed"
    assert proposal_result["identity"]["mutation_count"] == 0
    assert proposal_result["next_action"]["type"] == "accept_proposal"
    assert not (state / "plan.json").exists()
    assert main(common[1:]) == 0
    human = capsys.readouterr().out
    assert "collections=1" in human
    assert "workflows=1" in human
    assert "schedule=0 6 * * *" in human
    assert "timezone=America/Chicago" in human
    assert "target=task-target-1" in human
    assert "sources=daily-a" in human
    assert "rationale=Grouped because" in human
    assert "mapping=daily-a->collection-" in human
    assert "risks=info:cutover_requires_separate_approval" in human
    assert "questions=none" in human
    assert "next_action=accept_proposal" in human

    accepted = [
        *common,
        "--accept-proposal", "--expires-at", "2026-08-14T18:00:00Z",
        "--plan-state-path", str(state),
        "--plan-source-path", "collections/daily-a",
        "--output", "plan.json",
    ]
    assert main(accepted) == 0
    accepted_result = json.loads(capsys.readouterr().out)
    assert accepted_result["identity"]["mutation_count"] == 1
    plan = load_artifact(state / "plan.json", "lifecycle_plan", source_root=SOURCE_ROOT)
    assert plan.content_hash == accepted_result["identity"]["lifecycle_plan"]["content_hash"]
    assert main(accepted) == 2
    replay = json.loads(capsys.readouterr().out)
    assert replay["error"]["code"] == "immutable_plan_output_exists"
    assert load_artifact(
        state / "plan.json", "lifecycle_plan", source_root=SOURCE_ROOT
    ).content_hash == plan.content_hash


def test_lifecycle_human_output_renders_split_risk_and_paused_inclusion_decision(
    tmp_path: Path, capsys
) -> None:
    repository = tmp_path / "repository"
    state = tmp_path / "state"
    repository.mkdir()
    state.mkdir()
    capabilities_path = state / "capabilities.json"
    capabilities_path.write_text(json.dumps(_capabilities()), encoding="utf-8")
    observations_path = repository / "observations.json"
    observations_path.write_text(
        json.dumps(
            _observations(
                _item("daily-a"),
                _item("weekly-a", "0 6 * * 1"),
            )
        ),
        encoding="utf-8",
    )
    common = [
        "lifecycle", "plan",
        "--host-observations", str(observations_path),
        "--host-capabilities", str(capabilities_path),
        "--actor", "test-agent", "--reason", "human decision package fixture",
        "--repository-root", str(repository),
        "--state-root", str(state),
        "--source-root", str(SOURCE_ROOT),
    ]
    assert main(common) == 0
    split_output = capsys.readouterr().out
    assert "split=collection-" in split_output
    assert "fields=schedule" in split_output
    assert "mixed_schedule_split" in split_output
    assert "next_action=accept_proposal" in split_output

    observations_path.write_text(
        json.dumps(_observations(_item("paused-a", enabled=False, paused=True))),
        encoding="utf-8",
    )
    assert main(common) == 1
    paused_output = capsys.readouterr().out
    assert "inclusion=paused-a choices=include,exclude" in paused_output
    assert "questions=decide whether to include paused source paused-a" in paused_output
    assert "next_action=resolve_questions" in paused_output

    accepted = [
        "--json", *common,
        "--accept-proposal",
        "--expires-at", "2026-08-14T18:00:00Z",
        "--include-paused-id", "paused-a",
        "--selected-alternative", "accept-compatible-groups",
        "--plan-state-path", "paused-plan.json",
        "--plan-source-path", "collections/paused-a.json",
        "--output", "paused-plan.json",
    ]
    assert main(accepted) == 0
    accepted_result = json.loads(capsys.readouterr().out)
    accepted_plan = accepted_result["identity"]["lifecycle_plan"]
    assert accepted_result["status"] == "completed"
    assert accepted_plan["unresolved_decisions"] == []
    assert accepted_plan["workflow_mappings"][0]["source_id"] == "paused-a"


def test_cli_q003_missing_capability_is_structured_blocker(tmp_path: Path, capsys) -> None:
    repository = tmp_path / "repository"
    state = tmp_path / "state"
    repository.mkdir()
    state.mkdir()
    source = repository / "observations.json"
    source.write_text(json.dumps(_observations(_item("daily-a"))), encoding="utf-8")
    code = main([
        "--json", "lifecycle", "plan", "--host-observations", str(source),
        "--actor", "test-agent", "--reason", "Q-003 fixture",
        "--repository-root", str(repository), "--state-root", str(state),
        "--source-root", str(SOURCE_ROOT),
    ])
    result = json.loads(capsys.readouterr().out)
    assert code == 1
    assert result["status"] == "blocked"
    assert "verify callable host discovery schemas (Q-003)" in result["identity"]["proposal"]["unresolved_decisions"]
    assert any(
        risk["code"] == "host_capability_unavailable"
        and risk["severity"] == "blocking"
        for risk in result["identity"]["proposal"]["risks"]
    )
    assert result["identity"]["proposal"]["next_action"] == "resolve_questions"
    assert result["identity"]["mutation_count"] == 0

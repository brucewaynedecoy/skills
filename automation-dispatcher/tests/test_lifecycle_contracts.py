from __future__ import annotations

import argparse
import base64
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import pkgutil
import shutil

import pytest

import automation_dispatcher
from automation_dispatcher.backup import create_backup, verify_backup
from automation_dispatcher.cli import build_parser, main
from automation_dispatcher.database import connect, migrate, schema_version
from automation_dispatcher.lifecycle_contracts import (
    HOST_ADAPTER_OPERATIONS,
    LIFECYCLE_COMMANDS,
    LIFECYCLE_STAGES,
    LifecycleContractError,
    assert_plan_current,
    authorize_host_mutation,
    canonical_json_bytes,
    contract_catalog,
    contract_schema,
    require_host_capabilities,
    resolve_manifest_locator,
    seal_artifact,
    validate_artifact,
    validate_artifact_path,
    validate_host_result,
    validate_transition,
)


FIXTURES = Path(__file__).parent / "fixtures"
COMPATIBILITY = FIXTURES / "compatibility"
HASH = "0" * 64
NOW = "2026-08-12T12:00:00Z"


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


def _plan() -> dict:
    plan = _artifact("lifecycle_plan")
    plan.update(
        plan_id="plan-1",
        source_snapshot_id="snapshot-1",
        source_snapshot_hash=HASH,
    )
    return seal_artifact(plan)


def _request() -> dict:
    request = _artifact("host_mutation_request")
    request.update(
        operation_id="operation-1",
        plan_id="plan-1",
        plan_hash=HASH,
        collection_id="collection-1",
        approval_id="approval-1",
        target={
            "kind": "automation",
            "id": "automation-1",
            "expected_revision": "revision-1",
            "expected_state_hash": HASH,
        },
        mutation={"action": "update", "fields": {"enabled": True}},
        actor="test",
        reason="approved test mutation",
    )
    return seal_artifact(request)


def _approval(request: dict, *, approval_id: str | None = None) -> dict:
    approval = _artifact("approval_envelope")
    approval.update(
        approval_id=approval_id or request["approval_id"],
        plan_id=request["plan_id"],
        plan_hash=request["plan_hash"],
        collection_id=request["collection_id"],
        expected_host_state_hash=request["target"]["expected_state_hash"],
        mutation_hashes=[request["content_hash"]],
        approved_at="2026-08-12T11:00:00Z",
        expires_at="2026-08-12T13:00:00Z",
    )
    return seal_artifact(approval)


def _invoke(capsys, *arguments: str) -> tuple[int, dict]:
    code = main([*arguments])
    captured = capsys.readouterr()
    return code, json.loads(captured.out or captured.err)


def test_catalog_exposes_versioned_schemas_and_canonical_hashes() -> None:
    catalog = contract_catalog()
    assert catalog["schema_version"] == 1
    assert tuple(catalog["lifecycle_namespace"]["subcommands"]) == LIFECYCLE_COMMANDS
    assert set(catalog["artifacts"]) == {
        "approval_envelope",
        "collection_manifest",
        "command_result",
        "discovery_snapshot",
        "host_capability_snapshot",
        "host_mutation_request",
        "host_mutation_result",
        "lifecycle_command",
        "lifecycle_plan",
        "progress_record",
        "readiness_report",
        "semantic_drift_report",
    }
    for artifact_type, metadata in catalog["artifacts"].items():
        assert metadata["schema_ref"].endswith(f"/$defs/{artifact_type}")
        assert metadata["storage_owner"]
        artifact = _artifact(artifact_type)
        assert validate_artifact(artifact_type, artifact) == artifact
    assert canonical_json_bytes({"z": "café", "a": 1}) == b'{"a":1,"z":"caf\xc3\xa9"}'


def test_lifecycle_stage_transitions_fail_closed() -> None:
    assert LIFECYCLE_STAGES == (
        "discover",
        "propose",
        "initialize",
        "shadow_validate",
        "cut_over",
        "operate_evolve",
    )
    validate_transition("discover", "propose")
    validate_transition("operate_evolve", "discover")
    with pytest.raises(LifecycleContractError, match="illegal lifecycle transition"):
        validate_transition("discover", "initialize")


def test_t16_rejects_stale_plans_and_mismatched_hashes() -> None:
    plan = _plan()
    with pytest.raises(LifecycleContractError) as stale:
        assert_plan_current(
            plan,
            expected_plan_id="plan-1",
            expected_plan_hash="1" * 64,
            observed_snapshot_hash=HASH,
        )
    assert stale.value.code == "stale_plan"

    tampered = deepcopy(plan)
    tampered["actor"] = "substituted"
    with pytest.raises(LifecycleContractError) as mismatch:
        validate_artifact("lifecycle_plan", tampered)
    assert mismatch.value.code == "content_hash_mismatch"


def test_t16_rejects_ambiguous_manifests_and_forbidden_paths(tmp_path: Path) -> None:
    explicit = tmp_path / "explicit.json"
    heartbeat = tmp_path / "heartbeat.json"
    registry = tmp_path / "registry.json"
    assert resolve_manifest_locator(
        explicit_paths=(explicit,),
        heartbeat_paths=(heartbeat,),
        registry_paths=(registry,),
    ) == explicit.resolve()
    assert resolve_manifest_locator(
        heartbeat_paths=(heartbeat,), registry_paths=(registry,)
    ) == heartbeat.resolve()

    with pytest.raises(LifecycleContractError) as ambiguous:
        resolve_manifest_locator(
            explicit_paths=(tmp_path / "a.json", tmp_path / "b.json")
        )
    assert ambiguous.value.code == "ambiguous_manifest"

    source_root = tmp_path / "source"
    with pytest.raises(LifecycleContractError) as forbidden:
        validate_artifact_path(
            source_root / "runtime" / "state.json",
            storage_owner="external_state",
            source_root=source_root,
        )
    assert forbidden.value.code == "forbidden_artifact_path"

    actual_root = tmp_path / "actual-state"
    actual_root.mkdir()
    linked_root = tmp_path / "linked-state"
    linked_root.symlink_to(actual_root, target_is_directory=True)
    with pytest.raises(LifecycleContractError) as symlinked:
        validate_artifact_path(
            linked_root / "state.json",
            storage_owner="external_state",
            source_root=source_root,
        )
    assert symlinked.value.code == "symlink_artifact_path"


def test_source_controlled_manifest_rejects_nonportable_database_locators() -> None:
    manifest = _artifact("collection_manifest")
    manifest["database_locator"] = {
        "kind": "task_working_directory_relative",
        "path": "state/dispatcher.sqlite3",
    }
    manifest = seal_artifact(manifest)
    assert validate_artifact("collection_manifest", manifest) == manifest

    invalid_locators = (
        {"kind": "explicit_absolute", "path": "/tmp/dispatcher.sqlite3"},
        {"kind": "task_working_directory_relative", "path": "/tmp/dispatcher.sqlite3"},
        {"kind": "task_working_directory_relative", "path": "../dispatcher.sqlite3"},
        {"kind": "task_working_directory_relative", "path": "C:\\state\\dispatcher.db"},
        {"kind": "task_working_directory_relative", "path": "\\\\server\\state.db"},
        {"kind": "task_working_directory_relative", "path": "file:///tmp/state.db"},
    )
    for locator in invalid_locators:
        invalid = deepcopy(manifest)
        invalid["database_locator"] = locator
        invalid = seal_artifact(invalid)
        with pytest.raises(LifecycleContractError):
            validate_artifact("collection_manifest", invalid)


def test_t16_rejects_unsupported_schema_and_sensitive_material() -> None:
    plan = json.loads(
        (FIXTURES / "lifecycle" / "v1" / "unsupported-schema-plan.json").read_text()
    )
    plan = seal_artifact(plan)
    with pytest.raises(LifecycleContractError) as unsupported:
        validate_artifact("lifecycle_plan", plan)
    assert unsupported.value.code == "unsupported_schema_version"

    for key in (
        "token",
        "api_token",
        "api_key",
        "accessToken",
        "authorization_header",
        "sessionCookie",
        "prompt_text",
        "rawPromptBody",
        "credential_blob",
        "signedUrl",
        "transcript_body",
    ):
        command = _request()
        command["mutation"]["fields"][key] = "must not persist"
        command = seal_artifact(command)
        with pytest.raises(LifecycleContractError) as sensitive:
            validate_artifact("host_mutation_request", command)
        assert sensitive.value.code == "sensitive_material_forbidden"

    stable_references = _request()
    stable_references["mutation"]["fields"].update(
        api_token_hash="a" * 64,
        prompt_id="prompt-1",
        transcript_hash="b" * 64,
        credential_identifier="credential-1",
    )
    stable_references = seal_artifact(stable_references)
    assert (
        validate_artifact("host_mutation_request", stable_references)
        == stable_references
    )


def test_t16_rejects_missing_capabilities_and_unapproved_host_mutation() -> None:
    snapshot = json.loads(
        (FIXTURES / "lifecycle" / "v1" / "host-capabilities-current.json").read_text()
    )
    assert {item["name"] for item in snapshot["capabilities"]} == set(
        HOST_ADAPTER_OPERATIONS
    )
    with pytest.raises(LifecycleContractError) as unavailable:
        require_host_capabilities(snapshot, ("tasks.list", "automations.read"))
    assert unavailable.value.code == "host_capability_unavailable"

    request = _request()
    approval = _approval(request, approval_id="another-approval")
    with pytest.raises(LifecycleContractError) as rejected:
        authorize_host_mutation(
            request,
            approval,
            observed_host_state_hash=HASH,
            observed_host_revision="revision-1",
            now=NOW,
        )
    assert rejected.value.code == "approval_mismatch"


def test_host_mutation_requires_fresh_revision_and_defines_create_semantics() -> None:
    request = _request()
    approval = _approval(request)
    authorize_host_mutation(
        request,
        approval,
        observed_host_state_hash=HASH,
        observed_host_revision="revision-1",
        now=NOW,
    )

    for observed_revision in ("revision-2", None):
        with pytest.raises(LifecycleContractError) as drifted:
            authorize_host_mutation(
                request,
                approval,
                observed_host_state_hash=HASH,
                observed_host_revision=observed_revision,
                now=NOW,
            )
        assert drifted.value.code == "host_revision_drift"

    missing_expected = deepcopy(request)
    missing_expected["target"]["expected_revision"] = None
    missing_expected = seal_artifact(missing_expected)
    with pytest.raises(LifecycleContractError) as missing:
        authorize_host_mutation(
            missing_expected,
            _approval(missing_expected),
            observed_host_state_hash=HASH,
            observed_host_revision=None,
            now=NOW,
        )
    assert missing.value.code == "expected_host_revision_missing"

    create = deepcopy(request)
    create["target"]["expected_revision"] = None
    create["mutation"]["action"] = "create"
    create = seal_artifact(create)
    create_approval = _approval(create)
    authorize_host_mutation(
        create,
        create_approval,
        observed_host_state_hash=HASH,
        observed_host_revision=None,
        now=NOW,
    )
    with pytest.raises(LifecycleContractError) as appeared:
        authorize_host_mutation(
            create,
            create_approval,
            observed_host_state_hash=HASH,
            observed_host_revision="revision-appeared",
            now=NOW,
        )
    assert appeared.value.code == "host_target_exists"

    invalid_create = deepcopy(request)
    invalid_create["mutation"]["action"] = "create"
    invalid_create = seal_artifact(invalid_create)
    with pytest.raises(LifecycleContractError) as invalid:
        authorize_host_mutation(
            invalid_create,
            _approval(invalid_create),
            observed_host_state_hash=HASH,
            observed_host_revision=None,
            now=NOW,
        )
    assert invalid.value.code == "create_revision_invalid"


def test_t16_rejects_incomplete_or_ambiguous_host_results() -> None:
    result = seal_artifact(
        json.loads(
            (FIXTURES / "lifecycle" / "v1" / "incomplete-host-result.json").read_text()
        )
    )
    with pytest.raises(LifecycleContractError) as incomplete:
        validate_host_result(result, request_hash=HASH)
    assert incomplete.value.code == "incomplete_host_result"

    result["status"] = "effect_unknown"
    result = seal_artifact(result)
    with pytest.raises(LifecycleContractError) as unknown:
        validate_host_result(result, request_hash=HASH)
    assert unknown.value.code == "host_effect_unknown"


def test_frozen_v2_database_opens_migrates_inspects_backs_up_and_dispatches(
    tmp_path: Path, capsys
) -> None:
    frozen = COMPATIBILITY / "collection-v2.sqlite3.gz.b64"
    database = tmp_path / "collection-v2.sqlite3"
    database.write_bytes(__import__("gzip").decompress(base64.b64decode(frozen.read_bytes())))

    definition_data = json.loads((FIXTURES / "daily-workflow.json").read_text())
    definition_data["revision"] = 2
    definition_data["description"] = "Isolated frozen compatibility workflow."
    definition_data.pop("content_hash", None)
    definition = tmp_path / "daily-workflow.json"
    definition.write_text(json.dumps(definition_data, sort_keys=True), encoding="utf-8")

    connection = connect(database)
    try:
        assert migrate(connection) == []
        assert schema_version(connection) == 2
        row = connection.execute(
            "SELECT dispatcher_id, current_revision FROM dispatchers"
        ).fetchone()
        assert tuple(row) == ("ops-collection", 1)
    finally:
        connection.close()

    backup = tmp_path / "backup" / "collection-v2.sqlite3"
    created = create_backup(database, backup)
    assert created["verified"] is True
    assert verify_backup(backup)["restore_verified"] is True

    common = ("--database", str(database), "--json")
    code, status = _invoke(capsys, *common, "status")
    assert code == 0, status
    assert status["status"] == "ok"

    code, routed = _invoke(
        capsys,
        *common,
        "route-revise",
        "--dispatcher-id",
        "ops-collection",
        "--destination-task-id",
        "task-daily",
        "--expected-working-directory",
        str(tmp_path.resolve()),
        "--actor",
        "compatibility-test",
        "--reason",
        "isolate frozen fixture route",
    )
    assert code == 0, routed
    assert routed["route_revision"] == 2

    code, revised = _invoke(
        capsys,
        *common,
        "revise",
        "--definition",
        str(definition),
        "--actor",
        "compatibility-test",
        "--reason",
        "isolate frozen fixture definition",
    )
    assert code == 0, revised
    assert revised["revision"] == 2

    observed = json.dumps(
        {
            "task_id": {
                "value": "task-daily",
                "source": "runtime",
                "assurance": "verified_config",
            },
            "working_directory": {
                "value": str(tmp_path.resolve()),
                "source": "runtime",
                "assurance": "verified_config",
            },
        }
    )
    code, dispatched = _invoke(
        capsys,
        *common,
        "run",
        "--dispatcher-id",
        "ops-collection",
        "--owner",
        "compatibility-test",
        "--observed",
        observed,
        "--at",
        "2030-01-01T12:30:00Z",
        "--start",
        "2030-01-01T11:30:00Z",
    )
    assert code == 0, dispatched
    assert dispatched["runs"][0]["status"] == "action_required"


def test_frozen_baseline_inventory_remains_available() -> None:
    baseline = json.loads((COMPATIBILITY / "baseline-v0.1.0.json").read_text())
    parser = build_parser()
    subcommands = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    assert set(baseline["cli_commands"]) <= set(subcommands.choices)
    assert set(subcommands.choices) - set(baseline["cli_commands"]) == {"lifecycle"}

    modules = {f"automation_dispatcher.{item.name}" for item in pkgutil.iter_modules(automation_dispatcher.__path__)}
    modules.add("automation_dispatcher.__init__")
    assert set(baseline["public_python_modules"]).issubset(modules)

    migration_root = Path(automation_dispatcher.__file__).parent / "migrations"
    observed = {
        path.name: sha256(path.read_bytes()).hexdigest()
        for path in migration_root.glob("*.sql")
    }
    assert observed == baseline["migration_checksums"]
    assert shutil.which("automation-dispatcher") or build_parser().prog == "automation-dispatcher"

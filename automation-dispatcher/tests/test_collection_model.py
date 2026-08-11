from __future__ import annotations

import json
from pathlib import Path
from threading import Barrier, Lock, Thread

import pytest

import automation_dispatcher.audit as audit_module
import automation_dispatcher.cli as cli_module
import automation_dispatcher.registry as registry_module
from automation_dispatcher.database import connect
from automation_dispatcher.registry import register_workflow, set_workflow_enabled

from test_cli import FIXTURE, init_arguments, invoke, next_due_window


def _definition(tmp_path: Path, workflow_id: str, dispatcher_id: str, task_id: str) -> Path:
    definition = json.loads(FIXTURE.read_text(encoding="utf-8"))
    definition.pop("content_hash", None)
    definition["workflow_id"] = workflow_id
    definition["name"] = workflow_id.replace("-", " ").title()
    definition["dispatcher_id"] = dispatcher_id
    definition["reporting"]["task_id"] = task_id
    path = tmp_path / f"{workflow_id}.json"
    definition["authority_refs"] = [path.name]
    definition["procedure"]["reference"] = path.name
    path.write_text(json.dumps(definition, sort_keys=True), encoding="utf-8")
    return path


def _observed(tmp_path: Path, task_id: str) -> str:
    return json.dumps(
        {
            "task_id": {
                "value": task_id,
                "source": "runtime",
                "assurance": "verified_config",
            },
            "working_directory": {
                "value": str(tmp_path),
                "source": "runtime",
                "assurance": "verified_config",
            },
        }
    )


def test_arbitrary_collection_schedule_fans_out_to_all_enabled_workflows(
    tmp_path: Path, capsys
) -> None:
    database = tmp_path / "collections.sqlite3"
    common = ("--database", str(database), "--json")
    dispatcher_id = "client-operations-2026"
    task_id = "project-planning-thread"
    code, initialized = invoke(
        capsys,
        *common,
        *init_arguments(tmp_path, dispatcher_id=dispatcher_id, task_id=task_id),
    )
    assert code == 0, initialized

    workflow_ids = ("review-open-items", "prepare-status-note")
    for workflow_id in workflow_ids:
        code, registered = invoke(
            capsys,
            *common,
            "register",
            "--definition", str(_definition(tmp_path, workflow_id, dispatcher_id, task_id)),
            "--actor", "test",
            "--reason", "collection fan-out fixture",
        )
        assert code == 0, registered

    at, start, _ = next_due_window()
    code, due = invoke(
        capsys,
        *common,
        "due",
        "--dispatcher-id", dispatcher_id,
        "--at", at,
        "--start", start,
    )
    assert code == 0, due
    assert {item["workflow_id"] for item in due["occurrences"]} == set(workflow_ids)
    assert len({item["scheduled_for"] for item in due["occurrences"]}) == 1
    assert {item["dispatcher_revision"] for item in due["occurrences"]} == {1}

    code, disabled = invoke(
        capsys,
        *common,
        "disable",
        workflow_ids[1],
        "--actor", "test",
        "--reason", "pause one workflow",
    )
    assert code == 0, disabled
    assert disabled["receipt"]["status"] == "pending"
    code, due = invoke(
        capsys,
        *common,
        "due",
        "--dispatcher-id", dispatcher_id,
        "--at", at,
        "--start", start,
    )
    assert code == 0, due
    assert [item["workflow_id"] for item in due["occurrences"]] == [workflow_ids[0]]


def test_schedule_revision_is_immutable_and_claims_pin_collection_revision(
    tmp_path: Path, capsys
) -> None:
    database = tmp_path / "revision.sqlite3"
    common = ("--database", str(database), "--json")
    dispatcher_id = "team-planning"
    task_id = "planning-home"
    code, initialized = invoke(
        capsys,
        *common,
        *init_arguments(tmp_path, dispatcher_id=dispatcher_id, task_id=task_id),
    )
    assert code == 0, initialized
    definition = _definition(tmp_path, "planning-summary", dispatcher_id, task_id)
    code, registered = invoke(
        capsys,
        *common,
        "register",
        "--definition", str(definition),
        "--actor", "test",
        "--reason", "revision fixture",
    )
    assert code == 0, registered

    observed = _observed(tmp_path, task_id)
    code, first = invoke(
        capsys,
        *common,
        "claim",
        "--workflow-id", "planning-summary",
        "--scheduled-for", "2026-01-01T12:00:00Z",
        "--owner", "before-revision",
        "--observed", observed,
    )
    assert code == 0, first

    revised_schedule = {"version": 2, "kind": "cron", "expression": "0 7 * * *"}
    code, revised = invoke(
        capsys,
        *common,
        "schedule-revise",
        "--dispatcher-id", dispatcher_id,
        "--schedule", json.dumps(revised_schedule),
        "--timezone", "America/Chicago",
        "--max-lateness-seconds", "3600",
        "--catch-up", json.dumps({"policy": "latest", "max_lookback_seconds": 86400}),
        "--heartbeat-schedule", json.dumps({"verified": True, "schedule": revised_schedule}),
        "--actor", "test",
        "--reason", "move the collection one hour later",
    )
    assert code == 0, revised
    assert revised["status"] == "schedule_revised"
    assert revised["revision"] == 2
    assert revised["receipt"]["status"] == "pending"

    code, second = invoke(
        capsys,
        *common,
        "claim",
        "--workflow-id", "planning-summary",
        "--scheduled-for", "2026-01-02T13:00:00Z",
        "--owner", "after-revision",
        "--observed", observed,
    )
    assert code == 0, second

    connection = connect(database)
    rows = connection.execute(
        "SELECT run_id, dispatcher_revision FROM runs ORDER BY scheduled_for"
    ).fetchall()
    assert [(row["run_id"], row["dispatcher_revision"]) for row in rows] == [
        (first["run_id"], 1),
        (second["run_id"], 2),
    ]
    revisions = connection.execute(
        "SELECT revision, normalized_config_json FROM dispatcher_revisions "
        "WHERE dispatcher_id = ? ORDER BY revision",
        (dispatcher_id,),
    ).fetchall()
    assert [row["revision"] for row in revisions] == [1, 2]
    assert json.loads(revisions[0]["normalized_config_json"])["schedule"]["expression"] == "0 6 * * *"
    assert json.loads(revisions[1]["normalized_config_json"])["schedule"]["expression"] == "0 7 * * *"
    connection.close()


def test_registration_does_not_assign_an_already_closed_collection_occurrence(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "registration-cutoff.sqlite3"
    common = ("--database", str(database), "--json")
    dispatcher_id = "registration-cutoff"
    task_id = "cutoff-task"
    monkeypatch.setattr(cli_module, "_utc_now", lambda: "2030-01-01T05:00:00Z")
    monkeypatch.setattr(audit_module, "utc_now", lambda: "2030-01-01T05:00:00Z")
    code, initialized = invoke(
        capsys,
        *common,
        *init_arguments(
            tmp_path,
            dispatcher_id=dispatcher_id,
            task_id=task_id,
            max_lateness_seconds=7200,
        ),
    )
    assert code == 0, initialized

    monkeypatch.setattr(registry_module, "_now", lambda: "2030-01-01T13:00:00Z")
    monkeypatch.setattr(audit_module, "utc_now", lambda: "2030-01-01T13:00:00Z")
    definition = _definition(tmp_path, "late-registration", dispatcher_id, task_id)
    code, registered = invoke(
        capsys,
        *common,
        "register",
        "--definition", str(definition),
        "--actor", "test",
        "--reason", "registered after the closed occurrence",
    )
    assert code == 0, registered

    code, due = invoke(
        capsys,
        *common,
        "due",
        "--dispatcher-id", dispatcher_id,
        "--at", "2030-01-01T13:30:00Z",
        "--start", "2030-01-01T11:30:00Z",
    )
    assert code == 0, due
    assert due["status"] == "no_due"


def test_schedule_revision_applies_only_from_its_effective_cutover(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "schedule-cutover.sqlite3"
    common = ("--database", str(database), "--json")
    dispatcher_id = "schedule-cutover"
    task_id = "schedule-task"
    monkeypatch.setattr(cli_module, "_utc_now", lambda: "2030-01-01T05:00:00Z")
    monkeypatch.setattr(registry_module, "_now", lambda: "2030-01-01T05:00:00Z")
    monkeypatch.setattr(audit_module, "utc_now", lambda: "2030-01-01T05:00:00Z")
    code, initialized = invoke(
        capsys,
        *common,
        *init_arguments(
            tmp_path,
            dispatcher_id=dispatcher_id,
            task_id=task_id,
            max_lateness_seconds=14400,
        ),
    )
    assert code == 0, initialized
    definition = _definition(tmp_path, "cutover-workflow", dispatcher_id, task_id)
    code, registered = invoke(
        capsys,
        *common,
        "register",
        "--definition", str(definition),
        "--actor", "test",
        "--reason", "schedule cutover fixture",
    )
    assert code == 0, registered
    code, claimed = invoke(
        capsys,
        *common,
        "claim",
        "--workflow-id", "cutover-workflow",
        "--scheduled-for", "2030-01-01T12:00:00Z",
        "--owner", "before-cutover",
        "--observed", _observed(tmp_path, task_id),
    )
    assert code == 0, claimed

    monkeypatch.setattr(registry_module, "_now", lambda: "2030-01-01T13:30:00Z")
    monkeypatch.setattr(audit_module, "utc_now", lambda: "2030-01-01T13:30:00Z")
    revised_schedule = {"version": 2, "kind": "cron", "expression": "0 7 * * *"}
    code, revised = invoke(
        capsys,
        *common,
        "schedule-revise",
        "--dispatcher-id", dispatcher_id,
        "--schedule", json.dumps(revised_schedule),
        "--timezone", "America/Chicago",
        "--max-lateness-seconds", "14400",
        "--catch-up", json.dumps({"policy": "latest", "max_lookback_seconds": 86400}),
        "--heartbeat-schedule", json.dumps({"verified": True, "schedule": revised_schedule}),
        "--actor", "test",
        "--reason", "effective after the new wall-clock time",
    )
    assert code == 0, revised
    code, due = invoke(
        capsys,
        *common,
        "due",
        "--dispatcher-id", dispatcher_id,
        "--at", "2030-01-01T14:00:00Z",
        "--start", "2030-01-01T11:00:00Z",
    )
    assert code == 0, due
    assert due["status"] == "no_due"


def test_configuration_mutation_rolls_back_when_its_receipt_cannot_be_persisted(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "atomic-receipt.sqlite3"
    common = ("--database", str(database), "--json")
    code, initialized = invoke(capsys, *common, *init_arguments(tmp_path))
    assert code == 0, initialized
    definition = _definition(tmp_path, "atomic-registration", "ops-collection", "task-daily")
    connection = connect(database)

    def fail_receipt(*args, **kwargs):
        raise RuntimeError("injected receipt failure")

    monkeypatch.setattr(registry_module, "create_receipt", fail_receipt)
    with pytest.raises(RuntimeError, match="injected receipt failure"):
        register_workflow(
            connection,
            definition,
            actor="test",
            reason="prove atomic registration receipt",
        )
    assert connection.execute(
        "SELECT COUNT(*) FROM workflows WHERE workflow_id = 'atomic-registration'"
    ).fetchone()[0] == 0
    assert connection.execute(
        "SELECT COUNT(*) FROM audit_events WHERE workflow_id = 'atomic-registration'"
    ).fetchone()[0] == 0
    connection.close()


def test_initialization_rolls_back_when_its_receipt_cannot_be_persisted(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "atomic-init.sqlite3"
    common = ("--database", str(database), "--json")

    def fail_receipt(*args, **kwargs):
        raise ValueError("injected init receipt failure")

    monkeypatch.setattr(cli_module, "create_receipt", fail_receipt)
    code, failed = invoke(capsys, *common, *init_arguments(tmp_path))
    assert code == 2, failed
    connection = connect(database)
    assert connection.execute("SELECT COUNT(*) FROM dispatchers").fetchone()[0] == 0
    assert connection.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] == 0
    assert connection.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] == 0
    connection.close()


def test_reenable_cutoff_prevents_retroactive_catch_up(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "reenable.sqlite3"
    common = ("--database", str(database), "--json")
    code, initialized = invoke(capsys, *common, *init_arguments(tmp_path, max_lateness_seconds=14400))
    assert code == 0, initialized
    definition = _definition(tmp_path, "reenabled-workflow", "ops-collection", "task-daily")
    code, registered = invoke(
        capsys,
        *common,
        "register",
        "--definition", str(definition),
        "--actor", "test",
        "--reason", "reenable fixture",
    )
    assert code == 0, registered
    connection = connect(database)
    monkeypatch.setattr(audit_module, "utc_now", lambda: "2030-01-01T11:00:00Z")
    set_workflow_enabled(
        connection,
        "reenabled-workflow",
        enabled=False,
        actor="test",
        reason="disabled before occurrence",
    )
    monkeypatch.setattr(audit_module, "utc_now", lambda: "2030-01-01T13:00:00Z")
    enabled = set_workflow_enabled(
        connection,
        "reenabled-workflow",
        enabled=True,
        actor="test",
        reason="enabled after occurrence",
    )
    assert enabled["receipt"]["status"] == "pending"
    connection.close()
    code, due = invoke(
        capsys,
        *common,
        "due",
        "--dispatcher-id", "ops-collection",
        "--at", "2030-01-01T13:30:00Z",
        "--start", "2030-01-01T11:30:00Z",
    )
    assert code == 0, due
    assert due["status"] == "no_due"


def test_revision_keeps_its_original_lateness_policy(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "revision-policy.sqlite3"
    common = ("--database", str(database), "--json")
    dispatcher_id = "revision-policy"
    task_id = "revision-policy-task"
    monkeypatch.setattr(cli_module, "_utc_now", lambda: "2030-01-01T00:00:00Z")
    monkeypatch.setattr(registry_module, "_now", lambda: "2030-01-01T00:00:00Z")
    monkeypatch.setattr(audit_module, "utc_now", lambda: "2030-01-01T00:00:00Z")
    code, initialized = invoke(
        capsys,
        *common,
        *init_arguments(
            tmp_path,
            dispatcher_id=dispatcher_id,
            task_id=task_id,
            max_lateness_seconds=3600,
            schedule_expression="0 1 * * *",
            timezone="UTC",
            catch_up_policy="all",
        ),
    )
    assert code == 0, initialized
    definition = _definition(tmp_path, "policy-workflow", dispatcher_id, task_id)
    code, registered = invoke(
        capsys,
        *common,
        "register",
        "--definition", str(definition),
        "--actor", "test",
        "--reason", "revision policy fixture",
    )
    assert code == 0, registered

    monkeypatch.setattr(registry_module, "_now", lambda: "2030-01-01T02:30:00Z")
    monkeypatch.setattr(audit_module, "utc_now", lambda: "2030-01-01T02:30:00Z")
    schedule = {"version": 2, "kind": "cron", "expression": "0 1 * * *"}
    code, revised = invoke(
        capsys,
        *common,
        "schedule-revise",
        "--dispatcher-id", dispatcher_id,
        "--schedule", json.dumps(schedule),
        "--timezone", "UTC",
        "--max-lateness-seconds", "14400",
        "--catch-up", json.dumps({"policy": "all", "max_lookback_seconds": 86400}),
        "--heartbeat-schedule", json.dumps({"verified": True, "schedule": schedule}),
        "--actor", "test",
        "--reason", "expand only the new revision policy",
    )
    assert code == 0, revised
    code, due = invoke(
        capsys,
        *common,
        "due",
        "--dispatcher-id", dispatcher_id,
        "--at", "2030-01-01T02:45:00Z",
        "--start", "2030-01-01T00:00:00Z",
    )
    assert code == 0, due
    assert due["status"] == "no_due"


def test_max_occurrences_is_applied_after_closed_runs_are_filtered(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "max-occurrences.sqlite3"
    common = ("--database", str(database), "--json")
    dispatcher_id = "max-occurrences"
    task_id = "max-occurrences-task"
    monkeypatch.setattr(cli_module, "_utc_now", lambda: "2030-01-01T00:00:00Z")
    monkeypatch.setattr(registry_module, "_now", lambda: "2030-01-01T00:00:00Z")
    monkeypatch.setattr(audit_module, "utc_now", lambda: "2030-01-01T00:00:00Z")
    code, initialized = invoke(
        capsys,
        *common,
        *init_arguments(
            tmp_path,
            dispatcher_id=dispatcher_id,
            task_id=task_id,
            max_lateness_seconds=14400,
            schedule_expression="0 * * * *",
            timezone="UTC",
            catch_up_policy="all",
        ),
    )
    assert code == 0, initialized
    definition = _definition(tmp_path, "bounded-workflow", dispatcher_id, task_id)
    code, registered = invoke(
        capsys,
        *common,
        "register",
        "--definition", str(definition),
        "--actor", "test",
        "--reason", "max occurrences fixture",
    )
    assert code == 0, registered
    code, claimed = invoke(
        capsys,
        *common,
        "claim",
        "--workflow-id", "bounded-workflow",
        "--scheduled-for", "2030-01-01T03:00:00Z",
        "--owner", "closed-newest",
        "--observed", _observed(tmp_path, task_id),
    )
    assert code == 0, claimed
    code, due = invoke(
        capsys,
        *common,
        "due",
        "--dispatcher-id", dispatcher_id,
        "--at", "2030-01-01T03:30:00Z",
        "--start", "2030-01-01T00:30:00Z",
        "--max-occurrences", "1",
    )
    assert code == 0, due
    assert [item["scheduled_for"] for item in due["occurrences"]] == [
        "2030-01-01T02:00:00Z"
    ]


def test_latest_policy_is_applied_after_closed_runs_are_filtered(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "latest-policy.sqlite3"
    common = ("--database", str(database), "--json")
    dispatcher_id = "latest-policy"
    task_id = "latest-policy-task"
    monkeypatch.setattr(cli_module, "_utc_now", lambda: "2030-01-01T00:00:00Z")
    monkeypatch.setattr(registry_module, "_now", lambda: "2030-01-01T00:00:00Z")
    monkeypatch.setattr(audit_module, "utc_now", lambda: "2030-01-01T00:00:00Z")
    code, initialized = invoke(
        capsys,
        *common,
        *init_arguments(
            tmp_path,
            dispatcher_id=dispatcher_id,
            task_id=task_id,
            max_lateness_seconds=14400,
            schedule_expression="0 * * * *",
            timezone="UTC",
            catch_up_policy="latest",
        ),
    )
    assert code == 0, initialized
    definition = _definition(tmp_path, "latest-workflow", dispatcher_id, task_id)
    code, registered = invoke(
        capsys,
        *common,
        "register",
        "--definition", str(definition),
        "--actor", "test",
        "--reason", "latest policy fixture",
    )
    assert code == 0, registered
    code, claimed = invoke(
        capsys,
        *common,
        "claim",
        "--workflow-id", "latest-workflow",
        "--scheduled-for", "2030-01-01T03:00:00Z",
        "--owner", "closed-newest",
        "--observed", _observed(tmp_path, task_id),
    )
    assert code == 0, claimed
    code, due = invoke(
        capsys,
        *common,
        "due",
        "--dispatcher-id", dispatcher_id,
        "--at", "2030-01-01T03:30:00Z",
        "--start", "2030-01-01T00:30:00Z",
    )
    assert code == 0, due
    assert [item["scheduled_for"] for item in due["occurrences"]] == [
        "2030-01-01T02:00:00Z"
    ]


def test_concurrent_duplicate_enable_is_idempotent(tmp_path: Path, capsys) -> None:
    database = tmp_path / "concurrent-enable.sqlite3"
    common = ("--database", str(database), "--json")
    code, initialized = invoke(capsys, *common, *init_arguments(tmp_path))
    assert code == 0, initialized
    definition = _definition(tmp_path, "concurrent-workflow", "ops-collection", "task-daily")
    code, registered = invoke(
        capsys,
        *common,
        "register",
        "--definition", str(definition),
        "--actor", "test",
        "--reason", "concurrent enable fixture",
    )
    assert code == 0, registered
    connection = connect(database)
    set_workflow_enabled(
        connection,
        "concurrent-workflow",
        enabled=False,
        actor="test",
        reason="prepare concurrent enable",
    )
    connection.close()

    barrier = Barrier(2)
    lock = Lock()
    statuses: list[str] = []
    errors: list[BaseException] = []

    def enable() -> None:
        worker = connect(database)
        try:
            barrier.wait()
            result = set_workflow_enabled(
                worker,
                "concurrent-workflow",
                enabled=True,
                actor="test",
                reason="concurrent enable",
            )
            with lock:
                statuses.append(result["status"])
        except BaseException as exc:
            with lock:
                errors.append(exc)
        finally:
            worker.close()

    threads = [Thread(target=enable), Thread(target=enable)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert sorted(statuses) == ["already_enabled", "updated"]
    connection = connect(database)
    assert connection.execute(
        "SELECT COUNT(*) FROM audit_events "
        "WHERE workflow_id = 'concurrent-workflow' AND event_type = 'workflow_enabled'"
    ).fetchone()[0] == 1
    connection.close()


def test_unverified_heartbeat_fails_closed_before_any_run_is_claimed(
    tmp_path: Path, capsys
) -> None:
    database = tmp_path / "unverified.sqlite3"
    common = ("--database", str(database), "--json")
    dispatcher_id = "unverified-collection"
    task_id = "unverified-task"
    code, initialized = invoke(
        capsys,
        *common,
        *init_arguments(
            tmp_path,
            dispatcher_id=dispatcher_id,
            task_id=task_id,
            heartbeat_schedule={"verified": False},
        ),
    )
    assert code == 0, initialized
    definition = _definition(tmp_path, "unverified-workflow", dispatcher_id, task_id)
    code, registered = invoke(
        capsys,
        *common,
        "register",
        "--definition", str(definition),
        "--actor", "test",
        "--reason", "unverified heartbeat fixture",
    )
    assert code == 0, registered

    at, start, _ = next_due_window()
    code, result = invoke(
        capsys,
        *common,
        "run",
        "--dispatcher-id", dispatcher_id,
        "--owner", "test",
        "--observed", _observed(tmp_path, task_id),
        "--at", at,
        "--start", start,
    )
    assert code == 1, result
    assert result["status"] == "reconciliation_required"
    connection = connect(database)
    assert connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
    connection.close()

from __future__ import annotations

import json
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from automation_dispatcher.cli import main


FIXTURE = Path(__file__).parent / "fixtures" / "daily-workflow.json"


def init_arguments(
    tmp_path: Path,
    *,
    dispatcher_id: str = "ops-collection",
    task_id: str = "task-daily",
    heartbeat_schedule: dict | None = None,
    max_lateness_seconds: int = 3600,
    schedule_expression: str = "0 6 * * *",
    timezone: str = "America/Chicago",
    catch_up_policy: str = "latest",
    max_lookback_seconds: int = 86400,
) -> tuple[str, ...]:
    schedule = {"version": 2, "kind": "cron", "expression": schedule_expression}
    heartbeat = heartbeat_schedule or {"verified": True, "schedule": schedule}
    return (
        "init",
        "--dispatcher-id", dispatcher_id,
        "--name", "Operations collection",
        "--description", "Test workflow collection",
        "--schedule", json.dumps(schedule),
        "--max-lateness-seconds", str(max_lateness_seconds),
        "--catch-up", json.dumps({
            "policy": catch_up_policy,
            "max_lookback_seconds": max_lookback_seconds,
        }),
        "--expected-task-id", task_id,
        "--expected-working-directory", str(tmp_path),
        "--timezone", timezone,
        "--heartbeat-schedule", json.dumps(heartbeat),
        "--actor", "test",
        "--reason", "test initialization",
    )


def next_due_window(*, hour: int = 6) -> tuple[str, str, str]:
    zone = ZoneInfo("America/Chicago")
    local_now = datetime.now(zone)
    scheduled_local = datetime.combine(local_now.date(), time(hour), tzinfo=zone)
    if scheduled_local <= local_now + timedelta(minutes=1):
        scheduled_local += timedelta(days=1)
    scheduled = scheduled_local.astimezone(UTC)
    at = scheduled + timedelta(minutes=30)
    start = scheduled - timedelta(minutes=30)
    def render(value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")

    return render(at), render(start), render(scheduled)


def invoke(capsys, *arguments: str) -> tuple[int, dict]:
    code = main([*arguments])
    captured = capsys.readouterr()
    stream = captured.out or captured.err
    return code, json.loads(stream)


def test_cli_init_register_due_claim_complete_and_receipt(tmp_path: Path, capsys) -> None:
    database = tmp_path / "daily.sqlite3"
    common = ("--database", str(database), "--json")
    code, initialized = invoke(
        capsys,
        *common,
        *init_arguments(tmp_path),
    )
    assert code == 0
    assert initialized["status"] == "initialized"
    assert initialized["cli_version"]
    assert initialized["receipt"]["status"] == "pending"

    code, registered = invoke(
        capsys,
        *common,
        "register",
        "--definition", str(FIXTURE),
        "--actor", "test",
        "--reason", "test registration",
    )
    assert code == 0
    assert registered["status"] == "registered"
    assert registered["event_id"]
    assert registered["receipt"]["status"] == "pending"
    assert registered["heartbeat_reconciliation"]["status"] == "covered"

    at, start, _ = next_due_window()
    code, due = invoke(
        capsys,
        *common,
        "due",
        "--dispatcher-id", "ops-collection",
        "--at", at,
        "--start", start,
    )
    assert code == 0
    assert due["status"] == "due"
    scheduled_for = due["occurrences"][0]["scheduled_for"]
    observed = json.dumps(
        {
            "task_id": {"value": "task-daily", "source": "runtime", "assurance": "verified_config"},
            "working_directory": {"value": str(tmp_path), "source": "runtime", "assurance": "verified_config"},
        }
    )

    code, claimed = invoke(
        capsys,
        *common,
        "claim",
        "--workflow-id", "fixture-daily-review",
        "--scheduled-for", scheduled_for,
        "--owner", "test",
        "--observed", observed,
    )
    assert code == 0
    assert claimed["status"] == "claimed"

    code, completed = invoke(
        capsys,
        *common,
        "complete",
        claimed["run_id"],
        "--actor", "test",
        "--summary", "fixture completed",
    )
    assert code == 0
    assert completed["status"] == "succeeded"
    receipt = completed["receipt"]
    assert receipt["status"] == "pending"
    assert "posting_payload" not in receipt
    assert "rendered_content" not in receipt

    code, retried = invoke(
        capsys, *common, "receipt-retry", receipt["receipt_id"], "--actor", "test"
    )
    assert code == 0
    assert retried["content_hash"] == receipt["content_hash"]
    assert retried["event_id"]

    code, acknowledged = invoke(
        capsys,
        *common,
        "receipt-ack",
        receipt["receipt_id"],
        "--external-message-id", "message-1",
        "--actor", "test",
    )
    assert code == 0
    assert acknowledged["status"] == "posted"


def test_route_check_fails_closed_before_claim(tmp_path: Path, capsys) -> None:
    database = tmp_path / "daily.sqlite3"
    common = ("--database", str(database), "--json")
    code, _ = invoke(
        capsys,
        *common,
        *init_arguments(tmp_path),
    )
    assert code == 0
    observed = json.dumps(
        {
            "task_id": {"value": "wrong-task", "source": "runtime", "assurance": "attested"},
            "working_directory": {"value": str(tmp_path), "source": "runtime", "assurance": "attested"},
        }
    )
    code, checked = invoke(
        capsys,
        *common,
        "route-check",
        "--dispatcher-id", "ops-collection",
        "--observed", observed,
        "--actor", "test",
    )
    assert code == 1
    assert checked["status"] == "route_mismatch"
    assert checked["event_id"]
    assert checked["receipt"]["status"] == "pending"


def test_route_revision_is_immutable_and_immediately_authoritative(tmp_path: Path, capsys) -> None:
    database = tmp_path / "daily.sqlite3"
    common = ("--database", str(database), "--json")
    code, _ = invoke(
        capsys, *common, *init_arguments(tmp_path, task_id="task-old"),
    )
    assert code == 0
    definition = json.loads(FIXTURE.read_text(encoding="utf-8"))
    definition.pop("content_hash", None)
    definition["reporting"]["task_id"] = "task-old"
    definition["authority_refs"] = ["route-workflow.json"]
    definition["procedure"]["reference"] = "route-workflow.json"
    definition_path = tmp_path / "route-workflow.json"
    definition_path.write_text(json.dumps(definition), encoding="utf-8")
    code, registration = invoke(
        capsys, *common, "register", "--definition", str(definition_path),
        "--actor", "test", "--reason", "old route workflow",
    )
    assert code == 0, registration
    code, revised = invoke(
        capsys, *common, "route-revise",
        "--dispatcher-id", "ops-collection", "--destination-task-id", "task-new",
        "--expected-working-directory", str(tmp_path),
        "--actor", "test", "--reason", "intentional cutover",
    )
    assert code == 0
    assert revised["route_revision"] == 2
    assert revised["workflow_reconciliation_required"] == ["fixture-daily-review"]
    observed = json.dumps({
        "task_id": {"value": "task-new", "source": "runtime", "assurance": "verified_config"},
        "working_directory": {"value": str(tmp_path), "source": "runtime", "assurance": "verified_config"},
    })
    code, checked = invoke(
        capsys, *common, "route-check", "--dispatcher-id", "ops-collection",
        "--observed", observed, "--actor", "test",
    )
    assert code == 0
    assert checked["ok"] is True
    at, start, _ = next_due_window()
    code, blocked = invoke(
        capsys, *common, "run", "--dispatcher-id", "ops-collection",
        "--owner", "test", "--observed", observed,
        "--at", at, "--start", start,
    )
    assert code == 1
    assert blocked["runs"][0]["status"] == "definition_invalid"
    assert blocked["runs"][0]["receipt"]["destination_task_id"] == "task-new"


def test_verified_heartbeat_schedule_must_cover_max_lateness(tmp_path: Path, capsys) -> None:
    database = tmp_path / "daily.sqlite3"
    common = ("--database", str(database), "--json")
    schedule = json.dumps({
        "verified": True,
        "slots": [{
            "weekdays": [
                "monday", "tuesday", "wednesday", "thursday",
                "friday", "saturday", "sunday",
            ],
            "time": "23:59",
        }],
    })
    code, rejected = invoke(
        capsys,
        *common,
        *init_arguments(tmp_path, heartbeat_schedule=json.loads(schedule)),
    )
    assert code == 2
    assert rejected["status"] == "error"
    assert "does not cover" in rejected["message"]
    assert rejected["database_path"] == str(database)
    assert rejected["cli_version"]
    assert rejected["source_revision"]


def test_external_effect_nonzero_exit_is_effect_unknown(tmp_path: Path, capsys) -> None:
    script = tmp_path / "external_effect.py"
    script.write_text("raise SystemExit(1)\n", encoding="utf-8")
    definition = json.loads(FIXTURE.read_text(encoding="utf-8"))
    definition.pop("content_hash", None)
    definition["authority_refs"] = ["external-workflow.json"]
    definition["procedure"] = {
        "kind": "script",
        "reference": str(script),
        "external_effect": {"mode": "idempotency_key", "idempotency_key": "occurrence"},
    }
    definition_path = tmp_path / "external-workflow.json"
    definition_path.write_text(json.dumps(definition), encoding="utf-8")
    database = tmp_path / "daily.sqlite3"
    common = ("--database", str(database), "--json")
    code, registered = invoke(
        capsys, *common, *init_arguments(tmp_path),
    )
    assert code == 0, registered
    code, registration = invoke(
        capsys, *common, "register", "--definition", str(definition_path),
        "--actor", "test", "--reason", "external effect workflow",
    )
    assert code == 0, registration
    observed = json.dumps({
        "task_id": {"value": "task-daily", "source": "runtime", "assurance": "verified_config"},
        "working_directory": {"value": str(tmp_path), "source": "runtime", "assurance": "verified_config"},
    })
    at, start, _ = next_due_window()
    code, result = invoke(
        capsys, *common, "run", "--dispatcher-id", "ops-collection",
        "--owner", "test", "--observed", observed,
        "--at", at, "--start", start,
        "--approved-root", str(tmp_path),
    )
    assert code == 1
    assert result["runs"][0]["status"] == "effect_unknown"
    assert result["runs"][0]["run"]["reconciliation_state"] == "ambiguous"

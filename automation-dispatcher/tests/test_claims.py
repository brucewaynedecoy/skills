from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from automation_dispatcher.claims import (
    ClaimError,
    claim_occurrence,
    complete_run,
    mark_effect_started,
    mark_running,
    recover_run,
)
from automation_dispatcher.database import connect, initialize_database
from automation_dispatcher.registry import (
    dispatcher_configuration_hash,
    normalize_dispatcher_configuration,
    register_workflow,
    revise_workflow,
)


FIXTURE = Path(__file__).parent / "fixtures" / "daily-workflow.json"


def configured_database(tmp_path: Path) -> Path:
    database = tmp_path / "ops-collection.sqlite3"
    initialize_database(database)
    connection = connect(database)
    now = "2026-01-01T00:00:00Z"
    config = normalize_dispatcher_configuration(
        {
            "dispatcher_id": "ops-collection",
            "name": "Operations collection",
            "description": "Deterministic test collection",
            "timezone": "America/Chicago",
            "schedule": "0 6 * * *",
            "max_lateness_seconds": 3600,
            "catch_up": {"policy": "latest", "max_lookback_seconds": 86400},
            "heartbeat_schedule": {"verified": True, "schedule": "0 6 * * *"},
            "enabled": True,
        }
    )
    config_json = json.dumps(config, sort_keys=True, separators=(",", ":"))
    connection.execute(
        """
        INSERT INTO dispatchers (
            dispatcher_id, name, description, current_revision, schedule_json,
            expected_task_id,
            expected_working_directory, default_reporting_task_id,
            heartbeat_schedule_json, timezone, max_lateness_seconds,
            catch_up_policy, max_lookback_seconds, created_at, updated_at
        ) VALUES (?, ?, ?, 1, ?, 'task-daily', ?, 'task-daily', ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            config["dispatcher_id"], config["name"], config["description"],
            json.dumps(config["schedule"], sort_keys=True, separators=(",", ":")),
            str(tmp_path),
            json.dumps(config["heartbeat_schedule"], sort_keys=True, separators=(",", ":")),
            config["timezone"], config["max_lateness_seconds"],
            config["catch_up"]["policy"], config["catch_up"]["max_lookback_seconds"],
            now, now,
        ),
    )
    connection.execute(
        """INSERT INTO dispatcher_revisions (
               dispatcher_id, revision, normalized_config_json, config_hash,
               actor, reason, effective_at, created_at
           ) VALUES (?, 1, ?, ?, 'test', 'fixture setup', ?, ?)""",
        (
            config["dispatcher_id"], config_json,
            dispatcher_configuration_hash(config), now, now,
        ),
    )
    connection.commit()
    register_workflow(
        connection, FIXTURE, actor="test", reason="fixture registration"
    )
    connection.close()
    return database


def test_two_simultaneous_claims_produce_one_owner(tmp_path: Path) -> None:
    database = configured_database(tmp_path)
    barrier = threading.Barrier(2)
    results: list[dict] = []

    def worker(owner: str) -> None:
        connection = connect(database)
        try:
            barrier.wait()
            results.append(
                claim_occurrence(
                    connection,
                    "fixture-daily-review",
                    "2026-01-01T12:00:00Z",
                    claim_owner=owner,
                )
            )
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(owner,)) for owner in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(result["status"] for result in results) == ["already_claimed", "claimed"]
    connection = connect(database)
    assert connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM audit_events WHERE event_type='run_claimed'").fetchone()[0] == 1
    connection.close()


def test_revision_does_not_duplicate_an_occurrence(tmp_path: Path) -> None:
    database = configured_database(tmp_path)
    connection = connect(database)
    first = claim_occurrence(
        connection,
        "fixture-daily-review",
        "2026-01-01T12:00:00Z",
        claim_owner="first",
    )
    revised_path = tmp_path / "daily-workflow.json"
    revised = json.loads(FIXTURE.read_text(encoding="utf-8"))
    revised["revision"] = 2
    revised["description"] = "Revised fixture workflow."
    revised_path.write_text(json.dumps(revised), encoding="utf-8")
    revise_workflow(connection, revised_path, actor="test", reason="new description")
    second = claim_occurrence(
        connection,
        "fixture-daily-review",
        "2026-01-01T12:00:00Z",
        claim_owner="second",
    )
    assert second["status"] == "already_claimed"
    assert second["run_id"] == first["run_id"]
    connection.close()


def test_expired_claim_recovery_preserves_attempt_lineage(tmp_path: Path) -> None:
    database = configured_database(tmp_path)
    connection = connect(database)
    claimed_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    claim = claim_occurrence(
        connection,
        "fixture-daily-review",
        claimed_at,
        claim_owner="first",
        now=claimed_at,
    )
    recovered = recover_run(
        connection,
        claim["run_id"],
        new_owner="second",
        reason="expired lease",
        now=claimed_at + timedelta(hours=1),
    )
    assert recovered["status"] == "recovered"
    assert recovered["run"]["attempt"] == 2
    assert recovered["run"]["prior_claim_owner"] == "first"
    assert recovered["run"]["claim_owner"] == "second"
    connection.close()


def test_ambiguous_external_effect_fails_closed(tmp_path: Path) -> None:
    database = configured_database(tmp_path)
    connection = connect(database)
    claimed_at = datetime.now(UTC)
    claim = claim_occurrence(
        connection,
        "fixture-daily-review",
        claimed_at,
        claim_owner="first",
        now=claimed_at,
    )
    mark_running(connection, claim["run_id"], claim_owner="first")
    mark_effect_started(connection, claim["run_id"], actor="first")
    recovered = recover_run(
        connection,
        claim["run_id"],
        new_owner="second",
        reason="process disappeared after effect start",
        now=claimed_at + timedelta(hours=1),
    )
    assert recovered["status"] == "effect_unknown"
    assert connection.execute(
        "SELECT state FROM runs WHERE run_id=?", (claim["run_id"],)
    ).fetchone()[0] == "effect_unknown"
    connection.close()


def test_recovery_fences_stale_owner_and_expired_lease(tmp_path: Path) -> None:
    database = configured_database(tmp_path)
    connection = connect(database)
    claimed_at = datetime.now(UTC) - timedelta(hours=2)
    claim = claim_occurrence(
        connection,
        "fixture-daily-review",
        "2026-01-01T12:00:00Z",
        claim_owner="first",
        now=claimed_at,
    )
    with pytest.raises(ClaimError, match="lease expired"):
        mark_running(connection, claim["run_id"], claim_owner="first")
    recovered = recover_run(
        connection,
        claim["run_id"],
        new_owner="second",
        reason="expired owner fence",
        now=datetime.now(UTC),
    )
    with pytest.raises(ClaimError, match="stale worker"):
        complete_run(connection, claim["run_id"], actor="first", summary="stale")
    completed = complete_run(
        connection,
        recovered["run_id"],
        actor="second",
        summary="new owner",
        persist_receipt=True,
    )
    assert completed["status"] == "succeeded"
    assert connection.execute(
        "SELECT COUNT(*) FROM receipts WHERE run_id = ?", (claim["run_id"],)
    ).fetchone()[0] == 1
    connection.close()


def test_effect_ambiguity_precedes_retry_exhaustion(tmp_path: Path) -> None:
    database = configured_database(tmp_path)
    connection = connect(database)
    claimed_at = datetime.now(UTC) - timedelta(hours=1)
    claim = claim_occurrence(
        connection,
        "fixture-daily-review",
        "2026-01-01T12:00:00Z",
        claim_owner="first",
        now=claimed_at,
    )
    connection.execute(
        "UPDATE runs SET state='running', reconciliation_state='effect_started', attempt=2 WHERE run_id=?",
        (claim["run_id"],),
    )
    connection.commit()
    result = recover_run(
        connection,
        claim["run_id"],
        new_owner="operator",
        reason="ambiguous exhausted attempt",
        now=datetime.now(UTC),
    )
    assert result["status"] == "effect_unknown"
    connection.close()


def test_retry_limit_exhaustion_abandons_occurrence(tmp_path: Path) -> None:
    database = configured_database(tmp_path)
    connection = connect(database)
    claimed_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    claim = claim_occurrence(
        connection,
        "fixture-daily-review",
        claimed_at,
        claim_owner="first",
        now=claimed_at,
    )
    recover_run(
        connection,
        claim["run_id"],
        new_owner="second",
        reason="first recovery",
        now=claimed_at + timedelta(hours=1),
    )
    exhausted = recover_run(
        connection,
        claim["run_id"],
        new_owner="third",
        reason="retry exhausted",
        now=claimed_at + timedelta(hours=2),
    )
    assert exhausted["status"] == "abandoned"
    assert connection.execute(
        "SELECT error_class FROM runs WHERE run_id=?", (claim["run_id"],)
    ).fetchone()[0] == "retry_limit_exhausted"
    connection.close()

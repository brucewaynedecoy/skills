from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import tarfile
import time
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath

import pytest

from automation_dispatcher.claims import (
    claim_occurrence,
    complete_run,
    mark_effect_started,
    mark_running,
    recover_run,
)
from automation_dispatcher.database import connect
from automation_dispatcher.registry import register_workflow
from automation_dispatcher.scheduling import collection_occurrences_between

from test_claims import configured_database
from test_cli import FIXTURE, init_arguments, invoke, next_due_window


ROOT = Path(__file__).resolve().parents[1]


def _definition_copy(tmp_path: Path, *, name: str = "workflow.json") -> tuple[Path, dict]:
    definition = json.loads(FIXTURE.read_text(encoding="utf-8"))
    definition.pop("content_hash", None)
    definition["authority_refs"] = [name]
    definition["procedure"]["reference"] = name
    path = tmp_path / name
    return path, definition


def _write_definition(path: Path, definition: dict) -> None:
    path.write_text(json.dumps(definition, sort_keys=True), encoding="utf-8")


def _external_effect_database(tmp_path: Path) -> Path:
    database = configured_database(tmp_path)
    connection = connect(database)
    definition_path, definition = _definition_copy(tmp_path, name="effect-workflow.json")
    definition["revision"] = 2
    definition["description"] = "Fixture with an idempotent external effect contract."
    definition["procedure"]["external_effect"] = {
        "mode": "idempotency_key",
        "idempotency_key": "occurrence",
    }
    _write_definition(definition_path, definition)
    from automation_dispatcher.registry import revise_workflow

    revise_workflow(connection, definition_path, actor="test", reason="effect crash fixture")
    connection.close()
    return database


def test_dst_gap_adjustment_is_persisted_in_claim_audit_metadata(tmp_path: Path) -> None:
    database = configured_database(tmp_path)
    occurrence = collection_occurrences_between(
        {
            "timezone": "America/Chicago",
            "schedule": "30 2 * * *",
        },
        "2026-03-08T06:00:00Z",
        "2026-03-08T10:00:00Z",
    )[0]

    connection = connect(database)
    claim = claim_occurrence(
        connection,
        "fixture-daily-review",
        occurrence["scheduled_for"],
        claim_owner="gap-test",
        occurrence_metadata=occurrence,
    )
    payload = json.loads(
        connection.execute(
            "SELECT payload_json FROM audit_events WHERE event_id = ?",
            (claim["event"]["event_id"],),
        ).fetchone()[0]
    )
    assert payload["occurrence_metadata"]["adjustment"] == {
        "kind": "gap_advanced",
        "from_local": "2026-03-08T02:30:00",
        "to_local": "2026-03-08T03:00:00",
    }
    assert payload["occurrence_metadata"]["effective_local"] == "2026-03-08T03:00:00"
    connection.close()


def test_writer_contention_returns_sqlite_busy_within_a_bounded_timeout(tmp_path: Path) -> None:
    database = configured_database(tmp_path)
    writer = connect(database)
    contender = connect(database)
    contender.execute("PRAGMA busy_timeout = 100")
    writer.execute("BEGIN IMMEDIATE")

    started = time.monotonic()
    with pytest.raises(sqlite3.OperationalError, match="locked"):
        claim_occurrence(
            contender,
            "fixture-daily-review",
            "2026-01-01T12:00:00Z",
            claim_owner="contender",
        )
    elapsed = time.monotonic() - started

    assert contender.execute("PRAGMA busy_timeout").fetchone()[0] == 100
    assert elapsed < 1.0
    writer.rollback()
    assert writer.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
    contender.close()
    writer.close()


def test_duplicate_full_heartbeat_does_not_duplicate_run_receipt_or_effect(
    tmp_path: Path, capsys
) -> None:
    effect_log = tmp_path / "effect.log"
    script = tmp_path / "effect.py"
    script.write_text(
        "from pathlib import Path\n"
        "import os\n"
        "with Path(__file__).with_name('effect.log').open('a', encoding='utf-8') as stream:\n"
        "    stream.write(os.environ['AUTOMATION_DISPATCHER_OCCURRENCE_KEY'] + '\\n')\n"
        "print('effect complete')\n",
        encoding="utf-8",
    )
    definition_path, definition = _definition_copy(tmp_path, name="duplicate-workflow.json")
    definition["authority_refs"] = [definition_path.name]
    definition["procedure"] = {
        "kind": "script",
        "reference": script.name,
        "external_effect": {
            "mode": "idempotency_key",
            "idempotency_key": "occurrence",
        },
    }
    _write_definition(definition_path, definition)

    database = tmp_path / "daily.sqlite3"
    common = ("--database", str(database), "--json")
    code, initialized = invoke(
        capsys,
        *common,
        *init_arguments(tmp_path),
    )
    assert code == 0, initialized
    code, registered = invoke(
        capsys,
        *common,
        "register",
        "--definition", str(definition_path),
        "--actor", "test",
        "--reason", "duplicate heartbeat fixture",
    )
    assert code == 0, registered
    observed = json.dumps(
        {
            "task_id": {
                "value": "task-daily",
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
    at, start, _ = next_due_window()
    run_args = (
        *common,
        "run",
        "--dispatcher-id", "ops-collection",
        "--owner", "heartbeat",
        "--observed", observed,
        "--at", at,
        "--start", start,
        "--approved-root", str(tmp_path),
    )

    first_code, first = invoke(capsys, *run_args)
    second_code, second = invoke(capsys, *run_args)
    assert first_code == 0, first
    assert first["runs"][0]["status"] == "succeeded"
    assert second_code == 0, second
    assert second["status"] == "no_due"
    assert effect_log.read_text(encoding="utf-8").splitlines() == [
        first["runs"][0]["run"]["occurrence_key"]
    ]

    connection = connect(database)
    assert connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM receipts WHERE run_id IS NOT NULL").fetchone()[0] == 1
    assert connection.execute(
        "SELECT COUNT(*) FROM audit_events WHERE event_type = 'external_effect_started'"
    ).fetchone()[0] == 1
    connection.close()


def test_crash_before_effect_recovers_same_run_without_ambiguity(tmp_path: Path) -> None:
    database = configured_database(tmp_path)
    connection = connect(database)
    claimed_at = datetime.now(UTC)
    claim = claim_occurrence(
        connection,
        "fixture-daily-review",
        "2026-01-01T12:00:00Z",
        claim_owner="first",
        now=claimed_at,
    )
    mark_running(connection, claim["run_id"], claim_owner="first")

    recovered = recover_run(
        connection,
        claim["run_id"],
        new_owner="second",
        reason="crash before external effect",
        now=claimed_at + timedelta(hours=1),
    )
    assert recovered["status"] == "recovered"
    assert recovered["run"]["run_id"] == claim["run_id"]
    assert recovered["run"]["attempt"] == 2
    assert recovered["run"]["reconciliation_state"] == "not_started"
    assert connection.execute(
        "SELECT COUNT(*) FROM audit_events WHERE run_id = ? AND event_type = 'external_effect_unknown'",
        (claim["run_id"],),
    ).fetchone()[0] == 0
    connection.close()


def test_crash_after_idempotent_effect_reconciles_without_reexecution(tmp_path: Path) -> None:
    database = _external_effect_database(tmp_path)
    connection = connect(database)
    claimed_at = datetime.now(UTC)
    claim = claim_occurrence(
        connection,
        "fixture-daily-review",
        "2026-01-01T12:00:00Z",
        claim_owner="first",
        now=claimed_at,
    )
    mark_running(connection, claim["run_id"], claim_owner="first")
    mark_effect_started(connection, claim["run_id"], actor="first")

    reconciled = recover_run(
        connection,
        claim["run_id"],
        new_owner="operator",
        reason="crash after idempotent effect before completion",
        reconciliation_outcome="completed",
        reconciliation_evidence={"idempotency_key": claim["run"]["occurrence_key"]},
        persist_receipt=True,
        now=claimed_at + timedelta(hours=1),
    )
    row = connection.execute("SELECT * FROM runs WHERE run_id = ?", (claim["run_id"],)).fetchone()
    assert reconciled["status"] == "succeeded"
    assert row["state"] == "succeeded"
    assert row["attempt"] == 1
    assert row["reconciliation_state"] == "completed"
    assert connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1
    assert connection.execute(
        "SELECT COUNT(*) FROM receipts WHERE run_id = ?", (claim["run_id"],)
    ).fetchone()[0] == 1
    connection.close()


def test_terminal_transition_and_receipt_are_atomic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = configured_database(tmp_path)
    connection = connect(database)
    claim = claim_occurrence(
        connection,
        "fixture-daily-review",
        "2026-01-01T12:00:00Z",
        claim_owner="worker",
    )
    mark_running(connection, claim["run_id"], claim_owner="worker")

    def crash_before_receipt(*args, **kwargs):
        raise RuntimeError("simulated crash before receipt persistence")

    monkeypatch.setattr("automation_dispatcher.receipts.create_receipt", crash_before_receipt)
    with pytest.raises(RuntimeError, match="simulated crash"):
        complete_run(
            connection,
            claim["run_id"],
            actor="worker",
            summary="effect complete",
            persist_receipt=True,
        )

    assert connection.execute(
        "SELECT state FROM runs WHERE run_id = ?", (claim["run_id"],)
    ).fetchone()[0] == "running"
    assert connection.execute(
        "SELECT COUNT(*) FROM audit_events WHERE run_id = ? AND event_type = 'run_succeeded'",
        (claim["run_id"],),
    ).fetchone()[0] == 0
    assert connection.execute(
        "SELECT COUNT(*) FROM receipts WHERE run_id = ?", (claim["run_id"],)
    ).fetchone()[0] == 0
    connection.close()


def test_contaminated_checkout_builds_artifacts_without_runtime_state(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    shutil.copytree(
        ROOT,
        checkout,
        ignore=shutil.ignore_patterns(
            ".git", ".venv", ".pytest_cache", "__pycache__", "dist", "build"
        ),
    )
    contaminants = {
        "runtime.sqlite3": b"root database",
        ".automation-dispatcher/daily.sqlite3": b"live database",
        ".automation-dispatcher/daily.sqlite3-wal": b"wal",
        ".automation-dispatcher/daily.sqlite3-shm": b"shm",
        "backups/snapshot.sqlite3": b"backup",
        "exports/audit.json": b"export",
        ".env.runtime": b"SECRET=not-for-artifacts",
        "src/automation_dispatcher/contaminant.db": b"nested database",
    }
    for relative, content in contaminants.items():
        target = checkout / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    dist = tmp_path / "dist"
    completed = subprocess.run(
        ["uv", "build", "--offline", "--no-progress", "--out-dir", str(dist), str(checkout)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout
    wheel = next(dist.glob("*.whl"))
    sdist = next(dist.glob("*.tar.gz"))
    with zipfile.ZipFile(wheel) as archive:
        artifact_names = archive.namelist()
    with tarfile.open(sdist, "r:gz") as archive:
        artifact_names.extend(archive.getnames())

    def is_runtime_state(name: str) -> bool:
        parts = PurePosixPath(name).parts
        filename = parts[-1]
        return (
            any(part in {".automation-dispatcher", "backups", "exports"} for part in parts)
            or filename.endswith((".sqlite", ".sqlite3", ".db", "-journal", "-wal", "-shm"))
            or filename == ".env"
            or filename.startswith(".env.")
        )

    leaked = [name for name in artifact_names if is_runtime_state(name)]
    assert leaked == []

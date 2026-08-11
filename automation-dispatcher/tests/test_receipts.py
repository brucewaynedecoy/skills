from __future__ import annotations

from pathlib import Path

from automation_dispatcher.claims import claim_occurrence, complete_run
from automation_dispatcher.database import connect
import pytest

from automation_dispatcher.receipts import (
    acknowledge_receipt,
    create_receipt,
    pending_receipt,
    prepare_receipt_post,
)

from test_claims import configured_database


def test_receipt_retry_never_reexecutes_run(tmp_path: Path) -> None:
    database = configured_database(tmp_path)
    connection = connect(database)
    claim = claim_occurrence(
        connection,
        "fixture-daily-review",
        "2026-01-01T12:00:00Z",
        claim_owner="test",
    )
    complete_run(connection, claim["run_id"], actor="test", summary="done")
    connection.execute("BEGIN IMMEDIATE")
    receipt = create_receipt(
        connection,
        dispatcher_id="ops-collection",
        destination_task_id="task-daily",
        content="bounded receipt",
        run_id=claim["run_id"],
    )
    connection.commit()

    first = pending_receipt(connection, receipt["receipt_id"])
    second = pending_receipt(connection, receipt["receipt_id"])
    assert first["content_hash"] == second["content_hash"]
    assert "rendered_content" not in first
    assert "rendered_content" not in second
    assert connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1

    connection.execute("BEGIN IMMEDIATE")
    acknowledged = acknowledge_receipt(
        connection, receipt["receipt_id"], external_message_id="message-1"
    )
    connection.commit()
    assert acknowledged["status"] == "posted"
    assert connection.execute(
        "SELECT external_message_id FROM receipts WHERE receipt_id=?",
        (receipt["receipt_id"],),
    ).fetchone()[0] == "message-1"

    repeated = acknowledge_receipt(
        connection, receipt["receipt_id"], external_message_id="misleading-new-id"
    )
    assert repeated["already_posted"] is True
    assert repeated["external_message_id"] == "message-1"
    connection.close()


def test_posting_outcome_requires_explicit_reconciliation(tmp_path: Path) -> None:
    database = configured_database(tmp_path)
    connection = connect(database)
    connection.execute("BEGIN IMMEDIATE")
    receipt = create_receipt(
        connection,
        dispatcher_id="ops-collection",
        destination_task_id="task-daily",
        content="one stable payload",
    )
    connection.commit()
    first = prepare_receipt_post(connection, receipt["receipt_id"], actor="test")
    assert first["status"] == "posting"
    assert first["delivery_attempt"] == 1
    with pytest.raises(ValueError, match="outcome is unknown"):
        prepare_receipt_post(connection, receipt["receipt_id"], actor="test")
    retried = prepare_receipt_post(
        connection, receipt["receipt_id"], actor="test", confirm_not_posted=True
    )
    assert retried["delivery_attempt"] == 2
    assert retried["content_hash"] == first["content_hash"]
    connection.close()

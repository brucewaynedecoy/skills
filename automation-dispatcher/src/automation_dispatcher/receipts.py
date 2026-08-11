"""Canonical concise receipt creation and acknowledgment."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any, Mapping


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def receipt_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def render_run_receipt(
    run: Mapping[str, Any],
    workflow: Mapping[str, Any],
    *,
    event_id: int | None,
    event_hash: str | None,
) -> str:
    """Render a bounded receipt without embedding raw procedure output."""

    outcome = str(run.get("state", "unknown"))
    attention = outcome in {"failed", "abandoned", "effect_unknown"}
    summary = str(run.get("output_summary") or run.get("error_class") or "No summary")
    summary = " ".join(summary.split())[:1000]
    event_ref = f"{event_id or 'unknown'}/{(event_hash or 'unknown')[:12]}"
    lines = [
        f"### {workflow.get('name', run.get('workflow_id', 'Workflow'))}",
        f"- Workflow: `{run.get('workflow_id', 'unknown')}`",
        f"- Occurrence: `{run.get('scheduled_for', 'unknown')}`",
        f"- Outcome: **{outcome}** (attempt {run.get('attempt', 1)})",
        f"- Run: `{run.get('run_id', 'unknown')}`",
        f"- Audit: `{event_ref}`",
        f"- Summary: {summary}",
    ]
    if attention:
        lines.append("- Attention needed: review the run and recovery policy before retrying.")
    return "\n".join(lines)


def create_receipt(
    conn: Any,
    *,
    dispatcher_id: str,
    destination_task_id: str,
    content: str,
    run_id: str | None = None,
    workflow_id: str | None = None,
) -> dict[str, Any]:
    """Persist a pending receipt in the caller's current transaction."""

    receipt_id = str(uuid.uuid4())
    content_digest = receipt_hash(content)
    created_at = utc_now()
    conn.execute(
        """
        INSERT INTO receipts (
            receipt_id, run_id, workflow_id, dispatcher_id, destination_task_id, status,
            rendered_content, content_hash, created_at
        ) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?)
        """,
        (
            receipt_id,
            run_id,
            workflow_id,
            dispatcher_id,
            destination_task_id,
            content,
            content_digest,
            created_at,
        ),
    )
    return {
        "receipt_id": receipt_id,
        "run_id": run_id,
        "workflow_id": workflow_id,
        "dispatcher_id": dispatcher_id,
        "destination_task_id": destination_task_id,
        "status": "pending",
        "content_hash": content_digest,
        "created_at": created_at,
    }


def pending_receipt(conn: Any, receipt_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM receipts WHERE receipt_id = ?", (receipt_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown receipt: {receipt_id}")
    record = dict(row)
    if record["status"] == "posted":
        raise ValueError(f"receipt already acknowledged: {receipt_id}")
    record.pop("rendered_content", None)
    return record


def prepare_receipt_post(
    conn: Any,
    receipt_id: str,
    *,
    actor: str,
    confirm_not_posted: bool = False,
) -> dict[str, Any]:
    """Fence a delivery attempt and return the exact persisted payload.

    A receipt already in ``posting`` has an ambiguous external outcome. It is
    not returned again unless the caller explicitly confirms that the prior
    attempt did not post.
    """

    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            "SELECT * FROM receipts WHERE receipt_id = ?", (receipt_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown receipt: {receipt_id}")
        if row["status"] == "posted":
            raise ValueError(f"receipt already acknowledged: {receipt_id}")
        if row["status"] == "posting" and not confirm_not_posted:
            raise ValueError(
                "receipt posting outcome is unknown; reconcile it or confirm it was not posted"
            )
        attempted_at = utc_now()
        conn.execute(
            """
            UPDATE receipts
               SET status = 'posting', delivery_attempt = delivery_attempt + 1,
                   last_attempt_at = ?
             WHERE receipt_id = ?
            """,
            (attempted_at, receipt_id),
        )
        updated = conn.execute(
            "SELECT * FROM receipts WHERE receipt_id = ?", (receipt_id,)
        ).fetchone()
        from .audit import append_event

        workflow_id = updated["workflow_id"]
        if workflow_id is None and updated["run_id"] is not None:
            run = conn.execute(
                "SELECT workflow_id FROM runs WHERE run_id = ?", (updated["run_id"],)
            ).fetchone()
            workflow_id = run["workflow_id"] if run is not None else None
        event = append_event(
            conn,
            dispatcher_id=updated["dispatcher_id"],
            workflow_id=workflow_id,
            run_id=updated["run_id"],
            event_type="receipt_posting_started",
            payload={
                "receipt_id": receipt_id,
                "content_hash": updated["content_hash"],
                "delivery_attempt": updated["delivery_attempt"],
                "previous_status": row["status"],
                "confirmed_not_posted": confirm_not_posted,
            },
            actor=actor,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    record = dict(
        conn.execute("SELECT * FROM receipts WHERE receipt_id = ?", (receipt_id,)).fetchone()
    )
    record["posting_payload"] = {
        "thread_id": record["destination_task_id"],
        "message": record["rendered_content"],
    }
    record["event"] = event
    return record


def acknowledge_receipt(
    conn: Any, receipt_id: str, *, external_message_id: str | None = None
) -> dict[str, Any]:
    """Mark the exact persisted receipt as posted; never recreate the run."""

    existing = conn.execute(
        "SELECT * FROM receipts WHERE receipt_id = ?", (receipt_id,)
    ).fetchone()
    if existing is None:
        raise ValueError(f"unknown receipt: {receipt_id}")
    if existing["status"] == "posted":
        return {
            "receipt_id": receipt_id,
            "status": "posted",
            "posted_at": existing["posted_at"],
            "external_message_id": existing["external_message_id"],
            "already_posted": True,
        }
    posted_at = utc_now()
    cursor = conn.execute(
        """
        UPDATE receipts
           SET status = 'posted', posted_at = ?, external_message_id = ?
         WHERE receipt_id = ? AND status IN ('pending', 'posting', 'failed')
        """,
        (posted_at, external_message_id, receipt_id),
    )
    if cursor.rowcount != 1:
        row = conn.execute(
            "SELECT status FROM receipts WHERE receipt_id = ?", (receipt_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown receipt: {receipt_id}")
        if row["status"] != "posted":
            raise ValueError(f"receipt cannot be acknowledged from state {row['status']}")
    return {
        "receipt_id": receipt_id,
        "status": "posted",
        "posted_at": posted_at,
        "external_message_id": external_message_id,
        "already_posted": False,
    }

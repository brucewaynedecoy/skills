"""Exactly-once occurrence claims and explicit recovery transitions."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping

from .audit import append_event


TERMINAL_STATES = {"succeeded", "failed", "skipped", "abandoned", "effect_unknown"}


class ClaimError(RuntimeError):
    """Raised when a claim or transition is unsafe."""


def _parse_utc(value: str | datetime) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ClaimError("scheduled_for must include an explicit UTC offset")
    return parsed.astimezone(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def occurrence_key(
    workflow_id: str,
    scheduled_for: str | datetime,
    *,
    dispatcher_id: str | None = None,
) -> str:
    instant = _iso(_parse_utc(scheduled_for))
    material = (
        f"{dispatcher_id}\0{workflow_id}\0{instant}"
        if dispatcher_id is not None
        else f"{workflow_id}\0{instant}"
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def claim_occurrence(
    conn: Any,
    workflow_id: str,
    scheduled_for: str | datetime,
    *,
    claim_owner: str,
    observed_identity: Mapping[str, Any] | None = None,
    now: datetime | None = None,
    expected_revision: int | None = None,
    expected_dispatcher_revision: int | None = None,
    expected_definition_hash: str | None = None,
    expected_route_task_id: str | None = None,
    occurrence_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    instant = _iso(_parse_utc(scheduled_for))
    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    run_id = str(uuid.uuid4())
    observed_json = json.dumps(observed_identity or {}, sort_keys=True, separators=(",", ":"))
    conn.execute("BEGIN IMMEDIATE")
    try:
        workflow = conn.execute(
            "SELECT * FROM workflows WHERE workflow_id = ?", (workflow_id,)
        ).fetchone()
        if workflow is None:
            raise ClaimError(f"unknown workflow: {workflow_id}")
        if not workflow["enabled"]:
            raise ClaimError("workflow is disabled")
        dispatcher = conn.execute(
            "SELECT * FROM dispatchers WHERE dispatcher_id = ?",
            (workflow["dispatcher_id"],),
        ).fetchone()
        if dispatcher is None:
            raise ClaimError("workflow dispatcher is missing")
        dispatcher_revision = int(dispatcher["current_revision"])
        if (
            expected_dispatcher_revision is not None
            and dispatcher_revision != expected_dispatcher_revision
        ):
            raise ClaimError("dispatcher schedule revision changed before claim")
        key = occurrence_key(
            workflow_id,
            instant,
            dispatcher_id=workflow["dispatcher_id"],
        )
        active_route = dispatcher["default_reporting_task_id"] or dispatcher["expected_task_id"]
        if workflow["reporting_task_id"] != active_route:
            raise ClaimError("workflow reporting route does not match the active dispatcher route")
        if expected_route_task_id is not None and active_route != expected_route_task_id:
            raise ClaimError("dispatcher route changed before claim")
        if expected_revision is not None and workflow["current_revision"] != expected_revision:
            raise ClaimError("workflow revision changed before claim")
        if (
            expected_definition_hash is not None
            and workflow["definition_hash"] != expected_definition_hash
        ):
            raise ClaimError("workflow definition hash changed before claim")
        lease_expires = _iso(
            current_time + timedelta(seconds=workflow["claim_lease_seconds"])
        )
        existing = conn.execute(
            "SELECT * FROM runs WHERE workflow_id = ? AND scheduled_for = ?",
            (workflow_id, instant),
        ).fetchone()
        if existing is not None:
            conn.rollback()
            return {
                "status": "already_claimed",
                "dispatcher_id": workflow["dispatcher_id"],
                "workflow_id": workflow_id,
                "run_id": existing["run_id"],
                "run": dict(existing),
            }
        conn.execute(
            """
            INSERT INTO runs (
                run_id, workflow_id, workflow_revision, dispatcher_revision, scheduled_for,
                occurrence_key, discovered_at, state, claim_owner, claim_time,
                lease_expires_at, attempt, external_effect_key,
                reconciliation_state, observed_identity_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'claimed', ?, ?, ?, 1, ?, 'not_started', ?)
            """,
            (
                run_id, workflow_id, workflow["current_revision"], dispatcher_revision,
                instant, key,
                _iso(current_time), claim_owner, _iso(current_time), lease_expires,
                key, observed_json,
            ),
        )
        event = append_event(
            conn,
            dispatcher_id=workflow["dispatcher_id"],
            workflow_id=workflow_id,
            run_id=run_id,
            event_type="run_claimed",
            payload={
                "scheduled_for": instant,
                "occurrence_key": key,
                "dispatcher_revision": dispatcher_revision,
                "lease_expires_at": lease_expires,
                "attempt": 1,
                "occurrence_metadata": dict(occurrence_metadata or {}),
            },
            actor=claim_owner,
            observed_identity=observed_identity,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    run = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    return {
        "status": "claimed",
        "dispatcher_id": workflow["dispatcher_id"],
        "workflow_id": workflow_id,
        "run_id": run_id,
        "run": dict(run),
        "event": event,
    }


def mark_running(conn: Any, run_id: str, *, claim_owner: str) -> dict[str, Any]:
    return _transition(conn, run_id, from_states={"claimed", "recovered"}, to_state="running", actor=claim_owner)


def mark_effect_started(conn: Any, run_id: str, *, actor: str) -> dict[str, Any]:
    """Persist the ambiguity boundary before an external effect can occur."""

    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            """SELECT r.*, w.dispatcher_id FROM runs r
                 JOIN workflows w USING (workflow_id) WHERE run_id = ?""",
            (run_id,),
        ).fetchone()
        if row is None:
            raise ClaimError(f"unknown run: {run_id}")
        if row["state"] != "running":
            raise ClaimError("external effect can start only from running state")
        if row["claim_owner"] and actor != row["claim_owner"]:
            raise ClaimError("claim ownership changed; stale worker is fenced")
        if row["lease_expires_at"] and _parse_utc(row["lease_expires_at"]) <= datetime.now(UTC):
            raise ClaimError("claim lease expired; recover the run before continuing")
        if row["reconciliation_state"] not in {None, "not_started", "failed"}:
            raise ClaimError("external effect boundary is already active")
        conn.execute(
            "UPDATE runs SET reconciliation_state = 'effect_started' WHERE run_id = ?",
            (run_id,),
        )
        event = append_event(
            conn,
            dispatcher_id=row["dispatcher_id"],
            workflow_id=row["workflow_id"],
            run_id=run_id,
            event_type="external_effect_started",
            payload={"occurrence_key": row["occurrence_key"], "attempt": row["attempt"]},
            actor=actor,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {
        "status": "effect_started",
        "dispatcher_id": row["dispatcher_id"],
        "workflow_id": row["workflow_id"],
        "run_id": run_id,
        "event": event,
    }


def complete_run(
    conn: Any,
    run_id: str,
    *,
    actor: str,
    summary: str,
    evidence: list[str] | None = None,
    persist_receipt: bool = False,
) -> dict[str, Any]:
    return _transition(
        conn,
        run_id,
        from_states={"claimed", "running", "recovered"},
        to_state="succeeded",
        actor=actor,
        summary=summary,
        evidence=evidence,
        reconciliation_state="completed",
        persist_receipt=persist_receipt,
    )


def fail_run(
    conn: Any,
    run_id: str,
    *,
    actor: str,
    error_class: str,
    summary: str,
    effect_unknown: bool = False,
    persist_receipt: bool = False,
) -> dict[str, Any]:
    state = "effect_unknown" if effect_unknown else "failed"
    return _transition(
        conn,
        run_id,
        from_states={"claimed", "running", "recovered"},
        to_state=state,
        actor=actor,
        summary=summary,
        error_class=error_class,
        reconciliation_state="ambiguous" if effect_unknown else "failed",
        persist_receipt=persist_receipt,
    )


def recover_run(
    conn: Any,
    run_id: str,
    *,
    new_owner: str,
    reason: str,
    reconciliation_outcome: str | None = None,
    reconciliation_evidence: Mapping[str, Any] | list[Any] | None = None,
    persist_receipt: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            """SELECT r.*, w.dispatcher_id, w.claim_lease_seconds,
                      w.external_effect_mode, w.retry_policy_json
                 FROM runs r JOIN workflows w USING (workflow_id)
                WHERE run_id = ?""",
            (run_id,),
        ).fetchone()
        if row is None:
            raise ClaimError(f"unknown run: {run_id}")
        if row["state"] not in {"claimed", "running", "recovered"}:
            raise ClaimError(f"run cannot be recovered from state {row['state']}")
        if row["lease_expires_at"] and _parse_utc(row["lease_expires_at"]) > current_time:
            raise ClaimError("claim lease has not expired")
        retry_policy = json.loads(row["retry_policy_json"])
        max_attempts = int(retry_policy.get("max_attempts", 1))
        if row["reconciliation_state"] not in {None, "not_started", "failed"}:
            if reconciliation_outcome is not None and not reconciliation_evidence:
                raise ClaimError("reconciliation outcome requires durable evidence")
            if reconciliation_outcome not in {"completed", "not_completed"}:
                conn.execute(
                    "UPDATE runs SET state = 'effect_unknown', finished_at = ?, error_class = 'ambiguous_external_effect' WHERE run_id = ?",
                    (_iso(current_time), run_id),
                )
                event = append_event(
                    conn,
                    dispatcher_id=row["dispatcher_id"], workflow_id=row["workflow_id"], run_id=run_id,
                    event_type="external_effect_unknown",
                    payload={"prior_owner": row["claim_owner"], "reason": reason}, actor=new_owner,
                )
                receipt = (
                    _persist_terminal_receipt(conn, run_id, event, actor=new_owner)
                    if persist_receipt
                    else None
                )
                conn.commit()
                result = {
                    "status": "effect_unknown",
                    "dispatcher_id": row["dispatcher_id"],
                    "workflow_id": row["workflow_id"],
                    "run_id": run_id,
                    "event": event,
                }
                if receipt:
                    result["receipt"] = receipt
                return result
            if reconciliation_outcome == "completed":
                evidence_json = json.dumps(
                    reconciliation_evidence, sort_keys=True, separators=(",", ":")
                )
                conn.execute(
                    """UPDATE runs
                          SET state = 'succeeded', prior_claim_owner = claim_owner,
                              claim_owner = ?, finished_at = ?,
                              reconciliation_state = 'completed',
                              reconciliation_evidence_json = ?,
                              output_summary = 'External effect reconciled as completed'
                        WHERE run_id = ?""",
                    (new_owner, _iso(current_time), evidence_json, run_id),
                )
                event = append_event(
                    conn,
                    dispatcher_id=row["dispatcher_id"], workflow_id=row["workflow_id"], run_id=run_id,
                    event_type="external_effect_reconciled",
                    payload={"outcome": "completed", "evidence": reconciliation_evidence},
                    actor=new_owner,
                )
                receipt = (
                    _persist_terminal_receipt(conn, run_id, event, actor=new_owner)
                    if persist_receipt
                    else None
                )
                conn.commit()
                result = {
                    "status": "succeeded", "dispatcher_id": row["dispatcher_id"],
                    "workflow_id": row["workflow_id"], "run_id": run_id, "event": event,
                }
                if receipt:
                    result["receipt"] = receipt
                return result
            conn.execute(
                "UPDATE runs SET reconciliation_state = 'not_completed', reconciliation_evidence_json = ? WHERE run_id = ?",
                (json.dumps(reconciliation_evidence, sort_keys=True, separators=(",", ":")), run_id),
            )
        if int(row["attempt"]) >= max_attempts:
            conn.execute(
                "UPDATE runs SET state = 'abandoned', finished_at = ?, error_class = 'retry_limit_exhausted' WHERE run_id = ?",
                (_iso(current_time), run_id),
            )
            event = append_event(
                conn,
                dispatcher_id=row["dispatcher_id"], workflow_id=row["workflow_id"], run_id=run_id,
                event_type="run_abandoned",
                payload={"attempt": row["attempt"], "max_attempts": max_attempts, "reason": reason},
                actor=new_owner,
            )
            receipt = (
                _persist_terminal_receipt(conn, run_id, event, actor=new_owner)
                if persist_receipt
                else None
            )
            conn.commit()
            result = {
                "status": "abandoned", "dispatcher_id": row["dispatcher_id"],
                "workflow_id": row["workflow_id"], "run_id": run_id, "event": event,
            }
            if receipt:
                result["receipt"] = receipt
            return result
        attempt = int(row["attempt"]) + 1
        lease = _iso(current_time + timedelta(seconds=row["claim_lease_seconds"]))
        conn.execute(
            """UPDATE runs
                  SET state = 'recovered', prior_claim_owner = claim_owner,
                      claim_owner = ?, claim_time = ?, lease_expires_at = ?,
                      attempt = ?
                WHERE run_id = ?""",
            (new_owner, _iso(current_time), lease, attempt, run_id),
        )
        event = append_event(
            conn,
            dispatcher_id=row["dispatcher_id"], workflow_id=row["workflow_id"], run_id=run_id,
            event_type="run_recovered",
            payload={"prior_owner": row["claim_owner"], "attempt": attempt, "reason": reason, "lease_expires_at": lease},
            actor=new_owner,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    recovered = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    return {
        "status": "recovered",
        "dispatcher_id": row["dispatcher_id"],
        "workflow_id": row["workflow_id"],
        "run_id": run_id,
        "run": dict(recovered),
        "event": event,
    }


def _transition(
    conn: Any,
    run_id: str,
    *,
    from_states: set[str],
    to_state: str,
    actor: str,
    summary: str | None = None,
    evidence: list[str] | None = None,
    error_class: str | None = None,
    reconciliation_state: str | None = None,
    persist_receipt: bool = False,
) -> dict[str, Any]:
    timestamp = _iso(datetime.now(UTC))
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            """SELECT r.*, w.dispatcher_id FROM runs r
                 JOIN workflows w USING (workflow_id) WHERE run_id = ?""",
            (run_id,),
        ).fetchone()
        if row is None:
            raise ClaimError(f"unknown run: {run_id}")
        if row["state"] not in from_states:
            raise ClaimError(f"run cannot transition from {row['state']} to {to_state}")
        if row["claim_owner"] and actor != row["claim_owner"]:
            raise ClaimError("claim ownership changed; stale worker is fenced")
        if row["lease_expires_at"] and row["lease_expires_at"] <= timestamp:
            raise ClaimError("claim lease expired; recover the run before continuing")
        finished_at = timestamp if to_state in TERMINAL_STATES else None
        started_at = timestamp if to_state == "running" and not row["started_at"] else row["started_at"]
        conn.execute(
            """UPDATE runs
                  SET state = ?, started_at = ?, finished_at = ?, output_summary = ?,
                      evidence_json = ?, error_class = ?, reconciliation_state = COALESCE(?, reconciliation_state)
                WHERE run_id = ?""",
            (
                to_state, started_at, finished_at, summary,
                json.dumps(evidence or [], sort_keys=True), error_class,
                reconciliation_state, run_id,
            ),
        )
        event = append_event(
            conn,
            dispatcher_id=row["dispatcher_id"], workflow_id=row["workflow_id"], run_id=run_id,
            event_type=f"run_{to_state}",
            payload={"from": row["state"], "to": to_state, "summary": summary, "error_class": error_class},
            actor=actor,
        )
        receipt = (
            _persist_terminal_receipt(conn, run_id, event, actor=actor)
            if persist_receipt and to_state in TERMINAL_STATES
            else None
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    updated = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    result = {
        "status": to_state,
        "dispatcher_id": row["dispatcher_id"],
        "workflow_id": row["workflow_id"],
        "run_id": run_id,
        "run": dict(updated),
        "event": event,
    }
    if receipt:
        result["receipt"] = receipt
    return result


def _persist_terminal_receipt(
    conn: Any,
    run_id: str,
    event: Mapping[str, Any],
    *,
    actor: str,
) -> dict[str, Any]:
    """Create the one terminal receipt inside the run transition transaction."""

    from .receipts import create_receipt, render_run_receipt

    row = conn.execute(
        """SELECT r.*, w.dispatcher_id, w.name, w.reporting_task_id
             FROM runs r JOIN workflows w USING (workflow_id)
            WHERE run_id = ?""",
        (run_id,),
    ).fetchone()
    if row is None:
        raise ClaimError(f"unknown run: {run_id}")
    content = render_run_receipt(
        dict(row),
        {"name": row["name"]},
        event_id=event.get("event_id"),
        event_hash=event.get("event_hash"),
    )
    receipt = create_receipt(
        conn,
        dispatcher_id=row["dispatcher_id"],
        destination_task_id=row["reporting_task_id"],
        content=content,
        run_id=run_id,
        workflow_id=row["workflow_id"],
    )
    conn.execute(
        "UPDATE runs SET receipt_hash = ? WHERE run_id = ?",
        (receipt["content_hash"], run_id),
    )
    append_event(
        conn,
        dispatcher_id=row["dispatcher_id"],
        workflow_id=row["workflow_id"],
        run_id=run_id,
        event_type="receipt_pending",
        payload={"receipt_id": receipt["receipt_id"], "content_hash": receipt["content_hash"]},
        actor=actor,
    )
    return receipt

---
name: "automation-dispatcher"
description: "Create and operate durable, task-bound collections of scheduled agent workflows through the automation-dispatcher CLI and an external SQLite registry. Use when a request names automation-dispatcher, a workflow collection or collection schedule, a dispatcher heartbeat, registration or revision, due or claim processing, route or integrity checks, receipt reconciliation, recovery, backup, export, migration, or cutover. Daily and weekly are supported schedule presets and examples, not dispatcher identities or limits. Do not use for unrelated one-off reminders or treat task conversation as workflow configuration."
---

# Automation Dispatcher

Operate durable workflow collections through the packaged `automation-dispatcher` command. Treat each dispatcher as one collection: an arbitrary stable ID, one exact Codex task route, one authoritative collection schedule, and one external SQLite registry. Every enabled member inherits that schedule and receives one run opportunity per collection occurrence. Put a workflow that needs a different schedule in a different collection.

Treat the dispatcher database as operational authority and the configured Codex task as a reporting, clarification, and approval surface. Treat task titles as descriptive only. Daily and weekly are schedule presets and migration examples, not required dispatcher IDs, task names, or separate product modes.

## Preserve the gates

Classify the requested scope before acting:

1. Source or documentation work may change only repository files.
2. Initialization or dry-run work may create state only at an explicit, verified non-live path.
3. Live registry mutation requires explicit authorization for the exact dispatcher and database.
4. Task, heartbeat, or legacy-automation changes are a separate cutover gate. Never infer that authorization from code completion or database initialization.

Do not create, edit, disable, or delete a Codex task or automation unless the current request explicitly authorizes that live action.

## Load only the needed contract

- Read [references/workflow-definition.md](references/workflow-definition.md) before registering or revising a workflow. Definitions bind membership and execution authority; they do not own schedules.
- Read [references/registry-contract.md](references/registry-contract.md) before auditing collection configuration, schema, routes, runs, events, receipts, or identity assurance.
- Read [references/operator-runbook.md](references/operator-runbook.md) before installation, collection initialization or schedule revision, dispatch, backup, restore verification, recovery, migration, receipt posting, or cutover.

Load only the selected workflow definition and its registered authority references. Do not promote task conversation, unrelated memory, or another workflow's feedback into operational authority.

## Use the deterministic CLI

Use `automation-dispatcher` for every state change. Never edit a dispatcher database manually or compose ad hoc mutation SQL.

For repository development, run `uv run automation-dispatcher`. For live heartbeats, invoke a separately installed, exactly pinned `automation-dispatcher` command. Use an exact-version or exact-revision `uvx` command only for approved ephemeral operations; never use unpinned `uvx automation-dispatcher` in a live heartbeat.

Always provide the explicit database path required by the CLI. Refuse a database inside the source checkout, an installed skill directory, or an installed CLI environment. Runtime state belongs in the verified collection task's durable working directory.

Resolve relative script procedure references from the registered definition file's directory. Require every resolved script to remain inside an explicit approved root; never rely on the heartbeat's current working directory.

## Dispatch safely

Follow this sequence:

1. Resolve the dispatcher ID, database path, expected task route, requested mode, and observed runtime identity without inventing missing values.
2. Run `status`, `integrity-check`, and `route-check` as applicable. Verify that the heartbeat schedule covers the registered collection schedule within maximum lateness. Fail closed before due evaluation or claim on corruption, migration uncertainty, route mismatch, insufficient required assurance, definition-hash mismatch, or schedule-coverage failure.
3. Run `due` for read-only evaluation. Use a time override only for an explicitly requested dry run or deterministic test.
4. Prefer `run` for the orchestrated route-check, due, claim, execution, persistence, and receipt flow. Use lower-level claim/completion commands only for tests or documented recovery.
5. Execute only the claimed workflow revision and pass its stable occurrence idempotency key to external-effect procedures when supported.
6. Persist success, failure, or `effect_unknown` before reporting. Never automatically retry an ambiguous external effect.
7. Post only the exact persisted material receipt through the supported host task tool, then call `receipt-ack`. A post failure uses `receipt-retry`; it never re-executes the workflow.

No-due heartbeats should remain silent when the host permits it.

## Mutate registrations safely

Validate and dry-run a source-controlled definition before `register` or `revise`. Confirm its canonical hash, collection membership, authorities, procedure, retry and lease policy, external-effect contract, reporting route, sensitivity, and retention. Reject workflow-level timezone, schedule, lateness, or catch-up fields. Confirm that the destination collection's schedule is correct for the workflow and that the verified heartbeat covers it.

Use `schedule-revise` only under explicit authorization for the exact collection, schedule, timezone, lateness and catch-up policy, actor, and reason. Reconcile already materialized occurrences and verify heartbeat coverage before acceptance. The durable schedule revision never changes the live host automation implicitly; that remains a separate cutover gate.

Use `route-revise` only under explicit authorization for the exact dispatcher, destination task, working directory, identity requirements, actor, and reason. It revises the durable route and emits a receipt; changing the live heartbeat remains a separate gate.

Prefer `disable` plus retained history over deletion. Require exact identifiers for recovery, replay, receipt acknowledgment, restore verification, and other history-sensitive operations. Do not use a force bypass.

## Report evidence

Return the dispatcher, workflow and run identifiers when applicable, database path, status, event ID/hash prefix, CLI version/source revision, and pending receipt state. Keep secrets, source transcripts, signed URLs, and large tool output out of receipts.

If blocked, record the failure when safe and provide a concise attention-needed receipt without claiming that work ran.

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
- Read [references/guided-lifecycle-contract.md](references/guided-lifecycle-contract.md) before lifecycle discovery, planning, manifest resolution, approval, shadow validation, host-adapter work, or multi-collection coordination.
- Read [references/baseline-compatibility.md](references/baseline-compatibility.md) before changing an existing command, schema-v2 definition, database migration, installed entrypoint, or distribution resource.

Load only the selected workflow definition and its registered authority references. Do not promote task conversation, unrelated memory, or another workflow's feedback into operational authority.

## Use the deterministic CLI

Use `automation-dispatcher` for every state change. Never edit a dispatcher database manually or compose ad hoc mutation SQL.

For repository development, run `uv run automation-dispatcher`. For live heartbeats, invoke a separately installed, exactly pinned `automation-dispatcher` command. Use an exact-version or exact-revision `uvx` command only for approved ephemeral operations; never use unpinned `uvx automation-dispatcher` in a live heartbeat.

Always provide the explicit database path required by the CLI. Refuse a database inside the source checkout, an installed skill directory, or an installed CLI environment. Runtime state belongs in the verified collection task's durable working directory.

For guided-lifecycle artifact validation, explanation, resumable status, or semantic verification, use the grouped `lifecycle plan`, `lifecycle explain`, `lifecycle status`, and `lifecycle verify` commands with explicit state/source roots. `lifecycle apply --dry-run` retains its Phase 2 planning-only behavior and performs no registry, artifact, host, task, automation, or receipt mutation. Phase 4 non-dry-run apply is admitted only for the exact `initialize/apply` and `shadow_validate/evaluate` stage/action pairs described below. Treat `record-cutover` and the standalone `heartbeat-template` command as reserved until their later implementation phases.

## Discover and propose collections

Route ordinary requests to consolidate scheduled work, add a workflow, create a collection, resume setup, inspect lifecycle status, or change a collection schedule through the guided lifecycle. Do not make the user reconstruct low-level initialization or registration commands before a proposal exists.

Discovery in the current environment is fixture-driven and read-only. Use `lifecycle plan --host-observations <explicit-json-path>` only with an explicitly bounded selection, filter, input, or pagination scope. Supply a validated host-capability snapshot when callable task and automation read schemas have been verified. Q-003 remains fail-closed: absence of those verified callable schemas is visible as a blocker and never causes an implicit host call. Discovery preserves lifecycle state separately from managed/unmanaged classification; every managed source is excluded regardless of active or paused state, duplicate stable IDs and competing manifest claims fail closed, and stale candidates remain visible. Task titles are labels only.

Review the returned proposal as a decision package in both canonical JSON and bounded human output: compatible collection groups and their explicit rationale, deterministic split decisions, schedule and timezone, target task, source mappings, schema-v2 workflow drafts, exclusions, risks, unresolved questions, exact next action, and the concrete source-schedule occurrence boundary with `authorized: false`. Ask only for missing information that materially changes that package. Incompatible schedules, routes, authority boundaries, working roots, host targets, or execution constraints remain separate. Every paused unmanaged source requires an explicit include or exclude decision.

Discussion and proposal review are not acceptance. Add `--accept-proposal`, an `--expires-at` later than the actual acceptance time, exactly one topology alternative (`--selected-alternative keep-separate` or `accept-compatible-groups`), and one `--include-paused-id` or `--exclude-paused-id` for each paused candidate only after the user accepts the exact proposal. The topology choice materially determines plan collections. An accepted plan is bound to the discovery snapshot and proposal hashes; state and source paths are normalized within explicit state/repository roots and fenced from source, installed, broad, traversal, and symlink targets. Writing it requires an explicit external `--output` path. This stage never initializes a registry, changes a task or automation, or authorizes cutover.

Resolve relative script procedure references from the registered definition file's directory. Require every resolved script to remain inside an explicit approved root; never rely on the heartbeat's current working directory.

## Initialize and shadow-validate an accepted plan

Use non-dry-run `lifecycle apply` only when initialization at the exact plan-approved paths is explicitly authorized. Supply the accepted plan, the current validated discovery snapshot, the caller's exact plan and source-state hashes, the accepting actor, one collection ID, and every source/state path explicitly. Initialization requires `--stage initialize --action apply`; it generates only deterministic plan-owned definition and procedure files, initializes through the canonical registry service, dry-runs and registers definitions through the low-level registry API, verifies the full projection, writes the manifest and pinned heartbeat template, creates and restore-verifies the backup, and persists audit-bound progress. Differing existing files, partial registry projections, stale observations, expired approval, actor/hash mismatch, or unapproved paths stop before later artifacts are sealed.

Run `--stage shadow_validate --action evaluate` only after successful initialization. Also provide an explicit bounded source-occurrence JSON file, timezone-aware `--window-start` and `--window-end`, and `--readiness-path`. Each source occurrence must contain exactly `source_id`, `scheduled_for`, `intended_local`, `effective_local`, `timezone`, and `adjustment`; comparison preserves DST gap/fold identity. Shadow validation uses scheduling, routing, registry, integrity, audit, definition, heartbeat, backup-provenance, and progress evidence without claiming or running work, posting receipts, or changing database bytes. Existing scheduled sources remain authoritative.

Q-003 remains fail-closed until callable Codex task and automation schemas are proven in the active runtime. A blocked readiness report is evidence for reconciliation, not cutover authorization. Do not create or change a heartbeat, task, or automation from the generated template without a separate explicit cutover approval.

## Dispatch safely

Follow this sequence:

1. Resolve the dispatcher ID, database path, expected task route, requested mode, and observed runtime identity without inventing missing values.
2. Run `status`, `integrity-check`, and `route-check` as applicable. Verify that the heartbeat schedule covers the registered collection schedule within maximum lateness. Fail closed before due evaluation or claim on corruption, migration uncertainty, route mismatch, insufficient required assurance, definition-hash mismatch, or schedule-coverage failure.
3. Run `due` for read-only evaluation. Use a time override only for an explicitly requested dry run or deterministic test.
4. Prefer `run` for orchestrated route-check, due evaluation, claim, and script execution. Use `claim` directly only for tests or documented recovery. When `run` returns `action_required`, the heartbeat must use `complete` or `fail` as the required continuation described below.
5. Execute only the claimed workflow revision and pass its stable occurrence idempotency key to external-effect procedures when supported.
6. Persist success, failure, or `effect_unknown` before reporting. Never automatically retry an ambiguous external effect.
7. Post only the exact persisted material receipt through the supported host task tool, then call `receipt-ack`. A post failure uses `receipt-retry`; it never re-executes the workflow.

No-due heartbeats should remain silent when the host permits it.

For every `action_required` result from an agent, skill, or documented procedure, the heartbeat owns the rest of the run lifecycle. It must use only that result's `host_action` and the registered definition/authority references, perform no unrelated work, and then:

1. Call `complete <run-id> --actor <heartbeat-owner> --summary <bounded-summary>` with durable `--evidence` references after success, or `fail <run-id> --actor <heartbeat-owner> --error-class <class> --summary <bounded-summary>` after failure. Use `--effect-unknown` when an external effect may have occurred but cannot be reconciled. Do not leave the run in `running`, even when the procedure fails.
2. Take the `receipt.receipt_id` returned by that terminal command and call `receipt-retry <receipt-id> --actor <posting-actor>` once. This fences delivery and returns `posting_payload` containing the exact persisted `thread_id` and `message`.
3. Post exactly `posting_payload.message` to exactly `posting_payload.thread_id` through the supported task tool. Do not summarize, wrap, regenerate, or combine the message.
4. Re-read or otherwise reconcile the posted task message. Only after confirming the external message is the exact persisted payload, call `receipt-ack <receipt-id> --external-message-id <message-id> --actor <posting-actor>`.

If posting fails before any external effect, retry the persisted receipt; never rerun the procedure. If posting may have succeeded, reconcile the destination before retrying and never use `--confirm-not-posted` without independent proof. A heartbeat is not complete while any claimed agent/skill/documented run remains `running` or its material receipt remains unreconciled.

## Mutate registrations safely

Validate and dry-run a source-controlled definition before `register` or `revise`. Confirm its canonical hash, collection membership, authorities, procedure, retry and lease policy, external-effect contract, reporting route, sensitivity, and retention. Reject workflow-level timezone, schedule, lateness, or catch-up fields. Confirm that the destination collection's schedule is correct for the workflow and that the verified heartbeat covers it.

Use `schedule-revise` only under explicit authorization for the exact collection, schedule, timezone, lateness and catch-up policy, actor, and reason. Reconcile already materialized occurrences and verify heartbeat coverage before acceptance. The durable schedule revision never changes the live host automation implicitly; that remains a separate cutover gate.

Use `route-revise` only under explicit authorization for the exact dispatcher, destination task, working directory, identity requirements, actor, and reason. It revises the durable route and emits a receipt; changing the live heartbeat remains a separate gate.

Prefer `disable` plus retained history over deletion. Require exact identifiers for recovery, replay, receipt acknowledgment, restore verification, and other history-sensitive operations. Do not use a force bypass.

## Report evidence

Return the dispatcher, workflow and run identifiers when applicable, database path, status, event ID/hash prefix, CLI version/source revision, and pending receipt state. Keep secrets, source transcripts, signed URLs, and large tool output out of receipts.

If blocked, record the failure when safe and provide a concise attention-needed receipt without claiming that work ran.

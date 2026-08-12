---
title: "05 Automation Dispatcher"
kind: "prd"
status: "active"
---

# 05 Automation Dispatcher

## Purpose

Define the complete product contract for the Automation Dispatcher skill, its deterministic Python CLI, its external SQLite runtime, its guided lifecycle, its lifecycle artifacts, and its Codex host integration. Automation Dispatcher lets a user describe a scheduled-workflow outcome while the agent safely discovers, proposes, initializes, validates, cuts over, operates, and evolves durable task-bound collections.

The guided experience extends the existing dispatcher runtime without weakening its auditability, idempotency, recovery, packaging, or live-mutation gates. Raw commands remain available for advanced operation, recovery, and testing, but users are not expected to reconstruct the internal setup procedure.

## Scope

Automation Dispatcher owns:

- collection configuration and effective-dated revisions
- workflow registration, activation, revision, and definition validation
- collection scheduling, due evaluation, claims, leases, procedure execution, external-effect ambiguity, terminal transitions, receipts, audit events, recovery, migrations, integrity checks, backups, restore verification, and sanitized exports
- the six-stage guided lifecycle: discover, propose, initialize, shadow validate, cut over, and operate and evolve
- versioned discovery snapshots, lifecycle plans, portable collection manifests, progress records, readiness reports, canonical hashing, sanitization, drift detection, and resume keys
- the boundary through which supported Codex host tools inspect or change live tasks, automations, and task messages
- natural-language skill routing, lifecycle-facing and low-level CLI operations, machine-readable output, heartbeat generation and verification, installation, upgrades, packaging, validation, and operator documentation

Automation Dispatcher does not own the content of external authority documents or make task conversation into operational authority. The CLI does not pretend to mutate Codex state outside its process. Read-only discovery, source changes, non-live initialization, live registry mutation, and live task or automation mutation remain separate scopes. The user approves outcomes and exact consequential changes, not internal command sequences.

Code anchors:

- `automation-dispatcher/SKILL.md`
- `automation-dispatcher/src/automation_dispatcher/`
- `automation-dispatcher/tests/`

## Component and Capability Map

### Deterministic collection runtime

| Component | Capability |
| --- | --- |
| Definition normalization | Validate schema-version-2 workflows, collection membership, procedure contracts, authority references, reporting, retry, lease, sensitivity, retention, revisions, and canonical hashes |
| Collection scheduling | Normalize five-field cron expressions and supported presets, evaluate timezone-aware occurrences, preserve DST adjustment evidence, and apply effective lateness and catch-up policy |
| Registry | Store current dispatcher and workflow projections alongside immutable revision history and activation cutoffs |
| Claims | Create one run per workflow occurrence, pin workflow and dispatcher revisions, fence ownership by lease and claim owner, and prevent duplicate execution |
| Runner | Resolve relative scripts from the definition directory, restrict them to approved roots, bound output, pass stable idempotency identifiers, or return host actions |
| External-effect handling | Persist an effect-start boundary before execution and require reconciliation when the outcome may be ambiguous |
| Receipts | Persist one bounded material receipt with terminal state, fence delivery attempts, preserve the exact destination and payload, and acknowledge observed external message IDs |
| Routing | Compare configured and observed task, automation, working-directory, harness, and host identity at explicit assurance levels |
| Audit | Append canonical hash-linked immutable events in the caller's transaction and verify the full chain |
| Database lifecycle | Apply packaged forward-only migrations, reject unsafe legacy timing promotion, enforce foreign keys and integrity, and keep runtime state outside source and install roots |
| Backup and export | Create SQLite-consistent backups, verify them through temporary restore and integrity checks, and emit bounded redacted operational exports |

### Guided lifecycle

#### Discover

- Inspect only the in-scope Codex tasks and automations through supported host tools.
- Record stable automation and task IDs, enabled or paused state, schedules, timezones, target tasks, working directories, prompts, reporting routes, authorities, installation evidence, and route facts when observable.
- Label facts as confirmed, inferred, or missing. Do not infer collection identity from names such as “Daily Automations” or “Weekly Automations.”
- Exclude secrets and unnecessary prompt history, then normalize and hash a versioned discovery snapshot.

#### Propose

- Group workflows only when schedule, timezone, authority boundary, working-directory requirements, and route are genuinely compatible.
- Identify collections to create or reuse, candidate tasks and in-place heartbeat automations, workflow assignments, exclusions, conflicts, unresolved decisions, expected live changes, effective occurrence boundaries, and rollback paths.
- Ask only for choices that cannot be verified, such as the reporting task, inclusion of a paused automation, or an authority-boundary decision.
- Produce a versioned lifecycle plan bound to the exact discovery snapshot; do not mutate state.

#### Initialize

- After explicit non-live approval, generate state paths, collection configuration, schema-version-2 workflow definitions, canonical CLI inputs, and heartbeat templates from the approved plan.
- Initialize each external database, dry-run and register definitions, record configuration and receipts, and create verified backups and sanitized exports.
- Never require the user to translate prompts into definitions, calculate hashes, provide discoverable values, or invoke low-level commands.
- Make repeated unchanged application a no-op with durable progress; stop on conflicts with a reviewable diff.

#### Shadow validate

- Verify database integrity, foreign keys, audit chains, routes, definitions, schedules, heartbeat coverage, historical and upcoming occurrences, fan-out, duplicate ticks, claim contention, receipt fencing, backup restoration, authority isolation, and rollback readiness without executing live effects.
- Compare legacy and dispatcher occurrence calculations and prove the proposed cutover cannot omit or duplicate intended work.
- Produce a concise readiness report with pass, fail, warning, unresolved-decision, and evidence fields. Required failures block cutover.

#### Cut over

- Present one collection-specific live proposal containing exact task and automation IDs, before and after configuration, legacy automation disposition, occurrence boundary, rollback steps, and readiness evidence.
- After explicit approval, prefer updating compatible existing automations in place, then disable or revise only overlapping legacy automations in the safe sequence.
- Record observed host identifiers and configuration, verify route and schedule coverage, observe a bounded live occurrence when authorized, and reconcile every run and receipt.
- Report accepted, attention-needed, or rolled-back state. Approval cannot transfer between collections or from initialization to live mutation.

#### Operate and evolve

- Keep the safe heartbeat loop as the normal execution path.
- Route additions, revisions, enables, disables, schedule or route changes, audits, upgrades, recovery, new collections, lifecycle status, and resume through the same guided capability.
- Discover existing collections from verified heartbeat configuration, external dispatcher state, and recorded manifests, then state the selected collection and evidence before mutation.

### Lifecycle artifacts

| Artifact | Purpose | Required behavior |
| --- | --- | --- |
| Discovery snapshot | Preserve the read-only source facts used for planning | Versioned, canonical, bounded, confidence-aware, sanitized, and hashed |
| Lifecycle plan | Express desired topology and authorized staged work | Bound to one snapshot hash, reviewable without mutation, explicit about decisions, paths, host changes, rollback, and stage status |
| Portable collection manifest | Let agents locate and understand an existing collection across tasks or checkouts | Source-controlled, non-secret, path-explicit, linked and hashed from registry state, and free of mutable run data |
| Progress record | Make each plan stage and step safely resumable | Stable operation and step IDs, status, timestamps, actor, plan hash, evidence, product IDs, events, and receipts |
| Readiness report | Summarize shadow-validation and cutover readiness | Deterministic check IDs, pass/fail/warn status, blockers, unresolved decisions, evidence, and tested occurrence boundary |

### Codex host integration

| Host capability | Product behavior |
| --- | --- |
| Task discovery | Return stable task IDs, titles as display metadata, working directories, availability, and other supported route facts without treating titles as identity |
| Automation discovery | Return stable automation IDs, prompts, schedules, timezone or equivalent interpretation, enabled state, target task, and supported revision metadata |
| Task mutation | Create or update a collection task only after the exact proposal is approved and return observed identity |
| Automation mutation | Prefer compatible in-place heartbeat updates; create, revise, pause, or disable only the exact approved IDs and fields |
| Receipt posting | Post the exact persisted payload to the exact persisted task after the CLI's posting fence |
| Message reconciliation | Confirm whether the exact payload was posted and return the durable external message identifier before acknowledgment or retry |
| Cutover verification | Re-read live state after mutation and compare it with the approved plan and dispatcher route or schedule expectations |
| Rollback | Apply the approved non-destructive restoration sequence while preserving dispatcher evidence and occurrence boundaries |

### Skill and CLI experience

#### Natural-language skill experience

- Route requests for setup, consolidation, migration, collection scheduling, workflow addition or revision, new collection creation, lifecycle status, resume, cutover, dispatch, recovery, backup, export, and audit into Automation Dispatcher.
- Begin setup and change requests with discovery and a concise explanation of what the skill can do. Do not hand the user a manual sequence that the agent is expected to own.
- Ask only unresolved product choices, present proposals in user language, preserve exact approval gates, and show concise progress and evidence.
- Keep one-off reminders and unrelated scheduling outside the skill when they do not need a durable workflow collection.

#### Lifecycle CLI experience

- Validate and normalize discovery snapshots and lifecycle plans.
- Create a plan, explain it without mutation, apply approved non-live stages, report resumable status, verify live assumptions and readiness, generate heartbeat material, validate installed heartbeat coverage, and record host cutover results.
- Emit versioned JSON with stable status, identifiers, hashes, paths, next action, approval requirement, drift or conflict detail, event and receipt metadata, CLI version, and source revision when applicable.
- Provide concise human output for interactive operators without removing structured evidence.
- Bind mutations to exact plan IDs and hashes and return deterministic no-op, blocked, conflict, failed, and completed results.

#### Existing low-level CLI

- Preserve current commands for initialization, status, route checks and revisions, schedule revision, registration and revision, enable and disable, listing, due evaluation, claim, run, terminal transitions, recovery, receipt acknowledgment and retry, audit, integrity, backup, restore verification, export, and migration.
- Continue requiring explicit database paths and actors for mutations, structured failure exit codes, path validation, route and identity checks, and transactionally persisted events and receipts.
- Treat the low-level surface as an advanced and recovery interface after lifecycle operations exist, not as the normal onboarding flow.

#### Installation, upgrades, and documentation

- Install the skill and CLI separately. The skill provides agent behavior; the Python package provides deterministic execution and state handling.
- Support installation through `uv tool install` from an exact published version or exact source revision. Live heartbeats must not use an unpinned floating `uvx automation-dispatcher` invocation.
- Document CLI upgrade through an explicit pinned `uv tool upgrade` or uninstall and exact reinstall workflow, followed by version, migration dry-run or status, integrity, and installed-command verification before heartbeat use.
- Document skill upgrade through replacement from the authoritative source followed by metadata or validator checks and a new task or skill refresh as required by the host. Upgrading the skill does not upgrade the CLI or migrate live state automatically.
- Never create a global default database during installation. Initialization uses an explicit collection task working directory.
- Lead the README with the outcome, collection model, installation of both surfaces, and natural-language guided setup and change examples. Keep detailed raw commands, recovery, migration, backup, cutover, and troubleshooting in operator references.
- Check every documented command and flag against the parser or installed artifact and require every internal link to resolve.

## Contracts and Data

### Collection schedule and membership

- A dispatcher ID is an arbitrary lowercase slug and is never constrained to `daily`, `weekly`, or a task title.
- One collection owns one current schedule, timezone, maximum lateness, catch-up policy, maximum lookback, route, heartbeat coverage declaration, and enabled state.
- Every enabled workflow in the collection fans out from the same selected collection occurrence. Different schedules require different collections.
- Schedule and route changes create immutable dispatcher revisions with canonical normalized configuration and hashes. Due evaluation segments the lookback by effective revision intervals so a new schedule cannot synthesize retroactive occurrences outside its interval.
- Workflow registration and re-enable activation times prevent newly active workflows from receiving already-closed historical occurrences.

### Workflow definition and revision

- Source definitions use schema version 2, bind to exactly one dispatcher, and omit timezone, schedule, lateness, and catch-up fields.
- Registration validates the source file, canonical definition hash, procedure and external-effect mode, reporting route, retry and lease policies, authority references, sensitivity, and retention.
- The registry stores source location, current revision and hash, activation state, and immutable normalized revisions. Claimed runs execute the exact pinned revision rather than the current projection.
- Revision, enable, disable, and route or schedule mutations are transactional, auditable, and receipt-producing where material.

### Runs, claims, and effects

- A run is uniquely identified by a stable occurrence key and by the workflow plus scheduled instant. Duplicate heartbeats or concurrent workers cannot create a second run for the same occurrence.
- Claim, running, completion, failure, and recovery transitions require the current claim owner and an unexpired lease where applicable. Recovery transfers ownership explicitly and records prior ownership.
- Script procedures execute only from approved roots and receive the run and occurrence identifiers needed for idempotency. Agent, skill, and documented procedures return a bounded host action for the heartbeat to execute and terminalize.
- If an external effect may have occurred without a confirmed outcome, the run becomes `effect_unknown`; it is never treated as a safely retryable failure. Recovery requires an explicit reconciliation outcome and evidence.
- A terminal run transition and its one material receipt commit atomically so a crash cannot leave a terminal run without its report.

### Receipts and audit

- Pending receipts do not expose a postable payload. `receipt-retry` or its API equivalent atomically advances delivery to `posting`, records an attempt, appends an event, and returns the exact persisted task ID and message.
- The host posts exactly that persisted message to exactly that task without summarizing, combining, decorating, or regenerating it.
- If posting may have succeeded but acknowledgment was lost, the agent reconciles the destination before another attempt. `--confirm-not-posted` requires independent proof.
- Repeated acknowledgment returns the stored truth rather than inventing new timestamps or events.
- Every material mutation carries database, CLI, source, identity, and event metadata when applicable. Audit verification checks canonical payloads, hash links, and immutable event history.

### State and portability

- The CLI always receives an explicit database path. Runtime databases, backups, exports, and related mutable files are rejected inside the skill source, installed skill roots, installed CLI environments, broad filesystem roots, and configured forbidden roots.
- SQLite connections enable foreign keys, a bounded busy timeout, full synchronization, and transactional writes. Writer contention must terminate no later than the configured busy timeout plus a generous, platform-tolerant test allowance rather than silently weakening durability. This is a non-hang and durability requirement, not a latency benchmark.
- Migrations are immutable packaged resources. Legacy workflow-owned timing may be promoted only when every workflow in a dispatcher supplies complete, identical, valid timing; otherwise migration fails transactionally.

### Performance and resource policy

- W1 R0 defines no latency, throughput, startup-time, memory, package-size, or test-duration service-level objective. Performance acceptance is limited to preventing hangs and unbounded work under explicit configured limits such as the SQLite busy timeout, finite discovery scope, finite lookback, and bounded retries.
- Wall-clock assertions may use generous, platform-tolerant thresholds only as non-hang safeguards. They are not product benchmarks and must not become release gates for response time or throughput.
- Implementations must not weaken SQLite `FULL` synchronization, transactionality, audit integrity, receipt safety, or backup integrity to improve speed or satisfy a timing check.
- Any future numeric performance target requires an explicit user-approved workload, execution environment, rationale, measurement method, and PRD amendment. Observed slowness may be documented and prioritized, but it cannot become a W1 R0 blocking gate without that authority or a violation of an explicit configured limit.

Code anchors:

- `automation-dispatcher/src/automation_dispatcher/database.py`
- `automation-dispatcher/src/automation_dispatcher/backup.py`
- `automation-dispatcher/tests/test_acceptance_boundaries.py`

### Discovery snapshot and lifecycle plan

- Store stable host identifiers and normalized fields needed to compare schedules, routes, authority boundaries, working directories, and automation state.
- Distinguish confirmed observations from inference or absence and retain the evidence source for every relevant field.
- Replace sensitive prompt bodies or authority contents with classifications, hashes, durable locators, and bounded summaries unless exact content is necessary and explicitly approved.
- Every plan includes a schema version, plan ID, timestamps, actor, source snapshot ID and hash, collection proposals, workflow mappings, exclusions, unresolved decisions, approved scope, state and source paths, expected CLI and host operations, occurrence boundaries, rollback procedures, and per-stage state.
- Support an explain operation that produces human-readable intent and diffs without mutation.
- Bind all mutations to the exact canonical plan hash. Editing a material field invalidates prior approval, and changed live facts produce drift rather than an automatic plan rewrite.
- Model collection-specific approval separately so a plan may coordinate multiple collections without transferring cutover authority between them.

### Portable collection manifest

- Store non-secret dispatcher identity, name, schedule, timezone, route expectations, heartbeat schedule requirement, workflow definition locators, required skill and CLI revisions, and the external database locator.
- Live in an explicitly selected source-controlled directory outside `.automation-dispatcher`, installed skills, and installed CLI environments.
- Exclude credentials, run history, raw event data, receipt payloads, backups, and mutable SQLite content.
- Record the canonical manifest path and hash in dispatcher state and provide deterministic missing, moved, changed, and conflicting-manifest outcomes.

### Progress, resume, storage, and sanitization

- Record a stable operation ID and step ID before or with each material mutation, then record its result and evidence transactionally where possible.
- Status values distinguish planned, awaiting approval, running, completed, blocked, failed, reconciled, rolled back, and superseded without implying success from absence of an error.
- Revalidate plan hash, artifact locators, database integrity, source definition hashes, and applicable host assumptions before resuming.
- Return an already committed CLI result instead of repeating it. Reconcile observed host state before retrying a host mutation that may have succeeded.
- Until a verified task working directory exists, a read-only snapshot and proposal may remain ephemeral or use an explicitly selected path.
- Once initialized, durable lifecycle plan and progress for one collection live under that collection's external `.automation-dispatcher/` directory. A multi-collection operation may use an explicitly selected coordination directory.
- There is no default `~/.automation-dispatcher/` authority and no hidden project-local coordination directory.
- Canonicalize paths before containment checks and reject symlink escapes, broad roots, skill source, installed skills, installed CLI environments, and configured forbidden roots.
- Canonical JSON hashing excludes self-referential hash fields, rejects unsupported values, and produces stable bytes across repeated runs.

### Host discovery, mutation, and reconciliation

- Declare the in-scope task or automation set before broad inspection and do not silently absorb paused, project-bound, or authority-sensitive automations.
- Distinguish stable identifiers from display labels and confirmed fields from unsupported or missing fields. Repeated discovery is safe and creates no task, automation, message, database, or registry event.
- Bind every live mutation request to plan ID and hash, collection ID, exact task or automation ID, expected before-state, desired after-state, actor, reason, and operation ID.
- Reject or return a conflict when the observed before-state differs materially. Do not silently widen the change or create a replacement automation.
- Record attempted action, observed stable IDs, supported before and after fields, timestamps, status, and evidence needed for CLI recording.
- Treat a timeout or lost acknowledgment as ambiguous and reconcile the target before retrying.

### Heartbeat, cutover, and rollback

- One collection uses one heartbeat automation attached to its collection task. The heartbeat schedule covers the collection schedule within configured maximum lateness and may be more frequent than the collection itself.
- The heartbeat uses an exactly pinned installed CLI, explicit external database path, stable dispatcher ID, verified route identity, approved working directory and roots, and the complete host-action continuation and receipt protocol.
- Record stable automation and task IDs plus the observed prompt and schedule hash or equivalent evidence in dispatcher state.
- Changing the registry schedule or route never implicitly changes the live heartbeat; the guided lifecycle applies the corresponding host change under a separate gate.
- Cut over one collection at a time and identify the last legacy-owned and first dispatcher-owned occurrence.
- Prefer revising a compatible legacy automation in place when that produces the safest stable identity. Disable or revise overlaps only after the approved boundary sequence is established.
- Post-mutation verification checks task route, working directory, heartbeat prompt, schedule coverage, enabled state, automation identity, registry record, and any authorized live occurrence.
- Rollback pauses the affected heartbeat, preserves database and audit evidence, reconciles the last dispatcher-owned occurrence, restores legacy behavior from the next safe occurrence, and verifies the resulting route and schedule. Rollback does not delete the dispatcher database.

### CLI, heartbeat, and packaging contract

- JSON stdout is one structured result suitable for agent use. Failures use meaningful nonzero exit codes and include material database, version, source, identity, and event context when available.
- Human summaries do not omit blockers or imply that a live operation occurred when only source, dry-run, or initialization work completed.
- Generated heartbeat content includes pinned CLI invocation, explicit database and dispatcher, route observations, due and run flow, host-action terminalization, receipt fencing, exact posting, acknowledgment, and silent no-due behavior.
- CLI and skill versions are independently observable and upgradeable. Lifecycle plans and manifests state compatible minimum or exact requirements.
- Packaging includes required migrations, Python modules, metadata, references, and skill assets while excluding databases, WAL or SHM files, backups, exports, `.env` files, lifecycle state, and other checkout contamination.

## Integrations

- The skill coordinates user intent, discovery, questions, proposals, approvals, CLI calls, host calls, evidence, and continuation of host-action runs.
- The CLI validates artifacts, creates deterministic inputs, applies registry operations, evaluates schedules, performs shadow checks, records progress and host results, and exposes stable low-level commands for claims, receipts, audit, routing, backup, and recovery.
- The Codex host adapter uses only supported task and automation capabilities to inspect and mutate live state, post exact receipts, reconcile messages, and return observed identifiers.
- Source-controlled workflow definitions, portable manifests, and authority documents supply execution inputs without becoming mutable run state.
- `uv` builds, installs, upgrades, and runs exact Python artifacts. Skill discovery uses supported agent skill directories and metadata independently of CLI installation.

Code anchors:

- `automation-dispatcher/src/automation_dispatcher/cli.py`
- `automation-dispatcher/src/automation_dispatcher/registry.py`
- `automation-dispatcher/src/automation_dispatcher/scheduling.py`
- `automation-dispatcher/src/automation_dispatcher/routing.py`
- `automation-dispatcher/src/automation_dispatcher/receipts.py`

## Rebuild Notes

### Runtime safety

- Preserve all low-level commands and JSON behavior unless a versioned compatibility decision explicitly replaces them.
- Preserve transaction boundaries around claims, audit events, state projections, terminal receipts, and receipt posting fences.
- Test due evaluation across DST gaps and folds, schedule revisions, workflow activation, duplicate heartbeats, contention, crash windows, multi-workflow fan-out, and every external-effect recovery mode.
- Do not replace SQLite with task conversation, split one collection schedule across workflow definitions, or make deletion the normal way to remove a workflow.

### Lifecycle and artifacts

- Make natural-language consolidation, workflow addition, arbitrary-schedule collection creation, lifecycle status, and resume primary acceptance paths.
- Verify that the agent does not expose a manual checklist as the product experience or ask for fields it can discover or derive.
- Test fresh setup, consolidation, mixed schedules, paused automations, route and schedule changes, stale snapshots, partial host success, rollback, repeated apply, malicious paths, symlink escapes, redaction, stable hashes, partial writes, and multi-collection resume.
- Version every artifact schema independently and define compatible readers before writing migrations.
- Do not store the lifecycle plan only in chat, infer manifests from task names, or create a global hidden home-directory registry.

### Host integration

- Implement a narrow adapter over verified Codex task and automation capabilities rather than a fictional universal API.
- Test unsupported fields, missing assurance, changed schedules, duplicate creation attempts, in-place updates, partial success, timeouts, lost acknowledgments, message-post ambiguity, occurrence boundaries, and rollback.
- Do not use task titles as stable identity, raw automation directives in place of supported tools, or a second heartbeat when a compatible automation can be revised.
- Keep live acceptance separately authorized from source implementation and non-live testing.

### Experience and distribution

- Resolve `Q-001` before publishing lifecycle command names, then lock parser, JSON schema, README, runbook, wheel, and installed-tool tests together.
- Test wheels and sdists, exact installed commands outside the checkout, exact-revision `uvx`, packaged migrations, prohibited paths and symlinks, backup restoration, contaminated checkouts, skill validation, and documented commands.
- Preserve top-level public APIs or commands consumed by tests and operators unless a versioned deprecation path is explicit.
- Ensure wheels, sdists, installed skill packages, backups, and sanitized exports cannot accidentally include lifecycle runtime artifacts.

## Source Anchors

- [Automation Dispatcher skill](../../automation-dispatcher/SKILL.md)
- [Automation Dispatcher README](../../automation-dispatcher/README.md)
- [Registry contract](../../automation-dispatcher/references/registry-contract.md)
- [Workflow definition](../../automation-dispatcher/references/workflow-definition.md)
- [Operator runbook](../../automation-dispatcher/references/operator-runbook.md)
- [Guided-lifecycle design](../designs/2026-08-11-automation-dispatcher-guided-lifecycle-orchestration.md)
- [W1 R0 plan overview](../plans/2026-08-11-w1-r0-automation-dispatcher-guided-lifecycle/00-overview.md)
- `automation-dispatcher/src/automation_dispatcher/`
- `automation-dispatcher/tests/`
- `automation-dispatcher/pyproject.toml`
- `automation-dispatcher/scripts/validate_distribution.py`

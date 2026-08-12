---
title: "Automation Dispatcher Guided Lifecycle Orchestration"
kind: "design"
status: "draft"
follow_on:
  route: "change-plan"
  next_prompt: ".make-docs/references/system/prompts/designs-to-plan-change.prompt.md"
  why: "The design adds a guided product lifecycle to an already implemented skill and CLI without replacing their existing safety and durability contracts."
  coordinate_handoff: "unresolved; planner must resolve before writing."
# source:
#   type: "manual-request"
#   path: "current Codex task"
# lifecycle:
#   default_arc: "design -> plan -> PRD -> work -> implementation"
#   departure: "source-to-design-straddle"
#   reason: "The current implementation supplies the low-level dispatcher engine, while this design defines the missing user-facing orchestration layer."
---

# Automation Dispatcher Guided Lifecycle Orchestration

## Purpose

This document defines the missing user-facing lifecycle for the `automation-dispatcher` skill. It turns the existing low-level CLI and operational procedures into a guided, resumable agent workflow for discovering existing Codex automations, proposing compatible collections, initializing dispatcher state, generating and registering workflow definitions, shadow-validating behavior, performing controlled cutover, adding workflows later, and creating new collections.

The design makes setup and maintenance an explicit responsibility of the skill. A user should be able to describe the outcome they want in ordinary language and approve material decisions without remembering phase names, command sequences, database fields, definition schemas, or cutover mechanics.

This document does not authorize live initialization, registry mutation, task changes, automation changes, or implementation. It defines the product contract that subsequent planning and implementation must satisfy.

## Context

### Existing product boundary

The current implementation provides a durable and well-tested execution engine. The Python CLI initializes an explicitly configured collection database, stores collection and workflow revisions, evaluates schedules, claims runs idempotently, executes registered procedures, records audit events, persists receipts, recovers interrupted work, and supports backup, restore verification, export, and migration.

The current skill provides safety rules for using that engine. It separates source work, non-live initialization, live registry mutation, and Codex task or automation cutover into distinct approval gates. It also defines the heartbeat execution loop and requires deterministic CLI mutations rather than ad hoc database edits.

Those capabilities are necessary but not sufficient for the intended product. The public CLI is currently a set of operator primitives such as `init`, `register`, `due`, `run`, `backup`, and `integrity-check`. Its `init` command expects the caller to have already resolved the dispatcher identity, name, description, route, working directory, schedule, timezone, lateness policy, catch-up policy, heartbeat schedule, actor, and reason. Separate documentation tells an operator how to combine those primitives into initialization, registration, shadow validation, migration, and cutover sequences.

### User experience gap

The product currently exposes too much of its internal operating procedure to the user and to each new agent. A user who wants to consolidate existing scheduled tasks is effectively expected to know that the process includes inventory, schedule grouping, task-route selection, database initialization, workflow-definition authoring, dry-run registration, occurrence comparison, backup, shadow validation, cutover ordering, receipt reconciliation, and rollback preparation.

Even when an agent performs the commands, the agent must reconstruct the end-to-end process from the README, runbook, and prior conversation. That makes onboarding dependent on agent interpretation and hidden context instead of a first-class skill workflow. It also creates avoidable risks: skipped validation, inconsistent artifacts, repeated questions, partial initialization that cannot be resumed safely, and live cutover before the dispatcher is ready.

This is exactly the kind of repeated, safety-sensitive process that a skill should encapsulate. The user should supply intent and make decisions; the skill should own the mechanics.

### Relationship to existing authority

The existing authority correctly requires separate gates for source changes, non-live initialization, live registry mutation, and task or automation cutover. This design retains those gates but changes how they are presented and executed.

A gate is an approval boundary, not a manual-work boundary. When a user approves a gate, the skill should perform all deterministic child operations within that approved scope, record progress, verify the result, and return the next decision. The user must not have to recite or execute the child steps.

The database remains the operational source of truth. Task conversation remains the reporting, clarification, and approval surface. The CLI remains the only supported mutation interface for dispatcher state. The Codex host remains responsible for task and automation operations that the standalone CLI cannot perform.

### Design principles

- Intent first: accept ordinary-language goals rather than requiring command knowledge.
- Agent-owned mechanics: discovery, artifact generation, validation, CLI invocation, and evidence collection belong to the skill.
- Minimal questions: ask only for material choices that cannot be discovered or safely inferred.
- Plan before mutation: discovery and proposal are read-only until the user approves a clearly bounded application gate.
- Separate durable state from live cutover: successful initialization never silently changes a Codex task or automation.
- Resume instead of restart: every material lifecycle step is idempotent and recorded so a new agent can continue after interruption or context loss.
- Preserve existing safety: guided orchestration must call the existing deterministic primitives rather than bypassing route, hash, audit, receipt, backup, or recovery controls.
- Show outcomes, not plumbing: normal user-facing responses summarize decisions, evidence, and next approvals; raw commands remain available for operators and debugging.

## Decision

### Product promise

`automation-dispatcher` will provide an agent-owned guided lifecycle in addition to its existing dispatcher runtime. A fresh agent using the installed skill must be able to start from a user request such as the following without relying on prior conversation:

- “Set up Automation Dispatcher for my existing scheduled automations and consolidate compatible ones.”
- “Add this workflow to my 6:00 AM collection.”
- “Create a collection that runs at 9:00 AM on the first business day of each month.”
- “Show me what remains before this collection can be cut over.”
- “Resume the Automation Dispatcher setup we started earlier.”

These phrases are examples rather than magic commands. The skill must recognize equivalent intent from normal language.

### Responsibility split

The guided lifecycle spans three cooperating surfaces.

The skill is the coordinator. It interprets user intent, invokes supported Codex inspection tools, asks only unresolved questions, creates normalized inputs, drives CLI operations, posts reviewable proposals, enforces approval gates, and reports evidence.

The CLI is the deterministic state and validation engine. It validates discovery snapshots and lifecycle plans, initializes external state, generates canonical dispatcher inputs, validates workflow definitions, performs dry runs, records resumable progress, runs shadow checks that do not execute live effects, and exposes machine-readable status.

The Codex host adapter performs live task and automation operations. It inspects existing tasks and automations, creates or updates them only after explicit approval, posts persisted receipts, acknowledges delivery, and returns observed identifiers to the CLI for durable recording.

No layer may silently absorb another layer’s authority. In particular, the CLI must not pretend it can mutate Codex tasks without a supported host operation, and the skill must not bypass the CLI for dispatcher mutations.

### Guided lifecycle model

The lifecycle consists of six resumable stages. Each stage has a clear input, output, and gate.

#### 1. Discover

The skill performs a read-only inventory of the in-scope Codex automations and tasks. It captures stable automation identifiers, enabled or paused state, schedules, timezones, target task identifiers, working directories, prompts, known authorities, reporting destinations, and any observable installation or route data.

Discovery must distinguish confirmed live facts from inferred or missing values. It must not infer collection identity from task titles such as “Daily Automations” or “Weekly Automations.” It must not silently include paused, project-bound, or authority-sensitive automations unless the user placed them in scope.

The discovery result is normalized into a versioned snapshot that can be validated by the CLI and hashed. Secrets and large prompt histories are excluded. References to sensitive authorities are recorded by durable identifiers or paths rather than copied into the snapshot.

#### 2. Propose

The skill groups candidate workflows by genuinely compatible collection schedule, timezone, authority boundary, working-directory requirements, and route. A workflow with a different schedule belongs in a different collection even if the user wants its receipts reviewed in the same task.

The proposal identifies collections to create or reuse, workflows assigned to each collection, existing tasks that could serve as routes, existing automations that could be converted in place, excluded automations, unresolved decisions, schedule or authority conflicts, and the anticipated rollback path.

The user reviews product decisions rather than command arguments. Typical questions include which task should receive a collection’s receipts, whether a paused automation belongs in scope, whether two workflows with the same timing should share an authority boundary, or whether a new task should be created. Values that can be verified from live configuration must not be asked again.

The proposal stage is read-only. Its output is a versioned lifecycle plan with a stable plan ID, source snapshot hash, intended collections, workflow mappings, planned state paths, expected live mutations, rollback steps, and per-stage status.

#### 3. Initialize

After the user approves the exact non-live initialization scope, the skill applies the plan through deterministic CLI operations. It creates each dispatcher’s state only in the verified task working directory, initializes the external SQLite database, records the collection schedule and route, creates or updates source-controlled version-2 workflow definitions, dry-runs each registration, registers approved definitions, records receipts, and creates verified backups and sanitized exports.

The skill must generate the CLI arguments and definition files. The user must not be required to supply fields that discovery or the approved plan already contains, translate an existing prompt into a definition, calculate a canonical content hash, or invoke the individual commands.

Initialization is idempotent. Reapplying an unchanged approved plan reports already-completed steps without creating duplicate revisions, registrations, receipts, or backups. A conflicting change stops with a reviewable diff instead of silently revising authority.

Initialization does not create, enable, disable, or revise live Codex automations unless a later cutover gate explicitly authorizes those actions.

#### 4. Shadow validate

The skill runs a built-in validation suite against initialized state without executing live workflow effects. It verifies database integrity, foreign keys, audit-chain continuity, routes, definition hashes, collection schedule normalization, heartbeat coverage, upcoming and historical due calculations, workflow fan-out, duplicate-tick behavior, claim contention, receipt creation and retry fencing, backup restoration, authority isolation, and rollback readiness.

For migrations, the skill compares calculated collection occurrences with existing automation schedules and identifies overlap windows. It must prove that a proposed cutover sequence will neither omit an intended occurrence nor execute one twice.

Shadow validation produces a concise readiness report with passed checks, failed checks, warnings, unresolved decisions, and exact evidence references. A collection cannot advance to cutover while a required check is unresolved.

#### 5. Cut over

The skill presents a bounded live-change proposal for one collection at a time. The proposal identifies the exact task, automation IDs, before-and-after heartbeat configuration, legacy automation dispositions, effective occurrence boundary, rollback procedure, and evidence from initialization and shadow validation.

Only after explicit approval does the host adapter create or revise the collection heartbeat and disable or revise overlapping legacy automations. Existing compatible automations should be updated in place when possible rather than duplicated. The sequence must preserve the last completed legacy occurrence and the first dispatcher-owned occurrence.

The skill records observed live identifiers and configuration in the dispatcher through the CLI, verifies route and schedule coverage, observes a bounded live occurrence when authorized, reconciles every member workflow run and receipt, and reports whether the collection is accepted, needs attention, or was rolled back.

Cutover approval is not transferable between collections. Initialization approval is not cutover approval. Source-code implementation approval is not live-state approval.

#### 6. Operate and evolve

After cutover, the normal heartbeat continues to use the existing safe dispatch contract. The guided lifecycle also remains available for workflow additions, workflow revisions, schedule revisions, route changes, audits, upgrades, recovery, and new collections.

The skill discovers existing collections from verified heartbeat configuration, external dispatcher state, and recorded portable manifests rather than from task titles or chat memory. It reports the collection it selected and the evidence used to identify it before making changes.

### Durable lifecycle artifacts

The orchestration layer introduces versioned, machine-readable artifacts with canonical JSON hashing.

The discovery snapshot records read-only observed source state and confidence. It may remain ephemeral until the user chooses a destination, but any plan used for mutation must bind to its exact snapshot hash.

The lifecycle plan records the desired collection topology, unresolved decisions, approved scope, planned paths, workflow-definition destinations, expected live changes, rollback boundaries, and step status. Once a verified task working directory exists, its durable copy lives under that collection’s external `.automation-dispatcher/` state directory. A multi-collection migration may use an explicitly selected coordination directory, but the implementation must never default to the installed skill directory, the skill source checkout, or an implicit home-directory path.

A portable collection manifest records non-secret collection identity, schedule, route expectations, definition locations, CLI and skill revision requirements, and the external database locator. It lives in an explicitly selected source-controlled directory outside `.automation-dispatcher`; its path and hash are recorded in dispatcher state. It contains no secrets, run history, receipt payloads, or mutable database content.

Lifecycle progress records include a stable operation ID, plan hash, stage, step, status, timestamps, actor, evidence references, applicable dispatcher or workflow IDs, and the resulting audit event or receipt identifiers. Repeated execution uses these keys to resume safely.

### User-facing setup contract

The skill must begin by restating the requested outcome and the live scope it will inspect. It then performs read-only discovery without requiring the user to enumerate internal steps.

After discovery, the skill presents one compact decision package. It separates confirmed facts, recommendations, exclusions, conflicts, and questions. It should recommend a default whenever evidence supports one.

After approval, the skill completes every in-scope deterministic operation through the current gate and returns a readiness result. It does not stop after each low-level command or ask the user to paste generated commands.

When a separate gate is required, the skill explains the material effect in user terms. Examples include “create external dispatcher state,” “register these three workflows,” or “replace these two legacy schedules with this collection heartbeat.” It does not frame routine internal commands as individual approval decisions.

If the process is interrupted, the next invocation locates the plan, verifies its hash and live assumptions, reports completed and pending stages, and resumes from the first incomplete safe step. It never relies on the user to reconstruct progress from conversation.

### Existing-automation consolidation

For a request to consolidate existing automations, the skill must inspect the current live configuration before proposing changes. It must handle active and paused automations separately and preserve project-specific working directories and authority boundaries.

The resulting plan may create several collections even when the user initially describes only “daily” and “weekly” groupings. For example, two weekly workflows that run on different weekdays or times require different collection schedules. They may share a reporting task only if routing and authority policy allow it, but they cannot share one dispatcher occurrence stream.

Existing prompts are migration inputs, not permanent heartbeat procedures. The skill extracts each workflow’s stable purpose, registered procedure, authorities, reporting contract, effect behavior, and evidence policy into a source-controlled version-2 definition. The collection heartbeat retains only the stable bootstrap information needed to invoke the dispatcher.

### Adding a workflow to an existing collection

When the user asks to add a workflow, the skill locates candidate collections and verifies schedule compatibility. If exactly one collection matches the user’s stated schedule and authority boundary, it recommends that collection. If no collection matches, it recommends creating a new collection rather than silently changing an existing collection’s schedule.

The skill creates or updates the workflow definition, validates its authorities and external-effect contract, dry-runs registration, shows a semantic summary, and requests approval for the registration mutation. After approval it registers the definition, verifies the resulting receipt and backup, and reports the next inherited occurrence.

The user is not required to know the definition schema, dispatcher ID, database path, registration command, or content hash. Advanced operators may still provide or inspect those values.

### Creating a new collection

When the user requests an automation on a schedule not served by an existing compatible collection, the skill proposes a new collection. It resolves or asks for the destination task, working directory, timezone, schedule, lateness tolerance, catch-up behavior, and reporting expectations. It recommends safe defaults where policy allows and explains only consequential trade-offs.

After approval, it initializes and shadow-validates the collection, then presents a separate live proposal to create or attach the single heartbeat. Creating a collection does not require the task title or dispatcher ID to encode “daily,” “weekly,” or any other cadence identity.

### CLI orchestration surface

The implementation should add a small orchestration surface without removing the existing low-level commands. Exact command naming is a planning decision, but the capability contract is fixed.

The CLI must be able to validate and normalize a discovery snapshot, create a lifecycle plan, explain a plan without mutation, apply approved non-live stages, report resumable status, verify that live assumptions have not drifted, and record host-performed cutover results. It must emit machine-readable JSON suitable for the skill and concise human summaries suitable for operators.

One acceptable shape is a grouped `lifecycle` command with `plan`, `explain`, `apply`, `status`, `verify`, and `record-cutover` subcommands. An equally coherent set of top-level commands is acceptable if planning demonstrates clearer ergonomics. Regardless of spelling, every mutation must bind to an exact plan ID and hash, record actor and reason, and reject stale discovery or changed live assumptions.

The CLI must also provide a deterministic way to generate a heartbeat template and validate an installed heartbeat against the dispatcher’s recorded route and schedule-coverage contract. The host adapter remains responsible for applying that template to Codex.

Low-level commands remain supported for testing, recovery, scripted operations, and advanced users. The README should present the guided agent workflow first and move raw command sequences into an operator or troubleshooting section.

### Skill behavior changes

`SKILL.md` must explicitly route setup, consolidation, migration, workflow addition, new-collection creation, lifecycle status, and resume requests into the guided lifecycle. It must define the discovery-to-proposal-to-approval flow rather than merely pointing the agent at an operator runbook.

The skill must tell agents to use supported Codex task and automation tools for live inspection and mutation, use the CLI for dispatcher state, persist lifecycle progress, and avoid asking the user for discoverable values. It must preserve the existing dispatch loop, receipt fencing, authority isolation, path boundaries, and gate semantics.

Reference documentation should separate user intent examples, agent lifecycle behavior, CLI plan contracts, host-adapter responsibilities, operator recovery, and raw command reference. The README should sell and explain the guided experience before exposing internals.

### Approval model

The standard guided flow uses a small number of meaningful approvals:

1. Read-only discovery normally requires no mutation approval.
2. The user approves the proposed collection topology and explicitly scoped non-live initialization or registry changes.
3. The user separately approves the exact live task and automation cutover for one collection.
4. The user accepts or rejects observed live evidence and any proposed rollback.

Additional approvals are requested only when required by the host, when external effects expand beyond the approved scope, or when live drift invalidates the plan. The skill must not collapse these boundaries into one blanket approval, but it also must not turn every CLI call into a user decision.

### Failure and recovery behavior

Every lifecycle stage fails closed on stale plan hashes, changed automation schedules, missing tasks, route drift, definition drift, database-integrity failure, backup-verification failure, ambiguous external effects, or unresolved duplicate-occurrence risk.

A failure records the last completed safe step and enough evidence to resume. Retrying an operation must not duplicate collection revisions, workflow registrations, live automations, workflow runs, receipts, or backups. If a host mutation may have succeeded but acknowledgment was lost, the skill reconciles live configuration before applying anything again.

Rollback uses the existing non-destructive principles: pause the affected heartbeat, preserve dispatcher evidence, determine the last dispatcher-owned occurrence, restore legacy configuration only from the next safe occurrence, verify route and schedule, and never delete the dispatcher database as part of rollback.

### Security and privacy

Discovery and planning artifacts must not copy secrets, credentials, full sensitive transcripts, signed URLs, or unnecessary prompt history. They store references, hashes, classifications, and bounded summaries.

Plan and manifest paths are canonicalized and must remain outside the installed skill, the skill source checkout when used as runtime state, and installed CLI environments. Database and backup path policies remain mandatory.

The skill loads only the selected workflow definition and its registered authorities during execution. Guided onboarding does not make accumulated task conversation an authority source.

### Non-goals

- Replacing the SQLite registry or existing audit, receipt, claim, recovery, backup, and scheduling contracts.
- Hiding material live changes or weakening explicit cutover approval.
- Automatically merging workflows with merely similar schedules or task titles.
- Treating task conversation as durable configuration.
- Creating a single global database for all collections.
- Making the CLI directly mutate Codex tasks without a supported host adapter.
- Requiring every user to abandon low-level CLI access.
- Performing live initialization or cutover as part of implementing this design.

### Acceptance criteria

The guided lifecycle is complete only when all of the following are demonstrated:

- A fresh agent can start from a normal-language consolidation request with no hidden conversation context and produce a correct read-only inventory and proposal.
- The user is not asked to provide values that supported inspection can discover and is not required to invoke or understand low-level CLI commands.
- The proposal groups workflows by exact compatible collection schedule and authority boundary rather than by daily or weekly labels.
- Applying an approved plan initializes external dispatcher state, generates and validates version-2 workflow definitions, dry-runs and registers them, and produces verified backups without changing live automations.
- Reapplying the same plan is idempotent, and interruption at every material step can be resumed by a new agent from durable evidence.
- Shadow validation demonstrates route, integrity, schedule, occurrence, fan-out, duplicate-prevention, receipt, backup, authority-isolation, and rollback checks without executing live effects.
- Cutover requires a separate exact approval, prefers safe in-place automation revision, reconciles overlap boundaries, and proves no missed or duplicate occurrence.
- Adding a workflow to an existing collection can begin from normal language, automatically locates compatible collections, creates the definition, and requests only the registration decision.
- Creating a collection for a new schedule can begin from normal language and produces initialized, shadow-validated state before any heartbeat is created.
- Lifecycle status and resume requests work after context compaction, application restart, or agent replacement without relying on old task messages.
- Discovery snapshots, plans, and manifests are versioned, hashed, sanitized, path-safe, and excluded from the installed skill artifact unless they are explicit non-runtime fixtures.
- The README leads with the guided agent experience; operator documentation retains exact low-level commands for advanced use and recovery.
- Existing CLI and skill behavior remains backward compatible unless a separately approved change plan explicitly documents a required breaking change and migration.
- Unit, integration, packaging, contamination, and host-adapter acceptance tests cover the natural-language entry points and every lifecycle gate.

## Alternatives Considered

### Keep the current operator-driven workflow

This preserves the existing implementation and documentation, but it leaves users and fresh agents responsible for reconstructing a long, safety-sensitive process. It does not meet the goal of encapsulating repeatable work in a skill and remains prone to skipped or inconsistently applied steps.

### Add only a larger `init` command

A single command with more flags could create more state, but it would not solve discovery, collection grouping, workflow-definition generation, shadow comparison, Codex task mutation, resumability, or user-facing decision handling. It would also encourage collapsing live cutover into initialization, weakening the existing approval boundary.

### Put all orchestration in the Python CLI

The CLI is the right place for deterministic validation and state transitions, but it does not inherently have access to the Codex task and automation tools or the conversational context needed to resolve user intent. Forcing host integration into the CLI would couple the portable package to one runtime and blur authority boundaries.

### Put all orchestration in `SKILL.md`

Natural-language coordination belongs in the skill, but implementing progress, idempotency, plan hashing, validation, and resume behavior only as prose would recreate the current fragility. Deterministic lifecycle artifacts and state transitions need CLI support and tests.

### Automatically perform setup and cutover in one operation

This would feel convenient when everything succeeds, but it would hide material live effects and increase duplicate-execution risk. Initialization and shadow validation must finish before the user approves the exact live cutover.

### Use task titles or a home-directory catalog for discovery

Task titles are descriptive and mutable, while the existing design explicitly rejects daily or weekly identity semantics. An implicit home-directory catalog would contradict explicit external-state placement and could diverge from live heartbeat configuration. Discovery should use verified automation configuration, recorded state locators, and portable manifests.

## Consequences

The product becomes substantially easier to adopt and maintain. Users interact through goals and approvals, while agents consistently perform the same safe mechanics. Existing automations can be consolidated without requiring users to understand the registry schema or migration checklist.

The skill becomes more opinionated. It must recognize lifecycle intent, manage a multi-stage interaction, persist progress, and coordinate Codex host tools with CLI results. This increases the importance of clear responsibility boundaries and acceptance tests at the user-intent level.

The CLI gains a lifecycle-plan contract and additional commands or subcommands. That adds schema and migration work, but it provides deterministic resume, drift detection, auditability, and testability that prose-only orchestration cannot supply.

The implementation must introduce portable collection manifests or an equivalent discoverable locator without creating a hidden global authority. Planning must resolve exact artifact locations and how multi-collection plans are coordinated across working directories.

Documentation will have two layers: a guided user experience and a precise operator reference. Maintaining both requires explicit cross-checks so the friendly path never promises behavior that the CLI and host adapter do not implement.

The existing approval gates remain intact but become less burdensome. Users approve material changes at stage boundaries; they no longer approve or execute every internal command.

Live cutover remains deliberately separate from implementation. Completing the source changes described by this design will not itself initialize the user’s collections or modify their scheduled tasks.

## Intended Follow-On

- Route: `change-plan`
- Next Prompt: [Designs to change plan](../../.make-docs/references/system/prompts/designs-to-plan-change.prompt.md)
- Why: This design adds a guided onboarding, migration, and maintenance lifecycle to an existing skill and CLI while preserving their current runtime contracts.
- Coordinate Handoff: unresolved; planner must resolve before writing.

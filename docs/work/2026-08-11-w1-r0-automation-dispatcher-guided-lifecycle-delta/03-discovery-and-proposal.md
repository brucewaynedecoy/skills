---
title: "Phase 3: Discovery and Proposal"
kind: "work"
status: "active"
coordinate: "W1 R0 P3"
---

# Phase 3: Discovery and Proposal

## Purpose

Let the skill turn a natural-language request and current Codex state into an inspectable, non-mutating proposal for one or more dispatcher collections.

## Overview

This phase implements discovery and proposal only. The skill inspects available tasks and automations through the host adapter, normalizes candidate workflows, groups only compatible work, asks the minimum questions needed, and emits a hash-bound lifecycle plan. Nothing is initialized or cut over yet.

## Source PRD Docs

- [Product overview](../../prd/01-product-overview.md)
- [Automation Dispatcher](../../prd/05-automation-dispatcher.md)

## Stage 1 - Host discovery and normalized snapshot

### Tasks

- [x] t1: Implement a read-only host adapter that inventories relevant scheduled tasks, task targets, prompts, schedules, timezones, enabled/paused state, project or working-directory context, and observable identity/revision metadata.
- [x] t2: Normalize host observations into the versioned discovery snapshot while preserving source identity, uncertainty, unsupported fields, and raw references needed for later read-back.
- [x] t3: Detect already-managed heartbeats and existing manifests so repeat discovery distinguishes current collections, unmanaged legacy tasks, stale artifacts, and unrelated schedules.
- [x] t4: Add discovery filters, explicit selection, bounded input windows, and pagination so the user can scope a large task inventory without silently omitting candidates; bounded discovery means explicit selection, filter, input, or pagination scope and is not a throughput or latency target.
- [x] t5: Implement safe handling for missing host capabilities, inaccessible tasks, deleted targets, incomplete schedule metadata, and environment changes between reads.

### Acceptance criteria

- Discovery is read-only and produces the same canonical snapshot for equivalent host state.
- Task titles such as “Daily Automations” and “Weekly Automations” are treated as labels, never as collection identity or schedule authority.
- Paused, inaccessible, unsupported, and already-managed items are visible rather than silently dropped.
- A second discovery against unchanged state is a no-op with the same semantic result.
- Every discovery bound is expressed as explicit selection, filter, input, or pagination scope rather than as an inferred performance benchmark.

### Dependencies

- Phase 2 lifecycle CLI and artifacts.
- Phase 1 host-adapter contract.

## Stage 2 - Grouping and proposal engine

### Tasks

- [x] t6: Implement grouping rules that require compatible collection schedule, timezone, authority boundary, approved working roots, route identity, host target, and execution constraints.
- [x] t7: Preserve arbitrary supported schedules and treat daily or weekly schedules only as optional presets; split candidates when their collection-owned schedules are incompatible.
- [x] t8: Generate stable dispatcher and workflow identifier suggestions without deriving identity from mutable task titles.
- [x] t9: Convert legacy task prompts into draft schema-v2 workflow definitions with explicit procedure references, authority references, reporting contract, receipt template, data sensitivity, and evidence retention.
- [x] t10: Produce alternatives and warnings for unsafe or ambiguous cases, including mixed schedules, conflicting routes, unknown external effects, missing idempotency, and unsupported procedures.
- [x] t11: Compute a cutover candidate boundary from the source schedules without authorizing or applying it.

### Acceptance criteria

- Compatible daily tasks can be proposed as one collection, compatible weekly tasks as another, and arbitrary new schedules as separate collections without special names.
- Incompatible tasks are never forced into the same collection for convenience.
- Draft definitions contain no workflow-owned schedule fields and pass the same schema-v2 normalization used by low-level registration.
- Proposal output explains grouping decisions, risks, and unresolved questions in both human and JSON forms.

### Dependencies

- Stage 1 normalized discovery snapshot.
- Existing definition and scheduling modules.

## Stage 3 - Skill-guided conversation and plan approval

### Tasks

- [x] t12: Update the skill instructions to route natural-language requests for consolidation, adding a workflow, creating a collection, resuming setup, inspecting status, and changing a schedule into the correct lifecycle operation.
- [x] t13: Implement a minimal-question policy that asks only for information that cannot be discovered or safely defaulted and that would materially change the plan.
- [x] t14: Present the proposal as a concise decision package: proposed collections, workflows, schedule/timezone, target task, source-to-destination mapping, risks, and exact next action.
- [x] t15: Generate an immutable, hash-bound lifecycle plan only after explicit proposal acceptance; record the discovery snapshot hash, selected alternatives, actor, and expiry.
- [x] t16: Add natural-language and CLI acceptance fixtures for consolidating existing daily and weekly tasks, adding one workflow, creating an unrelated schedule, mixed-schedule splitting, paused tasks, and resuming after rediscovery.

### Implementation evidence

- `src/automation_dispatcher/lifecycle_discovery.py` implements supplied-observation discovery, separate lifecycle/management classification, duplicate and manifest-claim fencing, pagination, compatibility grouping and split risks, schema-v2 draft generation, concrete non-authorizing occurrence boundaries, mutually exclusive accepted topology materialization, acceptance-time expiry checks, accepted-path fencing, and proposal hashing.
- `src/automation_dispatcher/cli.py` extends `lifecycle plan` with bounded read-only discovery, explicit paused-source and topology decisions, parity between JSON and bounded human decision packages, and optional explicit accepted-plan output while preserving artifact-validation mode.
- `tests/test_lifecycle_discovery.py` covers ordinary-language routing, daily/weekly and arbitrary schedule splitting, route/target conflicts, paused inclusion decisions, managed-state precedence, duplicate identities and manifest claims, Q-003 fail-closed behavior, unknown cutover boundaries, alternative materialization, acceptance-time expiry, root/traversal/symlink/source/install path fencing, immutable approval binding, CLI proposal output, and explicit write fencing.
- Live host discovery, initialization, registry mutation, host mutation, and cutover remain outside P3. Q-003 remains blocked pending verified callable host schemas.

### Acceptance criteria

- A user can begin with an ordinary request and does not need to remember low-level initialization, registration, backup, or validation commands.
- The skill never treats discussion or proposal review as permission to initialize or mutate live state.
- Accepted plans are bound to exact discovered state and become stale when material inputs change.
- Scenario tests assert both the conversation outcome and the canonical plan contents.

### Dependencies

- Stage 2 proposal engine.

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

- [ ] t1: Implement a read-only host adapter that inventories relevant scheduled tasks, task targets, prompts, schedules, timezones, enabled/paused state, project or working-directory context, and observable identity/revision metadata.
- [ ] t2: Normalize host observations into the versioned discovery snapshot while preserving source identity, uncertainty, unsupported fields, and raw references needed for later read-back.
- [ ] t3: Detect already-managed heartbeats and existing manifests so repeat discovery distinguishes current collections, unmanaged legacy tasks, stale artifacts, and unrelated schedules.
- [ ] t4: Add bounded discovery filters and explicit selection so the user can scope a large task inventory without silently omitting candidates.
- [ ] t5: Implement safe handling for missing host capabilities, inaccessible tasks, deleted targets, incomplete schedule metadata, and environment changes between reads.

### Acceptance criteria

- Discovery is read-only and produces the same canonical snapshot for equivalent host state.
- Task titles such as “Daily Automations” and “Weekly Automations” are treated as labels, never as collection identity or schedule authority.
- Paused, inaccessible, unsupported, and already-managed items are visible rather than silently dropped.
- A second discovery against unchanged state is a no-op with the same semantic result.

### Dependencies

- Phase 2 lifecycle CLI and artifacts.
- Phase 1 host-adapter contract.

## Stage 2 - Grouping and proposal engine

### Tasks

- [ ] t6: Implement grouping rules that require compatible collection schedule, timezone, authority boundary, approved working roots, route identity, host target, and execution constraints.
- [ ] t7: Preserve arbitrary supported schedules and treat daily or weekly schedules only as optional presets; split candidates when their collection-owned schedules are incompatible.
- [ ] t8: Generate stable dispatcher and workflow identifier suggestions without deriving identity from mutable task titles.
- [ ] t9: Convert legacy task prompts into draft schema-v2 workflow definitions with explicit procedure references, authority references, reporting contract, receipt template, data sensitivity, and evidence retention.
- [ ] t10: Produce alternatives and warnings for unsafe or ambiguous cases, including mixed schedules, conflicting routes, unknown external effects, missing idempotency, and unsupported procedures.
- [ ] t11: Compute a cutover candidate boundary from the source schedules without authorizing or applying it.

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

- [ ] t12: Update the skill instructions to route natural-language requests for consolidation, adding a workflow, creating a collection, resuming setup, inspecting status, and changing a schedule into the correct lifecycle operation.
- [ ] t13: Implement a minimal-question policy that asks only for information that cannot be discovered or safely defaulted and that would materially change the plan.
- [ ] t14: Present the proposal as a concise decision package: proposed collections, workflows, schedule/timezone, target task, source-to-destination mapping, risks, and exact next action.
- [ ] t15: Generate an immutable, hash-bound lifecycle plan only after explicit proposal acceptance; record the discovery snapshot hash, selected alternatives, actor, and expiry.
- [ ] t16: Add natural-language and CLI acceptance fixtures for consolidating existing daily and weekly tasks, adding one workflow, creating an unrelated schedule, mixed-schedule splitting, paused tasks, and resuming after rediscovery.

### Acceptance criteria

- A user can begin with an ordinary request and does not need to remember low-level initialization, registration, backup, or validation commands.
- The skill never treats discussion or proposal review as permission to initialize or mutate live state.
- Accepted plans are bound to exact discovered state and become stale when material inputs change.
- Scenario tests assert both the conversation outcome and the canonical plan contents.

### Dependencies

- Stage 2 proposal engine.

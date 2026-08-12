---
title: "03 Open Questions and Risk Register"
kind: "prd"
status: "active"
---

# 03 Open Questions and Risk Register

## Purpose

This is the living register for confirmed product drift, unresolved decisions, and rebuild risks across the skills repository. Items remain here until their closing evidence or decision is recorded; implementation detail does not silently resolve them.

## Confirmed Drift

### D-001 Automation Dispatcher lacks the guided user lifecycle

| Status | Decision | Follow-Up |
| --- | --- | --- |
| Open | Preserve the current deterministic runtime and add the six-stage guided lifecycle defined in `05`. | Execute the W1 R0 delta backlog from the active PRD set. |

**Issue**: Automation Dispatcher currently provides safe low-level runtime and operator commands, but it does not yet own discovery, proposal, non-live initialization, shadow validation, cutover, or resumable lifecycle progress for the user.

**Why it matters**: Users must currently know or reconstruct internal setup steps, which defeats the skill's intended natural-language experience and makes consolidation or future workflow additions harder to perform consistently.

**Recommendation**: Implement the skill-coordinated lifecycle while retaining existing low-level commands and all runtime gates.

**To close**: Ship and validate the lifecycle capability, update user-first documentation, and prove natural-language setup, consolidation, addition, new-collection, resume, and cutover scenarios.

## Open Questions

### Q-001 Lifecycle CLI command and schema shape

| Status | Decision | Follow-Up |
| --- | --- | --- |
| Open | Capability behavior is fixed; exact command grouping, names, and schema versions remain an implementation decision. | Resolve during backlog refinement before public CLI implementation. |

**Question**: Should lifecycle operations use a grouped command such as `lifecycle plan|explain|apply|status|verify|record-cutover`, a set of top-level commands, or another equally coherent surface?

**Why it matters**: The surface must be easy for the skill to drive, understandable to operators, versionable, and compatible with existing commands.

**Recommendation**: Prefer a grouped lifecycle namespace unless parser and installed-tool testing demonstrates a clearer alternative.

**To close**: Record the command grammar and versioned JSON schemas, including stale-plan, no-op, conflict, and partial-progress results.

### Q-002 Manifest location and multi-collection coordination

| Status | Decision | Follow-Up |
| --- | --- | --- |
| Open | Require explicit paths outside prohibited runtime and install roots; do not introduce a hidden home-directory authority. | Select deterministic discovery and coordination rules during artifact implementation design. |

**Question**: How should the skill locate portable collection manifests and a multi-collection lifecycle plan after task restart without relying on task titles, chat memory, or an implicit home directory?

**Why it matters**: Resume and future workflow changes need reliable discovery while preserving portability and authority isolation.

**Recommendation**: Bind manifest locators and hashes into verified heartbeat configuration and dispatcher state, and require an explicit coordination directory for multi-collection operations.

**To close**: Validate the locator precedence, missing-manifest behavior, path restrictions, and multi-collection resume contract.

### Q-003 Supported Codex host capabilities and identity evidence

| Status | Decision | Follow-Up |
| --- | --- | --- |
| Open | Host integration must use supported task and automation tools and persist observed results; unsupported capabilities fail closed. | Verify the target Codex runtime before host-adapter acceptance. |

**Question**: Which live task and automation fields, mutation operations, stable identifiers, message identifiers, and identity assurances are available to the skill in each supported Codex host?

**Why it matters**: Discovery, in-place cutover, receipt acknowledgment, route verification, and lost-ack reconciliation depend on observed host facts.

**Recommendation**: Define a narrow adapter contract around verified capabilities and make missing assurance a reviewable blocker rather than an inferred value.

**To close**: Produce host capability tests and evidence for every discovery, mutation, reconciliation, and identity field required by `05`.

## Rebuild Risks

### R-001 Cutover misses or duplicates an occurrence

| Status | Decision | Follow-Up |
| --- | --- | --- |
| Open | Cut over one collection at a time at an explicit effective occurrence boundary. | Build deterministic overlap and boundary tests before any live cutover. |

**Issue**: Disabling legacy automations and enabling a dispatcher heartbeat in the wrong order can omit intended work or run it twice.

**Why it matters**: Collection consolidation is only safe if the last legacy occurrence and first dispatcher-owned occurrence are provable.

**Recommendation**: Reconcile live schedules, persisted runs, lateness, catch-up, and effective revisions before proposing the mutation sequence.

**To close**: Pass shadow and live-adapter tests for before, during, and after-boundary failures, including lost acknowledgments and rollback.

### R-002 Lifecycle artifacts leak sensitive material or enter prohibited locations

| Status | Decision | Follow-Up |
| --- | --- | --- |
| Open | Store references, hashes, classifications, and bounded summaries; enforce external path policy. | Add sanitization, symlink, contamination, and packaging tests for every new artifact. |

**Issue**: Discovery snapshots and plans could copy prompts, credentials, transcripts, signed URLs, or mutable state into source, installed skill, installed CLI, or distributable archives.

**Why it matters**: The lifecycle sees broad configuration and therefore increases the consequences of weak minimization or path validation.

**Recommendation**: Reuse canonical path checks, add field-level redaction, and validate built artifacts from contaminated checkouts.

**To close**: Demonstrate that snapshots, plans, manifests, backups, exports, wheels, sdists, and installed skills exclude prohibited data and paths.

### R-003 Guided orchestration regresses the existing runtime or distribution

| Status | Decision | Follow-Up |
| --- | --- | --- |
| Open | Existing low-level commands, schemas, migration guarantees, dispatch safety, and pinned installation behavior remain supported. | Make the current regression suite a required gate for lifecycle work. |

**Issue**: New orchestration code may accidentally weaken claims, receipts, routing, revisions, backups, package resources, or installed entrypoints.

**Why it matters**: The guided lifecycle extends a working dispatcher; it does not justify breaking advanced, recovery, or heartbeat use cases.

**Recommendation**: Layer orchestration over public runtime APIs and use forward-only migrations with installed-artifact testing.

**To close**: Pass the complete current suite plus lifecycle, migration, distribution, isolated-install, and pinned-`uvx` compatibility tests.

### R-004 Acceptance proves prose instead of deterministic resume and reconciliation

| Status | Decision | Follow-Up |
| --- | --- | --- |
| Open | Acceptance must inspect durable artifacts, host observations, and idempotent replay results. | Define scenario fixtures and state assertions in the implementation backlog. |

**Issue**: A conversational demo can look successful while hiding duplicate plans, stale assumptions, incomplete host mutations, or an unresumable partial operation.

**Why it matters**: The product promise is that the user can state intent while the skill reliably owns the procedure.

**Recommendation**: Test natural-language entry points through deterministic snapshot, plan, progress, database, receipt, and host-adapter boundaries.

**To close**: Pass interrupted and repeated runs for consolidation, workflow addition, new collection, cutover, rollback, and lost-ack scenarios.

### R-005 External CLI drift invalidates skill instructions

| Status | Decision | Follow-Up |
| --- | --- | --- |
| Open | Pin Automation Dispatcher for live heartbeats and inspect Bear live help for unfamiliar or version-sensitive operations. | Retain installed-artifact and command-contract validation for both skills. |

**Issue**: A skill may route an agent to flags or behavior that differ from the installed Automation Dispatcher or official `bearcli` version.

**Why it matters**: Version drift can turn a safe procedure into a failure or, for mutations, a materially different operation.

**Recommendation**: Keep explicit version checks and upgrade guidance, test the distributed Automation Dispatcher artifact outside the checkout, and rely on Bear's live help instead of an invented static error catalog.

**To close**: Establish release validation that detects documented-command drift and verifies supported minimum versions.

### R-006 Implementation invents unsupported performance gates

| Status | Decision | Follow-Up |
| --- | --- | --- |
| Open | Automation Dispatcher W1 R0 has no performance SLO; only configured-limit and non-hang checks are normative. Numeric targets require an explicit PRD decision with an approved workload, environment, rationale, and measurement method, and durability or safety must never be traded for speed. | Add matching PRD and W1 R0 backlog guardrails, then review implementation evidence for invented targets before phase acceptance. |

**Issue**: Broad proof language such as bounded, complete, or full can lead implementation agents to invent latency, throughput, memory, package-size, or test-duration targets that the product does not require.

**Why it matters**: Unsupported numeric gates can create fragile environment-dependent tests, encourage implementation loops around unattainable thresholds, and pressure agents to weaken SQLite durability, transactional safety, auditability, receipt handling, or backup integrity for speed.

**Recommendation**: Treat configured timeout and finite-scope assertions as termination and bounded-work safeguards rather than product performance benchmarks. Reject any new numeric performance gate unless the active Automation Dispatcher PRD explicitly defines its approved workload, environment, rationale, and measurement method.

**To close**: Confirm that the Automation Dispatcher PRD and W1 R0 backlog contain these guardrails and that implementation review finds no numeric performance target without the required explicit PRD decision or any durability or safety tradeoff made for speed.

## Source Anchors

- [Automation Dispatcher W1 R0 plan](../plans/2026-08-11-w1-r0-automation-dispatcher-guided-lifecycle/00-overview.md)
- [Automation Dispatcher guided-lifecycle design](../designs/2026-08-11-automation-dispatcher-guided-lifecycle-orchestration.md)
- [Automation Dispatcher skill](../../automation-dispatcher/SKILL.md)
- `automation-dispatcher/tests/test_acceptance_boundaries.py`
- [Bear skill](../../bear/SKILL.md)

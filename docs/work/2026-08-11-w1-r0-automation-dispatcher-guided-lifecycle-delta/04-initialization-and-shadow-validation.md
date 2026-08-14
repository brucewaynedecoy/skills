---
title: "Phase 4: Initialization and Shadow Validation"
kind: "work"
status: "active"
coordinate: "W1 R0 P4"
---

# Phase 4: Initialization and Shadow Validation

## Purpose

Apply an approved lifecycle plan through collection initialization and shadow validation while preventing workflow execution and live host cutover.

## Overview

This phase turns an accepted plan into source-controlled workflow inputs, an external collection database, registered definitions, a collection manifest, a heartbeat template, backups, and readiness evidence. The operation is resumable and idempotent. Existing scheduled tasks remain authoritative until a later, separately approved cutover.

## Source PRD Docs

- [Open questions and risk register](../../prd/03-open-questions-and-risk-register.md)
- [Automation Dispatcher](../../prd/05-automation-dispatcher.md)

## Stage 1 - Approved initialization apply

### Tasks

- [x] t1: Implement lifecycle-plan apply for initialization with exact plan-hash, actor, expected source state, explicit manifest path, and explicit external database path requirements.
- [x] t2: Generate schema-v2 workflow definition files and procedure-document stubs only at approved source-controlled paths, preserving existing user files and reporting byte-level conflicts instead of overwriting.
- [x] t3: Initialize or verify the collection database, route, collection schedule, timezone, catch-up policy, lateness policy, heartbeat coverage, and installed/source revision using existing low-level APIs.
- [x] t4: Dry-run and register each workflow through the canonical registry path, then verify normalized definitions, hashes, authorities, procedure containment, reporting targets, and pending receipts.
- [x] t5: Write the collection manifest only after database identity and registrations verify; bind it to the database, collection revision, workflow hashes, lifecycle-plan hash, and explicit heartbeat target.
- [x] t6: Generate a durable heartbeat prompt/template that explicitly invokes the skill, identifies the manifest and database, and delegates due evaluation and execution to the CLI.

### Acceptance criteria

- Initialization requires an approved, unexpired plan whose discovery and source inputs still match.
- Generated source files are deterministic and never overwrite differing user content.
- Mutable SQLite state is created only at an explicit verified external path.
- Repeating initialization after success returns a verified no-op; repeating after partial failure resumes at the first incomplete safe step.
- No workflow procedure, receipt post, or host automation mutation occurs in this stage.

### Dependencies

- Phase 3 accepted lifecycle plan.
- Existing registry, database, route, and definition APIs.

## Stage 2 - Shadow evaluation and readiness evidence

### Tasks

- [x] t7: Implement shadow due evaluation across representative historical and future windows without claiming runs or executing procedures.
- [x] t8: Compare source scheduled-task occurrences with proposed collection occurrences across timezone transitions, DST gaps/folds, schedule revisions, catch-up windows, lateness bounds, registration times, and enable/disable boundaries.
- [x] t9: Verify route identity, task target, working directory, harness, host, authority references, procedure containment, reporting destination, receipt fields, backup viability, and audit integrity.
- [x] t10: Generate a readiness report containing pass/fail evidence, semantic differences, unresolved external-effect risks, the proposed safe cutover boundary, rollback prerequisites, and exact blockers.
- [x] t11: Create and restore-verify a pre-cutover backup and bind its hash and verification result to lifecycle progress without storing the backup in the repository or skill installation.
- [x] t12: Implement a fail-closed readiness decision that cannot pass on warnings classified as blocking, stale source observations, missing workflows, or incomplete host coverage.

### Acceptance criteria

- Shadow validation exercises the full scheduling and routing logic without creating runs, claims, effects, or posted receipts.
- Every source occurrence in the comparison window is either matched once, intentionally outside the collection contract, or reported as a blocking difference.
- Readiness evidence is canonical, hash-bound, sanitized, and reproducible from the same inputs.
- Backup restore, integrity, foreign-key, and audit verification pass before readiness can pass.

### Dependencies

- Stage 1 initialized collection and manifest.

## Stage 3 - Recovery, drift, and phase gate

### Tasks

- [x] t13: Add crash injection around every initialization and readiness persistence boundary and prove safe resume without duplicate definitions, revisions, receipts, backups, or progress events.
- [x] t14: Detect edits to generated definitions, procedure documents, manifest, database projection, collection schedule, route, or discovered host state after initialization and before cutover.
- [x] t15: Produce semantic conflict guidance that identifies the changed field and safest action: accept a new plan, revise the source, reconcile the registry, or abandon and roll back initialization.
- [x] t16: Add full integration tests for first initialization, repeated initialization, partial resume, existing compatible collection, conflicting files, stale plan, forbidden paths, multi-collection manifests, and shadow mismatch.
- [x] t17: Run the existing dispatcher runtime, migration, backup, acceptance-boundary, CLI, and packaging tests and record the phase evidence.

### Acceptance criteria

- All injected failures recover to a truthful state and never report readiness prematurely.
- Drift blocks cutover until explicitly reconciled through a new or revised plan.
- Existing low-level behavior and package contents remain compatible.
- Phase closeout explicitly states that existing Codex tasks and automations are still unchanged.

### Phase evidence

- P4 initialization/shadow suite: `32 passed`; expanded lifecycle/CLI/registry gate: `80 passed`; full dispatcher suite: `193 passed`.
- Python compilation, both lifecycle contract JSON parses, and `git diff --check` passed.
- Offline wheel and source distribution built in an isolated temporary directory; both archives passed `scripts/validate_distribution.py`, and an isolated wheel install returned `automation-dispatcher 0.1.0` with the additive lifecycle apply grammar.
- Make Docs PRD authority validation passed with zero diagnostics. JDocMunch reindexed the four changed documents; repository-wide link audit retained 13 known Make Docs template/example placeholders and found no broken link in a changed Automation Dispatcher document.
- Runtime-artifact scan found no SQLite database, WAL/SHM/journal, backup, export, or environment-secret artifact in the repository or built distributions.
- Crash injection covers source generation, database initialization, workflow registration, manifest, heartbeat template, backup, audited progress savepoint/replacement, completed progress, and readiness persistence. Replays are no-ops and do not duplicate registry, audit, receipt, backup, or progress state.
- Shadow evidence proves database byte/row/audit-tip invariance, exact occurrence identity including DST behavior, route/config/definition/heartbeat reconciliation, restore-verified backup provenance, and immutable progress-audit binding.
- Q-003 remains fail-closed because callable Codex task and automation schemas are not proven. No live registry, task, automation, heartbeat, message, Bear note, installed skill, host state, cutover, publish, stage, commit, or push action occurred; existing scheduled tasks and automations remain authoritative and unchanged.

### Dependencies

- Stage 2 readiness implementation.

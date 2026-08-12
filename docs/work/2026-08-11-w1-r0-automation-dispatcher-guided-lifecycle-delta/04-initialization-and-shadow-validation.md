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

- [ ] t1: Implement lifecycle-plan apply for initialization with exact plan-hash, actor, expected source state, explicit manifest path, and explicit external database path requirements.
- [ ] t2: Generate schema-v2 workflow definition files and procedure-document stubs only at approved source-controlled paths, preserving existing user files and reporting byte-level conflicts instead of overwriting.
- [ ] t3: Initialize or verify the collection database, route, collection schedule, timezone, catch-up policy, lateness policy, heartbeat coverage, and installed/source revision using existing low-level APIs.
- [ ] t4: Dry-run and register each workflow through the canonical registry path, then verify normalized definitions, hashes, authorities, procedure containment, reporting targets, and pending receipts.
- [ ] t5: Write the collection manifest only after database identity and registrations verify; bind it to the database, collection revision, workflow hashes, lifecycle-plan hash, and explicit heartbeat target.
- [ ] t6: Generate a durable heartbeat prompt/template that explicitly invokes the skill, identifies the manifest and database, and delegates due evaluation and execution to the CLI.

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

- [ ] t7: Implement shadow due evaluation across representative historical and future windows without claiming runs or executing procedures.
- [ ] t8: Compare source scheduled-task occurrences with proposed collection occurrences across timezone transitions, DST gaps/folds, schedule revisions, catch-up windows, lateness bounds, registration times, and enable/disable boundaries.
- [ ] t9: Verify route identity, task target, working directory, harness, host, authority references, procedure containment, reporting destination, receipt fields, backup viability, and audit integrity.
- [ ] t10: Generate a readiness report containing pass/fail evidence, semantic differences, unresolved external-effect risks, the proposed safe cutover boundary, rollback prerequisites, and exact blockers.
- [ ] t11: Create and restore-verify a pre-cutover backup and bind its hash and verification result to lifecycle progress without storing the backup in the repository or skill installation.
- [ ] t12: Implement a fail-closed readiness decision that cannot pass on warnings classified as blocking, stale source observations, missing workflows, or incomplete host coverage.

### Acceptance criteria

- Shadow validation exercises the full scheduling and routing logic without creating runs, claims, effects, or posted receipts.
- Every source occurrence in the comparison window is either matched once, intentionally outside the collection contract, or reported as a blocking difference.
- Readiness evidence is canonical, hash-bound, sanitized, and reproducible from the same inputs.
- Backup restore, integrity, foreign-key, and audit verification pass before readiness can pass.

### Dependencies

- Stage 1 initialized collection and manifest.

## Stage 3 - Recovery, drift, and phase gate

### Tasks

- [ ] t13: Add crash injection around every initialization and readiness persistence boundary and prove safe resume without duplicate definitions, revisions, receipts, backups, or progress events.
- [ ] t14: Detect edits to generated definitions, procedure documents, manifest, database projection, collection schedule, route, or discovered host state after initialization and before cutover.
- [ ] t15: Produce semantic conflict guidance that identifies the changed field and safest action: accept a new plan, revise the source, reconcile the registry, or abandon and roll back initialization.
- [ ] t16: Add full integration tests for first initialization, repeated initialization, partial resume, existing compatible collection, conflicting files, stale plan, forbidden paths, multi-collection manifests, and shadow mismatch.
- [ ] t17: Run the existing dispatcher runtime, migration, backup, acceptance-boundary, CLI, and packaging tests and record the phase evidence.

### Acceptance criteria

- All injected failures recover to a truthful state and never report readiness prematurely.
- Drift blocks cutover until explicitly reconciled through a new or revised plan.
- Existing low-level behavior and package contents remain compatible.
- Phase closeout explicitly states that existing Codex tasks and automations are still unchanged.

### Dependencies

- Stage 2 readiness implementation.

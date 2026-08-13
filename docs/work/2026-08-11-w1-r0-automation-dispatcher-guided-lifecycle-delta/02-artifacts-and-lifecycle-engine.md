---
title: "Phase 2: Artifacts and Lifecycle Engine"
kind: "work"
status: "active"
coordinate: "W1 R0 P2"
---

# Phase 2: Artifacts and Lifecycle Engine

## Purpose

Implement the deterministic artifacts and resumable orchestration engine that make the guided lifecycle safe, inspectable, and recoverable.

## Overview

This phase builds the lifecycle substrate without performing host mutations. It adds canonical models, durable progress, semantic drift detection, step planning, status reporting, and CLI operations that can validate and explain lifecycle state. All state-changing operations remain explicit and audit-bound.

## Source PRD Docs

- [Product overview](../../prd/01-product-overview.md)
- [Architecture overview](../../prd/02-architecture-overview.md)
- [Open questions and risk register](../../prd/03-open-questions-and-risk-register.md)
- [Automation Dispatcher](../../prd/05-automation-dispatcher.md)

## Stage 1 - Canonical artifact implementation

### Tasks

- [x] t1: Implement typed, versioned models for discovery snapshots, lifecycle plans, collection manifests, progress records, readiness reports, semantic drift reports, and host mutation request/results.
- [x] t2: Implement canonical JSON serialization and verification so hashes are stable across key order, process, platform, and equivalent input forms.
- [x] t3: Implement field-level redaction and sanitized export views that omit secrets, unsafe procedure content, local-only absolute paths, and runtime evidence not approved for export.
- [x] t4: Implement explicit-path loading and atomic writing with parent validation, symlink resolution, forbidden-root checks, restrictive permissions where supported, and no fallback to the source or installed skill tree.
- [x] t5: Add schema evolution helpers that distinguish supported upgrades, unsupported future versions, corrupt artifacts, and valid older artifacts requiring migration.

### Acceptance criteria

- Round-trip tests preserve canonical content and hash values on supported platforms.
- Tampering, unknown incompatible versions, unsafe paths, and redaction leaks fail with structured errors.
- Artifact writes are atomic and do not leave a valid-looking partial file after injected failure.
- Sanitized exports contain only the documented allowlist.

### Dependencies

- Phase 1 accepted lifecycle and artifact contracts.

## Stage 2 - Durable lifecycle state machine

### Tasks

- [x] t6: Implement the lifecycle state machine with legal transition checks, phase prerequisites, blocked states, approval boundaries, and explicit terminal or resumable outcomes.
- [x] t7: Implement deterministic step identifiers and progress persistence so a completed step can be recognized after interruption without repeating external or database effects.
- [x] t8: Implement optimistic concurrency for lifecycle artifacts and registry-bound progress so stale agents cannot overwrite newer decisions or host observations.
- [x] t9: Implement semantic drift comparison for schedules, timezone, workflow identity, definitions, procedure references, authorities, routes, heartbeat targets, and host automation state.
- [x] t10: Implement recovery classification for safe retry, already applied, reconciliation required, invalidated plan, blocked prerequisite, and operator decision required.
- [x] t11: Bind lifecycle state changes to the existing audit chain and return event identifiers and hashes for every material mutation.

### Acceptance criteria

- Repeating any completed lifecycle step returns an idempotent result or a precise conflict; it does not duplicate registry rows, receipts, backups, or host requests.
- Stale lifecycle plans cannot advance after relevant input or host state changes.
- Crash injection before, during, and after artifact/progress writes produces a recoverable state with no false completion.
- Audit verification proves a complete transition history without weakening immutable-event behavior.

### Dependencies

- Stage 1 artifact implementation.
- Existing audit and database transaction APIs.

## Stage 3 - Lifecycle CLI foundation

### Tasks

- [x] t12: Add lifecycle commands for artifact validation, plan explanation, status, semantic verification, and the non-mutating portion of apply planning using the Phase 1 command contract.
- [x] t13: Support human-readable guidance and stable JSON output from the same internal result models without changing behavior by output format.
- [x] t14: Add structured next-action and blocking-reason output that the skill can translate into concise user prompts.
- [x] t15: Add an explicit dry-run mode that performs all reads and validations available at that stage while preventing registry, artifact, host, task, automation, and receipt mutations.
- [x] t16: Add CLI tests for success, no-op, stale, invalid, unsupported, partial-progress, recovery-required, and forbidden-path outcomes, including meaningful exit codes and complete metadata on exceptions.

### Acceptance criteria

- The CLI can validate and explain every lifecycle artifact without requiring the skill to reproduce validation logic.
- Dry-run results are side-effect free and state exactly what would be read, written, or requested in a later approved apply.
- JSON output is stable, versioned, and complete on both success and failure.
- Existing low-level command tests and the full runtime suite remain green.

### Dependencies

- Stage 2 lifecycle state machine.

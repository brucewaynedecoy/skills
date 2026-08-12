---
title: "Phase 1: Contracts and Foundation"
kind: "work"
status: "active"
coordinate: "W1 R0 P1"
---

# Phase 1: Contracts and Foundation

## Purpose

Freeze the contracts that every later guided-lifecycle phase will implement while preserving the current dispatcher runtime, CLI, database, audit, scheduling, receipt, and packaging behavior.

## Overview

This phase converts the remaining implementation questions into explicit, versioned interfaces. It establishes lifecycle vocabulary, command and JSON contracts, artifact locations, compatibility rules, and the boundary between the installed skill, the deterministic CLI, and Codex host actions. It does not initialize a live collection or mutate a Codex task or automation.

## Source PRD Docs

- [Product overview](../../prd/01-product-overview.md)
- [Architecture overview](../../prd/02-architecture-overview.md)
- [Open questions and risk register](../../prd/03-open-questions-and-risk-register.md)
- [Automation Dispatcher](../../prd/05-automation-dispatcher.md)

## Stage 1 - Baseline and compatibility envelope

### Tasks

- [ ] t1: Capture the current CLI command inventory, public Python modules, database schema version, migration checksums, package contents, installed entrypoint behavior, and full passing test baseline.
- [ ] t2: Record the current runtime invariants that the lifecycle work must not weaken: collection-owned schedules, effective-dated revisions, occurrence uniqueness, claim fencing, external-effect ambiguity handling, atomic terminal receipts, audit chaining, backup integrity, and external runtime paths.
- [ ] t3: Define a compatibility matrix for existing schema-v2 workflow definitions, existing collection databases, current low-level commands, JSON result metadata, exit codes, and packaged migration resources.
- [ ] t4: Add a frozen regression fixture representing an existing collection and prove that opening, migrating, inspecting, backing up, and dispatching it remains supported.

### Acceptance criteria

- The baseline names exact commands, APIs, schema versions, fixtures, and validation commands rather than relying on prose alone.
- Existing low-level users have an explicit compatibility promise and any permitted change has a named migration or deprecation path.
- The frozen collection fixture passes before lifecycle implementation begins.

### Dependencies

- Active PRDs and the approved W1 R0 plan.
- Current source tree, lockfile, and package metadata.

## Stage 2 - Lifecycle and artifact contracts

### Tasks

- [ ] t5: Define the six lifecycle stages and their legal transitions: discover, propose, initialize, shadow validate, cut over, and operate/evolve.
- [ ] t6: Choose and document the grouped lifecycle CLI namespace and versioned JSON command schemas, including required identity, database, source-revision, event, warning, next-action, and error metadata.
- [ ] t7: Define versioned schemas for the discovery snapshot, lifecycle plan, collection manifest, durable progress record, readiness report, semantic drift report, and host mutation request/result.
- [ ] t8: Define canonical serialization, content hashing, schema-version negotiation, unknown-field handling, redaction rules, and optimistic-concurrency fields for every lifecycle artifact.
- [ ] t9: Define the manifest locator contract for one or many collections, including explicit-path precedence, repository-relative resolution, database binding, heartbeat discoverability, and rejection of ambiguous or implicit home-directory guesses.
- [ ] t10: Define artifact path policy: source-controlled inputs, external mutable state, optional sanitized exports, forbidden roots, symlink handling, permissions expectations, and cleanup ownership.

### Acceptance criteria

- Every artifact has a machine-readable schema, canonical byte representation, stable hash rule, and explicit storage owner.
- Command results can be consumed by the skill without scraping human prose.
- Multiple collections can coexist without relying on collection names, task titles, or current working directory as identity.
- Sensitive prompts, credentials, local absolute paths, and runtime state cannot enter source-controlled artifacts unless an explicit sanitized contract permits them.

### Dependencies

- Stage 1 compatibility envelope.

## Stage 3 - Codex host boundary and decision closure

### Tasks

- [ ] t11: Verify current official Codex skill and scheduled-task behavior and inspect the callable host-tool schemas available in the target environment; record supported, unsupported, and environment-dependent capabilities.
- [ ] t12: Define a host-adapter protocol for listing and reading tasks and automations, identifying a stable task target, creating or updating one collection heartbeat, disabling legacy schedules, posting receipts, acknowledging results, and reading back state.
- [ ] t13: Define an approval envelope that binds the exact lifecycle-plan hash, expected host identities and revisions, requested mutations, safe cutover boundary, actor, expiry, and reconciliation evidence.
- [ ] t14: Define fail-closed behavior for missing host tools, unsupported surfaces, stale reads, partial mutation, approval loss, lost acknowledgement, and host/API schema drift.
- [ ] t15: Resolve Q-001, Q-002, and Q-003 in the risk register from the accepted contracts; update normative PRDs first if any resolution changes product behavior.
- [ ] t16: Add contract tests and JSON fixtures that reject stale plans, mismatched hashes, ambiguous manifests, forbidden paths, unsupported schema versions, incomplete host results, and unapproved mutation attempts.

### Acceptance criteria

- The host adapter exposes the smallest capability surface needed for lifecycle work and does not make the CLI a scheduler.
- A live mutation cannot be expressed without an exact approved plan and expected host state.
- Current official product guidance and current callable capability schemas are recorded separately so environment-specific gaps remain visible.
- Q-001, Q-002, and Q-003 are closed with evidence or remain explicitly blocking; they are not silently assumed away.
- Contract tests pass and no live task, automation, registry, or Bear state is changed.

### Dependencies

- Stage 2 lifecycle and artifact contracts.

---
title: "Phase 6: Experience, Distribution, and Closeout"
kind: "work"
status: "active"
coordinate: "W1 R0 P6"
---

# Phase 6: Experience, Distribution, and Closeout

## Purpose

Make the guided lifecycle understandable and installable, prove the complete product against its PRDs, and prepare a clean release and optional live adoption handoff.

## Overview

This phase brings the agent experience, CLI, documentation, packaging, and validation together. The README sells and explains the guided path first; raw commands remain available as reference and recovery tools. Closeout requires executable evidence, not prose-only confidence.

## Source PRD Docs

- [PRD index](../../prd/00-index.md)
- [Product overview](../../prd/01-product-overview.md)
- [Architecture overview](../../prd/02-architecture-overview.md)
- [Open questions and risk register](../../prd/03-open-questions-and-risk-register.md)
- [Automation Dispatcher](../../prd/05-automation-dispatcher.md)

## Stage 1 - Skill and operator experience

### Tasks

- [ ] t1: Rewrite the skill workflow around user goals and the six lifecycle stages, with natural-language triggers for consolidate, add, create, resume, inspect, revise, recover, and retire.
- [ ] t2: Ensure the skill invokes the CLI for deterministic validation and state changes, uses host tools only through the adapter contract, asks minimal questions, and explains every approval boundary plainly.
- [ ] t3: Update `agents/openai.yaml` metadata and default prompt so the installed skill is discoverable for scheduled-workflow collection goals without implying that daily or weekly task titles are required.
- [ ] t4: Rewrite the README guided path from install through discovery, proposal, initialization, shadow validation, cutover, routine additions, new collections, upgrades, backup, and recovery.
- [ ] t5: Move low-level command detail into focused references and update the registry, workflow-definition, and operator-runbook contracts for lifecycle artifacts, manifest discovery, host cutover, and troubleshooting.
- [ ] t6: Add copy-pasteable examples that use explicit safe paths and clearly label dry-run, source-only, registry mutation, and live-host mutation steps.

### Acceptance criteria

- A user can start with “help me consolidate these scheduled tasks” and does not need to know the CLI command sequence.
- Documentation distinguishes the reusable skill, Python CLI, external collection database, source workflow files, collection task, and heartbeat automation in plain language.
- Daily and weekly are examples or presets only; arbitrary supported collection schedules receive equal treatment.
- Upgrade instructions cover both the uv-installed CLI and the installed skill.
- Raw commands remain documented for inspection, recovery, and advanced operation.

### Dependencies

- Phases 2 through 5 stable command and artifact contracts.

## Stage 2 - End-to-end product acceptance

### Tasks

- [ ] t7: Add end-to-end acceptance for consolidating existing daily and weekly tasks into two collections from a natural-language request through a verified fake-host cutover.
- [ ] t8: Add end-to-end acceptance for adding a workflow to an existing collection, including discovery, compatibility checks, definition generation, registration, shadow validation, receipt, and unchanged heartbeat identity.
- [ ] t9: Add end-to-end acceptance for creating a collection on an unrelated arbitrary schedule, including a new stable task target and one collection heartbeat.
- [ ] t10: Add resume acceptance after interruption at every lifecycle stage, including stale-plan and semantic-drift branches.
- [ ] t11: Add negative acceptance for mixed schedules, route mismatch, unsafe procedure roots, missing idempotency, artifact leakage, unsupported host capabilities, failed backup, and unapproved cutover.
- [ ] t12: Verify ordinary operation after cutover: due evaluation, occurrence fan-out, claim fencing, external-effect ambiguity, terminal receipt creation, receipt posting/acknowledgement, recovery, audit, backup, restore, and schedule revision.

### Acceptance criteria

- Each PRD acceptance scenario is mapped to one or more executable tests with retained evidence.
- Tests assert registry, artifact, host, receipt, and audit outcomes, not only command exit codes or prose.
- Repeated heartbeats and repeated lifecycle requests are idempotent.
- No test requires or mutates the user's live Codex tasks, automations, Bear notes, or production runtime database.

### Dependencies

- Stage 1 skill and documentation.
- Phase 5 deterministic host adapter.

## Stage 3 - Regression, packaging, and installation gates

### Tasks

- [ ] t13: Run the full locked test suite plus focused lifecycle, scheduling, migration, concurrency, crash-window, host-adapter, receipt, backup, contamination, and acceptance tests.
- [ ] t14: Validate that SQLite writer contention returns a lock failure once the configured SQLite busy timeout elapses, allowing a generous platform-independent test tolerance; treat this as a non-hang and durability proof rather than a latency benchmark, never weaken SQLite `FULL` synchronization to satisfy it, and also validate duplicate full heartbeat invocation, DST audit evidence, effective-dated schedule revisions, activation cutoffs, and all supported external-effect recovery modes.
- [ ] t15: Build wheel and sdist from a deliberately contaminated checkout and verify packaged migrations and skill resources are present while databases, WAL/SHM/journals, backups, exports, secrets, caches, and lifecycle runtime artifacts are absent.
- [ ] t16: Install the exact built wheel into an isolated uv tool environment, run help/version/init/lifecycle smoke tests outside the checkout, and run the same exact source through `uvx`.
- [ ] t17: Run the standard skill validator, documentation link validation, distribution validator, lockfile check, compile/static checks, and any repository-required quality gates.
- [ ] t18: Test skill discovery and explicit invocation from a supported Codex surface, including restart guidance only when automatic discovery does not observe the update.

### Acceptance criteria

- The complete regression suite is green from a locked environment.
- Built artifacts are portable, contain required resources, and contain no mutable or sensitive runtime state.
- Exact-wheel install and `uvx` execution work outside the source checkout.
- The installed skill is discoverable and routes representative prompts to the guided lifecycle.
- Any unavailable environment-specific gate is reported as pending rather than treated as passed.
- No unsupported latency, throughput, startup-time, memory, package-size, test-duration, or other performance benchmark is a W1 R0 release gate; any numeric performance target requires explicit normative PRD authority.

### Dependencies

- Stage 2 end-to-end acceptance coverage.

## Stage 4 - Authority reconciliation and release handoff

### Tasks

- [ ] t19: Run an independent read-only review against all applicable active PRDs, the W1 R0 plan, this backlog, the current diff, and the frozen validation evidence.
- [ ] t20: Reconcile D-001, R-001 through R-006, and any newly discovered risks in the canonical risk register; close items only with direct implementation and test evidence.
- [ ] t21: Update the PRD index and follow-on notes only where implementation evidence changes current status; preserve the distinction between source-complete, installed, initialized, live-UAT, and deployed.
- [ ] t22: Produce a scoped release/upgrade handoff with exact changed files, compatibility notes, migration behavior, install and rollback commands, artifact locations, and validation results.
- [ ] t23: Prepare a separate live-adoption packet for the user's existing scheduled tasks, including discovery scope, proposed collection mapping, safe cutover plan, approval point, observation period, and rollback; do not execute it automatically.
- [ ] t24: Close the phase only after owner acceptance and any separately authorized local commit; do not infer push, installation, initialization, or live cutover authority.

### Acceptance criteria

- Independent review finds no unresolved requirement drift, breaking change, or unreported regression.
- PRD and risk status match current evidence and do not claim live operation without live proof.
- Release handoff is sufficient to install, upgrade, verify, and roll back the skill and CLI.
- Live adoption remains a clear, separately authorized next step.

### Dependencies

- Stage 3 green validation and distribution evidence.

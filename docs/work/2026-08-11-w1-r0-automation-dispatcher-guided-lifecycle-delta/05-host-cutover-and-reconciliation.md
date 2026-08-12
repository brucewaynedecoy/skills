---
title: "Phase 5: Host Cutover and Reconciliation"
kind: "work"
status: "active"
coordinate: "W1 R0 P5"
---

# Phase 5: Host Cutover and Reconciliation

## Purpose

Implement approval-bound Codex host changes that cut an initialized collection over to one task-bound heartbeat without duplicate or omitted occurrences.

## Overview

This phase adds the mutation side of the host adapter and the CLI records that make it auditable. Deterministic fake-host and contract tests are required for source acceptance. Mutating the user's actual Codex tasks or automations remains a separate live-UAT authorization.

## Source PRD Docs

- [Open questions and risk register](../../prd/03-open-questions-and-risk-register.md)
- [Automation Dispatcher](../../prd/05-automation-dispatcher.md)

## Stage 1 - Mutation protocol and cutover preparation

### Tasks

- [ ] t1: Implement host mutation request construction from an approved lifecycle plan and passing readiness report, including exact expected task, automation, schedule, prompt, revision, and safe-boundary state.
- [ ] t2: Implement pre-mutation read-back that invalidates the request when any relevant host or registry field differs from the approved expectation.
- [ ] t3: Implement an ordered cutover strategy that updates a compatible existing task-bound heartbeat in place when possible and creates a new one only when the accepted plan requires it.
- [ ] t4: Implement legacy schedule retirement at the approved safe boundary, preserving paused state and unrelated tasks and refusing broad title-based selection.
- [ ] t5: Implement CLI commands to validate a host mutation request and record intended, applied, acknowledged, reconciled, rolled-back, or ambiguous cutover outcomes in the lifecycle audit.
- [ ] t6: Require a fresh, explicit approval envelope immediately before the first live host mutation; bind it to plan, readiness, backup, host snapshot, actor, and expiry hashes.

### Acceptance criteria

- Host mutations address stable resolved identities, never names or search results alone.
- The exact requested changes can be reviewed before any mutation occurs.
- Stale plans, expired approvals, changed host state, failed readiness, or missing backup evidence stop before mutation.
- The CLI records state but does not pretend to perform unavailable host actions itself.

### Dependencies

- Phase 4 passing readiness report and verified backup.
- Phase 1 host-adapter and approval contracts.

## Stage 2 - Safe cutover, acknowledgement, and rollback

### Tasks

- [ ] t7: Implement the host-adapter mutation sequence with per-step read-back, stable idempotency keys, bounded retry rules, and durable result capture after each acknowledged action.
- [ ] t8: Activate the collection heartbeat only at the accepted boundary and ensure legacy schedules are disabled in an order that cannot create an overlapping or missing occurrence.
- [ ] t9: Post and acknowledge configuration and cutover receipts through the existing receipt fence, preserving lost-ack ambiguity and preventing duplicate external posts.
- [ ] t10: Implement rollback for every safely reversible partial state and explicit operator reconciliation for states where the host outcome is unknown or an occurrence may already have run.
- [ ] t11: Re-read the final host and registry state, compare it with the lifecycle plan, and generate a cutover verification report before marking the lifecycle stage complete.
- [ ] t12: Preserve source schedule identities and cutover evidence long enough to explain which system owned every boundary occurrence.

### Acceptance criteria

- Each boundary occurrence has exactly one owner and one recorded disposition.
- Repeating the same mutation request after success is a verified no-op.
- Lost acknowledgement never causes a blind second mutation or receipt post.
- Partial failure either returns to the last verified safe state or stops as reconciliation required with exact evidence.
- Cutover completion requires final host read-back and registry audit verification.

### Dependencies

- Stage 1 approved mutation request.

## Stage 3 - Host simulation, live-UAT packet, and risk evidence

### Tasks

- [ ] t13: Build a deterministic fake host that models list/read/create/update/pause/disable/post/ack operations, revisions, duplicate requests, stale reads, partial failures, and lost acknowledgements.
- [ ] t14: Add tests for in-place heartbeat conversion, new-heartbeat creation, task-target mismatch, schedule drift, legacy-disable failure, heartbeat-enable failure, duplicate invocation, host schema drift, lost ack, rollback, and resume.
- [ ] t15: Add cutover overlap/omission tests around exact occurrence boundaries, DST changes, catch-up windows, task pause/resume, and plan expiry.
- [ ] t16: Prepare a concise live-UAT runbook that lists prerequisites, exact proposed mutations, approval point, observation window, rollback steps, evidence capture, and stop conditions without executing it.
- [ ] t17: Map test and review evidence to R-001 and R-005; close or narrow those risks only when the evidence satisfies their PRD acceptance conditions.
- [ ] t18: Run an independent read-only integrity review of host selection, approval binding, occurrence ownership, receipt fencing, and rollback behavior before phase acceptance.

### Acceptance criteria

- Fake-host and contract tests cover every mutating operation and ambiguous failure window.
- Boundary tests prove no duplicate and no omitted occurrence for supported cutover paths.
- The live-UAT packet is ready but no live task or automation is changed without separate user authorization.
- Independent review finds no unresolved correctness defect; remaining environment limits are explicit.

### Dependencies

- Stage 2 host mutation and reconciliation implementation.

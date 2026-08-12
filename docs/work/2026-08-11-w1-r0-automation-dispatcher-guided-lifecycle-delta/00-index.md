---
title: "Automation Dispatcher Guided Lifecycle Delta"
kind: "work"
status: "active"
coordinate: "W1 R0"
follow_on:
  route: "implementation-loop"
  next_prompt: ".make-docs/references/system/execution-workflow.md"
  why: "The backlog is the implementation queue derived from the plan and PRD contract."
  coordinate_handoff: "Carry this backlog's W/R coordinate into phase history records and commits, adding the active P coordinate for each phase."
---

# Automation Dispatcher Guided Lifecycle Delta

## Purpose

This backlog turns the approved [W1 R0 plan](../../plans/2026-08-11-w1-r0-automation-dispatcher-guided-lifecycle/00-overview.md) and the active [Automation Dispatcher PRD](../../prd/05-automation-dispatcher.md) into a phase-sized implementation queue. It covers the missing guided lifecycle that lets an agent discover existing scheduled tasks, propose collections, initialize and shadow-test them, perform an approved cutover, and maintain them afterward.

The active [PRD index](../../prd/00-index.md) is normative. The plan supplies sequencing and provenance. This backlog does not authorize live registry initialization, Codex task changes, automation changes, Bear changes, commits, pushes, or deployment by itself.

## Phase Map

| Phase | Work packet | Primary outcome | Exit gate |
| --- | --- | --- | --- |
| P1 | [Contracts and foundation](01-contracts-and-foundation.md) | Versioned lifecycle, artifact, command, path, and host-adapter contracts | Decisions are explicit, compatibility is frozen, and contract tests pass |
| P2 | [Artifacts and lifecycle engine](02-artifacts-and-lifecycle-engine.md) | Canonical lifecycle artifacts, durable progress, drift detection, and resumable orchestration | Artifact and lifecycle-engine tests pass without changing live state |
| P3 | [Discovery and proposal](03-discovery-and-proposal.md) | Agent-guided discovery, grouping, proposal, and minimal-question flows | Existing-task and new-collection proposal scenarios pass |
| P4 | [Initialization and shadow validation](04-initialization-and-shadow-validation.md) | Approved non-live initialization, definition generation, registration, shadow checks, and readiness evidence | Repeated initialization is safe and no workflow or host effect runs |
| P5 | [Host cutover and reconciliation](05-host-cutover-and-reconciliation.md) | Approval-bound host mutation, safe-boundary cutover, reconciliation, and rollback | Deterministic host-adapter tests prove no overlap, omission, or silent drift |
| P6 | [Experience, distribution, and closeout](06-experience-distribution-and-closeout.md) | Natural-language UX, operator documentation, full regression evidence, and release readiness | Source, package, install, skill, and end-to-end acceptance gates pass |

## Usage Notes

- Execute phases in order. Do not begin a later phase until the current phase has passed its acceptance criteria, received independent review, and reached an explicitly accepted closeout state.
- Treat implementation, review, owner acceptance, local commit, push, installation, initialization, and live cutover as separate authorizations.
- Use the skill as the coordinator, the Python CLI as the deterministic state and validation engine, and a bounded Codex host adapter for task and automation inspection or mutation.
- Keep the current low-level CLI and SQLite runtime contracts compatible unless an accepted PRD change explicitly says otherwise.
- Keep all mutable runtime state outside the repository and installed skill roots. Generated lifecycle artifacts must use explicit paths, sanitized content, canonical hashes, and fail-closed path checks.
- Resolve open questions in the [risk register](../../prd/03-open-questions-and-risk-register.md) with evidence. If a resolution changes normative behavior, update the PRD authority before implementing the changed contract.
- Source implementation and deterministic adapter tests may proceed without live cutover. Any real Codex task or automation mutation requires a separate, explicit live-UAT authorization and an approved lifecycle plan.

## Intended Follow-On

- **Route:** `implementation-loop`
- Start with the first applicable phase and continue phase-by-phase only after its gate closes.
- Carry `W1 R0` into phase history records and commits, adding the active phase coordinate such as `W1 R0 P1`.
- Preserve unchecked tasks and open risks when evidence is incomplete; do not weaken acceptance criteria to force closure.

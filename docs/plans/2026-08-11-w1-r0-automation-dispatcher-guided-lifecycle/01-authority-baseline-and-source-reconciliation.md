---
title: "P1 Authority Baseline And Source Reconciliation"
kind: "plan-phase"
status: "draft"
coordinate: "W1 R0 P1"
source:
  type: "design"
  path: "docs/designs/2026-08-11-automation-dispatcher-guided-lifecycle-orchestration.md"
---

# P1 Authority Baseline And Source Reconciliation

## Purpose

Establish a trusted current-state and target-state map before product authorities are written. This phase prevents the PRDs from treating planned orchestration as already shipped or overlooking the mature runtime guarantees that the change must preserve.

## Scope

This phase owns source reconciliation and the first drafts of `docs/prd/01-product-overview.md` and `docs/prd/02-architecture-overview.md`. It produces structured handoff notes for later owner PRDs but does not write the shared index, risk register, glossary, work backlog, source code, skill docs, Bear note, or live state.

## Inputs

- [Guided lifecycle design](../../designs/2026-08-11-automation-dispatcher-guided-lifecycle-orchestration.md)
- [Plan overview](./00-overview.md)
- Bear note `484037A0-5CC6-4BB7-8C8C-7DCA5FE53F85`
- Current `automation-dispatcher` skill, README, references, Python sources, migrations, tests, package metadata, and lockfile

## Planned Work

1. Read the Bear authority and design as target intent, then inventory current implementation evidence through JCodeMunch and current documentation through JDocMunch.
2. Build a current-versus-target capability map covering collection creation, workflow registration, schedule ownership, route assurance, dispatch, receipts, recovery, backup/export, installation, guided discovery, proposal, initialization, shadow validation, cutover, operation, evolution, and resume.
3. Mark every capability as `implemented`, `partially implemented`, `documented-only`, `designed`, or `out of scope`, with evidence and owning PRD.
4. Confirm the three-surface topology: skill coordinator, deterministic CLI/state engine, and Codex host adapter.
5. Draft `01-product-overview.md` with users, key capabilities, product boundaries, and current limitations. The current limitation must explicitly state that guided lifecycle orchestration is designed but not yet implemented.
6. Draft `02-architecture-overview.md` with topology, module map, runtime boundaries, data flow, configuration surfaces, and source anchors.
7. Preserve the existing authority boundary: SQLite registry for operational truth, task conversation for reporting and approvals, source definitions for workflow authority, host adapter for live Codex operations.
8. Hand off candidate drift, questions, risks, and glossary terms to the assembly phase without writing shared files prematurely.

## Ownership And Dependencies

- Primary write scope: `docs/prd/01-product-overview.md`, `docs/prd/02-architecture-overview.md`.
- Read scope: design, Bear note, `automation-dispatcher/`, Make Docs contracts.
- Dependency: approved plan.
- Blocks: P2 and P3 must use this phase’s source precedence and capability-status map.

## Acceptance Criteria

- The product overview describes the Automation Dispatcher skill specifically rather than the repository’s general skill collection.
- The architecture overview identifies actual current modules and the planned orchestration boundary without inventing implementation.
- Existing runtime guarantees appear as preserved normative requirements.
- Target guided-lifecycle capabilities are explicitly marked as requirements to implement, not current behavior.
- Live operations remain out of scope and separately gated.
- Every substantive claim has a resolving source anchor or is entered as an open question.
- No shared PRD file outside the assigned scope is modified.

## Validation

- Verify required headings and PRD frontmatter against the selected templates.
- Cross-check module and command claims with JCodeMunch symbols.
- Cross-check skill and operator behavior with JDocMunch sections.
- Search for unsupported claims such as an existing lifecycle-plan command, current automatic automation discovery, or current automatic cutover.
- Return the capability-status map and shared-file handoff notes to the coordinator.

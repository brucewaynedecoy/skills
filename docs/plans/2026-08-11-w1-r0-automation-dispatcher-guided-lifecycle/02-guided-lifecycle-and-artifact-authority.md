---
title: "P2 Guided Lifecycle And Artifact Authority"
kind: "plan-phase"
status: "draft"
coordinate: "W1 R0 P2"
source:
  type: "design"
  path: "docs/designs/2026-08-11-automation-dispatcher-guided-lifecycle-orchestration.md"
---

# P2 Guided Lifecycle And Artifact Authority

## Purpose

Define the user-facing lifecycle and its durable data contracts precisely enough that backlog generation can split deterministic CLI work, skill behavior, persistence, tests, and compatibility without reopening the experience model.

## Scope

This phase owns the guided-lifecycle and lifecycle-artifact sections of `docs/prd/05-automation-dispatcher.md`. It does not own the existing runtime, host adapter, CLI spelling, shared index, risk register, glossary, or implementation backlog. It returns section content to the coordinator so parallel work does not create conflicting writes to the shared skill PRD.

## Inputs

- [Guided lifecycle design](../../designs/2026-08-11-automation-dispatcher-guided-lifecycle-orchestration.md)
- [Plan overview](./00-overview.md)
- P1 capability-status and terminology handoff
- Current CLI JSON result conventions, hashing helpers, external-state path policy, registry transaction rules, and audit/receipt contracts

## Planned Work

1. Define normal-language intent recognition for setup, consolidation, workflow addition, new collection creation, lifecycle status, resume, and cutover-readiness requests without treating example phrases as magic strings.
2. Specify the six lifecycle stages: discover, propose, initialize, shadow validate, cut over, and operate/evolve.
3. For each stage, define preconditions, read/write scope, required inputs, deterministic outputs, approval gate, failure modes, resume keys, and evidence returned to the user.
4. Specify minimal-question behavior: the skill asks only material unresolved choices, recommends defaults when evidence supports them, and never asks for values available through supported inspection.
5. Specify discovery grouping by exact schedule, timezone, authority boundary, working-directory requirements, and route. Explicitly reject grouping by task title or loose daily/weekly labels.
6. Specify the discovery snapshot schema boundary, including version, observed facts, confidence or assurance, exclusions, source references, sanitization, canonicalization, and hash.
7. Specify the lifecycle plan schema boundary, including stable plan ID, source snapshot hash, collection topology, workflow mappings, unresolved decisions, approved scope, planned paths, live mutation proposal, rollback boundary, per-stage status, and plan hash.
8. Specify the portable collection manifest boundary, including collection locator, non-secret configuration, definition locations, expected skill/CLI revision, manifest path/hash recording, and prohibition on mutable runtime history.
9. Specify lifecycle progress records and idempotency keys so a new agent can resume safely after context compaction, process failure, or application restart.
10. Define drift behavior for changed source snapshots, live automation schedules, tasks, routes, definitions, manifests, or database state. Stale plans fail closed with a semantic diff.
11. Define initialization replay semantics so unchanged plans do not duplicate revisions, registrations, receipts, exports, or backups.
12. Define shadow-validation evidence for integrity, routes, hashes, schedule coverage, occurrence fan-out, duplicates, claims, receipts, restore, authority isolation, overlap windows, and rollback readiness without live effects.
13. Define per-collection cutover approval and post-cutover acceptance without granting the standalone CLI authority to mutate Codex.
14. Capture security requirements for redaction, bounded summaries, secret exclusion, prohibited paths, source-checkout exclusion, and authority isolation.

## Decisions To Preserve

- User intent and approval drive the lifecycle; users do not execute internal command sequences.
- The skill coordinates, the CLI validates and persists, and the host adapter performs live Codex operations.
- Discovery and proposal are read-only.
- Initialization and registry mutation require exact approved scope.
- Live task and automation cutover is a separate exact gate for one collection.
- Resume is durable and hash-bound rather than conversation-dependent.
- No implicit home-directory global authority is introduced.
- Runtime state stays external to the installed skill and source checkout.

## Ownership And Dependencies

- Primary content scope: guided-lifecycle and lifecycle-artifact sections of `docs/prd/05-automation-dispatcher.md`; coordinator owns final file assembly.
- Dependency: P1 capability-status map and shared terminology.
- Parallelism: may run in parallel with P3.
- Coordination: artifact fields referenced by P3’s CLI/host authorities must be exchanged through the coordinator before assembly.

## Acceptance Criteria

- A downstream worker can derive testable lifecycle states and artifact schemas without consulting the original conversation.
- Each user-facing flow identifies exactly which gate requires approval and which child operations the skill performs automatically.
- Existing-automation consolidation, adding a workflow, and creating a new collection are all covered.
- Resume, replay, drift, ambiguous host mutation, and rollback behavior are normative and fail closed.
- Artifact placement rules do not introduce an implicit home-directory database or store runtime state inside the skill.
- Sensitive prompts, credentials, transcripts, and signed URLs are excluded by contract.
- The authority distinguishes target requirements from current implementation status.

## Validation

- Trace every design acceptance criterion related to lifecycle or artifacts to a normative section.
- Check for duplicated ownership with host or CLI sections and move requirements to the correct section.
- Test the prose against interruption scenarios at every stage.
- Verify terminology against the planned glossary handoff.
- Record unresolved exact schema or command choices in the risk register handoff rather than inventing them.

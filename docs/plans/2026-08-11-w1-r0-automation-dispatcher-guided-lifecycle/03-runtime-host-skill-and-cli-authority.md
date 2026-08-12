---
title: "P3 Runtime Host Skill And CLI Authority"
kind: "plan-phase"
status: "draft"
coordinate: "W1 R0 P3"
source:
  type: "design"
  path: "docs/designs/2026-08-11-automation-dispatcher-guided-lifecycle-orchestration.md"
---

# P3 Runtime Host Skill And CLI Authority

## Purpose

Preserve the current dispatcher runtime as an explicit product contract and define the new host, skill, CLI, heartbeat, operator, packaging, and compatibility boundaries that will implement the guided lifecycle safely.

## Scope

This phase owns the runtime, host-integration, and skill/CLI sections of `docs/prd/05-automation-dispatcher.md`. It consumes P2’s artifact contracts but does not own their schemas, the shared index/risk/glossary files, or implementation work. It returns section content to the coordinator so parallel work does not create conflicting writes to the shared skill PRD.

## Inputs

- [Guided lifecycle design](../../designs/2026-08-11-automation-dispatcher-guided-lifecycle-orchestration.md)
- [Plan overview](./00-overview.md)
- P1 current-state module and capability map
- P2 draft lifecycle and artifact contracts
- Current CLI, registry, database, scheduling, runner, claims, receipts, routing, backup, migrations, tests, skill, README, and references

## Planned Work

1. Define the current collection runtime: one dispatcher per collection, one authoritative versioned collection schedule, enabled workflows inheriting each occurrence, external SQLite per collection, and arbitrary dispatcher/task names.
2. Preserve route assurance, definition hashes, revision pinning, occurrence idempotency, lease ownership, external-effect ambiguity boundaries, atomic terminal receipts, receipt-post fencing, audit immutability, verified backups, sanitized exports, migration checksums, and prohibited runtime paths.
3. Preserve the current low-level CLI as a supported recovery, testing, scripting, and advanced-operator surface unless later implementation explicitly documents a compatible deprecation.
4. Define the orchestration capability surface independent of final command spelling: validate discovery, create/explain/apply/inspect/verify lifecycle plans, report resume status, validate live assumptions, generate and verify heartbeat configuration, and record host-performed cutover results.
5. Require every lifecycle mutation to bind to plan ID/hash, actor, reason, approved stage, expected source snapshot, and expected live assumptions.
6. Define stable JSON result requirements, nonzero failure semantics, bounded human output, applicable identities, audit event metadata, and version/source metadata.
7. Define the skill’s natural-language routing and its obligation to inspect supported Codex state, ask minimal questions, drive the CLI, persist progress, enforce gates, and report outcomes rather than commands.
8. Define the host adapter’s task and automation inventory inputs, supported mutation operations, observed identity, external message posting, acknowledgment, drift reconciliation, ambiguous-ack handling, and live mutation evidence.
9. Require existing compatible heartbeat automations to be revised in place when safe; forbid conflicting duplicate heartbeats.
10. Define heartbeat template generation and verification while preserving the thin-bootstrap contract and existing safe run/receipt continuation.
11. Define collection discovery using verified heartbeat configuration, dispatcher locators, and portable manifests rather than task titles or chat memory.
12. Define installation and packaging compatibility: skill installation and CLI installation remain separate; live heartbeats use pinned installed commands; exact-source `uvx` remains limited to approved ephemeral use; runtime artifacts remain excluded from distributions.
13. Define documentation layers: README guided flow first, agent lifecycle reference, artifact/host contracts, and low-level operator/recovery reference.
14. Define backward-compatibility tests for the existing CLI parser, schema migrations, installed wheel, source distribution, exact-source `uvx`, skill validation, and runtime-state contamination.

## Boundary Matrix

| Concern | Skill | CLI | Codex host adapter |
| --- | --- | --- | --- |
| Interpret user goal | Owns | Does not infer | Supplies observable state only |
| Inspect tasks and automations | Requests and interprets | Validates normalized snapshot | Owns supported inspection |
| Mutate dispatcher state | Coordinates approved command | Owns deterministic mutation | Does not bypass CLI |
| Mutate tasks and automations | Requests exact approved action | Records expected/result evidence | Owns supported live mutation |
| Persist lifecycle progress | Ensures completion | Owns canonical records and hashes | Returns external identifiers |
| Post receipts | Coordinates exact payload | Owns persisted content and fencing | Posts and returns acknowledgment evidence |
| Execute workflows | Follows registered procedure contract | Owns claims/state transitions and scripts | Performs agent/skill/documented host actions |
| Approvals | Presents semantic decision | Verifies approved scope metadata | Enforces host authorization where required |

## Ownership And Dependencies

- Primary content scope: runtime, host-integration, and skill/CLI sections of `docs/prd/05-automation-dispatcher.md`; coordinator owns final file assembly.
- Dependency: P1 baseline.
- Parallelism: may run in parallel with P2, but must consume P2’s stable artifact terminology before finalizing cross-links.
- Shared outputs: send risk items, exact-command open questions, compatibility constraints, and glossary terms to the assembly phase.

## Acceptance Criteria

- Every mature runtime guarantee named in the design remains visible and normative.
- The new orchestration capability does not bypass existing database, audit, claim, receipt, route, or backup controls.
- Host operations are clearly outside the standalone CLI and require separate live approval.
- The skill owns mechanics but does not silently broaden approval scope.
- Command spelling may remain unresolved, but required capabilities and JSON contracts are testable.
- Low-level CLI users and existing live heartbeats have an explicit compatibility and migration contract.
- README and reference responsibilities are unambiguous.
- No PRD claims that implementation or live cutover is already complete.

## Validation

- Trace current runtime claims to code symbols and tests through JCodeMunch.
- Trace skill and operator claims to current docs through JDocMunch.
- Compare P2 artifact fields and lifecycle states with all CLI and host references.
- Search for any requirement that grants live authority to the wrong surface.
- Search for regressions to daily/weekly identity, implicit state paths, unpinned heartbeat execution, or conversation-as-authority behavior.
- Record unresolved host capability and exact CLI-shape questions for P4.

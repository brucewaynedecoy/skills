---
title: "P4 Assembly Validation And Handoff"
kind: "plan-phase"
status: "draft"
coordinate: "W1 R0 P4"
source:
  type: "design"
  path: "docs/designs/2026-08-11-automation-dispatcher-guided-lifecycle-orchestration.md"
---

# P4 Assembly Validation And Handoff

## Purpose

Assemble the independently owned product authorities into one navigable, non-contradictory active PRD namespace, validate it deterministically, and prepare the authoritative handoff to a scoped implementation backlog.

## Scope

This phase owns `docs/prd/00-index.md`, `docs/prd/03-open-questions-and-risk-register.md`, and `docs/prd/04-glossary.md`, followed by a dedicated validation/fix pass over all newly created PRDs. It does not create the work backlog, modify implementation, update Bear, or touch live state.

## Inputs

- [Plan overview](./00-overview.md)
- P1 product and architecture authorities plus capability-status, risk, and terminology handoffs
- P2 guided-lifecycle and artifact authorities plus unresolved decisions and security handoffs
- P3 runtime, host, skill, and CLI authorities plus compatibility and host-capability handoffs
- Make Docs output, change-management, path/link, and authority-validation contracts

## Planned Work

1. Create `00-index.md` with the required reading order, document map, product-oriented kinds, current statuses, current focus, source anchors, audience paths, and `work-backlog-generation` follow-on.
2. Create `03-open-questions-and-risk-register.md` using the required sections and stable IDs. Include all mandatory items from the plan overview and merge additional worker findings without duplication.
3. Create `04-glossary.md` with one stable definition per product term and links to owning PRDs where useful.
4. Assemble `05-automation-dispatcher.md` from the lifecycle/artifact and runtime/host/skill content lanes, preserving one normative skill owner and clear internal section boundaries.
5. Create `06-bear.md` as the single PRD for the independently maintained Bear skill.
6. Verify that normative requirements have exactly one clear owner. Replace cross-document duplication with links or concise boundary summaries.
7. Verify that current runtime and target guided-lifecycle status are consistent across the overview, architecture, Automation Dispatcher sections, and related core PRDs.
8. Verify all source anchors and internal links, including links to the design, this plan, skill docs, and code paths.
9. Verify that filenames, H1s, frontmatter kinds, and index kinds are product-oriented and contain no prohibited editorial identity.
10. Verify that no active PRD uses document-level W/R/P identity. The `W1 R0` coordinate appears only in allowed source lineage or future requirement history.
11. Run `make-docs run prd authority validate --target-root <project-root>` and retain complete structured evidence.
12. Run JDocMunch broken-link and coverage checks, scoped Markdown hygiene checks, and source-claim review through JCodeMunch.
13. Conduct an independent contradiction and safety review focused on approval gates, idempotency, resume, external effects, cutover overlap, host acknowledgment, path safety, secrets, and low-level compatibility.
14. Make only bounded validation fixes. Escalate any substantive product conflict to the coordinator and leave the relevant risk item open rather than inventing a resolution.
15. Produce a final catalog of authoritative PRDs and a coverage matrix mapping every design acceptance criterion to one or more normative sections.
16. Recommend a scoped `W1 R0` delta work backlog, but stop before generating it unless the user separately requests the next lifecycle step.

## Required Risk Register Baseline

The assembled register must include:

- `D-001` for the confirmed gap between the current low-level operator workflow and the required guided lifecycle.
- `Q-001` for final CLI orchestration command and schema spelling.
- `Q-002` for portable manifest placement and multi-collection coordination.
- `Q-003` for supported Codex host inspection, mutation, and identity evidence.
- `R-001` for missed or duplicate occurrences during cutover.
- `R-002` for sensitive data or prohibited-path leakage in lifecycle artifacts.
- `R-003` for backward-compatibility and packaging regressions.
- `R-004` for insufficient user-intent and host-adapter acceptance proof.

Items may be closed only with documented evidence and a current normative resolution. Otherwise they remain `Open`, `Confirming`, or `Deferred` according to the contract.

## Validation Gates

### Structural gate

- Exactly the planned seven numbered PRDs exist: the five fixed core files plus one PRD for each maintained skill.
- Each uses the correct template headings and PRD 23 frontmatter.
- The index document map is complete and uses valid product-oriented kinds.
- No archive action occurred.

### Authority gate

- The deterministic PRD authority validator exits zero.
- Current normative requirements are inline and not delegated to provenance links.
- No editorial operation is represented as a product PRD.
- No duplicate or ownerless normative requirement remains.

### Source gate

- Current runtime claims resolve to current source or tests.
- Target lifecycle claims resolve to the design and plan.
- Current limitations clearly distinguish unimplemented orchestration.
- Bear is cited as source authority where relevant but was not mutated.

### Safety gate

- Registry, audit, receipt, claim, recovery, route, backup, and path guarantees are preserved.
- Approval boundaries remain separate and semantic.
- No PRD authorizes live initialization or cutover.
- No artifact contract permits secrets, implicit home authority, or skill-directory runtime state.

### Link and handoff gate

- JDocMunch reports no new broken links originating from active PRDs.
- Intended follow-on links resolve.
- The PRD index routes to `work-backlog-generation` and carries `W1 R0` source lineage.
- The recommended backlog is a scoped delta rather than a rewrite of nonexistent historical work.

## Ownership And Dependencies

- Assembly write scope: `docs/prd/00-index.md`, `docs/prd/03-open-questions-and-risk-register.md`, `docs/prd/04-glossary.md`.
- Validation/fix write scope: all newly created `docs/prd/*.md` after primary writers finish.
- Dependency: P1, P2, and P3 complete and handed off.
- Coordinator write scope: none when delegation is available; coordinator resolves substantive conflicts and accepts validation evidence.

## Acceptance Criteria

- The active PRD set is complete, navigable, source-backed, and internally consistent.
- Every candidate requirement in the plan has a final owning PRD or documented `none` rationale.
- Every design acceptance criterion maps to current normative authority.
- Open decisions and risks are visible in the canonical register rather than hidden in prose or conversation.
- Deterministic authority and link validation pass.
- No source, Bear, runtime database, task, automation, installation, work backlog, or live state was changed.
- The final handoff explicitly states that PRD completion does not authorize backlog generation or implementation.

## Intended Handoff

After the user accepts the validated PRD set, use its `00-index.md` follow-on to generate a scoped `W1 R0` Automation Dispatcher guided-lifecycle delta backlog. That backlog should sequence implementation by dependency: lifecycle schemas and persistence, deterministic CLI orchestration, skill and host integration, documentation and packaging, then adversarial and installed-artifact validation. The backlog must cite the active PRDs as authority and preserve live initialization and cutover as later separately authorized operational gates.

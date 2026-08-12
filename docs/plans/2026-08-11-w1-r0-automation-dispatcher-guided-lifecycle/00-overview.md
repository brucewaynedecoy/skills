---
title: "Automation Dispatcher Guided Lifecycle Plan"
kind: "plan"
status: "draft"
coordinate: "W1 R0"
source:
  type: "design"
  path: "docs/designs/2026-08-11-automation-dispatcher-guided-lifecycle-orchestration.md"
follow_on:
  route: "prd-generation"
  next_prompt: ".make-docs/references/system/prompts/plan-to-prd-change.prompt.md"
  why: "The design changes an existing implemented skill, but the project has no active PRD namespace; execution must establish current product authority before producing a scoped implementation backlog."
  coordinate_handoff: "Carry W1 R0 into the downstream PRD source lineage and the resulting delta work backlog."
---

# Automation Dispatcher Guided Lifecycle Plan

## Purpose

This plan turns the [Automation Dispatcher Guided Lifecycle Orchestration design](../../designs/2026-08-11-automation-dispatcher-guided-lifecycle-orchestration.md) into a decision-complete documentation program. Its execution will establish the first active PRD namespace for the `automation-dispatcher` skill, define the current runtime as preserved product authority, define the guided lifecycle as the target capability, identify unresolved implementation decisions and risks, and prepare a clean handoff to a scoped implementation backlog.

This plan does not implement the guided lifecycle, initialize dispatcher state, inspect or mutate live Codex automations, update the Bear authority, install packages, or perform cutover. It plans the product-authority work that must precede those actions.

## Objective

Create a coherent active PRD set that lets downstream backlog generation and implementation proceed without reopening the core product decisions already settled in the design. The PRD set must describe the product’s current and target authoritative shape rather than the editorial operation used to change it.

The resulting authority must preserve the existing collection runtime, SQLite state model, audit chain, idempotent claims, receipts, route assurance, backup and recovery behavior, package boundaries, and low-level CLI compatibility while adding a first-class agent-owned lifecycle for discovery, proposal, initialization, shadow validation, controlled cutover, operation, evolution, and resume.

## Governing Invariant

`docs/prd/` will describe the current authoritative product contract for `automation-dispatcher`. It will not contain “add,” “enhance,” “revise,” “migration,” or similar editorial subjects as PRD identities. Change sequencing, source reconciliation, implementation phases, cutover work, and requirement provenance remain in this plan, the future work backlog, and eventual history records.

The design’s gate model remains binding: a gate is an approval boundary, not a requirement for the user to perform or explain internal steps. Documentation or source implementation does not authorize live dispatcher initialization, registry mutation, task changes, automation changes, or cutover.

## Coordinate Decision

- Coordinate: `W1 R0`
- Decision: initial wave and initial revision
- Evidence: the design’s coordinate handoff is unresolved; `docs/plans/`, `docs/prd/`, `docs/work/`, and documentation history contain no earlier project artifacts; the Make Docs wave model therefore defaults the first plan to `W1 R0`.
- Route classification: authoritative change planning because the design explicitly declares `change-plan` and modifies an already implemented skill and CLI.
- Empty-authority handling: the active PRD namespace is empty, so there are no existing PRD owners to update and no archive gate. The required fixed core and coherent product authorities are classified as `create` while their source reconciliation distinguishes existing runtime behavior from new guided-lifecycle requirements.
- Backlog decision: a scoped `W1 R0` delta backlog is sufficient after the PRD set is generated and validated. A full historical implementation backlog is not required.

## Repository Summary

The product is a Python CLI and Codex skill under `automation-dispatcher/`. The current source includes deterministic collection scheduling, dispatcher and workflow registration, SQLite migrations, route assurance, due evaluation, idempotent claims, procedure execution, receipts, audit events, backup, restore verification, sanitized export, packaging, and an operator-facing README and runbook.

The current CLI exposes low-level commands through `automation-dispatcher/src/automation_dispatcher/cli.py`. Registry and dispatcher configuration live in `registry.py`; database initialization, migrations, integrity checking, and path policy live in `database.py`; workflow contracts live in `definitions.py`; collection recurrence lives in `scheduling.py`; procedure execution and host action handoff live in `runner.py`; claim and terminal-state safety live in `claims.py`; receipt fencing lives in `receipts.py`; route assurance lives in `routing.py`; and backup/export behavior lives in `backup.py`.

The design identifies a product-level gap rather than a failure of those runtime primitives. The skill and documentation currently require an agent or operator to reconstruct the full onboarding, migration, and maintenance sequence. The target product makes the skill responsible for that sequence while retaining the CLI as the deterministic state engine and the Codex host as the only surface that mutates tasks and automations.

## Maintenance Inputs

- [Guided lifecycle design](../../designs/2026-08-11-automation-dispatcher-guided-lifecycle-orchestration.md)
- Bear design note `484037A0-5CC6-4BB7-8C8C-7DCA5FE53F85`, to be read as existing product authority and reconciled during PRD generation without editing it during this plan
- `automation-dispatcher/SKILL.md`
- `automation-dispatcher/README.md`
- `automation-dispatcher/references/workflow-definition.md`
- `automation-dispatcher/references/registry-contract.md`
- `automation-dispatcher/references/operator-runbook.md`
- `automation-dispatcher/src/automation_dispatcher/`
- `automation-dispatcher/migrations/` or the actual packaged migration path resolved from source
- `automation-dispatcher/tests/`
- `automation-dispatcher/pyproject.toml` and `automation-dispatcher/uv.lock`

Live tasks, automations, and dispatcher databases are not PRD-generation inputs unless the user separately authorizes read-only live reconciliation. No live write is in scope.

## Active Authority Baseline

`docs/prd/` contains only router files and no active numbered PRDs. Therefore:

- Existing PRDs to update: none.
- Existing PRDs to link only: none.
- Existing active PRD set to archive: none.
- Fixed core to create: `00-index.md`, `01-product-overview.md`, `02-architecture-overview.md`, `03-open-questions-and-risk-register.md`, and `04-glossary.md`.
- Adaptive product authorities to create: one PRD per maintained skill. `05-automation-dispatcher.md` owns the current runtime, guided lifecycle, lifecycle artifacts, host integration, and skill/CLI experience as sections of one product authority; `06-bear.md` owns the independently maintained Bear skill.
- Requirement history entries: none initially because no active PRD contract is being replaced. Source anchors and the plan coordinate provide provenance. Later material replacements may add non-normative requirement history.

## Candidate Decision Matrix

| Candidate requirement area | Decision | Owning output | Reason |
| --- | --- | --- | --- |
| Product purpose, users, collection model, boundaries, and limitations | `create` | `docs/prd/01-product-overview.md` | Required fixed-core authority; no current owner exists. |
| System topology, skill/CLI/host split, registry, data flow, and configuration surfaces | `create` | `docs/prd/02-architecture-overview.md` | Required fixed-core authority; no current owner exists. |
| Known orchestration gap, unresolved command/schema choices, manifest-location decision, host capabilities, compatibility, and cutover risks | `create` | `docs/prd/03-open-questions-and-risk-register.md` | Required living register; no current owner exists. |
| Product terms including collection, dispatcher, workflow, occurrence, snapshot, lifecycle plan, portable manifest, host adapter, shadow validation, and cutover | `create` | `docs/prd/04-glossary.md` | Required fixed-core reference; no current owner exists. |
| Automation Dispatcher runtime, guided lifecycle, lifecycle artifacts, Codex host integration, and skill/CLI experience | `create` | `docs/prd/05-automation-dispatcher.md` | These concerns form one skill product and therefore share one owning PRD; their contracts remain separately navigable as sections. |
| Bear skill purpose, operations, safety boundaries, and integration surface | `create` | `docs/prd/06-bear.md` | Bear is an independently maintained skill and therefore receives its own skill PRD. |
| Replacing the SQLite registry, using task chat as authority, globalizing databases, collapsing gates, or making the CLI mutate Codex directly | `none` | Non-goals in owning PRDs | The design explicitly rejects these directions; they must be represented as current boundaries rather than separate authorities. |
| Updating the Bear design note | `none` | Outside PRD execution | The note remains an input authority; any Bear mutation needs a separate explicit request. |
| Initializing or cutting over the user’s live collections | `none` | Outside PRD execution | Live operations remain separately gated and are not authorized by design or planning. |

## Existing PRDs To Update

None. The active namespace is empty.

If PRDs appear before execution, the executor must stop, re-run ownership analysis, and revise this plan rather than overwriting or duplicating newly active owners.

## Genuinely New Product PRDs

The planned adaptive PRDs are named for the maintained skills they own:

- `05-automation-dispatcher.md`
- `06-bear.md`

The flat tree remains appropriate, but its adaptive unit is the skill rather than each internal subsystem. Runtime, lifecycle, artifact, host-integration, and experience details stay inside the Automation Dispatcher PRD or in linked design, plan, work, reference, and library documents.

## Requirement History Entries

No initial entries are planned because there is no prior active PRD text to preserve. The PRDs will cite the design, this plan, the Bear authority, and current implementation as source anchors. The absence of requirement history must not be misread as absence of product history; it reflects that this is the first active PRD namespace.

## Affected Links, Risks, Plans, And Work

The PRD index must link the fixed core and all adaptive authorities. Every adaptive PRD must link related owners and the design through source anchors. The architecture overview must link the runtime, lifecycle-artifact, host-integration, and skill/CLI authorities.

The risk register must include at least:

- `D-001`: the current implementation has deterministic runtime primitives but lacks the required guided user lifecycle.
- `Q-001`: exact orchestration command grouping, names, and JSON schema versions remain a planning or implementation decision as long as the design’s capability contract is preserved.
- `Q-002`: exact storage and discovery rules for portable manifests and multi-collection lifecycle coordination require resolution without introducing an implicit home-directory authority.
- `Q-003`: supported Codex host tools and identity evidence available during discovery and cutover must be verified before host-adapter implementation is considered complete.
- `R-001`: a cutover implementation could miss or duplicate an occurrence if legacy and dispatcher boundaries are not reconciled deterministically.
- `R-002`: discovery snapshots, plans, or manifests could leak sensitive prompt material or be stored inside prohibited skill/install locations.
- `R-003`: orchestration changes could regress the existing low-level CLI, runtime safety, packaging, or installed heartbeat behavior.
- `R-004`: prose-only natural-language acceptance tests could appear convincing while failing to prove deterministic resume and host reconciliation.

This plan is the first `W1 R0` plan and therefore has no prior plan to update. After PRD validation, the intended next artifact is a scoped `docs/work/YYYY-MM-DD-w1-r0-automation-dispatcher-guided-lifecycle-delta/` backlog. That later backlog must cite the generated PRDs, not this plan, as normative product authority.

## Output Contract

Execution creates exactly one active flat PRD namespace:

```text
docs/prd/
├── 00-index.md
├── 01-product-overview.md
├── 02-architecture-overview.md
├── 03-open-questions-and-risk-register.md
├── 04-glossary.md
├── 05-automation-dispatcher.md
└── 06-bear.md
```

Each document must use its matching Make Docs template, PRD 23 frontmatter, required headings, project-relative links, and source anchors. Current product requirements belong inline in their owning sections. Editorial sequencing stays in this plan and the future work backlog.

PRD generation must reconcile claims against source. Existing runtime behavior is grounded in the current code, schema, tests, skill, and operator references. Target guided-lifecycle behavior is grounded in the design. When those sources conflict, the design governs target product intent, current code governs confirmed present behavior, and the discrepancy belongs in the risk register until implementation closes it.

## Execution Mode And Lifecycle Handling

- Mode: change-oriented PRD authority creation for an existing implemented product with an empty active namespace.
- Archive gate: not required because no active numbered PRD set exists.
- Mutation scope: `docs/prd/` only during PRD generation, plus validation fixes within those newly created documents.
- Out-of-scope writes: `automation-dispatcher/` source or docs, Bear, live databases, tasks, automations, installations, `docs/work/`, and history records.
- Closeout: validated PRDs remain draft or active according to the chosen templates; implementation remains unstarted until the user separately requests downstream work generation and execution.

## Phase Map

| Phase | File | Purpose | Dependency |
| --- | --- | --- | --- |
| P1 | [Authority baseline and source reconciliation](./01-authority-baseline-and-source-reconciliation.md) | Establish source precedence, current-vs-target mapping, fixed-core skeletons, and risk inventory. | Approved plan only. |
| P2 | [Guided lifecycle and artifact authority](./02-guided-lifecycle-and-artifact-authority.md) | Define the natural-language lifecycle, durable artifacts, approvals, idempotency, drift, and resume contracts. | P1 mappings and terminology. |
| P3 | [Runtime, host, skill, and CLI authority](./03-runtime-host-skill-and-cli-authority.md) | Preserve runtime contracts and define host, skill, CLI, heartbeat, compatibility, and operator boundaries. | P1 baseline; coordinates with P2 contracts. |
| P4 | [Assembly, validation, and handoff](./04-assembly-validation-and-handoff.md) | Assemble shared docs, reconcile links and risks, run deterministic validation, and prepare the PRD-to-work handoff. | P1 through P3 complete. |

P2 and P3 may execute in parallel after P1 because their write scopes are disjoint. P4 begins only after both are complete.

## Dependencies

- The plan must be approved as the saved execution authority.
- The source design and current `automation-dispatcher` checkout must remain available.
- The Bear authority must be readable; mutation is unnecessary.
- JCodeMunch and JDocMunch should be available and freshly indexed. If either index is stale, reindex before falling back to direct reads.
- Make Docs templates and `make-docs run prd authority validate` must be available.
- No active PRD files may appear without a plan revision and ownership re-evaluation.
- Delegation should be available for parallel P2 and P3 execution; single-agent fallback is acceptable only when the execution harness lacks delegation.

## Coordinator Policy And Worker Ownership

When delegation is available, the coordinator owns orchestration, gate enforcement, conflict resolution, and final evidence but has no document write scope.

| Workstream | Write scope | Responsibilities | Dependencies |
| --- | --- | --- | --- |
| Baseline worker | `docs/prd/01-product-overview.md`, `docs/prd/02-architecture-overview.md`, baseline mapping evidence | Reconcile current code and docs with the design; establish product and topology authority without prematurely filling shared index/risk/glossary files. | P1 only. |
| Lifecycle worker | Lifecycle and artifact sections of `docs/prd/05-automation-dispatcher.md` | Own natural-language entry points, stages, artifacts, approvals, drift, idempotency, resume, and security contracts. | P1 complete; return section content to the coordinator for assembly. |
| Runtime and integration worker | Runtime, host-integration, and skill/CLI sections of `docs/prd/05-automation-dispatcher.md` | Preserve runtime guarantees and define host, skill, CLI, heartbeat, compatibility, packaging, and operator boundaries. | P1 complete; return section content to the coordinator for assembly. |
| Assembly worker | `docs/prd/00-index.md`, `docs/prd/03-open-questions-and-risk-register.md`, `docs/prd/04-glossary.md` | Assemble navigation, shared terminology, drift/questions/risks, backlinks, and intended follow-on after owner PRDs stabilize. | P1 through P3 outputs. |
| Validation and fix worker | All newly created `docs/prd/*.md`, after primary writers finish | Run structural, link, authority, source-coverage, and contradiction checks; make only contract or cross-document consistency fixes and report any substantive conflict to the coordinator. | Assembly complete. |

Workers are not alone in the repository. They must preserve unrelated changes, avoid reverting other work, honor disjoint ownership, and adjust to already-landed shared outputs.

## MCP Strategy

- Use JDocMunch to read the design, skill documentation, Make Docs contracts, generated PRDs, and link graph.
- Use JCodeMunch to inspect current code symbols, source anchors, call boundaries, and tests without batch-reading the checkout.
- Reindex stale documentation or code indexes before using direct filesystem reads.
- Use the Bear skill and `bearcli` for read-only access to the existing authority note if PRD claims require it.
- Use OpenAI product documentation or supported Codex inspection tools only when current host capabilities must be verified; prefer official sources and do not mutate live state.
- If an MCP service is unavailable after reindex or retry, use narrow `rg` and bounded direct reads, recording the fallback in execution evidence.

## Validation

Plan execution must prove:

- all seven planned numbered PRD files exist, with exactly one adaptive PRD per maintained skill and no unnumbered Markdown added directly under `docs/prd/`;
- filenames, H1 titles, frontmatter kinds, and document-map kinds are product-oriented rather than editorial;
- required headings and PRD 23 frontmatter are present;
- every candidate in this plan maps to `create` or `none` exactly as decided, unless a documented plan revision changes the baseline;
- source anchors resolve to the design, relevant skill docs, and specific current code locations;
- the index, cross-authority links, and intended follow-on links resolve;
- current runtime requirements and target guided-lifecycle requirements are clearly distinguished without describing old behavior as already implemented;
- the risk register contains the required drift, questions, and risks with valid IDs and statuses;
- no live paths, secrets, task transcripts, or mutable runtime data are copied into PRDs;
- `make-docs run prd authority validate --target-root <project-root>` exits zero;
- JDocMunch reports no new broken links originating from the generated PRDs;
- a dedicated validation pass finds no contradictory ownership, duplicated normative requirements, or accidental weakening of existing safety guarantees.

## Intended Follow-On

- Route: `prd-generation`
- Next step: generate the active PRD namespace from this plan using [Plan to PRD change](../../../.make-docs/references/system/prompts/plan-to-prd-change.prompt.md).
- Why: the existing implementation and new guided lifecycle need one current product authority before a delta backlog can sequence source, skill, documentation, packaging, host-integration, and acceptance work.
- Coordinate Handoff: carry `W1 R0` into PRD source lineage and the downstream `W1 R0` delta work backlog.

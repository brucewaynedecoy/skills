---
title: "Skills Repository PRD Index"
kind: "prd"
status: "active"
follow_on:
  route: "work-backlog-generation"
  next_prompt: ".make-docs/references/system/prompts/prd-to-work-full-prd.prompt.md"
  why: "The active PRD set is the effective product contract for repository and skill work."
  coordinate_handoff: "Carry W1 R0 into the Automation Dispatcher guided-lifecycle delta backlog; assign separate coordinates before queuing unrelated Bear or repository work."
---

# Skills Repository PRD Index

## Purpose

This PRD set defines the current authoritative product contract for the skills repository and every skill currently maintained in it. It covers the shared repository boundary, the Automation Dispatcher runtime and planned guided lifecycle, and the Bear CLI skill. It is for product owners, maintainers, implementers, reviewers, and agents that need a reliable starting point before changing a skill.

The repository contains two independently useful skills. Automation Dispatcher combines an agent skill with a Python CLI and external SQLite state to operate scheduled workflow collections. Bear teaches an agent to use Bear's official CLI safely and precisely. The repository does not turn those skills into one runtime or grant one skill authority over the other.

After the fixed core, each maintained skill has exactly one owning PRD named with the skill directory's canonical slug. Skill-internal runtime, lifecycle, integration, artifact, and experience requirements remain sections of that owning PRD; designs, plans, work backlogs, and implementation references hold supporting detail without becoming additional skill PRDs.

## Reading Order

1. [01-product-overview.md](./01-product-overview.md)
2. [02-architecture-overview.md](./02-architecture-overview.md)
3. [03-open-questions-and-risk-register.md](./03-open-questions-and-risk-register.md)
4. [04-glossary.md](./04-glossary.md)
5. [05-automation-dispatcher.md](./05-automation-dispatcher.md)
6. [06-bear.md](./06-bear.md)

## Document Map

| Document | Kind | Status | Related Docs | Focus |
| --- | --- | --- | --- | --- |
| `00-index.md` | `core` | `active` | All PRDs | Explain the authority set and how to read it |
| `01-product-overview.md` | `core` | `active` | `02`, `05`, `06` | Define repository purpose, users, capabilities, boundaries, and limitations |
| `02-architecture-overview.md` | `core` | `active` | `05`, `06` | Define repository topology, runtime boundaries, data flow, and configuration surfaces |
| `03-open-questions-and-risk-register.md` | `core` | `active` | All PRDs | Keep confirmed drift, unresolved decisions, and rebuild risks visible |
| `04-glossary.md` | `core` | `active` | All PRDs | Define canonical repository and skill terms |
| `05-automation-dispatcher.md` | `capability` | `active` | `01`, `02`, `03`, `04` | Define Automation Dispatcher's runtime, guided lifecycle, artifacts, host integration, skill, CLI, and distribution contracts |
| `06-bear.md` | `capability` | `active` | `01`, `02`, `03`, `04` | Define safe Bear discovery, reading, mutation, organization, and export behavior |

## Source Anchors

- [Repository README](../../README.md)
- [Automation Dispatcher skill](../../automation-dispatcher/SKILL.md)
- [Automation Dispatcher README](../../automation-dispatcher/README.md)
- [Automation Dispatcher guided-lifecycle design](../designs/2026-08-11-automation-dispatcher-guided-lifecycle-orchestration.md)
- [Automation Dispatcher W1 R0 plan](../plans/2026-08-11-w1-r0-automation-dispatcher-guided-lifecycle/00-overview.md)
- [Bear skill](../../bear/SKILL.md)

## Audience Paths

### New developer

Read the product and architecture overviews, then the one PRD for the skill being changed. Review `03` before implementation.

### Product or technical lead

Read `01`, `03`, and the relevant skill PRD. For Automation Dispatcher lifecycle planning, use `05` as product authority and the W1 R0 source plan only for sequencing and provenance.

### AI coding assistant

Read `02`, `03`, and the owning skill PRD before opening implementation files. Preserve the gate and authority rules in the owning skill, use code and tests as evidence for current behavior, and treat this PRD set as normative when design or plan prose differs.

## Intended Follow-On

This handoff is advisory-default-but-overridable: it is authoritative unless the user explicitly overrides it, and it is not a gate or precondition.

- Route: `work-backlog-generation`
- Next step: Generate the Automation Dispatcher guided-lifecycle delta backlog from this PRD set.
- Why: The PRD set now reconciles the existing runtime and the approved guided-lifecycle design, so phase-sized implementation work can be queued without reopening settled product decisions.
- Coordinate Handoff: Carry `W1 R0` into `docs/work/` for the Automation Dispatcher guided-lifecycle delta. Resolve a new coordinate before generating unrelated Bear or repository work.

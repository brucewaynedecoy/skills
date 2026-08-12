---
title: "04 Glossary"
kind: "prd"
status: "active"
---

# 04 Glossary

## Purpose

Define the canonical terms used across the repository and skill PRDs so that user-facing language, agent instructions, CLI fields, tests, and implementation use the same concepts.

## Terms

| Term | Definition |
| --- | --- |
| Agent skill | An installable instruction package rooted at `SKILL.md` that routes an agent through a specialized capability and its safety contract. |
| Approval gate | A boundary at which the agent must receive authorization for an exact consequential scope; it is not a list of internal steps the user must perform. |
| Authority reference | A durable identifier or path that a workflow may load as operational input; unrelated conversation and memory are not authority. |
| Bear Markdown | Bear's supported Markdown dialect and structural conventions for note content, headings, tags, tasks, links, and attachments. |
| Catch-up policy | A collection rule that determines whether missed eligible occurrences are ignored, reduced to the latest, bounded, or all considered within the lookback. |
| Collection | One Automation Dispatcher configuration containing a schedule, timezone, task route, heartbeat, database, and one or more member workflows. |
| Cutover | The separately approved live transition from legacy automations to a collection heartbeat at an explicit occurrence boundary. |
| Discovery snapshot | A versioned, canonical, read-only record of observed in-scope host state, confidence, and bounded references used to create a lifecycle plan. |
| Dispatcher | The durable identity and runtime projection for one collection. Dispatcher identity is a slug, not a cadence label or task title. |
| Due occurrence | A scheduled collection instant eligible under the effective schedule, lateness, catch-up, activation, and existing-run rules. |
| External effect | A procedure outcome that changes state outside the dispatcher and therefore requires idempotency, reconciliation, or an `effect_unknown` boundary. |
| Heartbeat | The single Codex automation attached to a collection task that periodically wakes the dispatcher; it may run more frequently than the collection schedule. |
| Host action | Work that the CLI cannot execute directly and returns to the agent for execution through supported host tools. |
| Host adapter | The agent-side integration that inspects or changes Codex tasks and automations, posts receipts, and returns observed results to the CLI. |
| Lifecycle plan | A versioned, hashed, reviewable specification of desired collections, workflow mappings, state paths, live mutations, rollback boundaries, unresolved decisions, and per-stage progress. |
| Occurrence key | A stable idempotency identifier for one workflow at one scheduled collection instant. |
| Portable collection manifest | A source-controlled, non-secret record of collection identity, schedule, route expectations, definition locations, required versions, and the external database locator. |
| Receipt | A bounded, persisted message describing a material dispatcher event or run result and its delivery state. |
| Receipt fence | The durable `pending` to `posting` transition that must occur before the exact persisted receipt payload is exposed for host delivery. |
| Registry | The external SQLite database that is authoritative for Automation Dispatcher configuration, revisions, runs, events, and receipts. |
| Route assurance | The deterministic comparison of configured and observed task, working-directory, harness, host, and automation identity at required assurance levels. |
| Shadow validation | Built-in verification of initialized collection state and proposed cutover boundaries without executing live workflow effects. |
| Skill source | The source-controlled directory in this repository; it is distinct from an installed skill copy and cannot hold mutable runtime state. |
| Workflow | A versioned member of one collection that defines procedure, authority, retry, lease, reporting, sensitivity, and retention but inherits the collection schedule. |
| Workflow definition | A source-controlled schema-version-2 document that binds a workflow to its dispatcher and canonical execution contract. |

## Source Anchors

- [Automation Dispatcher workflow definition](../../automation-dispatcher/references/workflow-definition.md)
- [Automation Dispatcher registry contract](../../automation-dispatcher/references/registry-contract.md)
- [Automation Dispatcher guided-lifecycle design](../designs/2026-08-11-automation-dispatcher-guided-lifecycle-orchestration.md)
- [Bear note format and sections](../../bear/references/note-format-and-sections.md)

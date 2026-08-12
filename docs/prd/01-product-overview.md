---
title: "01 Product Overview"
kind: "prd"
status: "active"
---

# 01 Product Overview

## Purpose

The skills repository provides source-controlled, installable agent skills that turn broad user requests into safe, repeatable tool workflows. Each skill combines concise routing instructions with the references, scripts, package metadata, and tests needed for its own capability. The repository currently contains Automation Dispatcher and Bear.

The product goal is not to make users memorize command sequences. A skill should let a user state the outcome they want, let the agent discover facts that can be verified, ask only for genuine decisions, apply deterministic tooling where state must be durable, and report evidence at the right approval boundaries.

## Users

- People who want Codex to perform specialized work through natural-language requests without teaching the agent the operating procedure each time.
- Operators who need explicit paths, identities, approvals, hashes, receipts, or read-back evidence for consequential actions.
- Skill maintainers who need a durable contract for routing, safety, installation, compatibility, and validation.
- Agents that need bounded instructions and authoritative references before using external applications or persistent runtime state.

## Key Capabilities

### Skills repository

- Maintain each skill as an independently discoverable package rooted at its own `SKILL.md`.
- Keep skill instructions concise while routing detailed contracts to local references.
- Preserve user authority by separating read-only discovery, repository changes, external state initialization, and live mutations.
- Validate skill packaging, links, documentation, and applicable runtime behavior before distribution.

### Automation Dispatcher

- Operate any number of task-bound workflow collections, each with one collection schedule, timezone, route, external SQLite registry, and heartbeat automation.
- Register multiple versioned workflows in a collection without putting schedules inside workflow definitions.
- Evaluate due occurrences, claim work idempotently, execute scripts or return host actions, persist terminal outcomes, fence receipt delivery, audit mutations, recover safely, and back up or export state.
- Guide a user through discovering existing scheduled tasks, proposing compatible collections, initializing non-live state, shadow validating, cutting over one collection at a time, and resuming interrupted work.
- Add, revise, enable, disable, or move future workflows through the same guided experience without requiring the user to reconstruct the setup procedure.

### Bear

- Discover and use the official `bearcli` command shipped with Bear 2.8 or later on macOS.
- Search, inspect, read, create, edit, append, overwrite, organize, pin, archive, restore, trash, and work with attachments or exports through the narrowest suitable command.
- Resolve exact note targets, preserve attachment and concurrency safeguards, interpret exit codes, and verify silent writes through read-back.
- Use visible Bear app interaction only when requested or operationally required.

## System Boundaries

- Skills are installed into a supported agent skill directory, but their mutable runtime state belongs elsewhere. Installation does not initialize a live dispatcher, alter Bear, or authorize any external mutation.
- Automation Dispatcher registry state is authoritative for collection configuration, workflow membership, revisions, runs, events, and receipts. Task conversation is a reporting and approval surface, not workflow configuration.
- A collection's schedule applies to every enabled member workflow. Workflows with different schedules require different collections even when they report to the same task.
- Automation Dispatcher may prepare and record Codex task or automation changes, but only a supported host operation may apply those changes and only after the exact live scope is approved.
- Bear operates the local Bear application through the official CLI. It does not install Bear automatically, use Bear Claw, or invent unsupported batch operations.
- The repository is a product container, not a shared runtime. Automation Dispatcher and Bear do not share databases, state, authority, or release behavior merely because they are stored together.

## Current Limitations

- Automation Dispatcher's low-level runtime and operator CLI exist, but the guided discovery, planning, initialization, shadow-validation, cutover, and resume experience defined in this PRD set is not yet implemented.
- Exact CLI command names and schema versions for Automation Dispatcher lifecycle orchestration remain open as long as the required capability and compatibility contracts are met.
- Host capabilities for inspecting and mutating Codex tasks and automations must be verified against the supported runtime before lifecycle cutover implementation can be accepted.
- Bear requires macOS, Bear 2.8 or later, and an available official `bearcli`; some version-sensitive operations require live help inspection.
- Each skill remains responsible for its own installation, upgrade, and platform prerequisites. The repository does not currently provide one shared installer or cross-skill runtime.

## Source Anchors

- [Repository README](../../README.md)
- [Automation Dispatcher skill](../../automation-dispatcher/SKILL.md)
- [Automation Dispatcher README](../../automation-dispatcher/README.md)
- [Automation Dispatcher guided-lifecycle design](../designs/2026-08-11-automation-dispatcher-guided-lifecycle-orchestration.md)
- [Bear skill](../../bear/SKILL.md)

# Automation Dispatcher Guided Lifecycle Contract v1

This is the repository foundation contract for guided migration and operation of Automation Dispatcher collections. It defines planning and host boundaries only. It does not authorize a live registry write, Codex task or automation mutation, receipt post, Bear mutation, publication, or deployment.

Machine-readable authority lives in `automation_dispatcher.contracts.v1` and the enforcement helpers in `automation_dispatcher.lifecycle_contracts`.

## Lifecycle stages

The stages are sequential and resumable:

1. `discover` records current source, registry, task, automation, and capability evidence without mutation.
2. `propose` creates a reviewable lifecycle plan and exclusions.
3. `initialize` performs only approved local initialization and preserves rollback state.
4. `shadow_validate` proves schedule, route, receipt, backup, and semantic equivalence without duplicate live execution.
5. `cut_over` applies approved host changes at the named safe occurrence boundary and reads them back.
6. `operate_evolve` verifies health, handles receipts, and starts a fresh discovery cycle for later change.

Legal forward transitions are adjacent. `propose -> discover`, `initialize -> propose`, and `shadow_validate -> initialize` are allowed review/rollback moves; `operate_evolve -> discover` begins a new cycle. Every other skip fails closed.

## Command namespace and results

The reserved additive namespace is:

```text
automation-dispatcher lifecycle plan
automation-dispatcher lifecycle explain
automation-dispatcher lifecycle apply
automation-dispatcher lifecycle status
automation-dispatcher lifecycle verify
automation-dispatcher lifecycle record-cutover
automation-dispatcher lifecycle heartbeat-template
```

Phase 1 freezes this grammar and its JSON contracts; it does not expose the namespace through the current parser. Existing low-level commands remain unchanged.

Every lifecycle command request uses the `lifecycle_command` schema. Every machine-readable result uses `command_result` and carries schema version, command, status, collection/plan identity, resolved database path, source revision, event evidence, warnings, next action, and structured error. Unknown fields and unknown schema versions fail closed.

## Artifact catalog

| Artifact | Purpose | Storage owner |
| --- | --- | --- |
| `discovery_snapshot` | Immutable observed source and host inventory, including unsupported capabilities. | Caller-ephemeral until an explicit lifecycle directory is selected. |
| `lifecycle_plan` | Exact collections, mappings, exclusions, paths, operations, boundaries, rollback, and stage state. | Explicit external lifecycle or multi-collection coordination directory. |
| `collection_manifest` | Portable source-controlled collection definition and database locator. | Explicit source-controlled collection directory. |
| `progress_record` | Durable resumable operation journal. | External lifecycle state. |
| `readiness_report` | Shadow-validation checks, blockers, occurrence boundary, and verdict. | External lifecycle state; optional sanitized export. |
| `semantic_drift_report` | Expected-versus-observed source change evidence. | External lifecycle state; optional sanitized export. |
| `host_capability_snapshot` | Callable adapter surface observed in one environment. | External lifecycle state. |
| `host_mutation_request` | One exact host operation bound to a plan and approval. | External lifecycle state. |
| `host_mutation_result` | Before/after readback and reconciliation evidence for that request. | External lifecycle state. |
| `approval_envelope` | Exact scope and validity fence for host mutation. | External lifecycle state. |
| `lifecycle_command` | Versioned command input. | Ephemeral caller. |
| `command_result` | Versioned command output. | Ephemeral caller or external progress evidence. |

Each entry has a JSON Schema reference in `contracts/v1/catalog.json`. Canonical bytes are UTF-8 JSON with sorted keys, compact separators, Unicode preserved, no trailing newline, and non-finite numbers rejected. `content_hash` is lowercase SHA-256 over those bytes after removing only the top-level `content_hash` field.

Only schema version 1 is accepted. Schemas reject unknown fields at defined object boundaries. Persistent artifacts must not contain credentials, passwords, prompts, raw prompts, secrets, signed URLs, tokens, transcripts, or equivalent raw sensitive material. Sensitive-key matching normalizes snake case, punctuation, and camel case, so names such as `api_token`, `accessToken`, and `prompt_text` are also forbidden. Only explicit stable-reference suffixes such as `_hash`, `_id`, and `_identifier` exempt a sensitive stem. Store stable identifiers, hashes, bounded summaries, and explicit evidence references instead.

Optimistic concurrency is explicit: plans bind the discovery snapshot hash; operations bind plan ID/hash, collection identity, target revision/state hash, and approval ID; results bind the request hash. A mismatch is stale or conflicting state, never an invitation to guess.

## Manifest discovery and multi-collection identity

Manifest resolution uses the first non-empty tier:

1. exact paths supplied by the caller;
2. exact paths bound into verified heartbeat configuration;
3. exact paths bound into dispatcher registry state.

Multiple distinct matches inside one tier are ambiguous and fail closed. Relative paths require an explicit repository root. The current working directory, task title, chat memory, and implicit home-directory locations are never manifest authority.

A manifest binds one `dispatcher_id`, schedule, timezone, route, heartbeat requirement, workflow-definition locators, required versions, and a database locator. Because the manifest is source controlled, its database locator is always `task_working_directory_relative`; absolute, home-relative, drive-qualified, and parent-traversing paths are invalid. An absolute runtime path may appear only in a separate explicitly sanitized external-state artifact, never in the portable manifest. A multi-collection lifecycle plan retains each collection ID independently and records mappings, exclusions, paths, and per-collection occurrence boundaries; collections are not merged merely because schedules or destinations match.

## Path and cleanup policy

Source-controlled inputs live only under an explicit repository root. Mutable databases, plans, approvals, progress, capability snapshots, and host results live in an explicit external state root. Sanitized reports may be exported only when the schema and caller label them as sanitized.

Paths fail closed when they are relative without an explicit root, resolve to `/` or the user home directory, enter a configured source or installed root, traverse any existing symlink, or place source-controlled artifacts beneath `.automation-dispatcher`. External state validation requires explicit forbidden source/install roots. The state owner must use owner-only permissions where the host supports them and owns retention and cleanup; the skill never silently cleans source files or an unowned directory.

## Host adapter

The v1 adapter is deliberately narrow. A host implementation may expose these operations:

- `tasks.list` and `tasks.read`;
- `automations.list` and `automations.read`;
- `tasks.ensure_stable`;
- `automations.create_or_update_heartbeat`;
- `automations.disable_legacy`;
- `messages.post_receipt` and `messages.acknowledge_receipt`;
- `host.read_back`.

The CLI remains the only registry, schedule, occurrence, run, audit, backup, and receipt state machine. The adapter must not become a second scheduler.

A capability snapshot records whether each operation is callable, its concrete tool surface, and why it is or is not supported. Missing operations, a false support flag, or a missing callable surface block the dependent stage. Official product behavior and environment-callable schemas are separate evidence sets.

OpenAI's current Scheduled Tasks documentation says tasks can run in the background, local desktop tasks require the app to remain running, web tasks cannot access local folders, and task management is performed in the web or desktop UI rather than the CLI or IDE extension: <https://learn.chatgpt.com/docs/automations>. In the target Phase 1 execution environment, no callable Codex task/automation list, read, or mutation schemas were exposed. Consequently, discovery can record the absence, but live host-adapter acceptance and all host mutation remain blocked until a target runtime supplies and verifies those schemas.

## Approval and mutation

An approval envelope binds:

- approval, plan, and collection identities;
- the exact canonical plan hash;
- the expected host state hash and target revisions carried by each request;
- an allowlist of exact request hashes;
- the safe cutover occurrence boundary;
- the approving actor;
- approval and expiry timestamps;
- bounded reconciliation evidence that must be satisfied before retrying an uncertain effect.

Before any mutation, validate the plan and request schemas and hashes, re-read the host, compare expected state and revision, confirm the exact request hash is approved, and confirm the approval is active. A `create` request must carry `expected_revision: null` and may proceed only while the observed revision is also null. Every other action requires a non-null approved revision that exactly matches the fresh observed revision. After the call, persist observed before/after state and evidence, then read back again. Success without observed after-state is incomplete. An unknown effect requires reconciliation before retry.

Approval loss, expiry, plan or source drift, unsupported tools, partial mutation, host/API schema drift, stale reads, a missing acknowledgment, or uncertain effect all stop the stage. Lost receipt acknowledgment is reconciled by reading the destination and matching durable receipt identity/content hash; the procedure is never rerun to recover delivery.

## Decision closure

- Q-001 is closed by the grouped namespace and the version-1 command/artifact schemas.
- Q-002 is closed by explicit-path, heartbeat-bound, then registry-bound precedence, with explicit multi-collection coordination and no home-directory guessing.
- Q-003's contract is defined, but target-host acceptance remains explicitly blocked because this environment exposes no callable Codex task/automation schemas. The blocker is environmental, not permission to infer or simulate host state.

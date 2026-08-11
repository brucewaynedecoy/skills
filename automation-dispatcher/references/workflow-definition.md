# Workflow definition

Read this reference before creating, registering, or revising a workflow definition. Definitions are portable source-controlled inputs; registration records their canonical form, revision, and SHA-256 hash in one collection dispatcher's database.

A workflow definition declares membership and execution authority. It never owns the collection's schedule, timezone, maximum lateness, or catch-up policy.

## Contents

- [Collection membership](#collection-membership)
- [Canonical fields](#canonical-fields)
- [Minimal schema-version-2 example](#minimal-schema-version-2-example)
- [Schedule inheritance](#schedule-inheritance)
- [Authority scope](#authority-scope)
- [Procedure kinds and effects](#procedure-kinds-and-effects)
- [Registration and revision sequence](#registration-and-revision-sequence)
- [Required rejection cases](#required-rejection-cases)

## Collection membership

Set `dispatcher_id` to the arbitrary stable slug of the collection whose shared schedule is correct for the workflow. The task title is descriptive only and must not determine the dispatcher ID.

Every enabled member is paired with every due collection occurrence and receives the same normalized `scheduled_for` instant. A workflow that needs a different recurrence belongs in another collection, even if its receipts are reviewed in the same place.

## Canonical fields

Definitions are UTF-8 JSON objects. Use stable lowercase workflow and dispatcher IDs containing only letters, digits, and hyphens. Schema version 2 uses these keys:

- `schema_version`: `2`.
- `workflow_id`: stable workflow slug.
- `name` and `description`: human-readable identity and purpose.
- `dispatcher_id`: arbitrary stable collection slug.
- `enabled`: explicit boolean.
- `retry`: positive `max_attempts` plus non-negative `backoff_seconds`.
- `claim_lease_seconds`: positive integer.
- `procedure`: canonical kind `script|skill|documented`, stable `reference`, and `external_effect` contract.
- `authority_refs`: non-empty exact sources this workflow may treat as authority.
- `reporting`: non-empty `task_id` plus optional `receipt_fields`, normally matching the collection route.
- `receipt`: a non-empty `template`, `required_fields`, or both.
- `data_sensitivity`: classification.
- `evidence_retention`: non-empty `policy` plus optional non-negative `days`.
- `revision`: monotonically increasing workflow-definition revision.
- `content_hash`: optional source assertion containing the SHA-256 of canonical compact JSON with sorted keys and without this field itself. If supplied, it must match. The CLI always computes and records the canonical hash.

Schema version 2 rejects `timezone`, `due_rule`, `schedule`, `max_lateness_seconds`, and `catch_up` at the workflow level. Those values are durable collection configuration.

The implementation's validator and canonical dry-run output are authoritative. Do not add operational meaning through task conversation.

## Minimal schema-version-2 example

Replace angle-bracket values and use the CLI's dry-run output to compute or verify the canonical content hash before registration.

```json
{
  "schema_version": 2,
  "workflow_id": "inbox-triage",
  "name": "Inbox triage",
  "description": "Run the approved inbox-triage procedure.",
  "dispatcher_id": "morning-ops",
  "enabled": true,
  "retry": {
    "max_attempts": 2,
    "backoff_seconds": 300
  },
  "claim_lease_seconds": 900,
  "procedure": {
    "kind": "script",
    "reference": "procedures/inbox-triage.py",
    "external_effect": {
      "mode": "idempotency_key",
      "idempotency_key": "occurrence"
    }
  },
  "authority_refs": [
    "authorities/inbox-triage.md"
  ],
  "reporting": {
    "task_id": "<verified-collection-task-id>",
    "receipt_fields": [
      "run_id",
      "status"
    ]
  },
  "receipt": {
    "required_fields": [
      "run_id",
      "status"
    ]
  },
  "data_sensitivity": "internal",
  "evidence_retention": {
    "policy": "references-only",
    "days": 30
  },
  "revision": 1
}
```

## Schedule inheritance

The collection dispatcher owns one versioned schedule, IANA timezone, maximum lateness, catch-up policy, and verified heartbeat-coverage contract. Its canonical schedule uses version-2 five-field local-time cron JSON, for example:

```json
{"version":2,"kind":"cron","expression":"0 6 * * *"}
```

Daily and weekly are input presets only and normalize to the same general grammar. The collection schedule supports hourly or stepped, daily, weekly, and monthly patterns without turning cadence into identity. Rules with unsupported extensions, invalid ranges, or simultaneous day-of-month and day-of-week constraints fail closed.

Use the deterministic daylight-saving policy:

- Advance a nonexistent spring-forward wall time to the first valid local instant and record the adjustment.
- Select the first occurrence of an ambiguous fall-back wall time and create exactly one occurrence.

Store each resulting `scheduled_for` in UTC. Derive the workflow occurrence key from dispatcher ID, workflow ID, and normalized UTC occurrence, not from either revision. A collection or workflow revision cannot create a second run for the same workflow and instant.

The host heartbeat is polling infrastructure, not workflow configuration. It may match the collection schedule or run more frequently for bounded catch-up, but its verified invocation schedule must cover every collection occurrence within maximum lateness. A live heartbeat cadence change remains a separate automation mutation.

## Authority scope

List exact, stable authority references. The executing agent may load only the selected definition and those references as operational authority. Validate that every required reference exists and resolves within an approved location. A task correction becomes durable only through a source-controlled definition revision and explicit CLI `revise` operation.

## Procedure kinds and effects

A procedure may be a bundled deterministic script, an installed skill with a narrow prompt contract, or a documented agent procedure. Prefer deterministic scripts for fragile operations.

A relative script `procedure.reference` resolves from the registered definition file's parent directory, not the heartbeat working directory. The resolved regular file must remain inside at least one explicit `--approved-root`; Python files run through the installed interpreter, while other scripts must be executable. The runner never invokes a shell.

Classify external effects with the canonical modes:

- `none`: no external mutation.
- `idempotency_key`: accepts `idempotency_key: occurrence`.
- `reconciliation`: includes a stable `reconciliation_reference` that can return completed, not completed, or ambiguous.

Reject a definition that may create an external effect without an idempotency key or deterministic reconciliation path. An ambiguous effect becomes `effect_unknown`, is not retried automatically, and requires owner review.

## Registration and revision sequence

1. Select the collection whose shared schedule and task route are correct for the workflow.
2. Create or update the source-controlled schema-version-2 definition without schedule fields.
3. Validate stable IDs, collection membership, authorities, procedure, retry/lease policy, effect contract, reporting route, sensitivity, and retention.
4. Review the CLI-produced canonical form, inherited schedule and next occurrences, and SHA-256 hash in dry-run mode.
5. Confirm the verified heartbeat covers the collection schedule within maximum lateness. Stop for an owner decision if it does not.
6. Commit the portable definition under the repository's normal process.
7. Register or revise that committed definition and hash in the explicitly authorized collection database.
8. Create a verified backup after the material configuration change and persist its receipt.
9. Change a live heartbeat only under a separate explicit automation authorization.

Revisions preserve prior definitions in append-only history. Disabling prevents future claims while retaining definitions, runs, events, and receipts. Normal removal means disable and archive, not physical deletion.

## Required rejection cases

Reject malformed workflow or dispatcher IDs, unknown collections, workflow-level schedule/timezone/lateness/catch-up fields, missing authorities or procedures, paths outside approved roots, unexpected definition hashes, routes outside the collection's allowed task, unsafe effects, unbounded recovery or retry, and evidence or receipt policies that could expose secrets or sensitive payloads.

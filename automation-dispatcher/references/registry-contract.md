# Registry contract

Use this reference when inspecting or explaining collection configuration, schedule revisions, route assurance, workflow occurrences, claims, audit events, or receipts. Use the CLI rather than mutation SQL.

## Authority and isolation

Each arbitrarily named dispatcher owns one task-bound workflow collection and one external SQLite database. The database is operational authority. The configured Codex task is the human review, receipt, clarification, and approval surface and must not silently alter configuration. Task titles are descriptive only. Daily and weekly are schedule presets and examples, not dispatcher identities.

Use this precedence order:

1. Runtime safety constraints and explicit owner instructions in the current invocation.
2. The validated installed skill and packaged CLI version.
3. Database schema, current projections, and immutable dispatcher/workflow revisions and events.
4. The registered workflow definition at its recorded SHA-256 hash.
5. Authority references named by that workflow definition.
6. Task conversation as non-authoritative reporting context.

Mutable state must not be stored in the source checkout, an installed skill directory, or a CLI tool environment. Reject database paths inside any of those locations. Use one database per collection so schedules, authority, failures, and write contention remain isolated.

## Logical schema

`schema_migrations` records ordered migration versions, checksums, and application times. Apply migrations transactionally and reject checksum drift.

`dispatchers` is the current collection projection: arbitrary stable dispatcher ID, human name and description, automation ID, expected task and working directory, optional host/harness fields, IANA timezone, canonical version-2 schedule JSON, maximum lateness, catch-up policy, verified heartbeat schedule, enabled state, package/source identity, and timestamps. Do not retain a daily/weekly cadence enum as operational authority.

`dispatcher_revisions` is append-only. Each row preserves normalized collection schedule and operational configuration, content hash, actor, reason, effective time, and revision number. A schedule change never erases prior configuration.

`dispatcher_routes` preserves route revisions with destination, effective time, actor, reason, revision, and assurance requirements. The current route may also be projected onto `dispatchers`.

The verified heartbeat schedule describes the separately configured host invocation. It may match the collection schedule or run more frequently. Initialization and `schedule-revise` must reject coverage that cannot reach each collection occurrence within `max_lateness_seconds`; missing or unverified heartbeat configuration is not evidence of coverage.

`workflows` is the current member projection: stable workflow ID, dispatcher foreign key, enabled state, definition location/revision/hash, retry/lease settings, procedure and authority metadata, reporting route, sensitivity/retention policy, and timestamps. Workflow rows do not own schedules, timezone, maximum lateness, or catch-up policy.

`workflow_revisions` is append-only. Each row preserves the canonical schema-version-2 definition, hash, actor, reason, and effective time. Normal update or delete must fail.

`runs` contains one logical projection per workflow and collection occurrence. It records workflow and dispatcher revisions, shared `scheduled_for`, stable occurrence and external-effect keys, timestamps, state, claim/lease data, attempt and recovery lineage, reconciliation, configured and observed identities, evidence, outcome, and receipt hash. Enforce uniqueness on `(workflow_id, scheduled_for)`.

`audit_events` is append-only and ordered per dispatcher. Each event contains applicable dispatcher/workflow/run IDs, type, UTC time, actor, observed identity, canonical JSON payload, previous hash, and current hash. The chain detects ordinary inconsistency; it is not cryptographic nonrepudiation against a local administrator.

`receipts` stores durable receipt ID, optional run ID, dispatcher, destination task, posting state, exact concise content, content hash, timestamps, and external message ID when available. Posting retries reuse persisted content and never rerun a workflow.

## Collection schedules and occurrences

The collection schedule is canonical version-2 five-field local-time cron JSON resolved in the registered IANA timezone. Reject unsupported extensions, invalid ranges, and simultaneous day-of-month and day-of-week constraints. Daily and weekly presets normalize to this same representation.

Use one deterministic daylight-saving policy: advance a nonexistent spring-forward wall time to the first valid instant and record the adjustment; select the first fall-back occurrence and create exactly one collection occurrence.

Every enabled workflow in the consistent membership snapshot is paired with the same normalized UTC `scheduled_for`. Derive the occurrence idempotency key from dispatcher ID, workflow ID, and normalized UTC `scheduled_for`, not from dispatcher or workflow revision. A revision cannot create a second run for the same workflow occurrence. An owner-authorized replay must have explicit replay lineage.

## Run states and transactions

Expected run states include `claimed`, `running`, `succeeded`, `failed`, `skipped`, `abandoned`, `effect_unknown`, and `recovered`.

Keep write transactions short:

1. Enable foreign keys and run required schema, integrity, route, and schedule-coverage checks.
2. Calculate due collection occurrences outside a write transaction.
3. Enumerate enabled members from a consistent registry snapshot.
4. In one short write transaction, insert or claim one run per member for the shared collection occurrence, assign leases, and append events.
5. Execute each pinned registered procedure outside the transaction.
6. In another short transaction, persist each terminal or ambiguous state, evidence, receipt, and events.

Use a bounded busy timeout. If another owner already holds a claim, return an already-claimed result instead of waiting indefinitely. Recover an expired lease only through the explicit recovery command with prior owner, lease, reason, attempt, and lineage recorded.

If a crash may have occurred after an external effect, reconcile through the registered idempotency mechanism or deterministic procedure. If the result remains ambiguous, persist `effect_unknown`, prohibit automatic retry, and request an owner decision.

## Identity and route assurance

Keep configured identity separate from observed runtime identity. Configured values may include dispatcher, automation, expected task, working directory, host/harness, reporting task, and minimum assurance. Observed values may include task, invocation, host, harness/version, session/rollout, working directory, and model when exposed.

Never fabricate an observation. Store nullable values with an identity source such as `runtime`, `automation_config`, `declared`, or `unknown`, and an assurance such as `attested`, `verified_config`, `declared`, or `unknown`.

Before claim or execution:

- Fail closed with `route_mismatch` if an observable route field conflicts with configuration.
- Fail closed with `route_unattested` if a required field is absent or below minimum assurance.
- Fail closed if collection schedule or verified heartbeat coverage is invalid.
- Record an unavailable optional identity as unknown without rejecting the run.
- Treat a value merely repeated by the heartbeat prompt as declared, not runtime-attested.

## Integrity and audit checks

An operational integrity check must cover:

- Known migration version and matching migration checksums.
- `PRAGMA integrity_check` success.
- Separate `PRAGMA foreign_key_check` success.
- Valid current collection schedule and dispatcher-revision projection.
- Definition bytes matching each registered hash before execution.
- Audit hash-chain continuity under the documented canonical JSON serialization.
- Append-only protections for dispatcher revisions, workflow revisions, and audit events.

A successful SQLite file integrity result alone is insufficient.

## Receipt contract

Create receipts for workflow completion, actionable failure, recovery, route mismatch/unattested identity, schedule or registration changes, and other material mutations. A workflow receipt identifies the collection, workflow and occurrence, outcome and attempt, run/event IDs and hash prefix, observed route identity and assurance when available, short result, durable evidence references, and attention-needed text when incomplete.

Persist canonical receipt content before posting. Fence delivery as `posting` before exposing the exact payload to the host adapter. After posting, acknowledge the external message ID. If posting may have succeeded but acknowledgment was lost, reconcile the destination before retrying; never resend an ambiguous receipt or rerun the workflow to regenerate it.

Exclude secrets, full transcripts, temporary URLs, private payloads, and large tool output. A no-due heartbeat may be silent.

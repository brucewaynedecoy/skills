# Operator runbook

Use this runbook for installation, collection initialization and schedule revision, routine dispatch, receipt posting, backup, restore verification, recovery, migration, and cutover. Replace every angle-bracket placeholder with a verified exact value before running a command.

## Contents

- [Four separate surfaces](#four-separate-surfaces)
- [Develop and validate from source](#develop-and-validate-from-source)
- [Install the skill](#install-the-skill)
- [Install the live CLI exactly](#install-the-live-cli-exactly)
- [Use uvx only for exact ephemeral work](#use-uvx-only-for-exact-ephemeral-work)
- [Resolve runtime state](#resolve-runtime-state)
- [Initialize a collection](#initialize-a-collection)
- [Apply guided initialization and shadow validation](#apply-guided-initialization-and-shadow-validation)
- [Revise a collection schedule](#revise-a-collection-schedule)
- [Routine preflight and dispatch](#routine-preflight-and-dispatch)
- [Register revise and disable workflows](#register-revise-and-disable-workflows)
- [Post and acknowledge receipts](#post-and-acknowledge-receipts)
- [Back up and verify restore](#back-up-and-verify-restore)
- [Recover an interrupted run](#recover-an-interrupted-run)
- [Migrate and cut over](#migrate-and-cut-over)
- [Roll back without duplication](#roll-back-without-duplication)

## Four separate surfaces

Do not conflate these surfaces:

1. **Skill source/install** supplies `SKILL.md`, references, and Codex metadata. Codex discovers a local skill from a scanned `.agents/skills` location, a user skill location, or an installed plugin.
2. **CLI source/install** supplies the Python package and `automation-dispatcher` console command. Skill discovery does not install the CLI; CLI installation does not install or enable the skill.
3. **Runtime state** is one mutable SQLite database plus backups and exports in the verified collection task's durable working directory. It is not copied into either installation.
4. **Live Codex state** is the configured task and its heartbeat. Changing it is a separate, explicitly authorized cutover operation.

Verify all four independently. Source work does not authorize database initialization. Low-level `init` does not authorize workflow registration; bounded registration may occur only when an accepted lifecycle plan and explicit Phase 4 initialization approval authorize it. No initialization authorizes a live heartbeat change.

## Develop and validate from source

Use the locked project environment:

```bash
uv sync --locked --dev
uv run automation-dispatcher --help
uv run pytest
uv build
```

Run the standard skill validator separately with an exact transient PyYAML dependency:

```bash
uv run --no-project --with 'PyYAML==6.0.2' python \
  /path/to/skill-creator/scripts/quick_validate.py \
  /path/to/automation-dispatcher
```

Inspect the wheel and source distribution to confirm packaged migrations are present and runtime database, journal, WAL, SHM, backup, export, and secret files are absent. Exercise the built command outside the checkout against a temporary database.

## Install the skill

For local authoring, place or symlink the complete skill directory at a Codex-scanned location such as `$HOME/.agents/skills/automation-dispatcher`, then verify `$automation-dispatcher` appears in skill discovery. For shared distribution, package the skill as a plugin through the approved publication workflow.

This step must not install the CLI, create a collection database, register workflows, or alter a task.

## Install the live CLI exactly

Install a released exact version:

```bash
uv tool install 'automation-dispatcher==0.1.0'
automation-dispatcher --version
```

Or install an exact immutable Git revision after substituting the real repository and full commit SHA:

```bash
uv tool install 'automation-dispatcher @ git+https://<host>/<owner>/<repo>.git@<full-commit-sha>'
automation-dispatcher --version
```

Record the installed package version and source revision. A live heartbeat invokes the installed `automation-dispatcher` executable directly. Do not use `uv run`, a mutable checkout path, a branch name, a floating tag, `@latest`, or unpinned `uvx` for live dispatch.

## Use uvx only for exact ephemeral work

An approved audit, dry run, initialization, recovery, or test may use an isolated exact version:

```bash
uvx --isolated 'automation-dispatcher@0.1.0' --version
```

Or an exact immutable source revision:

```bash
uvx --isolated --from 'automation-dispatcher @ git+https://<host>/<owner>/<repo>.git@<full-commit-sha>' automation-dispatcher --version
```

Never use `uvx automation-dispatcher` without an exact version or source. `uvx` environments are ephemeral; they do not relocate or replace the configured external database.

## Resolve runtime state

Use one database per collection:

```text
<verified-task-working-directory>/.automation-dispatcher/<dispatcher-id>.sqlite3
```

The sibling state directory may contain non-secret collection configuration, `backups/`, and `exports/`. If the working directory is under Git, ignore the mutable state directory.

Before `init`, resolve the database path to an absolute canonical path. The CLI rejects a filesystem root, the home directory, a source/package root, an installed environment root, their descendants, and every root configured in `AUTOMATION_DISPATCHER_FORBIDDEN_ROOTS`. Apply the same external-path discipline to backup and export destinations.

All operational commands except `--version` use the global database option. Place `--database` (or `--db`) and `--json` before the subcommand:

```bash
automation-dispatcher --database "<absolute-database-path>" --json <subcommand> <subcommand-options>
```

## Initialize a collection

Choose an arbitrary stable lowercase dispatcher slug. Do not derive it from the task title. Verify the collection name, purpose, exact task ID, existing working directory, IANA timezone, collection schedule, maximum lateness, catch-up policy, and host heartbeat schedule.

The canonical schedule is version-2 five-field local-time cron JSON. For 06:00 every day:

```json
{"version":2,"kind":"cron","expression":"0 6 * * *"}
```

Daily and weekly inputs are presets only and normalize to the same general grammar. Initialize only at an explicitly approved non-live or live database path:

```bash
automation-dispatcher \
  --database "<absolute-database-path>" \
  --json \
  init \
  --dispatcher-id "<collection-slug>" \
  --name "<collection-name>" \
  --description "<collection-purpose>" \
  --schedule "@<absolute-collection-schedule-json>" \
  --timezone "<iana-timezone>" \
  --max-lateness-seconds "<non-negative-integer>" \
  --catch-up "@<absolute-catch-up-policy-json>" \
  --expected-task-id "<verified-task-id>" \
  --expected-working-directory "<verified-existing-working-directory>" \
  --heartbeat-schedule "@<absolute-verified-heartbeat-schedule-json>" \
  --actor "<actor-id>" \
  --reason "<approved-initialization-reason>"
```

Add `--automation-id`, `--expected-harness`, `--expected-host`, `--required-identity`, `--skill-version`, or `--source-revision` only when those values are verified. Repeated initialization is idempotent only when immutable configuration matches.

Initialization changes only the named external database. It does not register workflows, execute work, create or change a task heartbeat, or disable legacy automation.

## Apply guided initialization and shadow validation

Guided initialization is a separate path from low-level `init`. It applies one collection from an accepted, unexpired lifecycle plan at exact approved source and state paths. Use the actor who accepted the plan, a freshly validated discovery snapshot matching the plan, and literal hashes read from those canonical artifacts:

```bash
automation-dispatcher --json lifecycle apply \
  --plan "<absolute-accepted-plan-path>" \
  --actor "<accepting-actor-id>" \
  --reason "<approved-initialization-reason>" \
  --stage initialize \
  --action apply \
  --collection-id "<collection-id>" \
  --expected-plan-hash "<plan-content-hash>" \
  --expected-source-state-hash "<discovery-content-hash>" \
  --current-source-observation "<absolute-current-discovery-path>" \
  --database-path "<absolute-approved-database-path>" \
  --source-directory "<absolute-approved-generated-source-directory>" \
  --manifest-path "<absolute-approved-manifest-path>" \
  --heartbeat-template-path "<absolute-approved-heartbeat-template-path>" \
  --backup-path "<absolute-approved-backup-path>" \
  --progress-output "<absolute-approved-progress-path>" \
  --repository-root "<absolute-repository-root>" \
  --state-root "<absolute-state-root>" \
  --source-root "<absolute-source-root>"
```

Repeat `--installed-root` for every installed skill or CLI root that must remain forbidden. The command fails closed on stale discovery, actor/hash/expiry mismatch, unapproved or symlinked paths, differing generated bytes, partial registry state, missing route/audit evidence, or an unrelated existing backup. A successful replay is a verified no-op. The generated heartbeat is an operator template only; do not install it or change live host state.

Prepare source occurrence evidence as a JSON array whose objects contain exactly `source_id`, UTC `scheduled_for`, local `intended_local`, local `effective_local`, `timezone`, and nullable canonical `adjustment`. Then evaluate the same plan without execution:

```bash
automation-dispatcher --json lifecycle apply \
  --plan "<absolute-accepted-plan-path>" \
  --actor "<accepting-actor-id>" \
  --reason "<shadow-validation-reason>" \
  --stage shadow_validate \
  --action evaluate \
  --collection-id "<collection-id>" \
  --expected-plan-hash "<plan-content-hash>" \
  --expected-source-state-hash "<discovery-content-hash>" \
  --current-source-observation "<absolute-current-discovery-path>" \
  --database-path "<absolute-approved-database-path>" \
  --source-directory "<absolute-approved-generated-source-directory>" \
  --manifest-path "<absolute-approved-manifest-path>" \
  --heartbeat-template-path "<absolute-approved-heartbeat-template-path>" \
  --backup-path "<absolute-approved-backup-path>" \
  --progress-output "<absolute-approved-progress-path>" \
  --readiness-path "<absolute-approved-readiness-path>" \
  --source-occurrences "<absolute-source-occurrences-json>" \
  --window-start "<timezone-aware-inclusive-start>" \
  --window-end "<timezone-aware-exclusive-end>" \
  --repository-root "<absolute-repository-root>" \
  --state-root "<absolute-state-root>" \
  --source-root "<absolute-source-root>"
```

Shadow validation compares exact occurrence identity including DST adjustments and verifies the registry, route, source definitions, heartbeat, audit chain, integrity, restore-tested backup provenance, and audited backup-hash binding. It creates only the explicit readiness artifact and must not change database bytes, claims, runs, receipts, or host state. Q-003 remains a readiness blocker until callable Codex task and automation schemas are proven. Keep existing scheduled tasks and automations authoritative and request cutover separately.

## Revise a collection schedule

Reconcile already materialized occurrences, proposed timezone and schedule, lateness and catch-up policy, and verified heartbeat coverage before mutation. Then append an immutable dispatcher revision:

```bash
automation-dispatcher \
  --database "<absolute-database-path>" \
  --json \
  schedule-revise \
  --dispatcher-id "<collection-slug>" \
  --schedule "@<absolute-collection-schedule-json>" \
  --timezone "<iana-timezone>" \
  --max-lateness-seconds "<non-negative-integer>" \
  --catch-up "@<absolute-catch-up-policy-json>" \
  --heartbeat-schedule "@<absolute-verified-heartbeat-schedule-json>" \
  --actor "<actor-id>" \
  --reason "<schedule-revision-reason>"
```

The command mutates durable configuration and revision history only. It never changes the live host automation implicitly. Obtain separate authorization and verify the live task configuration before updating a heartbeat.

## Routine preflight and dispatch

Use a verified observed-identity JSON object inline or prefix an absolute JSON file path with `@`:

```bash
automation-dispatcher --database "<absolute-database-path>" --json status
automation-dispatcher --database "<absolute-database-path>" --json integrity-check
automation-dispatcher --database "<absolute-database-path>" --json route-check \
  --dispatcher-id "<collection-slug>" \
  --observed "@<absolute-observed-identity-json>" \
  --actor "<heartbeat-owner>"
automation-dispatcher --database "<absolute-database-path>" --json due \
  --dispatcher-id "<collection-slug>"
automation-dispatcher --database "<absolute-database-path>" --json run \
  --dispatcher-id "<collection-slug>" \
  --owner "<heartbeat-owner>" \
  --observed "@<absolute-observed-identity-json>" \
  --approved-root "<absolute-approved-procedure-root>"
```

Prefer machine-readable JSON for the host adapter. Confirm each material result identifies the collection and database plus applicable workflow/run/event IDs, event hash, version/source, status, and pending receipt.

Stop before claim if migration, integrity, collection schedule, heartbeat coverage, definition verification, route, or required identity assurance fails. Record optional absent identities as unknown.

Use `--at`, `--start`, and `--max-occurrences` only for approved deterministic due/run windows. Use `claim` directly only in tests or documented recovery; ordinary heartbeats start with `run`. When `run` returns `action_required` for an agent, skill, or documented procedure, the heartbeat must perform only the returned registered host action, then use `complete` or `fail` to persist its terminal outcome and receipt before posting that receipt.

Relative script references resolve from the registered definition file's directory. Pass each permissible containing directory as `--approved-root`; the resolved script must be a regular file inside one of those roots. Do not broaden approved roots merely to make a definition run.

## Register revise and disable workflows

Select a collection whose shared schedule is correct. Schema-version-2 workflow definitions must not contain `timezone`, `due_rule`, `schedule`, `max_lateness_seconds`, or `catch_up`.

Dry-run a committed definition first:

```bash
automation-dispatcher --database "<absolute-database-path>" --json register \
  --definition "<absolute-definition-json>" \
  --actor "<actor-id>" \
  --reason "<registration-reason>" \
  --dry-run
```

Review canonical membership, inherited schedule and next occurrences, hash, procedure, authorities, effect contract, route, sensitivity, and retention. After approval, repeat without `--dry-run`. Use `revise` with the same options for a higher definition revision. Enable or disable by exact workflow ID:

```bash
automation-dispatcher --database "<absolute-database-path>" --json disable "<workflow-id>" \
  --actor "<actor-id>" \
  --reason "<disable-reason>"
```

Inspect members with `list --dispatcher-id "<collection-slug>"`. Registration, revision, enablement, and disablement mutate only the named external database; they do not alter a live heartbeat.

Revise a route only under its separate authorization gate:

```bash
automation-dispatcher --database "<absolute-database-path>" --json route-revise \
  --dispatcher-id "<collection-slug>" \
  --destination-task-id "<verified-destination-task-id>" \
  --expected-working-directory "<verified-existing-working-directory>" \
  --required-identity "@<absolute-required-identity-json>" \
  --actor "<actor-id>" \
  --reason "<route-revision-reason>"
```

The command appends an immutable route revision, updates the current projection, and creates a pending receipt. It does not change a live task heartbeat or legacy automation.

## Post and acknowledge receipts

The CLI persists canonical pending content before exposing a posting payload. The host adapter:

1. Calls `receipt-retry "<receipt-id>" --actor "<posting-actor>"` to atomically fence delivery as `posting`, append its audit event, and obtain the exact persisted payload.
2. Posts that exact payload to the registered task through the supported task tool.
3. Acknowledges it with:

```bash
automation-dispatcher --database "<absolute-database-path>" --json receipt-ack "<receipt-id>" \
  --external-message-id "<external-message-id>" \
  --actor "<posting-actor>"
```

If posting failed before any external effect, retry the same persisted receipt. If posting may have succeeded but acknowledgment was lost, reconcile the destination first. Use `--confirm-not-posted` only after independently proving the prior attempt did not post. Never resend an ambiguous receipt merely because acknowledgment is missing, and never rerun a workflow to regenerate it.

## Back up and verify restore

Use the CLI backup operation, which uses SQLite's backup API or another transactionally safe snapshot. Never raw-copy a live database.

After migration or material configuration change:

1. Create a backup outside the live database filename:

   ```bash
   automation-dispatcher --database "<absolute-database-path>" --json backup \
     --destination "<absolute-backup-path>"
   ```

2. Record size, SHA-256, schema version, last audit event/hash, and verification result.
3. Run `automation-dispatcher --json restore-verify "<absolute-backup-path>"`. This subcommand verifies the backup at its own path and does not use the global database option.
4. Run both SQLite integrity and foreign-key checks plus audit-chain verification.
5. Never overwrite the live database during a restore test.

Create a sanitized export with `--database "<absolute-database-path>" --json export --destination "<absolute-export-path>"`. Apply pending migrations only under the migration gate with `--database "<absolute-database-path>" --json migrate`, then immediately run integrity checking and create a verified backup.

Retain the live database, verified backups, and exports independently of skill and CLI upgrades.

## Recover an interrupted run

Resolve the exact dispatcher, workflow, run, occurrence, prior owner, lease, and latest audit event before recovery.

- If execution never reached an external effect, use the explicit recovery operation and preserve lineage.
- If an idempotency key proves the effect completed, reconcile and persist completion without repeating it.
- If deterministic reconciliation proves it did not complete, recover under the registered retry policy.
- If the effect remains ambiguous, persist `effect_unknown`, do not retry automatically, and request an owner decision.

After establishing the outcome, use the exact run ID:

```bash
automation-dispatcher --database "<absolute-database-path>" --json recover "<run-id>" \
  --owner "<new-owner>" \
  --reason "<recovery-reason>" \
  --reconciliation-outcome "<completed-or-not_completed>" \
  --reconciliation-evidence "@<absolute-durable-evidence-json>"
```

Every supplied reconciliation outcome requires non-empty durable JSON evidence. Omit invented outcomes: an unresolved effect must remain `effect_unknown` and produce an attention-needed receipt. Never alter `scheduled_for` to manufacture another occurrence.

## Migrate and cut over

Source implementation, database initialization, shadow validation, and live cutover are separate gates.

For a legacy schema-v1 registry, `migrate` promotes workflow timing into the collection only when every member has complete, identical timing; mixed or missing timing fails transactionally. Migration cannot rewrite source definition files. Convert every member definition to schema version 2, remove workflow-owned timezone, schedule/due-rule, lateness, and catch-up fields, then explicitly `revise` or `register` the converted definition before dispatch.

For each collection independently:

1. Reconcile current task, automation, workflow authority, working directory, and genuinely shared schedule.
2. Validate the source skill and built CLI without live state.
3. Initialize external state and routes without executing workflows.
4. Register only committed definitions whose members inherit the collection schedule; create verified backups and exports.
5. Shadow route checks, due calculations, member fan-out, duplicate ticks and claims, schedule revision, lease recovery, receipt retry, and contamination resistance while legacy workflows remain authoritative.
6. Obtain explicit cutover authorization.
7. Change the one approved live heartbeat and overlapping legacy automation in a non-overlapping sequence.
8. Re-read live configuration, observe one bounded collection occurrence, and reconcile every enabled member and receipt to the database.

Different schedules require different collections. Do not force workflows together merely because both are described as daily or weekly. Do not disable a legacy automation merely because code exists or dry-run tests pass.

## Roll back without duplication

1. Pause or disable the affected collection heartbeat under explicit authorization.
2. Record the reason and last completed collection occurrence in the database and task.
3. Reconcile every member's claimed, completed, ambiguous, and receipt-only state.
4. Set legacy automations' next occurrences so completed work cannot repeat, then restore them.
5. Preserve the dispatcher database and backups as audit evidence.
6. Re-run live route, schedule, and heartbeat-coverage verification.

For corruption, restore the latest verified backup into a new file, verify it, and reconcile it with task receipts. Never overwrite the only damaged copy.

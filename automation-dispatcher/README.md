# Automation Dispatcher

Automation Dispatcher groups related recurring Codex work into durable, task-bound workflow collections. One collection can run several workflows together, prevent duplicate claims, survive restarts, and leave a reconciliable history without creating a separate host automation for every job.

Each collection has:

- an arbitrary stable dispatcher ID and descriptive name;
- one exact Codex task route and durable working directory;
- one authoritative schedule, timezone, lateness policy, and catch-up policy;
- one external SQLite registry; and
- any number of enabled workflows that inherit the collection schedule.

Every enabled member receives one idempotent run opportunity for each collection occurrence. If two workflows need different schedules, put them in different collections. Daily and weekly are convenient presets and migration examples only; dispatcher IDs and task titles carry no scheduling semantics.

This is a good fit when scheduled work must be easy to find and review, safe after interruption, protected from the wrong task or working directory, and backed by receipts, audit history, and verified backups.

## How it fits together

Automation Dispatcher has four separate surfaces:

1. **The Codex skill** teaches Codex how to configure and operate collections safely.
2. **The CLI** handles collection schedules, claims, execution, recovery, receipts, and backups.
3. **An external SQLite database** stores collection configuration and run history outside both installations.
4. **A Codex task heartbeat** invokes one collection and posts its persisted material receipts.

The database is operational authority. The configured task is the human review, clarification, and approval surface; its conversation and title do not silently change collection or workflow configuration.

## Requirements

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- One verified Codex task and durable working directory for each collection

## Install it

Skill installation and CLI installation are independent. Neither step creates runtime state or changes a live heartbeat.

### 1. Install the Codex skill

Place or symlink this complete folder into a Codex skill directory. For local authoring:

```bash
mkdir -p ~/.agents/skills
ln -s /absolute/path/to/automation-dispatcher ~/.agents/skills/automation-dispatcher
```

Restart or refresh Codex, then confirm that `$automation-dispatcher` appears in skill discovery.

### 2. Install the CLI exactly

Install an exact released version for live use:

```bash
uv tool install 'automation-dispatcher==0.1.0'
automation-dispatcher --version
```

Or build and install the exact wheel from this checkout:

```bash
uv build
uv tool install --from ./dist/automation_dispatcher-0.1.0-py3-none-any.whl automation-dispatcher
automation-dispatcher --version
```

An approved ephemeral audit, dry run, initialization, or recovery may use an exact version or immutable source revision with `uvx`. Never use unpinned `uvx automation-dispatcher`, and never use `uvx` for a live heartbeat.

### Upgrade an existing CLI installation

If you installed the CLI before the collection-schedule update, refresh it before using the new commands or workflow format.

First, see what `uv` has installed:

```bash
uv tool list
automation-dispatcher --version
```

For a newer published release, the normal upgrade is:

```bash
uv tool upgrade automation-dispatcher
automation-dispatcher --version
```

The corrected checkout currently has the same `0.1.0` version number as the earlier build, so a normal upgrade may report that nothing changed. Rebuild and force-install this exact wheel instead:

```bash
cd /path/to/automation-dispatcher
uv build
uv tool install --force --from ./dist/automation_dispatcher-0.1.0-py3-none-any.whl automation-dispatcher
automation-dispatcher --version
automation-dispatcher --help
```

This replaces only the CLI's isolated `uv` environment. It does not delete or move the external SQLite database, change a task, or change a live heartbeat. The Codex skill is installed separately; if you copied it instead of linking it to this checkout, refresh that copy too.

## Create a collection

Use one explicit database per collection in the verified task working directory:

```text
<verified-task-working-directory>/.automation-dispatcher/<dispatcher-id>.sqlite3
```

There is no implicit home-directory default. Do not place runtime state inside the source checkout, installed skill, or installed CLI environment.

This example creates a generically named collection whose members run at 06:00 local time. The heartbeat file describes the separately verified host invocation schedule; it may match the collection schedule or run more often, but it must cover every collection occurrence within maximum lateness.

```bash
automation-dispatcher \
  --database "/absolute/path/to/ops-task/.automation-dispatcher/morning-ops.sqlite3" \
  --json \
  init \
  --dispatcher-id "morning-ops" \
  --name "Morning operations" \
  --description "Run approved operational checks together" \
  --schedule '{"version":2,"kind":"cron","expression":"0 6 * * *"}' \
  --timezone "America/Chicago" \
  --max-lateness-seconds 3600 \
  --catch-up '{"policy":"latest","max_lookback_seconds":86400}' \
  --expected-task-id "<verified-codex-task-id>" \
  --expected-working-directory "/absolute/path/to/ops-task" \
  --heartbeat-schedule "@/absolute/path/to/verified-heartbeat.json" \
  --actor "<actor-id>" \
  --reason "Initialize the morning operations collection"
```

The canonical schedule is five-field local-time cron: minute, hour, day of month, month, and day of week. Daily and weekly inputs may be accepted as presets, but they normalize to this general representation. The dispatcher rejects ambiguous rules that constrain both day-of-month and day-of-week.

Initialization changes only the named external database. Activating or changing the live heartbeat is a separate cutover gate.

## Add a workflow

Each source-controlled workflow definition identifies its collection, procedure, authority references, retry and lease policy, external-effect contract, reporting, sensitivity, and retention. It does not own a timezone or schedule. See the [workflow definition guide](references/workflow-definition.md) for schema version 2 and a canonical example.

Dry-run a committed definition first:

```bash
automation-dispatcher \
  --database "/absolute/path/to/ops-task/.automation-dispatcher/morning-ops.sqlite3" \
  --json \
  register \
  --definition "/absolute/path/to/workflow.json" \
  --actor "<actor-id>" \
  --reason "Add the workflow to morning operations" \
  --dry-run
```

Review the normalized definition, inherited collection schedule, content hash, route, and next occurrences. If correct and authorized, repeat without `--dry-run`. Use `revise` for a later definition revision or `disable <workflow-id>` to stop future claims while retaining history.

## Revise the collection schedule

Schedule changes append an immutable dispatcher revision. Reconcile existing occurrences and verify heartbeat coverage before applying one:

```bash
automation-dispatcher \
  --database "/absolute/path/to/ops-task/.automation-dispatcher/morning-ops.sqlite3" \
  --json \
  schedule-revise \
  --dispatcher-id "morning-ops" \
  --schedule '{"version":2,"kind":"cron","expression":"30 6 * * *"}' \
  --timezone "America/Chicago" \
  --max-lateness-seconds 3600 \
  --catch-up '{"policy":"latest","max_lookback_seconds":86400}' \
  --heartbeat-schedule "@/absolute/path/to/verified-heartbeat.json" \
  --actor "<actor-id>" \
  --reason "Move the collection occurrence to 06:30"
```

This command mutates durable collection configuration only. Updating the live host automation remains a separate explicitly authorized action.

## Run due workflows

The heartbeat supplies observed task and working-directory identity as verified JSON. The dispatcher fails closed before claims if the route, integrity, required assurance, definition hash, or schedule coverage is invalid.

```bash
automation-dispatcher \
  --database "/absolute/path/to/ops-task/.automation-dispatcher/morning-ops.sqlite3" \
  --json \
  run \
  --dispatcher-id "morning-ops" \
  --owner "<heartbeat-owner>" \
  --observed "@/absolute/path/to/observed-identity.json" \
  --approved-root "/absolute/path/to/workflow-procedures"
```

If nothing is due, the command exits cleanly. Otherwise it pairs the collection occurrence with every enabled member and claims each workflow occurrence once. It executes script procedures and persists their terminal or ambiguous results plus receipts. For an agent, skill, or documented procedure, it returns `action_required`; the heartbeat must perform the registered host action and finish the terminal-result and receipt loop below.

## Inspect and audit

Global options such as `--database` and `--json` come before the subcommand.

```bash
COLLECTION_DB="/absolute/path/to/ops-task/.automation-dispatcher/morning-ops.sqlite3"

automation-dispatcher --database "$COLLECTION_DB" --json status
automation-dispatcher --database "$COLLECTION_DB" --json list --dispatcher-id "morning-ops"
automation-dispatcher --database "$COLLECTION_DB" --json due --dispatcher-id "morning-ops"
automation-dispatcher --database "$COLLECTION_DB" --json integrity-check
automation-dispatcher --database "$COLLECTION_DB" --json audit --dispatcher-id "morning-ops" --verify
automation-dispatcher --database "$COLLECTION_DB" --json backup \
  --destination "/absolute/path/to/backups/morning-ops.sqlite3"
```

Run `automation-dispatcher --help` or `automation-dispatcher <command> --help` for the full command reference.

## Receipts and recovery

Receipts are persisted before posting. `receipt-retry <receipt-id> --actor <actor>` fences one delivery attempt and returns the exact stored payload. Post that payload through the supported task tool, then record the external message ID with `receipt-ack`. If posting may have succeeded but acknowledgment is missing, reconcile the destination first; do not resend an ambiguous receipt or rerun the workflow.

### Complete heartbeat template for agent, skill, and documented procedures

`run` executes script procedures itself. For an agent, skill, or documented procedure it claims the occurrence, marks the run `running`, and returns a result like this:

```json
{
  "status": "action_required",
  "run_id": "<run-id>",
  "host_action": {
    "kind": "skill",
    "reference": "<registered-procedure-reference>",
    "run_id": "<run-id>",
    "occurrence_key": "<stable-idempotency-key>",
    "authority_refs": ["<registered-authority-reference>"]
  }
}
```

For each such result, the scheduled agent must complete the entire loop in the same heartbeat:

1. Perform only the procedure named by `host_action`, using only its registered authority references. Pass `occurrence_key` to any external-effect operation that supports idempotency.
2. Persist exactly one terminal outcome. On success:

   ```bash
   automation-dispatcher --database "<absolute-database-path>" --json complete "<run-id>" \
     --actor "<heartbeat-owner>" \
     --summary "<bounded-result-summary>" \
     --evidence "<durable-evidence-reference>"
   ```

   On failure:

   ```bash
   automation-dispatcher --database "<absolute-database-path>" --json fail "<run-id>" \
     --actor "<heartbeat-owner>" \
     --error-class "<stable-error-class>" \
     --summary "<bounded-failure-summary>"
   ```

   Add `--effect-unknown` when an external effect may have occurred and reconciliation cannot establish its outcome. Never allow a handled procedure failure to leave the run in `running`.
3. Read `receipt.receipt_id` from the `complete` or `fail` result, then fence delivery and obtain the persisted payload:

   ```bash
   automation-dispatcher --database "<absolute-database-path>" --json receipt-retry "<receipt-id>" \
     --actor "<posting-actor>"
   ```

4. Through the supported task tool, post exactly `posting_payload.message` to exactly `posting_payload.thread_id`. Do not edit, summarize, prefix, suffix, or recreate the message.
5. Re-read or otherwise reconcile the external post. Verify that its destination and message exactly match the persisted `posting_payload`, retain the returned external message ID, and only then acknowledge it:

   ```bash
   automation-dispatcher --database "<absolute-database-path>" --json receipt-ack "<receipt-id>" \
     --external-message-id "<external-message-id>" \
     --actor "<posting-actor>"
   ```

6. Before ending the heartbeat, confirm every `action_required` run reached a terminal state and every material receipt posted in this heartbeat is reconciled and acknowledged. If the post definitely failed, retry the same persisted receipt without rerunning the procedure. If it may have posted, reconcile first; never resend an ambiguous receipt.

Interrupted runs keep their original occurrence and attempt lineage. Recover only after determining whether an external effect completed, did not complete, or remains ambiguous. Persist `effect_unknown` and request an owner decision when reconciliation cannot establish the outcome.

See the [operator runbook](references/operator-runbook.md) for receipt fencing, recovery, route revisions, migrations, backups, and cutover. See the [registry contract](references/registry-contract.md) for collection revisions, occurrence identity, audit, and receipt rules.

## Develop and test

```bash
uv sync --locked --dev
uv run automation-dispatcher --help
uv run pytest
uv build
```

The repository and distributions must remain free of live databases, journals, WAL/SHM files, backups, exports, and secrets.

# Automation Dispatcher Baseline Compatibility

This reference freezes the repository compatibility envelope that existed before the guided-lifecycle foundation. The machine-readable inventory is `tests/fixtures/compatibility/baseline-v0.1.0.json`; the frozen schema-v2 collection is `tests/fixtures/compatibility/collection-v2.sqlite3.gz.b64`.

## Baseline inventory

The baseline is package version `0.1.0`, database schema version `2`, and installed entrypoint `automation-dispatcher = automation_dispatcher.cli:main`. The full pre-change suite collected and passed 111 tests.

The existing command grammar remains:

`audit`, `backup`, `claim`, `complete`, `disable`, `due`, `enable`, `export`, `fail`, `init`, `integrity-check`, `list`, `migrate`, `receipt-ack`, `receipt-retry`, `recover`, `register`, `restore-verify`, `revise`, `route-check`, `route-revise`, `run`, `schedule-revise`, and `status`.

The public Python modules present at the baseline are `audit`, `backup`, `claims`, `cli`, `database`, `definitions`, `receipts`, `registry`, `routing`, `runner`, and `scheduling`, plus the package initializer and packaged migrations.

The migration resources and their SHA-256 checksums are:

| Resource | SHA-256 |
| --- | --- |
| `0001_initial.sql` | `795f41f8ef61f0506b585c4fba0f9f44fcecb6cbd9df182d9191bb1a65d05a7d` |
| `0002_collection_model.sql` | `1c0f898c429338ef3901dc80995fc0b5d722ecaff785983f93b7d7639d8ef6dd` |

The wheel contains the package initializer, the eleven public modules, the migration package initializer, both migration SQL resources, and distribution metadata including the console entrypoint. The source distribution additionally contains `README.md`, `SKILL.md`, agent metadata, `pyproject.toml`, references, and the same source package.

## Runtime invariants

Guided lifecycle work must preserve all of these invariants:

- A collection owns one schedule and route; workflows do not override either.
- Dispatcher and workflow revisions are effective-dated and immutable.
- Occurrences are unique and claims are fenced by owner, lease, definition revision, dispatcher revision, and occurrence identity.
- Ambiguous external effects stop automatic retry until reconciliation proves whether the effect occurred.
- Terminal run state and the corresponding receipt are recorded atomically.
- Audit events remain hash chained and integrity-checkable.
- Backups use SQLite snapshots and are restore-verified before success is reported.
- Mutable runtime databases and lifecycle state remain outside source, installed package, cache, and other prohibited roots.
- Receipt retry never reruns the underlying procedure.

## Compatibility matrix

| Surface | Compatibility promise | Regression evidence |
| --- | --- | --- |
| Schema-v2 workflow definitions | Existing definitions remain accepted with the same content-hash and revision rules. | Existing definition tests and frozen collection dispatch. |
| Existing schema-v2 databases | Open, no-op migrate, status inspection, verified backup, and dispatch remain supported. | `test_frozen_v2_database_opens_migrates_inspects_backs_up_and_dispatches`. |
| Existing low-level commands | Names, required arguments, behavior, and exit-code convention remain unchanged. | Frozen command inventory plus the full CLI suite. |
| JSON results | Existing `database_path`, `cli_version`, `source_revision`, event identity/hash, status, warning/error, and receipt fields remain additive-compatible. | Existing CLI and acceptance-boundary tests. |
| Exit codes | `0` means successful handling, `1` means a fail-closed operational result, and `2` means argument/contract/runtime failure. | Existing CLI tests. |
| Packaged migrations | Existing filenames and bytes are immutable; new resources are additive. | Frozen SHA-256 inventory and packaging tests. |
| Installed entrypoint | The console script continues to invoke `automation_dispatcher.cli:main`. | Distribution validation and installed-wheel smoke test. |

The guided-lifecycle namespace and contract resources are additive. Phase 1 did not change the existing parser. Phase 2 adds the grouped lifecycle parser without changing the existing low-level command grammar, database schema, scheduling engine, receipt protocol, or packaging entrypoint.

## Performance boundary

No accepted W1 R0 authority establishes a numeric performance service-level objective or benchmark gate. Phase 1 therefore preserves the existing non-hanging and bounded-work expectations exercised by the test suite without inventing a numeric threshold. A future numeric gate requires explicit normative authority before it can block acceptance.

## Validation

Run from `automation-dispatcher/`:

```sh
uv run pytest -q
uv run pytest --collect-only -o addopts=''
uv build
uv run python scripts/validate_distribution.py
```

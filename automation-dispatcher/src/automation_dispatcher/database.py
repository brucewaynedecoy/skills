"""SQLite connection, migration, initialization, and integrity primitives."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from importlib import resources
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from typing import Iterator


BUSY_TIMEOUT_MS = 5_000
_MIGRATION_RE = re.compile(r"^(?P<version>[0-9]{4,})_(?P<label>[a-z0-9_]+)\.sql$")


class MigrationError(RuntimeError):
    """Raised when migration history cannot be advanced safely."""


def utc_now() -> str:
    """Return the canonical timestamp representation used by the database."""

    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _canonical_collection_schedule_json(value: object) -> str:
    from .scheduling import normalize_collection_schedule

    parsed = json.loads(value) if isinstance(value, str) else value
    return _canonical_json(normalize_collection_schedule(parsed))


def _canonical_dispatcher_configuration_json(
    dispatcher_id: object,
    name: object,
    description: object,
    timezone_name: object,
    schedule_json: object,
    max_lateness_seconds: object,
    catch_up_policy: object,
    max_lookback_seconds: object,
    heartbeat_schedule_json: object,
    enabled: object,
) -> str:
    # Local import avoids a module cycle: registry imports utc_now from here.
    from .registry import normalize_dispatcher_configuration

    schedule = (
        json.loads(schedule_json) if isinstance(schedule_json, str) else schedule_json
    )
    heartbeat = (
        json.loads(heartbeat_schedule_json)
        if isinstance(heartbeat_schedule_json, str)
        else heartbeat_schedule_json
    )
    configuration = normalize_dispatcher_configuration(
        {
            "dispatcher_id": dispatcher_id,
            "name": name,
            "description": description,
            "timezone": timezone_name,
            "schedule": schedule,
            "max_lateness_seconds": max_lateness_seconds,
            "catch_up": {
                "policy": catch_up_policy,
                "max_lookback_seconds": max_lookback_seconds,
            },
            "heartbeat_schedule": heartbeat,
            "enabled": enabled,
        }
    )
    return _canonical_json(configuration)


def _register_migration_functions(connection: sqlite3.Connection) -> None:
    connection.create_function(
        "sha256_hex",
        1,
        lambda value: sha256(str(value).encode("utf-8")).hexdigest(),
        deterministic=True,
    )
    connection.create_function(
        "canonical_collection_schedule_json",
        1,
        _canonical_collection_schedule_json,
        deterministic=True,
    )
    connection.create_function(
        "canonical_dispatcher_configuration_json",
        10,
        _canonical_dispatcher_configuration_json,
        deterministic=True,
    )


def connect(path: str | Path) -> sqlite3.Connection:
    """Open a configured SQLite connection.

    Connections use a bounded busy timeout and SQLite's rollback journal.  The
    default deferred transaction mode is intentional: helpers such as
    ``append_event`` never commit a caller's transaction.
    """

    database_path = Path(path).expanduser().resolve()
    connection = sqlite3.connect(database_path, timeout=BUSY_TIMEOUT_MS / 1_000)
    connection.row_factory = sqlite3.Row
    _register_migration_functions(connection)
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA foreign_keys = ON")
    journal_mode = connection.execute("PRAGMA journal_mode = DELETE").fetchone()[0]
    if str(journal_mode).lower() != "delete":
        connection.close()
        raise sqlite3.OperationalError(
            f"database did not enter rollback-journal mode: {journal_mode}"
        )
    connection.execute("PRAGMA synchronous = FULL")
    if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        connection.close()
        raise sqlite3.OperationalError("SQLite foreign-key enforcement is unavailable")
    return connection


def _migration_resources() -> list[tuple[int, str, bytes, str]]:
    package = resources.files("automation_dispatcher.migrations")
    migrations: list[tuple[int, str, bytes, str]] = []
    for item in package.iterdir():
        match = _MIGRATION_RE.fullmatch(item.name)
        if not match:
            continue
        content = item.read_bytes()
        migrations.append(
            (int(match.group("version")), item.name, content, sha256(content).hexdigest())
        )
    migrations.sort(key=lambda migration: migration[0])
    versions = [migration[0] for migration in migrations]
    if not migrations:
        raise MigrationError("no packaged migrations found")
    if len(versions) != len(set(versions)):
        raise MigrationError("packaged migrations contain duplicate versions")
    return migrations


def _iter_statements(sql: str) -> Iterator[str]:
    """Split a migration without breaking trigger bodies at inner semicolons."""

    pending = ""
    for line in sql.splitlines(keepends=True):
        pending += line
        if sqlite3.complete_statement(pending):
            statement = pending.strip()
            if statement:
                yield statement
            pending = ""
    if pending.strip():
        raise MigrationError("migration contains an incomplete SQL statement")


def _applied_migrations(connection: sqlite3.Connection) -> dict[int, sqlite3.Row]:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
    ).fetchone()
    if not exists:
        return {}
    return {
        int(row["version"]): row
        for row in connection.execute(
            "SELECT version, name, checksum, applied_at FROM schema_migrations ORDER BY version"
        )
    }


def _validate_collection_upgrade(connection: sqlite3.Connection) -> None:
    """Fail closed unless legacy workflow timing maps to one collection schedule.

    Version 1 stored timing on each workflow.  Version 2 moves it to the
    dispatcher, so an upgrade is safe only when every existing dispatcher has
    at least one workflow and all of its workflows have semantically identical
    timing configuration.  The check runs inside the migration transaction so
    the evidence cannot change between validation and backfill.
    """

    dispatchers = connection.execute(
        "SELECT * FROM dispatchers ORDER BY dispatcher_id"
    ).fetchall()
    for dispatcher in dispatchers:
        dispatcher_id = str(dispatcher["dispatcher_id"])
        workflows = connection.execute(
            "SELECT workflow_id, timezone, schedule_json, max_lateness_seconds, "
            "catch_up_policy, max_lookback_seconds FROM workflows "
            "WHERE dispatcher_id = ? ORDER BY workflow_id",
            (dispatcher_id,),
        ).fetchall()
        if not workflows:
            raise MigrationError(
                "collection upgrade requires legacy timing evidence for dispatcher "
                f"{dispatcher_id!r}; register a workflow or initialize a fresh database"
            )

        normalized: list[tuple[str, str, int, str, int]] = []
        for workflow in workflows:
            try:
                schedule = _canonical_collection_schedule_json(workflow["schedule_json"])
            except Exception as error:
                raise MigrationError(
                    "collection upgrade found invalid legacy schedule JSON for workflow "
                    f"{workflow['workflow_id']!r} in dispatcher {dispatcher_id!r}"
                ) from error
            normalized.append(
                (
                    str(workflow["timezone"]).strip(),
                    schedule,
                    int(workflow["max_lateness_seconds"]),
                    str(workflow["catch_up_policy"]).strip().lower(),
                    int(workflow["max_lookback_seconds"]),
                )
            )

        if any(item != normalized[0] for item in normalized[1:]):
            workflow_ids = [str(workflow["workflow_id"]) for workflow in workflows]
            raise MigrationError(
                "collection upgrade found mixed legacy timing for dispatcher "
                f"{dispatcher_id!r} across workflows {workflow_ids}; split the collection "
                "or reconcile timing explicitly before migration"
            )

        try:
            _canonical_dispatcher_configuration_json(
                dispatcher_id,
                dispatcher_id,
                "",
                normalized[0][0],
                normalized[0][1],
                normalized[0][2],
                normalized[0][3],
                normalized[0][4],
                dispatcher["heartbeat_schedule_json"],
                dispatcher["enabled"],
            )
        except Exception as error:
            raise MigrationError(
                "collection upgrade cannot normalize legacy configuration for dispatcher "
                f"{dispatcher_id!r}: {error}"
            ) from error


def migrate(connection: sqlite3.Connection) -> list[dict[str, object]]:
    """Apply all pending packaged migrations in one forward-only transaction."""

    if connection.in_transaction:
        raise MigrationError("migrate requires a connection with no active transaction")

    _register_migration_functions(connection)

    packaged = _migration_resources()
    packaged_by_version = {migration[0]: migration for migration in packaged}
    applied = _applied_migrations(connection)

    unknown = sorted(set(applied) - set(packaged_by_version))
    if unknown:
        raise MigrationError(f"database contains unknown migration versions: {unknown}")

    for version, row in applied.items():
        _, expected_name, _, expected_checksum = packaged_by_version[version]
        if row["name"] != expected_name:
            raise MigrationError(
                f"migration {version} name mismatch: {row['name']} != {expected_name}"
            )
        if row["checksum"] != expected_checksum:
            raise MigrationError(f"migration {version} checksum mismatch")

    if applied:
        maximum = max(applied)
        missing = [version for version in packaged_by_version if version <= maximum and version not in applied]
        if missing:
            raise MigrationError(f"migration history is not forward-only; missing: {missing}")
    else:
        maximum = 0

    pending = [migration for migration in packaged if migration[0] > maximum]
    if not pending:
        return []

    results: list[dict[str, object]] = []
    try:
        connection.execute("BEGIN IMMEDIATE")
        for version, name, content, checksum in pending:
            if version == 2:
                _validate_collection_upgrade(connection)
            for statement in _iter_statements(content.decode("utf-8")):
                connection.execute(statement)
            applied_at = utc_now()
            connection.execute(
                "INSERT INTO schema_migrations(version, name, checksum, applied_at) "
                "VALUES (?, ?, ?, ?)",
                (version, name, checksum, applied_at),
            )
            results.append(
                {
                    "version": version,
                    "name": name,
                    "checksum": checksum,
                    "applied_at": applied_at,
                }
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return results


def schema_version(connection: sqlite3.Connection) -> int:
    """Return the highest applied migration version, or zero for an empty DB."""

    applied = _applied_migrations(connection)
    return max(applied, default=0)


def assert_runtime_path_is_external(path: str | Path) -> Path:
    """Resolve and reject runtime state inside code/install or at broad roots."""

    resolved = Path(path).expanduser().resolve()
    package_root = Path(__file__).resolve().parents[2]
    install_root = Path(sys.prefix).resolve()
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser().resolve()
    known_skill_roots = {
        codex_home / "skills" / "automation-dispatcher",
        Path.home().resolve() / ".agents" / "skills" / "automation-dispatcher",
    }
    configured_roots = {
        Path(value).expanduser().resolve()
        for value in os.environ.get("AUTOMATION_DISPATCHER_FORBIDDEN_ROOTS", "").split(os.pathsep)
        if value
    }
    forbidden_roots = {package_root, install_root, *known_skill_roots, *configured_roots}
    if resolved in {Path(resolved.anchor), Path.home().resolve(), *forbidden_roots}:
        raise ValueError("runtime path cannot be a filesystem, home, or package root")
    if any(root in resolved.parents for root in forbidden_roots):
        raise ValueError("runtime state must be stored outside the installed/source skill")
    return resolved


def initialize_database(path: str | Path) -> dict[str, object]:
    """Create a database, apply migrations, and verify its physical integrity."""

    database_path = Path(path).expanduser().resolve()
    database_path = assert_runtime_path_is_external(database_path)
    if database_path.exists() and not database_path.is_file():
        raise ValueError(f"database path is not a file: {database_path}")
    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = connect(database_path)
    try:
        applied = migrate(connection)
        version = schema_version(connection)
    finally:
        connection.close()

    verification = integrity_check(database_path)
    if not verification["ok"]:
        raise sqlite3.DatabaseError(f"initialized database failed verification: {verification}")
    return {
        "database_path": str(database_path),
        "applied_migrations": applied,
        "schema_version": version,
        "journal_mode": "delete",
        "foreign_keys": True,
        "busy_timeout_ms": BUSY_TIMEOUT_MS,
        "verification": verification,
    }


def integrity_check(path: str | Path) -> dict[str, object]:
    """Run SQLite integrity and foreign-key checks without creating a database."""

    database_path = Path(path).expanduser().resolve()
    if not database_path.is_file():
        return {
            "database_path": str(database_path),
            "ok": False,
            "integrity_ok": False,
            "foreign_keys_ok": False,
            "integrity_errors": ["database file does not exist"],
            "foreign_key_errors": [],
            "schema_version": 0,
        }

    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(
            f"{database_path.as_uri()}?mode=ro",
            uri=True,
            timeout=BUSY_TIMEOUT_MS / 1_000,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA foreign_keys = ON")
        integrity_rows = [row[0] for row in connection.execute("PRAGMA integrity_check")]
        integrity_errors = [] if integrity_rows == ["ok"] else integrity_rows
        foreign_key_errors = [
            {
                "table": row[0],
                "rowid": row[1],
                "parent": row[2],
                "foreign_key_index": row[3],
            }
            for row in connection.execute("PRAGMA foreign_key_check")
        ]
        version = schema_version(connection)
        integrity_ok = not integrity_errors
        foreign_keys_ok = not foreign_key_errors
        return {
            "database_path": str(database_path),
            "ok": integrity_ok and foreign_keys_ok,
            "integrity_ok": integrity_ok,
            "foreign_keys_ok": foreign_keys_ok,
            "integrity_errors": integrity_errors,
            "foreign_key_errors": foreign_key_errors,
            "schema_version": version,
        }
    except sqlite3.Error as error:
        return {
            "database_path": str(database_path),
            "ok": False,
            "integrity_ok": False,
            "foreign_keys_ok": False,
            "integrity_errors": [str(error)],
            "foreign_key_errors": [],
            "schema_version": 0,
        }
    finally:
        if connection is not None:
            connection.close()

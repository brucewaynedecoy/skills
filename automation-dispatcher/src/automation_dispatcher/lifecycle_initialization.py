"""Approved lifecycle initialization and non-executing shadow validation."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import shlex
from typing import Any, Mapping, Sequence
import uuid

from . import __version__
from .audit import verify_audit_chain
from .backup import create_backup, verify_backup
from .database import connect, integrity_check
from .lifecycle_artifacts import model_for
from .lifecycle_contracts import LifecycleContractError, seal_artifact, validate_artifact
from .lifecycle_engine import (
    deterministic_operation_id,
    deterministic_step_id,
    persist_progress,
    verify_progress_audit_binding,
)
from .registry import (
    RegistryError,
    dispatcher_configuration_from_row,
    dispatcher_configuration_hash,
    heartbeat_reconciliation,
    initialize_dispatcher,
    normalize_dispatcher_configuration,
    prepare_definition,
    register_workflow,
)
from .routing import check_route
from .scheduling import collection_occurrences_between


class LifecycleInitializationError(LifecycleContractError):
    """A deterministic initialization or shadow-validation failure."""


@dataclass(frozen=True)
class InitializationPaths:
    """Every mutable or generated path used by lifecycle initialization."""

    database: Path
    source_directory: Path
    manifest: Path
    heartbeat_template: Path
    backup: Path
    progress: Path
    readiness: Path | None = None


def _fail(code: str, message: str, **details: Any) -> None:
    raise LifecycleInitializationError(code, message, **details)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _hash_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _path_has_symlink(path: Path) -> bool:
    current = path
    while True:
        if current.exists() and current.is_symlink():
            return True
        if current.parent == current:
            return False
        current = current.parent


def _approved_source_path(
    path: str | Path,
    *,
    plan: Mapping[str, Any],
    repository_root: str | Path,
    source_directory: Path,
) -> Path:
    root = Path(repository_root).expanduser().resolve(strict=True)
    candidate = Path(path).expanduser().resolve(strict=False)
    if not _inside(candidate, root) or not _inside(candidate, source_directory):
        _fail("source_path_outside_root", "generated source path is outside approved roots", path=str(candidate))
    if _path_has_symlink(candidate):
        _fail("symlink_artifact_path", "generated source path traverses a symlink", path=str(candidate))
    approved = _source_path_allowlist(plan, source_directory)
    if candidate not in approved:
        _fail("unapproved_source_path", "generated source path is not covered by the accepted plan", path=str(candidate))
    return candidate


def _source_path_allowlist(plan: Mapping[str, Any], source_directory: Path) -> set[Path]:
    """Return exact accepted paths plus deterministic implementation-owned outputs."""

    approved = {
        Path(item).expanduser().resolve(strict=False) for item in plan["source_paths"]
    }
    approved.add((source_directory / "heartbeat.txt").resolve(strict=False))
    for collection in plan["collections"]:
        for draft in collection.get("workflow_drafts", ()):
            definition = draft.get("definition")
            if not isinstance(definition, Mapping):
                continue
            definition_path = (
                source_directory / "definitions" / f"{definition['workflow_id']}.json"
            ).resolve(strict=False)
            approved.add(definition_path)
            procedure = definition.get("procedure")
            if isinstance(procedure, Mapping) and procedure.get("kind") == "documented":
                reference = procedure.get("reference")
                if isinstance(reference, str):
                    approved.add((definition_path.parent / reference).resolve(strict=False))
            for reference in definition.get("authority_refs", ()):
                approved.add((definition_path.parent / str(reference)).resolve(strict=False))
    return approved


def _validate_source_directory(
    source_directory: Path, *, repository_root: str | Path
) -> None:
    root = Path(repository_root).expanduser().resolve(strict=True)
    if not _inside(source_directory, root):
        _fail("source_path_outside_root", "source directory is outside the repository root")
    if _path_has_symlink(source_directory):
        _fail("symlink_artifact_path", "source directory traverses a symlink")


def _approved_state_path(
    path: str | Path,
    *,
    plan: Mapping[str, Any],
    state_root: str | Path,
    source_root: str | Path,
    installed_roots: Sequence[str | Path],
) -> Path:
    root = Path(state_root).expanduser().resolve(strict=True)
    candidate = Path(path).expanduser().resolve(strict=False)
    if not _inside(candidate, root):
        _fail("state_path_outside_root", "state path is outside the explicit state root", path=str(candidate))
    forbidden = [Path(source_root).expanduser().resolve(strict=False), *[
        Path(item).expanduser().resolve(strict=False) for item in installed_roots
    ]]
    if any(candidate == item or _inside(candidate, item) for item in forbidden):
        _fail("forbidden_artifact_path", "state path enters a source or installed root", path=str(candidate))
    if _path_has_symlink(candidate):
        _fail("symlink_artifact_path", "state path traverses a symlink", path=str(candidate))
    approved = {str(Path(item).expanduser().resolve(strict=False)) for item in plan["state_paths"]}
    if str(candidate) not in approved:
        _fail("unapproved_state_path", "state path is not explicitly listed in the accepted plan", path=str(candidate))
    if not candidate.parent.is_dir():
        _fail("state_parent_missing", "state artifact parent must already exist", path=str(candidate.parent))
    return candidate


def _write_exact(path: Path, content: bytes, *, mode: int = 0o600) -> bool:
    if path.exists():
        if not path.is_file():
            _fail("source_conflict", "artifact path is not a file", path=str(path))
        observed = path.read_bytes()
        if observed != content:
            _fail(
                "source_conflict",
                "existing artifact differs; refusing to overwrite user content",
                path=str(path),
                expected_sha256=_hash_bytes(content),
                observed_sha256=_hash_bytes(observed),
                expected_size=len(content),
                observed_size=len(observed),
                guidance="revise the source, accept a new plan, or choose a new approved path",
            )
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
    return True


def _approval_expiry(plan: Mapping[str, Any]) -> datetime:
    values = [item.split(":", 1)[1] for item in plan["approved_scope"] if item.startswith("expires_at:")]
    if len(values) != 1:
        _fail("plan_expiry_missing", "accepted plan must contain exactly one expiry fence")
    try:
        parsed = datetime.fromisoformat(values[0].replace("Z", "+00:00"))
    except ValueError as exc:
        raise LifecycleInitializationError("invalid_plan_expiry", "accepted plan expiry is invalid") from exc
    if parsed.tzinfo is None:
        _fail("invalid_plan_expiry", "accepted plan expiry requires a timezone")
    return parsed.astimezone(UTC)


def _validate_authority(
    plan: Mapping[str, Any],
    current_source: Mapping[str, Any],
    *,
    expected_plan_hash: str,
    expected_source_state_hash: str,
    actor: str,
    now: datetime | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    accepted = validate_artifact("lifecycle_plan", plan)
    observed = validate_artifact("discovery_snapshot", current_source)
    if accepted["content_hash"] != expected_plan_hash:
        _fail("plan_hash_mismatch", "caller plan hash does not match the accepted plan")
    if accepted["actor"] != actor:
        _fail("plan_actor_mismatch", "initialization actor does not match the accepting actor")
    if accepted["unresolved_decisions"]:
        _fail("blocked_prerequisite", "accepted plan still has unresolved decisions", items=accepted["unresolved_decisions"])
    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    if current_time >= _approval_expiry(accepted):
        _fail("plan_expired", "accepted lifecycle plan has expired")
    observed_hash = observed["content_hash"]
    if not (
        observed_hash == expected_source_state_hash == accepted["source_snapshot_hash"]
        and observed["snapshot_id"] == accepted["source_snapshot_id"]
    ):
        _fail(
            "source_snapshot_drift",
            "current validated discovery evidence no longer matches the accepted plan",
            expected=accepted["source_snapshot_hash"],
            caller_expected=expected_source_state_hash,
            observed=observed_hash,
            guidance="rediscover and accept a new plan",
        )
    return accepted, observed


def _collection(plan: Mapping[str, Any], collection_id: str) -> dict[str, Any]:
    matches = [dict(item) for item in plan["collections"] if item.get("dispatcher_id") == collection_id]
    if len(matches) != 1:
        _fail("collection_identity_mismatch", "plan must contain exactly one requested collection", collection_id=collection_id)
    return matches[0]


def _procedure_stub(workflow_id: str, source_id: str) -> bytes:
    return (
        f"# {workflow_id} procedure\n\n"
        f"Source: `{source_id}`\n\n"
        "This is a generated initialization stub. Replace it only through a newly accepted lifecycle plan.\n"
    ).encode("utf-8")


def _generate_sources(
    collection: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    repository_root: str | Path,
    source_directory: Path,
) -> tuple[list[Path], dict[str, str], dict[str, str], int]:
    paths: list[Path] = []
    hashes: dict[str, str] = {}
    source_hashes: dict[str, str] = {}
    writes = 0
    for draft_entry in collection.get("workflow_drafts", ()):
        definition = draft_entry.get("definition")
        if not isinstance(definition, Mapping):
            _fail("incomplete_workflow_definition", "accepted plan contains an incomplete workflow draft")
        workflow_id = str(definition["workflow_id"])
        definition_path = _approved_source_path(
            source_directory / "definitions" / f"{workflow_id}.json",
            plan=plan,
            repository_root=repository_root,
            source_directory=source_directory,
        )
        procedure = definition.get("procedure")
        if isinstance(procedure, Mapping) and procedure.get("kind") == "documented":
            reference = procedure.get("reference")
            if not isinstance(reference, str):
                _fail("invalid_procedure_reference", "documented procedure requires a string reference")
            procedure_path = _approved_source_path(
                definition_path.parent / reference,
                plan=plan,
                repository_root=repository_root,
                source_directory=source_directory,
            )
            writes += int(_write_exact(procedure_path, _procedure_stub(workflow_id, str(draft_entry["source_id"]))))
            source_hashes[procedure_path.relative_to(source_directory).as_posix()] = _hash_bytes(
                procedure_path.read_bytes()
            )
        for reference in definition.get("authority_refs", ()):
            authority_path = _approved_source_path(
                definition_path.parent / str(reference),
                plan=plan,
                repository_root=repository_root,
                source_directory=source_directory,
            )
            if not authority_path.is_file():
                _fail("authority_reference_missing", "workflow authority reference does not exist", path=str(authority_path))
        content = json.dumps(definition, sort_keys=True, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
        writes += int(_write_exact(definition_path, content))
        _, _, projection = prepare_definition(definition_path)
        paths.append(definition_path)
        hashes[workflow_id] = str(projection["definition_hash"])
        source_hashes[definition_path.relative_to(source_directory).as_posix()] = _hash_bytes(
            definition_path.read_bytes()
        )
    return paths, hashes, source_hashes, writes


def _dispatcher_config(collection: Mapping[str, Any]) -> dict[str, Any]:
    schedule = collection["schedule"]
    return normalize_dispatcher_configuration(
        {
            "dispatcher_id": collection["dispatcher_id"],
            "name": collection.get("name") or collection["dispatcher_id"],
            "description": "Initialized from an accepted Automation Dispatcher lifecycle plan.",
            "timezone": collection["timezone"],
            "schedule": schedule,
            "max_lateness_seconds": int(collection.get("max_lateness_seconds", 3600)),
            "catch_up": collection.get("catch_up") or {"policy": "latest", "max_lookback_seconds": 86400},
            "heartbeat_schedule": collection.get("heartbeat_requirement")
            or {"verified": False, "schedule": schedule},
            "enabled": True,
        }
    )


def _initialize_dispatcher(
    database: Path,
    collection: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    actor: str,
    reason: str,
    source_revision: str,
) -> tuple[dict[str, Any], bool]:
    config = _dispatcher_config(collection)
    working_roots = collection.get("approved_working_roots") or ()
    if not working_roots:
        _fail("working_directory_missing", "collection has no approved task working directory")
    working_directory = Path(str(working_roots[0])).expanduser().resolve(strict=True)
    if not _inside(database, working_directory):
        _fail("database_locator_invalid", "database must be inside the approved task working directory")
    dispatcher_id = str(collection["dispatcher_id"])
    requirements = {
        "task_id": {"required": True, "minimum_assurance": "verified_config"},
        "working_directory": {"required": True, "minimum_assurance": "verified_config"},
        "harness": {"required": False, "minimum_assurance": "unknown", "allow_unknown": True},
        "host": {"required": False, "minimum_assurance": "unknown", "allow_unknown": True},
    }
    try:
        result = initialize_dispatcher(
            database,
            dispatcher_id=dispatcher_id,
            name=config["name"],
            description=config["description"],
            schedule=config["schedule"],
            timezone=config["timezone"],
            max_lateness_seconds=config["max_lateness_seconds"],
            catch_up=config["catch_up"],
            heartbeat_schedule=config["heartbeat_schedule"],
            expected_task_id=str(collection["target_task_id"]),
            expected_working_directory=working_directory,
            actor=actor,
            reason=reason,
            required_identity=requirements,
            skill_version=__version__,
            source_revision=source_revision,
            timestamp=str(plan["created_at"]),
            route_id=str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"automation-dispatcher:{plan['content_hash']}:{dispatcher_id}:route:1",
                )
            ),
        )
    except RegistryError as exc:
        _fail(
            "registry_conflict",
            str(exc),
            guidance="reconcile the registry or accept a new lifecycle plan",
        )
    return result, result["status"] == "initialized"


def _register_definitions(database: Path, definitions: Sequence[Path], *, actor: str, reason: str) -> tuple[list[dict[str, Any]], int]:
    results: list[dict[str, Any]] = []
    mutations = 0
    conn = connect(database)
    try:
        for path in definitions:
            _, _, projection = prepare_definition(path)
            existing = conn.execute("SELECT * FROM workflows WHERE workflow_id = ?", (projection["workflow_id"],)).fetchone()
            if existing is not None:
                if existing["definition_hash"] != projection["definition_hash"] or existing["definition_path"] != projection["definition_path"]:
                    _fail("registry_conflict", "existing workflow differs from generated definition", workflow_id=projection["workflow_id"], guidance="reconcile the registry or accept a new plan")
                results.append({"workflow_id": projection["workflow_id"], "definition_hash": projection["definition_hash"], "status": "already_registered"})
                continue
            register_workflow(conn, path, actor=actor, reason=reason, dry_run=True)
            result = register_workflow(conn, path, actor=actor, reason=reason)
            results.append(result)
            mutations += 1
    finally:
        conn.close()
    return results, mutations


def _initialization_projection(
    database: Path,
    collection: Mapping[str, Any],
    workflow_hashes: Mapping[str, str],
    definition_paths: Mapping[str, Path],
) -> dict[str, Any]:
    """Return one shared, fail-closed initialized-state projection."""

    dispatcher_id = str(collection["dispatcher_id"])
    errors: list[str] = []
    conn = connect(database)
    try:
        dispatcher = conn.execute(
            "SELECT * FROM dispatchers WHERE dispatcher_id = ?", (dispatcher_id,)
        ).fetchone()
        if dispatcher is None:
            return {"ok": False, "errors": ["dispatcher row is missing"]}
        revision = conn.execute(
            "SELECT * FROM dispatcher_revisions WHERE dispatcher_id = ? AND revision = ?",
            (dispatcher_id, dispatcher["current_revision"]),
        ).fetchone()
        route = conn.execute(
            "SELECT * FROM dispatcher_routes WHERE dispatcher_id = ? ORDER BY revision DESC LIMIT 1",
            (dispatcher_id,),
        ).fetchone()
        workflows = conn.execute(
            "SELECT workflow_id,definition_hash,definition_path FROM workflows WHERE dispatcher_id = ? ORDER BY workflow_id",
            (dispatcher_id,),
        ).fetchall()
        audit = verify_audit_chain(conn, dispatcher_id)
    finally:
        conn.close()
    expected_config = _dispatcher_config(collection)
    expected_hash = dispatcher_configuration_hash(expected_config)
    try:
        observed_config = dispatcher_configuration_from_row(dispatcher)
    except Exception as exc:
        observed_config = None
        errors.append(f"dispatcher configuration is invalid: {exc}")
    try:
        revision_config = (
            json.loads(revision["normalized_config_json"])
            if revision is not None
            else None
        )
    except (TypeError, json.JSONDecodeError) as exc:
        revision_config = None
        errors.append(f"dispatcher revision configuration is invalid: {exc}")
    if (
        revision is None
        or int(dispatcher["current_revision"]) != 1
        or revision["config_hash"] != expected_hash
        or revision_config != expected_config
        or observed_config != expected_config
    ):
        errors.append("dispatcher revision, config hash, or full configuration differs")
    expected_directory = str(
        Path(str(collection["approved_working_roots"][0])).expanduser().resolve(strict=True)
    )
    if (
        route is None
        or int(route["revision"]) != 1
        or route["destination_task_id"] != collection["target_task_id"]
        or route["expected_working_directory"] != expected_directory
    ):
        errors.append("required route revision or projection is missing")
    try:
        observed_heartbeat = heartbeat_reconciliation(dispatcher)
        expected_heartbeat = heartbeat_reconciliation(expected_config)
        if observed_heartbeat != expected_heartbeat:
            errors.append("heartbeat reconciliation differs")
    except Exception as exc:
        observed_heartbeat = {"error": str(exc)}
        errors.append(f"heartbeat reconciliation is invalid: {exc}")
    observed_workflows = {
        row["workflow_id"]: row["definition_hash"] for row in workflows
    }
    if observed_workflows != dict(workflow_hashes):
        errors.append("workflow registry projection differs")
    for row in workflows:
        expected_path = definition_paths.get(row["workflow_id"])
        if expected_path is None or Path(row["definition_path"]).resolve(strict=False) != expected_path.resolve(strict=False):
            errors.append(f"workflow definition path differs: {row['workflow_id']}")
    if not audit["valid"] or audit["event_count"] < 1:
        errors.append("nonempty valid audit evidence is required")
    return {
        "ok": not errors,
        "errors": errors,
        "dispatcher_revision": int(dispatcher["current_revision"]),
        "config_hash": revision["config_hash"] if revision is not None else None,
        "route_present": route is not None,
        "workflow_hashes": observed_workflows,
        "heartbeat_reconciliation": observed_heartbeat,
        "audit": audit,
    }


def _backup_projection(path: Path, dispatcher_id: str) -> dict[str, Any] | None:
    conn = connect(path)
    try:
        dispatcher = conn.execute(
            "SELECT current_revision FROM dispatchers WHERE dispatcher_id = ?",
            (dispatcher_id,),
        ).fetchone()
        if dispatcher is None:
            return None
        revision = conn.execute(
            "SELECT config_hash FROM dispatcher_revisions WHERE dispatcher_id = ? AND revision = ?",
            (dispatcher_id, dispatcher["current_revision"]),
        ).fetchone()
        tip = conn.execute(
            "SELECT event_id,event_hash FROM audit_events WHERE dispatcher_id = ? ORDER BY event_id DESC LIMIT 1",
            (dispatcher_id,),
        ).fetchone()
        return {
            "revision": int(dispatcher["current_revision"]),
            "config_hash": revision["config_hash"] if revision else None,
            "workflows": [
                (row["workflow_id"], row["definition_hash"])
                for row in conn.execute(
                    "SELECT workflow_id,definition_hash FROM workflows WHERE dispatcher_id = ? ORDER BY workflow_id",
                    (dispatcher_id,),
                )
            ],
            "audit_tip": tuple(tip) if tip is not None else None,
        }
    finally:
        conn.close()


def _backup_provenance(
    database: Path, backup: Path, *, dispatcher_id: str
) -> dict[str, Any]:
    """Compare a restore candidate to the live initialized projection read-only."""

    live_projection = _backup_projection(database, dispatcher_id)
    backup_projection = _backup_projection(backup, dispatcher_id)
    errors: list[str] = []
    if live_projection is None:
        errors.append("initialized dispatcher is missing from the live database")
    if backup_projection is None:
        errors.append("initialized dispatcher is missing from the backup")
    if live_projection is not None and backup_projection is not None:
        for key in ("revision", "config_hash", "workflows"):
            if backup_projection[key] != live_projection[key]:
                errors.append(f"backup {key} projection differs from live state")
        backup_tip = backup_projection["audit_tip"]
        if backup_tip is None:
            errors.append("backup lacks required nonempty audit provenance")
        else:
            conn = connect(database)
            try:
                matching_tip = conn.execute(
                    "SELECT event_hash FROM audit_events WHERE dispatcher_id = ? AND event_id = ?",
                    (dispatcher_id, backup_tip[0]),
                ).fetchone()
            finally:
                conn.close()
            if matching_tip is None or matching_tip["event_hash"] != backup_tip[1]:
                errors.append("backup audit tip is not a prefix of the live audit chain")
    return {
        "ok": not errors,
        "errors": errors,
        "live_projection": live_projection,
        "backup_projection": backup_projection,
    }


def _backup(database: Path, destination: Path, *, dispatcher_id: str) -> tuple[dict[str, Any], bool]:
    if destination.exists():
        verification = verify_backup(destination)
        if not verification["ok"]:
            _fail("backup_verification_failed", "existing backup failed restore verification", verification=verification)
        provenance = _backup_provenance(
            database, destination, dispatcher_id=dispatcher_id
        )
        if not provenance["ok"]:
            _fail(
                "backup_provenance_mismatch",
                "existing backup does not match the initialized dispatcher projection",
                evidence=provenance,
                guidance="remove the unrelated backup or choose a new approved backup path",
            )
        return verification, False
    created = create_backup(database, destination)
    provenance = _backup_provenance(
        database, destination, dispatcher_id=dispatcher_id
    )
    if not provenance["ok"]:
        _fail(
            "backup_provenance_mismatch",
            "new backup projection differs from its source database",
            evidence=provenance,
        )
    return created, True


def _maybe_crash(step: str, crash_after_step: str | None) -> None:
    if crash_after_step == step:
        raise RuntimeError(f"injected lifecycle crash after {step}")


def initialize_from_plan(
    plan: Mapping[str, Any],
    current_source: Mapping[str, Any],
    *,
    collection_id: str,
    expected_plan_hash: str,
    expected_source_state_hash: str,
    actor: str,
    reason: str,
    paths: InitializationPaths,
    repository_root: str | Path,
    state_root: str | Path,
    source_root: str | Path,
    installed_roots: Sequence[str | Path] = (),
    source_revision: str = "unknown",
    now: datetime | None = None,
    crash_after_step: str | None = None,
) -> dict[str, Any]:
    """Apply one accepted collection plan without executing workflows or mutating a host."""

    accepted, observed = _validate_authority(
        plan, current_source, expected_plan_hash=expected_plan_hash,
        expected_source_state_hash=expected_source_state_hash, actor=actor, now=now,
    )
    collection = _collection(accepted, collection_id)
    source_directory = Path(paths.source_directory).expanduser().resolve(strict=True)
    _validate_source_directory(source_directory, repository_root=repository_root)
    manifest_path = _approved_source_path(paths.manifest, plan=accepted, repository_root=repository_root, source_directory=source_directory)
    exact_plan_sources = {
        Path(item).expanduser().resolve(strict=False) for item in accepted["source_paths"]
    }
    if manifest_path not in exact_plan_sources:
        _fail("unapproved_source_path", "manifest path must be an exact accepted-plan source path")
    if manifest_path.parent != source_directory:
        _fail("unapproved_source_path", "source directory must be the accepted manifest directory")
    heartbeat_path = _approved_source_path(paths.heartbeat_template, plan=accepted, repository_root=repository_root, source_directory=source_directory)
    database = _approved_state_path(paths.database, plan=accepted, state_root=state_root, source_root=source_root, installed_roots=installed_roots)
    backup_path = _approved_state_path(paths.backup, plan=accepted, state_root=state_root, source_root=source_root, installed_roots=installed_roots)
    progress_path = _approved_state_path(paths.progress, plan=accepted, state_root=state_root, source_root=source_root, installed_roots=installed_roots)

    definitions, workflow_hashes, source_file_hashes, writes = _generate_sources(
        collection, plan=accepted, repository_root=repository_root, source_directory=source_directory,
    )
    _maybe_crash("source_generation", crash_after_step)
    database_result, initialized = _initialize_dispatcher(
        database, collection, plan=accepted, actor=actor, reason=reason, source_revision=source_revision,
    )
    _maybe_crash("database_initialization", crash_after_step)
    registrations, registration_mutations = _register_definitions(database, definitions, actor=actor, reason=reason)
    _maybe_crash("workflow_registration", crash_after_step)
    definition_paths = {
        path.stem: path for path in definitions
    }
    projection = _initialization_projection(
        database, collection, workflow_hashes, definition_paths
    )
    if not projection["ok"]:
        _fail(
            "initialization_projection_invalid",
            "initialized database projection is incomplete or inconsistent",
            evidence=projection,
            guidance="repair or abandon the partial database before resuming",
        )

    working_directory = Path(str(collection["approved_working_roots"][0])).expanduser().resolve(strict=True)
    database_locator = database.relative_to(working_directory).as_posix()
    definition_locators = [path.relative_to(manifest_path.parent).as_posix() for path in definitions]
    conn = connect(database)
    try:
        dispatcher = conn.execute("SELECT current_revision FROM dispatchers WHERE dispatcher_id = ?", (collection_id,)).fetchone()
        pending_receipts = conn.execute("SELECT COUNT(*) FROM receipts WHERE dispatcher_id = ? AND status != 'acknowledged'", (collection_id,)).fetchone()[0]
    finally:
        conn.close()
    cli_project = Path(__file__).resolve().parents[2]
    command_prefix = (
        f"uv run --project {shlex.quote(str(cli_project))} automation-dispatcher "
        f"--database {shlex.quote(str(database))} --json"
    )
    heartbeat = (
        "Invoke the `automation-dispatcher` skill.\n"
        f"Required CLI version: {__version__}\n"
        f"Pinned command prefix: `{command_prefix}`\n"
        f"Dispatcher: `{collection_id}`\nManifest: `{manifest_path}`\nDatabase: `{database}`\n"
        "Require fresh route-observation JSON for every route check; discovery evidence is not fresh attestation.\n"
        f"1. Status: `{command_prefix} status`.\n"
        f"2. Integrity: `{command_prefix} integrity-check`. Stop and report action_required on failure.\n"
        f"3. Route: `{command_prefix} route-check --dispatcher-id {collection_id} --observed <fresh-route.json> --actor heartbeat`. Stop and report action_required on mismatch.\n"
        f"4. Due: `{command_prefix} due --dispatcher-id {collection_id}`. Stay silent when no occurrence is due.\n"
        f"5. Run due work only through `{command_prefix} run --dispatcher-id {collection_id} --owner heartbeat --observed <fresh-route.json> --approved-root <approved-root>`.\n"
        "6. Stop and report action_required without improvising. Finalize only an explicitly owned run through `complete <run-id> --actor heartbeat --summary <summary>` or `fail <run-id> --actor heartbeat --error-class <class> --summary <summary>`; never edit run state directly.\n"
        "7. Post every action_required, completed, or failed receipt's rendered_content exactly once to its destination_task_id. After successful posting, acknowledge only that receipt using `receipt-ack <receipt-id> --external-message-id <message-id> --actor heartbeat`.\n"
        "8. If delivery definitively failed before posting, use `receipt-retry <receipt-id> --actor heartbeat --confirm-not-posted`, then reload and post; never rerun the workflow for receipt delivery and never acknowledge an unposted receipt.\n"
        "Do not create, update, enable, disable, or delete host tasks or automations. Existing sources remain authoritative; cutover requires separate explicit approval.\n"
    ).encode("utf-8")
    manifest = model_for("collection_manifest").seal({
        "schema_version": 1, "artifact_type": "collection_manifest",
        "manifest_id": deterministic_step_id(accepted["content_hash"], "initialize", "manifest", collection_id),
        "dispatcher_id": collection_id, "schedule": collection["schedule"], "timezone": collection["timezone"],
        "route": {"task_id": collection["target_task_id"], "working_directory": str(working_directory)},
        "heartbeat_requirement": {"target_task_id": collection["target_task_id"], "cutover_authorized": False},
        "workflow_definition_locators": definition_locators,
        "required_versions": {"cli_version": __version__, "source_revision": source_revision,
            "plan_hash": accepted["content_hash"], "collection_revision": dispatcher["current_revision"],
            "workflow_hashes": workflow_hashes, "source_file_hashes": source_file_hashes,
            "heartbeat_template_path": heartbeat_path.relative_to(source_directory).as_posix(),
            "heartbeat_template_hash": _hash_bytes(heartbeat)},
        "database_locator": {"kind": "task_working_directory_relative", "path": database_locator},
    }).as_dict()
    writes += int(_write_exact(manifest_path, _canonical(manifest)))
    _maybe_crash("manifest", crash_after_step)
    writes += int(_write_exact(heartbeat_path, heartbeat))
    _maybe_crash("heartbeat_template", crash_after_step)
    backup_result, backup_created = _backup(
        database, backup_path, dispatcher_id=collection_id
    )
    _maybe_crash("backup", crash_after_step)
    progress_artifact = model_for("progress_record").seal({
        "schema_version": 1, "artifact_type": "progress_record",
        "operation_id": deterministic_operation_id(accepted["content_hash"], "initialize"),
        "plan_id": accepted["plan_id"], "plan_hash": accepted["content_hash"], "stage": "initialize",
        "step_id": deterministic_step_id(accepted["content_hash"], "initialize", "complete", collection_id),
        "status": "completed", "started_at": accepted["created_at"], "updated_at": observed["observed_at"],
        "actor": actor, "evidence": [
            manifest["content_hash"],
            f"backup_restore_verified:sha256:{backup_result['sha256']}",
        ],
        "dispatcher_id": collection_id, "workflow_id": None, "event_id": None, "receipt_id": None,
    })
    progress_connection = connect(database)
    try:
        projection = progress_connection.execute(
            """SELECT dispatcher.current_revision, revision.config_hash
                 FROM dispatchers AS dispatcher
                 JOIN dispatcher_revisions AS revision
                   ON revision.dispatcher_id = dispatcher.dispatcher_id
                  AND revision.revision = dispatcher.current_revision
                WHERE dispatcher.dispatcher_id = ?""",
            (collection_id,),
        ).fetchone()
        if projection is None:
            _fail("collection_missing", "collection projection is missing before progress persistence")
        progress_connection.execute("BEGIN IMMEDIATE")
        progress_result = persist_progress(
            progress_path,
            progress_artifact,
            plan=accepted,
            actor=actor,
            connection=progress_connection,
            dispatcher_id=collection_id,
            expected_dispatcher_revision=int(projection["current_revision"]),
            expected_dispatcher_config_hash=str(projection["config_hash"]),
            source_root=source_root,
            installed_roots=tuple(installed_roots),
            before_replace=(
                (lambda _path: _maybe_crash("progress_persist", crash_after_step))
                if crash_after_step == "progress_persist"
                else None
            ),
        )
        progress_connection.commit()
    except Exception:
        progress_connection.rollback()
        raise
    finally:
        progress_connection.close()
    progress = progress_result["record"]
    _maybe_crash("progress", crash_after_step)
    progress_created = progress_result["status"] == "persisted"
    mutation_count = (
        writes
        + int(initialized)
        + registration_mutations
        + int(backup_created)
        + int(progress_created)
    )
    return {
        "status": "no_op" if mutation_count == 0 else "completed", "mutation_count": mutation_count,
        "plan_id": accepted["plan_id"], "plan_hash": accepted["content_hash"], "collection_id": collection_id,
        "database_path": str(database), "source_snapshot_hash": observed["content_hash"],
        "definitions": [str(path) for path in definitions], "workflow_hashes": workflow_hashes,
        "database": database_result, "registrations": registrations, "manifest": manifest,
        "manifest_path": str(manifest_path), "heartbeat_template_path": str(heartbeat_path),
        "backup": backup_result, "progress": progress, "progress_path": str(progress_path),
        "pending_receipts": pending_receipts, "workflow_execution_count": 0, "host_mutation_count": 0,
    }


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LifecycleInitializationError("manifest_invalid", f"cannot read collection manifest: {exc}") from exc
    return model_for("collection_manifest").from_mapping(value).as_dict()


_OCCURRENCE_FIELDS = {
    "source_id",
    "scheduled_for",
    "intended_local",
    "effective_local",
    "timezone",
    "adjustment",
}


def _occurrence_identity(value: Mapping[str, Any]) -> bytes:
    return _canonical({field: value[field] for field in sorted(_OCCURRENCE_FIELDS)})


def _validated_source_occurrences(
    values: Sequence[Mapping[str, Any]],
    *,
    source_ids: set[str],
    timezone: str,
    window_start: str,
    window_end: str,
) -> list[dict[str, Any]]:
    if isinstance(values, (str, bytes)) or len(values) > 100_000:
        _fail("invalid_source_occurrences", "source occurrence evidence exceeds the bounded schema")
    try:
        raw_start = datetime.fromisoformat(window_start.replace("Z", "+00:00"))
        raw_end = datetime.fromisoformat(window_end.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as exc:
        raise LifecycleInitializationError(
            "invalid_occurrence_window", "shadow occurrence window must be ISO-8601"
        ) from exc
    if raw_start.tzinfo is None or raw_end.tzinfo is None:
        _fail("invalid_occurrence_window", "shadow occurrence window requires timezones")
    start = raw_start.astimezone(UTC)
    end = raw_end.astimezone(UTC)
    if end < start:
        _fail("invalid_occurrence_window", "shadow occurrence window end precedes start")
    result: list[dict[str, Any]] = []
    for index, raw in enumerate(values):
        if not isinstance(raw, Mapping) or set(raw) != _OCCURRENCE_FIELDS:
            _fail(
                "invalid_source_occurrences",
                "source occurrence must contain the exact canonical scheduling fields",
                index=index,
                required=sorted(_OCCURRENCE_FIELDS),
            )
        item = dict(raw)
        if item["source_id"] not in source_ids or item["timezone"] != timezone:
            _fail("invalid_source_occurrences", "source occurrence identity is outside the accepted collection", index=index)
        try:
            raw_scheduled = datetime.fromisoformat(
                str(item["scheduled_for"]).replace("Z", "+00:00")
            )
            intended = datetime.fromisoformat(str(item["intended_local"]))
            effective = datetime.fromisoformat(str(item["effective_local"]))
        except ValueError as exc:
            raise LifecycleInitializationError(
                "invalid_source_occurrences", "source occurrence contains an invalid datetime", index=index
            ) from exc
        if raw_scheduled.tzinfo is None:
            _fail("invalid_source_occurrences", "scheduled_for requires a timezone", index=index)
        scheduled = raw_scheduled.astimezone(UTC)
        canonical_scheduled = scheduled.isoformat(timespec="seconds").replace("+00:00", "Z")
        if (
            str(item["scheduled_for"]) != canonical_scheduled
            or str(item["intended_local"]) != intended.isoformat(timespec="seconds")
            or str(item["effective_local"]) != effective.isoformat(timespec="seconds")
            or intended.tzinfo is not None
            or effective.tzinfo is not None
            or not (start <= scheduled < end)
        ):
            _fail("invalid_source_occurrences", "source occurrence datetime is outside the canonical bounded form", index=index)
        adjustment = item["adjustment"]
        if adjustment is not None and (
            not isinstance(adjustment, Mapping)
            or set(adjustment) != {"kind", "from_local", "to_local"}
            or adjustment.get("kind") != "gap_advanced"
        ):
            _fail("invalid_source_occurrences", "source occurrence adjustment is invalid", index=index)
        result.append(item)
    return result


def shadow_validate_from_plan(
    plan: Mapping[str, Any],
    current_source: Mapping[str, Any],
    source_occurrences: Sequence[Mapping[str, Any]],
    *,
    collection_id: str,
    expected_plan_hash: str,
    expected_source_state_hash: str,
    actor: str,
    paths: InitializationPaths,
    repository_root: str | Path,
    state_root: str | Path,
    source_root: str | Path,
    window_start: str,
    window_end: str,
    installed_roots: Sequence[str | Path] = (),
    now: datetime | None = None,
    crash_after_step: str | None = None,
) -> dict[str, Any]:
    """Compare source and dispatcher occurrences without claims, runs, effects, or host calls."""

    accepted, observed = _validate_authority(
        plan, current_source, expected_plan_hash=expected_plan_hash,
        expected_source_state_hash=expected_source_state_hash, actor=actor, now=now,
    )
    collection = _collection(accepted, collection_id)
    source_directory = Path(paths.source_directory).expanduser().resolve(strict=True)
    _validate_source_directory(source_directory, repository_root=repository_root)
    manifest_path = _approved_source_path(paths.manifest, plan=accepted, repository_root=repository_root, source_directory=source_directory)
    exact_plan_sources = {
        Path(item).expanduser().resolve(strict=False) for item in accepted["source_paths"]
    }
    if manifest_path not in exact_plan_sources:
        _fail("unapproved_source_path", "manifest path must be an exact accepted-plan source path")
    if manifest_path.parent != source_directory:
        _fail("unapproved_source_path", "source directory must be the accepted manifest directory")
    database = _approved_state_path(paths.database, plan=accepted, state_root=state_root, source_root=source_root, installed_roots=installed_roots)
    backup_path = _approved_state_path(paths.backup, plan=accepted, state_root=state_root, source_root=source_root, installed_roots=installed_roots)
    progress_path = _approved_state_path(paths.progress, plan=accepted, state_root=state_root, source_root=source_root, installed_roots=installed_roots)
    if paths.readiness is None:
        _fail("readiness_path_required", "shadow validation requires an explicit readiness path")
    readiness_path = _approved_state_path(paths.readiness, plan=accepted, state_root=state_root, source_root=source_root, installed_roots=installed_roots)
    manifest = _read_manifest(manifest_path)
    database_hash_before = _hash_bytes(database.read_bytes())

    conn = connect(database)
    try:
        before_counts = {
            "runs": conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0],
            "receipts": conn.execute("SELECT COUNT(*) FROM receipts").fetchone()[0],
            "audit_events": conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0],
            "workflows": conn.execute("SELECT COUNT(*) FROM workflows").fetchone()[0],
            "workflow_revisions": conn.execute("SELECT COUNT(*) FROM workflow_revisions").fetchone()[0],
        }
        dispatcher = conn.execute("SELECT * FROM dispatchers WHERE dispatcher_id = ?", (collection_id,)).fetchone()
        revision = conn.execute(
            """SELECT revision,normalized_config_json,config_hash
                 FROM dispatcher_revisions
                WHERE dispatcher_id = ?
                  AND revision = (SELECT current_revision FROM dispatchers WHERE dispatcher_id = ?)""",
            (collection_id, collection_id),
        ).fetchone()
        workflows = conn.execute("SELECT workflow_id,definition_hash,definition_path FROM workflows WHERE dispatcher_id = ? ORDER BY workflow_id", (collection_id,)).fetchall()
        route = conn.execute(
            "SELECT * FROM dispatcher_routes WHERE dispatcher_id = ? ORDER BY revision DESC LIMIT 1",
            (collection_id,),
        ).fetchone()
        audit = verify_audit_chain(conn, collection_id)
    finally:
        conn.close()
    if dispatcher is None:
        _fail("collection_missing", "initialized collection is missing from the database")
    source_ids = sorted(str(item["source_id"]) for item in collection["workflow_drafts"])
    canonical_source_occurrences = _validated_source_occurrences(
        source_occurrences,
        source_ids=set(source_ids),
        timezone=str(collection["timezone"]),
        window_start=window_start,
        window_end=window_end,
    )
    proposed = collection_occurrences_between(
        _dispatcher_config(collection), window_start, window_end
    )
    expected_pairs = Counter(
        _occurrence_identity({"source_id": source_id, **item})
        for source_id in source_ids
        for item in proposed
    )
    observed_pairs = Counter(
        _occurrence_identity(item) for item in canonical_source_occurrences
    )
    missing = [
        {**json.loads(identity), "count": count}
        for identity, count in sorted((expected_pairs - observed_pairs).items())
    ]
    unexpected = [
        {**json.loads(identity), "count": count}
        for identity, count in sorted((observed_pairs - expected_pairs).items())
    ]
    blockers: list[str] = []
    changes: list[dict[str, Any]] = []
    shared_projection = _initialization_projection(
        database,
        collection,
        manifest["required_versions"].get("workflow_hashes", {}),
        {
            str(draft["definition"]["workflow_id"]): (
                source_directory
                / "definitions"
                / f"{draft['definition']['workflow_id']}.json"
            )
            for draft in collection["workflow_drafts"]
            if isinstance(draft.get("definition"), Mapping)
        },
    )
    if not shared_projection["ok"]:
        blockers.extend(
            f"initialization projection invalid: {error}"
            for error in shared_projection["errors"]
        )
        changes.append({
            "field": "initialization_projection",
            "errors": shared_projection["errors"],
            "guidance": "repair or abandon initialization before cutover",
        })
    if missing or unexpected:
        blockers.append("shadow occurrence comparison differs")
        changes.append({"field": "occurrences", "missing": missing, "unexpected": unexpected,
            "guidance": "revise the source schedule or accept a new lifecycle plan"})
    blockers.append("Q-003 callable Codex task and automation schemas are not proven in this runtime")
    integrity = integrity_check(database)
    if not integrity["ok"]:
        blockers.append("database integrity or foreign-key verification failed")
    backup_verification = verify_backup(backup_path)
    if not backup_verification["ok"]:
        blockers.append("backup restore verification failed")
    backup_provenance = (
        _backup_provenance(database, backup_path, dispatcher_id=collection_id)
        if backup_verification["ok"]
        else {"ok": False, "errors": ["restore verification failed"]}
    )
    if not backup_provenance["ok"]:
        blockers.extend(
            f"backup provenance invalid: {error}"
            for error in backup_provenance["errors"]
        )
        changes.append({
            "field": "backup_provenance",
            "errors": backup_provenance["errors"],
            "guidance": "restore the plan-bound pre-cutover backup before cutover",
        })
    try:
        progress_value = json.loads(progress_path.read_text(encoding="utf-8"))
        persisted_progress = validate_artifact("progress_record", progress_value)
        progress_connection = connect(database)
        try:
            progress_audit_binding = verify_progress_audit_binding(
                progress_connection,
                persisted_progress,
                dispatcher_id=collection_id,
            )
        finally:
            progress_connection.close()
        progress_backup_binding_ok = bool(
            persisted_progress["plan_hash"] == accepted["content_hash"]
            and persisted_progress["dispatcher_id"] == collection_id
            and persisted_progress["status"] == "completed"
            and progress_audit_binding["valid"]
            and f"backup_restore_verified:sha256:{backup_verification.get('sha256')}"
            in persisted_progress["evidence"]
        )
    except (OSError, json.JSONDecodeError, LifecycleContractError) as exc:
        persisted_progress = {"error": str(exc)}
        progress_audit_binding = {
            "valid": False,
            "errors": [{"error": "progress_invalid", "message": str(exc)}],
        }
        progress_backup_binding_ok = False
    if not progress_audit_binding["valid"]:
        blockers.append("progress record does not match its immutable lifecycle audit event")
        changes.append({
            "field": "progress_audit_binding",
            "errors": progress_audit_binding["errors"],
            "guidance": "restore the exact audited progress record before cutover",
        })
    if not progress_backup_binding_ok:
        blockers.append("backup hash is not bound to completed audited initialization progress")
        changes.append({
            "field": "backup_progress_binding",
            "guidance": "restore the progress-bound backup or repeat accepted initialization",
        })
    if not audit["valid"]:
        blockers.append("audit chain verification failed")
    expected_config = _dispatcher_config(collection)
    observed_config = dispatcher_configuration_from_row(dispatcher)
    expected_config_hash = dispatcher_configuration_hash(expected_config)
    current_revision = int(dispatcher["current_revision"])
    manifest_revision = manifest["required_versions"].get("collection_revision")
    projection_ok = bool(
        revision is not None
        and current_revision == manifest_revision
        and revision["config_hash"] == expected_config_hash
        and json.loads(revision["normalized_config_json"]) == expected_config
        and observed_config == expected_config
    )
    if not projection_ok:
        blockers.append("current dispatcher revision or canonical configuration drifted")
        changes.append({
            "field": "dispatcher_configuration",
            "expected_revision": manifest_revision,
            "observed_revision": current_revision,
            "expected_config_hash": expected_config_hash,
            "observed_config_hash": revision["config_hash"] if revision else None,
            "guidance": "reconcile the registry or accept a new lifecycle plan",
        })
    try:
        heartbeat = heartbeat_reconciliation(dispatcher)
        expected_heartbeat = heartbeat_reconciliation(expected_config)
        heartbeat_ok = heartbeat == expected_heartbeat
    except Exception as exc:
        heartbeat = {"error": str(exc)}
        expected_heartbeat = None
        heartbeat_ok = False
    if not heartbeat_ok:
        blockers.append("heartbeat reconciliation drifted from the accepted collection configuration")
    manifest_hashes = manifest["required_versions"].get("workflow_hashes", {})
    observed_hashes = {row["workflow_id"]: row["definition_hash"] for row in workflows}
    if manifest_hashes != observed_hashes:
        blockers.append("registered workflow projection drifted from the manifest")
        changes.append({"field": "workflow_hashes", "expected": manifest_hashes, "observed": observed_hashes,
            "guidance": "reconcile the registry or abandon and roll back initialization"})
    if manifest["required_versions"].get("plan_hash") != accepted["content_hash"]:
        blockers.append("manifest lifecycle-plan binding drifted")
        changes.append({"field": "manifest.plan_hash", "guidance": "restore the generated manifest or accept a new plan"})
    expected_source_hashes = manifest["required_versions"].get("source_file_hashes", {})
    observed_source_hashes: dict[str, str | None] = {}
    for locator, expected_hash in sorted(expected_source_hashes.items()):
        source_path = _approved_source_path(
            source_directory / locator,
            plan=accepted,
            repository_root=repository_root,
            source_directory=source_directory,
        )
        observed_hash = _hash_bytes(source_path.read_bytes()) if source_path.is_file() else None
        observed_source_hashes[locator] = observed_hash
        if observed_hash != expected_hash:
            blockers.append(f"generated source drifted: {locator}")
            changes.append({"field": f"source_file:{locator}", "expected": expected_hash,
                "observed": observed_hash, "guidance": "restore the generated source or accept a new plan"})
    observed_definition_locators: set[str] = set()
    for row in workflows:
        registered_path = Path(row["definition_path"]).expanduser().resolve(strict=False)
        locator = registered_path.relative_to(manifest_path.parent).as_posix() if _inside(registered_path, manifest_path.parent) else None
        if locator is not None:
            observed_definition_locators.add(locator)
        definition_ok = False
        if locator in manifest["workflow_definition_locators"] and registered_path.is_file():
            try:
                _, _, file_projection = prepare_definition(registered_path)
                definition_ok = (
                    file_projection["workflow_id"] == row["workflow_id"]
                    and file_projection["definition_hash"] == row["definition_hash"]
                    and manifest_hashes.get(row["workflow_id"]) == row["definition_hash"]
                )
            except Exception:
                definition_ok = False
        if not definition_ok:
            blockers.append(f"registered definition path or bytes drifted: {row['workflow_id']}")
            changes.append({
                "field": f"definition_projection:{row['workflow_id']}",
                "observed_path": str(registered_path),
                "guidance": "restore the exact registered definition or accept a new plan",
            })
    if observed_definition_locators != set(manifest["workflow_definition_locators"]):
        blockers.append("registered definition paths drifted from the manifest")
    heartbeat_locator = manifest["required_versions"].get("heartbeat_template_path")
    heartbeat_expected = manifest["required_versions"].get("heartbeat_template_hash")
    if heartbeat_locator and heartbeat_expected:
        heartbeat_observed_path = _approved_source_path(
            source_directory / heartbeat_locator,
            plan=accepted,
            repository_root=repository_root,
            source_directory=source_directory,
        )
        heartbeat_observed = (
            _hash_bytes(heartbeat_observed_path.read_bytes())
            if heartbeat_observed_path.is_file()
            else None
        )
        if heartbeat_observed != heartbeat_expected:
            blockers.append("heartbeat template drifted")
            changes.append({"field": "heartbeat_template", "expected": heartbeat_expected,
                "observed": heartbeat_observed, "guidance": "restore the generated template or accept a new plan"})
    expected_route = manifest["route"]
    if dispatcher["expected_task_id"] != expected_route.get("task_id") or dispatcher["expected_working_directory"] != expected_route.get("working_directory"):
        blockers.append("collection route drifted from the manifest")
        changes.append({"field": "route", "guidance": "reconcile the registry or accept a new plan"})
    source_items = {
        str(item.get("stable_id")): item
        for item in [*observed["tasks"], *observed["automations"]]
    }
    selected_items = [source_items[source_id] for source_id in source_ids if source_id in source_items]
    observed_task_ids = {item.get("target_task_id") for item in selected_items}
    observed_working_directories = {
        str(item.get("approved_working_roots", [None])[0])
        for item in selected_items
        if item.get("approved_working_roots")
    }
    route_projection_ok = bool(
        route is not None
        and route["destination_task_id"] == expected_route.get("task_id")
        and route["expected_working_directory"] == expected_route.get("working_directory")
    )
    if not route_projection_ok:
        blockers.append("collection route projection is missing")
        changes.append({"field": "route_projection", "guidance": "restore the route or accept a new plan"})
    route_requirements = json.loads(route["required_identity_json"]) if route is not None else {}
    route_evidence = check_route(
        {
            "task_id": expected_route.get("task_id"),
            "working_directory": expected_route.get("working_directory"),
        },
        {
            "task_id": {
                "value": next(iter(observed_task_ids)) if len(observed_task_ids) == 1 else None,
                "source": "discovery_snapshot",
                "assurance": "declared",
            },
            "working_directory": {
                "value": (
                    next(iter(observed_working_directories))
                    if len(observed_working_directories) == 1
                    else None
                ),
                "source": "discovery_snapshot",
                "assurance": "declared",
            },
        },
        route_requirements,
    )
    if not route_evidence["ok"]:
        blockers.append("route identity is not freshly attested at required assurance")
    conn = connect(database)
    try:
        after_counts = {
            "runs": conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0],
            "receipts": conn.execute("SELECT COUNT(*) FROM receipts").fetchone()[0],
            "audit_events": conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0],
            "workflows": conn.execute("SELECT COUNT(*) FROM workflows").fetchone()[0],
            "workflow_revisions": conn.execute("SELECT COUNT(*) FROM workflow_revisions").fetchone()[0],
        }
    finally:
        conn.close()
    if before_counts != after_counts:
        _fail("shadow_execution_detected", "shadow validation changed run or receipt state")
    database_hash_after = _hash_bytes(database.read_bytes())
    if database_hash_before != database_hash_after:
        _fail("shadow_database_mutation", "shadow validation changed database bytes")
    boundary = next((item for item in accepted["occurrence_boundaries"] if item.get("collection_id") == collection_id), {})
    checks = [
        {"name": "source_snapshot_current", "passed": True, "hash": observed["content_hash"]},
        {"name": "initialization_projection", "passed": shared_projection["ok"],
         "evidence": shared_projection},
        {"name": "occurrence_equivalence", "passed": not missing and not unexpected,
         "matched": sum((expected_pairs & observed_pairs).values()), "missing": missing, "unexpected": unexpected},
        {"name": "route_projection", "passed": route_projection_ok},
        {"name": "route_identity", "passed": route_evidence["ok"], "evidence": route_evidence},
        {"name": "dispatcher_projection", "passed": projection_ok,
         "revision": current_revision, "config_hash": revision["config_hash"] if revision else None},
        {"name": "heartbeat_reconciliation", "passed": heartbeat_ok, "evidence": heartbeat},
        {"name": "registry_projection", "passed": manifest_hashes == observed_hashes},
        {"name": "integrity", "passed": bool(integrity["ok"]), "evidence": integrity},
        {"name": "audit_chain", "passed": bool(audit["valid"]), "evidence": audit},
        {"name": "backup_restore", "passed": bool(backup_verification["ok"]),
         "sha256": backup_verification.get("sha256"),
         "audit_tip": {"event_id": backup_verification.get("last_audit_event_id"),
                       "event_hash": backup_verification.get("last_audit_event_hash")}},
        {"name": "backup_provenance", "passed": backup_provenance["ok"],
         "evidence": backup_provenance},
        {"name": "backup_progress_binding", "passed": progress_backup_binding_ok,
         "evidence": persisted_progress},
        {"name": "progress_audit_binding", "passed": progress_audit_binding["valid"],
         "evidence": progress_audit_binding},
        {"name": "host_capability_coverage", "passed": False, "reason": "Q-003 fail-closed"},
        {"name": "non_execution", "passed": True, "before": before_counts, "after": after_counts},
    ]
    report_id = "readiness-" + sha256(_canonical({
        "plan_hash": accepted["content_hash"], "collection_id": collection_id,
        "source_hash": observed["content_hash"], "window_start": window_start, "window_end": window_end,
    })).hexdigest()[:24]
    report = model_for("readiness_report").seal({
        "schema_version": 1, "artifact_type": "readiness_report", "report_id": report_id,
        "plan_id": accepted["plan_id"], "plan_hash": accepted["content_hash"], "collection_id": collection_id,
        "generated_at": observed["observed_at"], "checks": checks, "blockers": sorted(set(blockers)),
        "unresolved_decisions": list(accepted["unresolved_decisions"]), "tested_occurrence_boundary": {
            "window_start": window_start, "window_end": window_end, "candidate": boundary,
            "existing_sources_authoritative": True, "cutover_authorized": False,
        }, "status": "blocked" if blockers else "ready",
    }).as_dict()
    wrote = _write_exact(readiness_path, _canonical(report))
    _maybe_crash("readiness", crash_after_step)
    return {
        "status": "blocked" if blockers else "completed", "mutation_count": int(wrote),
        "plan_id": accepted["plan_id"], "plan_hash": accepted["content_hash"], "collection_id": collection_id,
        "database_path": str(database), "readiness": report, "readiness_path": str(readiness_path),
        "semantic_changes": changes, "workflow_execution_count": 0, "claim_count": 0,
        "receipt_post_count": 0, "host_mutation_count": 0,
    }

"""Typed lifecycle artifacts, sanitized exports, and crash-safe explicit-path I/O."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import tempfile
from typing import Any, Callable, ClassVar, Mapping

from .lifecycle_contracts import (
    CONTRACT_VERSION,
    LifecycleContractError,
    canonical_json_bytes,
    seal_artifact,
    validate_artifact,
    validate_artifact_path,
)


class SchemaDisposition(StrEnum):
    CURRENT = "current"
    UPGRADE_SUPPORTED = "upgrade_supported"
    MIGRATION_REQUIRED = "migration_required"
    UNSUPPORTED_FUTURE = "unsupported_future"
    CORRUPT = "corrupt"


@dataclass(frozen=True)
class SchemaClassification:
    disposition: SchemaDisposition
    observed_version: object
    target_version: int = CONTRACT_VERSION
    migration_supported: bool = False


def classify_schema_version(
    value: Mapping[str, Any], *, supported_upgrade_versions: frozenset[int] = frozenset()
) -> SchemaClassification:
    """Classify schema evolution before attempting current-schema validation."""

    version = value.get("schema_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 0:
        return SchemaClassification(SchemaDisposition.CORRUPT, version)
    if version == CONTRACT_VERSION:
        return SchemaClassification(SchemaDisposition.CURRENT, version)
    if version > CONTRACT_VERSION:
        return SchemaClassification(SchemaDisposition.UNSUPPORTED_FUTURE, version)
    if version in supported_upgrade_versions:
        return SchemaClassification(
            SchemaDisposition.UPGRADE_SUPPORTED,
            version,
            migration_supported=True,
        )
    return SchemaClassification(
        SchemaDisposition.MIGRATION_REQUIRED,
        version,
        migration_supported=False,
    )


@dataclass(frozen=True)
class LifecycleArtifact:
    """An immutable typed view over one validated versioned lifecycle artifact."""

    artifact_type: ClassVar[str] = ""
    data: dict[str, Any]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "LifecycleArtifact":
        return cls(validate_artifact(cls.artifact_type, value))

    @classmethod
    def seal(cls, value: Mapping[str, Any]) -> "LifecycleArtifact":
        candidate = dict(value)
        candidate.setdefault("schema_version", CONTRACT_VERSION)
        candidate.setdefault("artifact_type", cls.artifact_type)
        return cls.from_mapping(seal_artifact(candidate))

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.data)

    @property
    def content_hash(self) -> str:
        return self.data["content_hash"]

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self.canonical_bytes())


def _artifact_model(name: str) -> type[LifecycleArtifact]:
    return type(
        "".join(part.title() for part in name.split("_")) + "Artifact",
        (LifecycleArtifact,),
        {"artifact_type": name},
    )


ARTIFACT_MODELS: dict[str, type[LifecycleArtifact]] = {
    name: _artifact_model(name)
    for name in (
        "discovery_snapshot",
        "lifecycle_plan",
        "collection_manifest",
        "progress_record",
        "readiness_report",
        "semantic_drift_report",
        "host_capability_snapshot",
        "host_mutation_request",
        "host_mutation_result",
        "approval_envelope",
        "lifecycle_command",
        "command_result",
    )
}

DiscoverySnapshotArtifact = ARTIFACT_MODELS["discovery_snapshot"]
LifecyclePlanArtifact = ARTIFACT_MODELS["lifecycle_plan"]
CollectionManifestArtifact = ARTIFACT_MODELS["collection_manifest"]
ProgressRecordArtifact = ARTIFACT_MODELS["progress_record"]
ReadinessReportArtifact = ARTIFACT_MODELS["readiness_report"]
SemanticDriftReportArtifact = ARTIFACT_MODELS["semantic_drift_report"]
HostMutationRequestArtifact = ARTIFACT_MODELS["host_mutation_request"]
HostMutationResultArtifact = ARTIFACT_MODELS["host_mutation_result"]


def model_for(artifact_type: str) -> type[LifecycleArtifact]:
    try:
        return ARTIFACT_MODELS[artifact_type]
    except KeyError as exc:
        raise LifecycleContractError(
            "unsupported_artifact_type",
            f"unsupported lifecycle artifact type: {artifact_type}",
            artifact_type=artifact_type,
        ) from exc


def _validated_path(
    path: str | Path,
    *,
    storage_owner: str,
    explicit_root: str | Path | None,
    source_root: str | Path | None,
    installed_roots: tuple[str | Path, ...],
) -> Path:
    resolved = validate_artifact_path(
        path,
        storage_owner=storage_owner,
        explicit_root=explicit_root,
        source_root=source_root,
        installed_roots=installed_roots,
    )
    parent = resolved.parent
    if not parent.is_dir():
        raise LifecycleContractError(
            "artifact_parent_missing",
            "artifact parent must already exist",
            parent=str(parent),
        )
    if hasattr(os, "getuid") and parent.stat().st_uid != os.getuid():
        raise LifecycleContractError(
            "artifact_parent_unowned",
            "artifact parent must be owned by the current user",
            parent=str(parent),
        )
    return resolved


def load_artifact(
    path: str | Path,
    artifact_type: str,
    *,
    storage_owner: str = "external_state",
    explicit_root: str | Path | None = None,
    source_root: str | Path | None = None,
    installed_roots: tuple[str | Path, ...] = (),
) -> LifecycleArtifact:
    resolved = _validated_path(
        path,
        storage_owner=storage_owner,
        explicit_root=explicit_root,
        source_root=source_root,
        installed_roots=installed_roots,
    )
    if not resolved.is_file():
        raise LifecycleContractError(
            "artifact_not_found", "lifecycle artifact does not exist", path=str(resolved)
        )
    try:
        decoded = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LifecycleContractError(
            "corrupt_artifact", "lifecycle artifact is not valid UTF-8 JSON", path=str(resolved)
        ) from exc
    if not isinstance(decoded, Mapping):
        raise LifecycleContractError(
            "corrupt_artifact", "lifecycle artifact root must be an object", path=str(resolved)
        )
    classification = classify_schema_version(decoded)
    if classification.disposition is not SchemaDisposition.CURRENT:
        raise LifecycleContractError(
            classification.disposition.value,
            f"artifact schema is {classification.disposition.value}",
            observed_version=classification.observed_version,
            target_version=classification.target_version,
            migration_supported=classification.migration_supported,
        )
    return model_for(artifact_type).from_mapping(decoded)


def atomic_write_artifact(
    path: str | Path,
    artifact: LifecycleArtifact | Mapping[str, Any],
    *,
    artifact_type: str | None = None,
    storage_owner: str = "external_state",
    explicit_root: str | Path | None = None,
    source_root: str | Path | None = None,
    installed_roots: tuple[str | Path, ...] = (),
    expected_content_hash: str | None = None,
    before_replace: Callable[[Path], None] | None = None,
    after_replace: Callable[[Path], None] | None = None,
) -> Path:
    """Atomically persist one artifact with optimistic concurrency and mode 0600."""

    if isinstance(artifact, LifecycleArtifact):
        validated = artifact
    else:
        kind = artifact_type or str(artifact.get("artifact_type", ""))
        validated = model_for(kind).from_mapping(artifact)
    resolved = _validated_path(
        path,
        storage_owner=storage_owner,
        explicit_root=explicit_root,
        source_root=source_root,
        installed_roots=installed_roots,
    )
    if resolved.exists():
        if resolved.is_symlink():
            raise LifecycleContractError(
                "symlink_artifact_path", "artifact destination cannot be a symlink"
            )
        if expected_content_hash is not None:
            current_type = artifact_type or validated.artifact_type
            current = load_artifact(
                resolved,
                current_type,
                storage_owner=storage_owner,
                source_root=source_root,
                installed_roots=installed_roots,
            )
            if current.content_hash != expected_content_hash:
                raise LifecycleContractError(
                    "optimistic_concurrency_conflict",
                    "artifact changed since it was read",
                    expected=expected_content_hash,
                    observed=current.content_hash,
                )
    elif expected_content_hash is not None:
        raise LifecycleContractError(
            "optimistic_concurrency_conflict",
            "expected artifact no longer exists",
            expected=expected_content_hash,
            observed=None,
        )

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{resolved.name}.", suffix=".tmp", dir=resolved.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(validated.canonical_bytes())
            stream.flush()
            os.fsync(stream.fileno())
        if before_replace is not None:
            before_replace(temporary)
        os.replace(temporary, resolved)
        os.chmod(resolved, 0o600)
        directory = os.open(resolved.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        if after_replace is not None:
            after_replace(resolved)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        finally:
            raise
    return resolved


_EXPORT_ALLOWLISTS = {
    "readiness_report": frozenset(
        {
            "schema_version",
            "artifact_type",
            "report_id",
            "plan_id",
            "plan_hash",
            "collection_id",
            "generated_at",
            "checks",
            "blockers",
            "unresolved_decisions",
            "tested_occurrence_boundary",
            "status",
        }
    ),
    "semantic_drift_report": frozenset(
        {
            "schema_version",
            "artifact_type",
            "report_id",
            "plan_id",
            "plan_hash",
            "expected_source_hash",
            "observed_source_hash",
            "changes",
            "status",
            "generated_at",
        }
    ),
}
_EXPORT_OMIT_KEYS = {
    "command",
    "credential",
    "evidence",
    "password",
    "procedure",
    "prompt",
    "runtime_evidence",
    "script",
    "secret",
    "signed_url",
    "token",
    "transcript",
}


def _sanitize_export_value(value: Any, *, key: str = "") -> Any:
    normalized = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
    if any(part in _EXPORT_OMIT_KEYS for part in normalized.split("_")):
        return "[redacted]"
    if isinstance(value, Mapping):
        return {
            str(child_key): _sanitize_export_value(child, key=str(child_key))
            for child_key, child in sorted(value.items(), key=lambda item: str(item[0]))
            if not any(
                part in _EXPORT_OMIT_KEYS
                for part in re.sub(
                    r"[^a-z0-9]+", "_", str(child_key).lower()
                ).strip("_").split("_")
            )
        }
    if isinstance(value, list):
        return [_sanitize_export_value(item, key=key) for item in value]
    if isinstance(value, str):
        if _is_local_absolute_path(value):
            return f"[local-path:{sha256(value.encode('utf-8')).hexdigest()[:12]}]"
    return value


def _is_local_absolute_path(value: str) -> bool:
    """Recognize POSIX, Windows drive/UNC, and home-relative local paths on any host."""

    home_relative = re.match(r"^~(?:[^/\\]+)?(?:[/\\]|$)", value) is not None
    return (
        home_relative
        or PurePosixPath(value).is_absolute()
        or PureWindowsPath(value).is_absolute()
    )


def sanitized_export(artifact: LifecycleArtifact | Mapping[str, Any]) -> LifecycleArtifact:
    """Return the documented allowlisted export for optional report artifact types."""

    value = artifact.data if isinstance(artifact, LifecycleArtifact) else dict(artifact)
    kind = str(value.get("artifact_type", ""))
    try:
        allowlist = _EXPORT_ALLOWLISTS[kind]
    except KeyError as exc:
        raise LifecycleContractError(
            "artifact_not_exportable",
            f"{kind or 'unknown artifact'} has no sanitized export contract",
        ) from exc
    validate_artifact(kind, value)
    exported = {
        key: _sanitize_export_value(value[key], key=key)
        for key in sorted(allowlist)
        if key in value
    }
    return model_for(kind).from_mapping(seal_artifact(exported))

"""Versioned, fail-closed contracts for the guided lifecycle foundation."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from hashlib import sha256
from importlib import resources
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping, Sequence


CONTRACT_VERSION = 1
LIFECYCLE_STAGES = (
    "discover",
    "propose",
    "initialize",
    "shadow_validate",
    "cut_over",
    "operate_evolve",
)
LEGAL_TRANSITIONS = {
    "discover": frozenset({"propose"}),
    "propose": frozenset({"discover", "initialize"}),
    "initialize": frozenset({"propose", "shadow_validate"}),
    "shadow_validate": frozenset({"initialize", "cut_over"}),
    "cut_over": frozenset({"shadow_validate", "operate_evolve"}),
    "operate_evolve": frozenset({"discover"}),
}
LIFECYCLE_COMMANDS = (
    "plan",
    "explain",
    "apply",
    "status",
    "verify",
    "record-cutover",
    "heartbeat-template",
)
HOST_ADAPTER_OPERATIONS = (
    "tasks.list",
    "tasks.read",
    "automations.list",
    "automations.read",
    "tasks.ensure_stable",
    "automations.create_or_update_heartbeat",
    "automations.disable_legacy",
    "messages.post_receipt",
    "messages.acknowledge_receipt",
    "host.read_back",
)
_SENSITIVE_KEYS = {
    "authorization",
    "bearer",
    "cookie",
    "credential",
    "credentials",
    "passphrase",
    "password",
    "prompt",
    "raw_prompt",
    "secret",
    "signed_url",
    "token",
    "transcript",
}
_SENSITIVE_COMPOUNDS = {
    "access_key",
    "api_key",
    "private_key",
    "secret_key",
    "session_cookie",
    "signed_url",
}
_SAFE_SENSITIVE_SUFFIXES = {"hash", "id", "ids", "identifier", "identifiers"}


class LifecycleContractError(ValueError):
    """A deterministic lifecycle contract failure."""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.details = details


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    """Return the v1 canonical byte representation."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def content_hash(value: Mapping[str, Any]) -> str:
    """Hash an artifact without allowing its hash field to hash itself."""

    material = dict(value)
    material.pop("content_hash", None)
    return sha256(canonical_json_bytes(material)).hexdigest()


def seal_artifact(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy carrying its canonical content hash."""

    sealed = deepcopy(dict(value))
    sealed["content_hash"] = content_hash(sealed)
    return sealed


def contract_catalog() -> dict[str, Any]:
    """Load the packaged v1 contract catalog."""

    resource = resources.files("automation_dispatcher.contracts.v1").joinpath("catalog.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def contract_schema(artifact_type: str) -> dict[str, Any]:
    """Return one artifact's machine-readable JSON Schema definition."""

    resource = resources.files("automation_dispatcher.contracts.v1").joinpath(
        "contracts.schema.json"
    )
    bundle = json.loads(resource.read_text(encoding="utf-8"))
    try:
        return bundle["$defs"][artifact_type]
    except KeyError as exc:
        raise LifecycleContractError(
            "unsupported_artifact_type",
            f"unsupported lifecycle artifact type: {artifact_type}",
            artifact_type=artifact_type,
        ) from exc


def _matches_type(value: Any, expected: str) -> bool:
    return {
        "array": isinstance(value, list),
        "boolean": isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "null": value is None,
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "object": isinstance(value, Mapping),
        "string": isinstance(value, str),
    }[expected]


def _validate_schema(value: Any, schema: Mapping[str, Any], path: str = "$") -> None:
    expected_type = schema.get("type")
    if expected_type is not None:
        choices = [expected_type] if isinstance(expected_type, str) else expected_type
        if not any(_matches_type(value, choice) for choice in choices):
            raise LifecycleContractError(
                "schema_type_mismatch",
                f"{path} has an invalid type",
                path=path,
                expected=choices,
            )
    if "const" in schema and value != schema["const"]:
        raise LifecycleContractError(
            "schema_const_mismatch", f"{path} must equal {schema['const']!r}", path=path
        )
    if "enum" in schema and value not in schema["enum"]:
        raise LifecycleContractError(
            "schema_enum_mismatch", f"{path} is not an allowed value", path=path
        )
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise LifecycleContractError(
                "schema_string_too_short", f"{path} is too short", path=path
            )
        if "pattern" in schema and re.fullmatch(schema["pattern"], value) is None:
            raise LifecycleContractError(
                "schema_pattern_mismatch", f"{path} has an invalid format", path=path
            )
        if schema.get("format") == "date-time":
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise LifecycleContractError(
                    "schema_datetime_invalid", f"{path} is not an ISO-8601 date-time", path=path
                ) from exc
            if parsed.tzinfo is None:
                raise LifecycleContractError(
                    "schema_datetime_unzoned", f"{path} must include a timezone", path=path
                )
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            raise LifecycleContractError(
                "schema_array_too_short", f"{path} has too few items", path=path
            )
        if schema.get("uniqueItems"):
            encoded = [canonical_json_bytes({"value": item}) for item in value]
            if len(encoded) != len(set(encoded)):
                raise LifecycleContractError(
                    "schema_array_not_unique", f"{path} contains duplicate items", path=path
                )
        if "items" in schema:
            for index, item in enumerate(value):
                _validate_schema(item, schema["items"], f"{path}[{index}]")
    if isinstance(value, Mapping):
        required = schema.get("required", ())
        missing = sorted(set(required) - set(value))
        if missing:
            raise LifecycleContractError(
                "schema_required_missing",
                f"{path} is missing required fields: {', '.join(missing)}",
                path=path,
                missing=missing,
            )
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(value) - set(properties))
            if unknown:
                raise LifecycleContractError(
                    "schema_unknown_fields",
                    f"{path} contains unknown fields: {', '.join(unknown)}",
                    path=path,
                    unknown=unknown,
                )
        for key, child_schema in properties.items():
            if key in value:
                _validate_schema(value[key], child_schema, f"{path}.{key}")


def _reject_sensitive_material(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            rendered = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(key))
            words = tuple(
                word for word in re.split(r"[^a-z0-9]+", rendered.lower()) if word
            )
            compact = "".join(words)
            normalized = "_".join(words)
            carries_sensitive_name = (
                any(word in _SENSITIVE_KEYS for word in words)
                or any(compound in normalized for compound in _SENSITIVE_COMPOUNDS)
                or any(
                    compact.startswith(sensitive) or compact.endswith(sensitive)
                    for sensitive in _SENSITIVE_KEYS
                )
            )
            is_stable_reference = bool(words) and words[-1] in _SAFE_SENSITIVE_SUFFIXES
            if carries_sensitive_name and not is_stable_reference:
                raise LifecycleContractError(
                    "sensitive_material_forbidden",
                    f"{path}.{key} is forbidden in lifecycle artifacts",
                    path=f"{path}.{key}",
                )
            _reject_sensitive_material(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_sensitive_material(child, f"{path}[{index}]")


def validate_artifact(artifact_type: str, value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate schema, sanitization, and canonical hash without mutating input."""

    if value.get("schema_version") != CONTRACT_VERSION:
        raise LifecycleContractError(
            "unsupported_schema_version",
            f"schema_version must be {CONTRACT_VERSION}",
            observed=value.get("schema_version"),
        )
    if value.get("artifact_type") != artifact_type:
        raise LifecycleContractError(
            "artifact_type_mismatch",
            f"artifact_type must be {artifact_type}",
            observed=value.get("artifact_type"),
        )
    _validate_schema(value, contract_schema(artifact_type))
    _reject_sensitive_material(value)
    observed_hash = value.get("content_hash")
    expected_hash = content_hash(value)
    if observed_hash != expected_hash:
        raise LifecycleContractError(
            "content_hash_mismatch",
            "artifact content_hash does not match canonical content",
            expected=expected_hash,
            observed=observed_hash,
        )
    return deepcopy(dict(value))


def validate_transition(current: str, target: str) -> None:
    """Reject lifecycle skips and unrecognized stages."""

    if current not in LEGAL_TRANSITIONS or target not in LIFECYCLE_STAGES:
        raise LifecycleContractError(
            "unsupported_lifecycle_stage", f"unsupported lifecycle transition: {current} -> {target}"
        )
    if target not in LEGAL_TRANSITIONS[current]:
        raise LifecycleContractError(
            "illegal_lifecycle_transition", f"illegal lifecycle transition: {current} -> {target}"
        )


def assert_plan_current(
    plan: Mapping[str, Any],
    *,
    expected_plan_id: str,
    expected_plan_hash: str,
    observed_snapshot_hash: str,
) -> None:
    """Fence stale or substituted plans before any staged operation."""

    validate_artifact("lifecycle_plan", plan)
    if plan["plan_id"] != expected_plan_id:
        raise LifecycleContractError("plan_id_mismatch", "plan identity does not match approval")
    if plan["content_hash"] != expected_plan_hash:
        raise LifecycleContractError("stale_plan", "plan hash does not match approval")
    if plan["source_snapshot_hash"] != observed_snapshot_hash:
        raise LifecycleContractError(
            "source_snapshot_drift", "source snapshot changed after the plan was created"
        )


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def validate_artifact_path(
    path: str | Path,
    *,
    storage_owner: str,
    explicit_root: str | Path | None = None,
    source_root: str | Path | None = None,
    installed_roots: Sequence[str | Path] = (),
) -> Path:
    """Resolve one path and enforce the v1 storage-owner and symlink policy."""

    raw = Path(path).expanduser()
    if not raw.is_absolute():
        if explicit_root is None:
            raise LifecycleContractError(
                "relative_path_without_root", "relative artifact paths require an explicit root"
            )
        raw = Path(explicit_root).expanduser() / raw
    resolved = raw.resolve(strict=False)
    broad_roots = {Path("/"), Path.home().resolve()}
    if resolved in broad_roots:
        raise LifecycleContractError("forbidden_artifact_path", "broad roots cannot own artifacts")
    forbidden = [Path(item).expanduser().resolve(strict=False) for item in installed_roots]
    if source_root is not None:
        forbidden.append(Path(source_root).expanduser().resolve(strict=False))
    if any(_within(resolved, root) for root in forbidden):
        raise LifecycleContractError(
            "forbidden_artifact_path", "artifact path is inside a source or installed root"
        )
    for candidate in (raw, *raw.parents):
        if candidate.exists() and candidate.is_symlink():
            raise LifecycleContractError(
                "symlink_artifact_path", "artifact paths cannot traverse a symlink"
            )
    if storage_owner == "source_controlled" and ".automation-dispatcher" in resolved.parts:
        raise LifecycleContractError(
            "forbidden_artifact_path", "source-controlled artifacts cannot live in runtime state"
        )
    if storage_owner == "external_state" and source_root is None and not installed_roots:
        raise LifecycleContractError(
            "unbounded_external_state", "external state requires explicit forbidden roots"
        )
    return resolved


def resolve_manifest_locator(
    *,
    explicit_paths: Sequence[str | Path] = (),
    heartbeat_paths: Sequence[str | Path] = (),
    registry_paths: Sequence[str | Path] = (),
    repository_root: str | Path | None = None,
) -> Path:
    """Resolve one manifest by fixed precedence without cwd or home guessing."""

    for source, candidates in (
        ("explicit", explicit_paths),
        ("heartbeat", heartbeat_paths),
        ("registry", registry_paths),
    ):
        normalized = []
        for candidate in candidates:
            value = Path(candidate).expanduser()
            if not value.is_absolute():
                if repository_root is None:
                    raise LifecycleContractError(
                        "relative_manifest_without_repository",
                        f"{source} manifest path requires an explicit repository root",
                    )
                value = Path(repository_root).expanduser() / value
            normalized.append(value.resolve(strict=False))
        unique = sorted(set(normalized), key=str)
        if len(unique) > 1:
            raise LifecycleContractError(
                "ambiguous_manifest", f"multiple {source} manifests matched", candidates=list(map(str, unique))
            )
        if unique:
            return unique[0]
    raise LifecycleContractError(
        "manifest_not_found",
        "no explicit, heartbeat-bound, or registry-bound manifest was supplied",
    )


def _parse_utc(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LifecycleContractError("invalid_timestamp", f"{field} is invalid") from exc
    if parsed.tzinfo is None:
        raise LifecycleContractError("invalid_timestamp", f"{field} must include a timezone")
    return parsed.astimezone(UTC)


def authorize_host_mutation(
    request: Mapping[str, Any],
    approval: Mapping[str, Any],
    *,
    observed_host_state_hash: str,
    observed_host_revision: str | None,
    now: str,
) -> None:
    """Bind one live host operation to an exact, unexpired approval envelope."""

    validate_artifact("host_mutation_request", request)
    validate_artifact("approval_envelope", approval)
    request_hash = request["content_hash"]
    checks = {
        "approval_id": request["approval_id"] == approval["approval_id"],
        "plan_id": request["plan_id"] == approval["plan_id"],
        "plan_hash": request["plan_hash"] == approval["plan_hash"],
        "collection_id": request["collection_id"] == approval["collection_id"],
        "expected_host_state_hash": observed_host_state_hash
        == approval["expected_host_state_hash"],
        "mutation_hash": request_hash in approval["mutation_hashes"],
    }
    failed = sorted(key for key, valid in checks.items() if not valid)
    if failed:
        raise LifecycleContractError(
            "approval_mismatch", "host mutation is outside the approval envelope", failed=failed
        )
    instant = _parse_utc(now, "now")
    if instant < _parse_utc(approval["approved_at"], "approved_at") or instant >= _parse_utc(
        approval["expires_at"], "expires_at"
    ):
        raise LifecycleContractError("approval_expired", "host mutation approval is not active")
    if request["target"]["expected_state_hash"] != observed_host_state_hash:
        raise LifecycleContractError(
            "host_state_drift", "observed host state differs from the approved request"
        )
    expected_revision = request["target"]["expected_revision"]
    action = request["mutation"]["action"]
    if action == "create":
        if expected_revision is not None:
            raise LifecycleContractError(
                "create_revision_invalid",
                "create operations must approve an absent target revision",
            )
        if observed_host_revision is not None:
            raise LifecycleContractError(
                "host_target_exists",
                "create operation target appeared after approval",
            )
    else:
        if expected_revision is None:
            raise LifecycleContractError(
                "expected_host_revision_missing",
                "non-create operations require an approved target revision",
            )
        if observed_host_revision != expected_revision:
            raise LifecycleContractError(
                "host_revision_drift",
                "observed host revision differs from the approved request",
                expected=expected_revision,
                observed=observed_host_revision,
            )


def require_host_capabilities(
    snapshot: Mapping[str, Any], required_operations: Sequence[str]
) -> None:
    """Fail closed unless every required host-adapter operation is callable."""

    validated = validate_artifact("host_capability_snapshot", snapshot)
    declared = {item["name"]: item for item in validated["capabilities"]}
    unknown = sorted(set(required_operations) - set(HOST_ADAPTER_OPERATIONS))
    if unknown:
        raise LifecycleContractError(
            "unsupported_host_operation",
            "the requested host operation is outside the v1 adapter contract",
            operations=unknown,
        )
    missing = sorted(name for name in required_operations if name not in declared)
    unsupported = sorted(
        name
        for name in required_operations
        if name in declared
        and (not declared[name]["supported"] or not declared[name]["surface"])
    )
    if missing or unsupported:
        raise LifecycleContractError(
            "host_capability_unavailable",
            "required host-adapter capabilities are not callable",
            missing=missing,
            unsupported=unsupported,
        )


def validate_host_result(
    result: Mapping[str, Any], *, request_hash: str
) -> dict[str, Any]:
    """Require complete observed host evidence and fence ambiguous effects."""

    validated = validate_artifact("host_mutation_result", result)
    if validated["request_hash"] != request_hash:
        raise LifecycleContractError("request_hash_mismatch", "host result belongs to another request")
    if validated["status"] in {"completed", "no_op"} and validated["observed_after"] is None:
        raise LifecycleContractError(
            "incomplete_host_result", "successful host results require observed after-state"
        )
    if validated["status"] == "effect_unknown":
        raise LifecycleContractError(
            "host_effect_unknown", "ambiguous host effects require reconciliation before retry"
        )
    return validated


def configured_forbidden_roots() -> tuple[Path, ...]:
    """Return explicit forbidden roots without treating the home directory as state authority."""

    value = os.environ.get("AUTOMATION_DISPATCHER_FORBIDDEN_ROOTS", "")
    return tuple(Path(item).expanduser().resolve(strict=False) for item in value.split(os.pathsep) if item)


__all__ = [
    "CONTRACT_VERSION",
    "HOST_ADAPTER_OPERATIONS",
    "LEGAL_TRANSITIONS",
    "LIFECYCLE_COMMANDS",
    "LIFECYCLE_STAGES",
    "LifecycleContractError",
    "assert_plan_current",
    "authorize_host_mutation",
    "canonical_json_bytes",
    "configured_forbidden_roots",
    "content_hash",
    "contract_catalog",
    "contract_schema",
    "resolve_manifest_locator",
    "require_host_capabilities",
    "seal_artifact",
    "validate_artifact",
    "validate_artifact_path",
    "validate_host_result",
    "validate_transition",
]

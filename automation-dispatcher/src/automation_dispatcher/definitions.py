"""Workflow definition loading, validation, and canonicalization.

The module deliberately uses only the Python standard library.  Definitions
are JSON at the source boundary and are normalized into one stable shape
before they are hashed or persisted.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping


WORKFLOW_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TIME_RE = re.compile(r"^(?P<hour>[01]\d|2[0-3]):(?P<minute>[0-5]\d)(?::(?P<second>[0-5]\d))?$")
WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
WEEKDAY_ALIASES = {
    **{name: name for name in WEEKDAYS},
    **{name[:3]: name for name in WEEKDAYS},
}
PROCEDURE_KINDS = {
    "script",
    "bundled_script",
    "skill",
    "installed_skill",
    "documented",
    "documented_agent_procedure",
}
EXTERNAL_EFFECT_MODES = {"none", "idempotency_key", "reconciliation"}
CATCH_UP_POLICIES = {"none", "latest", "bounded", "all"}


class DefinitionError(ValueError):
    """A workflow definition cannot be normalized safely."""


def normalize_dispatcher_id(value: Any) -> str:
    """Return an arbitrary stable dispatcher slug using the workflow ID grammar."""

    if not isinstance(value, str):
        raise DefinitionError(
            "dispatcher_id must contain lowercase letters, numbers, and hyphens"
        )
    dispatcher_id = value.strip()
    if not WORKFLOW_ID_RE.fullmatch(dispatcher_id):
        raise DefinitionError(
            "dispatcher_id must contain lowercase letters, numbers, and hyphens"
        )
    return dispatcher_id


def _first(mapping: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in mapping:
            return mapping[name]
    return default


def _required(mapping: Mapping[str, Any], *names: str) -> Any:
    value = _first(mapping, *names)
    if value is None:
        raise DefinitionError(f"missing required field: {names[0]}")
    return value


def _positive_int(value: Any, field: str, *, allow_zero: bool = False) -> int:
    if isinstance(value, bool):
        raise DefinitionError(f"{field} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise DefinitionError(f"{field} must be an integer") from exc
    minimum = 0 if allow_zero else 1
    if result < minimum:
        qualifier = "non-negative" if allow_zero else "positive"
        raise DefinitionError(f"{field} must be {qualifier}")
    return result


def _duration(value: Any, field: str, *, allow_zero: bool = False) -> int:
    """Normalize a duration to integer seconds.

    JSON definitions normally use seconds.  Compact human forms (``15m``)
    and the common ISO-8601 ``PT#H#M#S`` subset are accepted at the boundary
    but never retained in canonical JSON.
    """

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and not value.is_integer():
            raise DefinitionError(f"{field} must resolve to whole seconds")
        return _positive_int(int(value), field, allow_zero=allow_zero)
    if not isinstance(value, str):
        raise DefinitionError(f"{field} must be a duration in seconds")
    text = value.strip().upper()
    compact = re.fullmatch(r"(\d+)\s*([SMHD])", text)
    if compact:
        factors = {"S": 1, "M": 60, "H": 3600, "D": 86400}
        return _positive_int(
            int(compact.group(1)) * factors[compact.group(2)],
            field,
            allow_zero=allow_zero,
        )
    iso = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", text)
    if iso and any(group is not None for group in iso.groups()):
        seconds = int(iso.group(1) or 0) * 3600 + int(iso.group(2) or 0) * 60 + int(iso.group(3) or 0)
        return _positive_int(seconds, field, allow_zero=allow_zero)
    if text.isdigit():
        return _positive_int(int(text), field, allow_zero=allow_zero)
    raise DefinitionError(f"{field} is not a supported duration")


def _normalize_time(value: Any) -> str:
    if not isinstance(value, str):
        raise DefinitionError("due_rule.time must be HH:MM[:SS]")
    match = TIME_RE.fullmatch(value.strip())
    if not match:
        raise DefinitionError("due_rule.time must be HH:MM[:SS]")
    return f"{match.group('hour')}:{match.group('minute')}:{match.group('second') or '00'}"


def normalize_due_rule(value: Any) -> dict[str, Any]:
    """Normalize the legacy version-1 daily/weekly grammar for compatibility tools."""

    if not isinstance(value, Mapping):
        raise DefinitionError("due_rule must be an object")
    raw_version = _first(value, "version", "grammar_version", default=1)
    if isinstance(raw_version, str) and raw_version.strip().lower().startswith("v"):
        raw_version = raw_version.strip()[1:]
    version = _positive_int(raw_version, "due_rule.version")
    if version != 1:
        raise DefinitionError("due_rule.version must be 1")
    frequency = str(_required(value, "frequency", "kind", "type")).strip().lower()
    if frequency not in {"daily", "weekly"}:
        raise DefinitionError("due_rule.frequency must be daily or weekly")
    result: dict[str, Any] = {
        "version": 1,
        "frequency": frequency,
        "time": _normalize_time(_required(value, "time", "local_time")),
    }
    supplied_weekdays = _first(value, "weekdays", "days", "weekday")
    if frequency == "daily":
        if supplied_weekdays not in (None, [], ()):
            raise DefinitionError("daily due rules must not specify weekdays")
        result["weekdays"] = []
        return result
    if isinstance(supplied_weekdays, (str, int)):
        supplied_weekdays = [supplied_weekdays]
    if not isinstance(supplied_weekdays, (list, tuple)) or not supplied_weekdays:
        raise DefinitionError("weekly due rules require one or more weekdays")
    days: set[str] = set()
    for item in supplied_weekdays:
        if isinstance(item, bool):
            raise DefinitionError("weekly weekday values are invalid")
        if isinstance(item, int):
            if item < 0 or item > 6:
                raise DefinitionError("integer weekdays must be between 0 and 6")
            day = WEEKDAYS[item]
        else:
            day = WEEKDAY_ALIASES.get(str(item).strip().lower())
            if day is None:
                raise DefinitionError(f"unknown weekday: {item}")
        days.add(day)
    result["weekdays"] = [day for day in WEEKDAYS if day in days]
    return result


def _canonical_reference(value: Any, field: str) -> str:
    if isinstance(value, Mapping):
        value = _first(value, "reference", "ref", "path", "uri")
    if not isinstance(value, str) or not value.strip():
        raise DefinitionError(f"{field} must be a non-empty reference")
    reference = value.strip()
    if "\x00" in reference:
        raise DefinitionError(f"{field} contains a NUL byte")
    return reference


def _normalize_external_effect(value: Any, procedure: Mapping[str, Any]) -> dict[str, Any]:
    if value in (None, False):
        return {"mode": "none"}
    if value is True:
        value = {"mode": "idempotency_key", "idempotency_key": "occurrence"}
    if isinstance(value, str):
        value = {"mode": value}
    if not isinstance(value, Mapping):
        raise DefinitionError("procedure.external_effect must be an object")
    mode = str(_first(value, "mode", "strategy", default="none")).strip().lower().replace("-", "_")
    if mode in {"idempotent", "idempotency"}:
        mode = "idempotency_key"
    if mode in {"reconcile", "reconciled"}:
        mode = "reconciliation"
    if mode not in EXTERNAL_EFFECT_MODES:
        raise DefinitionError("procedure.external_effect.mode is invalid")
    result: dict[str, Any] = {"mode": mode}
    if mode == "idempotency_key":
        key = _first(value, "idempotency_key", "key", default="occurrence")
        if key not in {"occurrence", "occurrence_id", "scheduled_occurrence"}:
            raise DefinitionError("external effects must use the stable occurrence idempotency key")
        result["idempotency_key"] = "occurrence"
    elif mode == "reconciliation":
        reference = _first(
            value,
            "reconciliation_reference",
            "reconciliation_ref",
            "reference",
            default=_first(procedure, "reconciliation_reference", "reconciliation_ref"),
        )
        result["reconciliation_reference"] = _canonical_reference(
            reference, "procedure.external_effect.reconciliation_reference"
        )
    return result


def _normalize_procedure(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise DefinitionError("procedure must be an object")
    kind = str(_required(value, "kind", "type")).strip().lower().replace("-", "_")
    if kind not in PROCEDURE_KINDS:
        raise DefinitionError(f"unsupported procedure kind: {kind}")
    aliases = {
        "bundled_script": "script",
        "installed_skill": "skill",
        "documented_agent_procedure": "documented",
    }
    kind = aliases.get(kind, kind)
    reference = _canonical_reference(_required(value, "reference", "ref", "path"), "procedure.reference")
    result = {"kind": kind, "reference": reference}
    result["external_effect"] = _normalize_external_effect(
        _first(value, "external_effect", "effects"), value
    )
    return result


def _normalize_reporting(value: Any, obj: Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(value, str):
        value = {"task_id": value}
    if value is None:
        task = _first(obj, "reporting_task", "reporting_task_id")
        value = {"task_id": task}
    if not isinstance(value, Mapping):
        raise DefinitionError("reporting must be an object")
    task_id = _required(value, "task_id", "task", "destination_task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        raise DefinitionError("reporting.task_id must be a non-empty string")
    fields = _first(value, "receipt_fields", default=[])
    if fields is None:
        fields = []
    if not isinstance(fields, (list, tuple)) or any(not isinstance(item, str) or not item.strip() for item in fields):
        raise DefinitionError("reporting.receipt_fields must be a list of names")
    return {"task_id": task_id.strip(), "receipt_fields": sorted(set(item.strip() for item in fields))}


def _normalize_receipt(value: Any, reporting: Mapping[str, Any]) -> dict[str, Any]:
    if value is None:
        fields = reporting.get("receipt_fields", [])
        if not fields:
            raise DefinitionError("receipt template or required fields are required")
        return {"required_fields": list(fields)}
    if isinstance(value, str):
        if not value.strip():
            raise DefinitionError("receipt.template must not be empty")
        return {"template": value.strip()}
    if isinstance(value, (list, tuple)):
        value = {"required_fields": value}
    if not isinstance(value, Mapping):
        raise DefinitionError("receipt must be an object, template, or field list")
    template = _first(value, "template", "receipt_template")
    fields = _first(value, "required_fields", "fields", default=[])
    result: dict[str, Any] = {}
    if template is not None:
        if not isinstance(template, str) or not template.strip():
            raise DefinitionError("receipt.template must not be empty")
        result["template"] = template.strip()
    if fields:
        if not isinstance(fields, (list, tuple)) or any(not isinstance(item, str) or not item.strip() for item in fields):
            raise DefinitionError("receipt.required_fields must be a list of names")
        result["required_fields"] = sorted(set(item.strip() for item in fields))
    if not result:
        raise DefinitionError("receipt template or required fields are required")
    return result


def _normalize_retention(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = {"policy": value}
    if not isinstance(value, Mapping):
        raise DefinitionError("evidence_retention must be an object")
    policy = _required(value, "policy", "classification")
    if not isinstance(policy, str) or not policy.strip():
        raise DefinitionError("evidence_retention.policy must be a non-empty string")
    result: dict[str, Any] = {"policy": policy.strip().lower()}
    days = _first(value, "days", "retention_days")
    if days is not None:
        result["days"] = _positive_int(days, "evidence_retention.days", allow_zero=True)
    return result


def _normalize_catch_up(value: Any, obj: Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(value, str):
        value = {"policy": value}
    if not isinstance(value, Mapping):
        raise DefinitionError("catch_up must be an object")
    policy = str(_required(value, "policy", "mode")).strip().lower().replace("-", "_")
    if policy not in CATCH_UP_POLICIES:
        raise DefinitionError(f"unsupported catch_up.policy: {policy}")
    lookback = _first(value, "max_lookback_seconds", "max_lookback", "lookback")
    if lookback is None:
        lookback = _first(obj, "max_lookback_seconds", "max_lookback")
    if lookback is None:
        raise DefinitionError("catch_up.max_lookback_seconds is required")
    return {
        "policy": policy,
        "max_lookback_seconds": _duration(lookback, "catch_up.max_lookback_seconds", allow_zero=True),
    }


def _normalize_retry(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise DefinitionError("retry must be an object")
    return {
        "max_attempts": _positive_int(_required(value, "max_attempts", "attempts"), "retry.max_attempts"),
        "backoff_seconds": _duration(
            _first(value, "backoff_seconds", "backoff", default=0),
            "retry.backoff_seconds",
            allow_zero=True,
        ),
    }


def _canonical_payload(normalized: Mapping[str, Any]) -> bytes:
    payload = deepcopy(dict(normalized))
    payload.pop("content_hash", None)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def definition_hash(normalized: Mapping[str, Any]) -> str:
    """Return the SHA-256 of canonical JSON, excluding ``content_hash``."""

    if not isinstance(normalized, Mapping):
        raise TypeError("normalized definition must be a mapping")
    return sha256(_canonical_payload(normalized)).hexdigest()


def normalize_definition(obj: Mapping[str, Any], base_dir: str | Path | None = None) -> dict[str, Any]:
    """Return the canonical workflow definition, including its content hash.

    ``base_dir`` does not alter portable reference strings.  It is accepted so
    callers can use the same call signature for validation and normalization.
    """

    del base_dir  # reference existence and containment are validation concerns
    if not isinstance(obj, Mapping):
        raise DefinitionError("workflow definition must be a JSON object")
    workflow_id = str(_required(obj, "workflow_id", "id")).strip()
    if not WORKFLOW_ID_RE.fullmatch(workflow_id):
        raise DefinitionError("workflow_id must contain lowercase letters, numbers, and hyphens")
    name = _required(obj, "name")
    description = _required(obj, "description")
    if not isinstance(name, str) or not name.strip():
        raise DefinitionError("name must be a non-empty string")
    if not isinstance(description, str) or not description.strip():
        raise DefinitionError("description must be a non-empty string")
    raw_schema_version = _required(obj, "schema_version")
    schema_version = _positive_int(raw_schema_version, "schema_version")
    if schema_version != 2:
        raise DefinitionError(
            "schema_version must be 2; legacy version-1 definitions require explicit migration"
        )
    dispatcher_id = normalize_dispatcher_id(_required(obj, "dispatcher_id", "dispatcher"))
    enabled = _required(obj, "enabled")
    if not isinstance(enabled, bool):
        raise DefinitionError("enabled must be a boolean")
    workflow_schedule_fields = (
        "timezone",
        "time_zone",
        "due_rule",
        "due",
        "schedule",
        "max_lateness_seconds",
        "maximum_lateness",
        "max_lateness",
        "catch_up",
        "catchup",
        "max_lookback_seconds",
        "max_lookback",
    )
    supplied_schedule_fields = [field for field in workflow_schedule_fields if field in obj]
    if supplied_schedule_fields:
        raise DefinitionError(
            "schema-version-2 workflows inherit dispatcher scheduling and must not specify: "
            + ", ".join(supplied_schedule_fields)
        )
    reporting = _normalize_reporting(_first(obj, "reporting"), obj)
    authorities = _required(obj, "authority_refs", "allowed_authority_refs", "authorities")
    if not isinstance(authorities, (list, tuple)) or not authorities:
        raise DefinitionError("authority_refs must be a non-empty list")
    authority_refs = sorted(set(_canonical_reference(item, "authority_refs") for item in authorities))

    normalized: dict[str, Any] = {
        "schema_version": schema_version,
        "workflow_id": workflow_id,
        "name": name.strip(),
        "description": description.strip(),
        "dispatcher_id": dispatcher_id,
        "enabled": enabled,
        "retry": _normalize_retry(_required(obj, "retry", "retry_policy")),
        "claim_lease_seconds": _duration(
            _required(obj, "claim_lease_seconds", "claim_lease_duration", "claim_lease"),
            "claim_lease_seconds",
        ),
        "procedure": _normalize_procedure(_required(obj, "procedure")),
        "authority_refs": authority_refs,
        "reporting": reporting,
        "receipt": _normalize_receipt(_first(obj, "receipt", "receipt_template", "required_receipt_fields"), reporting),
        "data_sensitivity": str(_required(obj, "data_sensitivity", "sensitivity")).strip().lower(),
        "evidence_retention": _normalize_retention(_required(obj, "evidence_retention", "retention")),
        "revision": _positive_int(_required(obj, "revision", "definition_revision"), "revision"),
    }
    if not normalized["data_sensitivity"]:
        raise DefinitionError("data_sensitivity must be a non-empty classification")
    expected_hash = definition_hash(normalized)
    supplied_hash = obj.get("content_hash")
    if supplied_hash is not None and (not isinstance(supplied_hash, str) or supplied_hash.lower() != expected_hash):
        raise DefinitionError("content_hash does not match canonical definition")
    normalized["content_hash"] = expected_hash
    return normalized


def load_definition(path: str | Path) -> dict[str, Any]:
    """Load a UTF-8 JSON workflow definition without mutating it."""

    source = Path(path)
    try:
        with source.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise DefinitionError(f"cannot load workflow definition {source}: {exc}") from exc
    if not isinstance(value, dict):
        raise DefinitionError("workflow definition root must be a JSON object")
    return value


def _resolve_local_reference(reference: str, base_dir: Path) -> Path | None:
    if re.match(r"^[a-z][a-z0-9+.-]*://", reference, re.IGNORECASE):
        if reference.startswith("file://"):
            return Path(reference[7:]).expanduser().resolve(strict=False)
        return None
    path = Path(reference).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve(strict=False)


def _is_within(path: Path, roots: Iterable[Path]) -> bool:
    return any(path == root or root in path.parents for root in roots)


def validate_definition(
    definition: Mapping[str, Any],
    base_dir: str | Path | None = None,
    *,
    allowed_authorities: Iterable[str | Path] | None = None,
    allowed_authority_refs: Iterable[str | Path] | None = None,
    allowed_authority_roots: Iterable[str | Path] | None = None,
    allowed_procedures: Iterable[str | Path] | None = None,
    approved_procedure_refs: Iterable[str | Path] | None = None,
    allowed_procedure_roots: Iterable[str | Path] | None = None,
    allowed_reporting_tasks: Iterable[str] | None = None,
    allowed_reporting_task_ids: Iterable[str] | None = None,
    reporting_task_id: str | None = None,
    require_existing_refs: bool = True,
) -> list[str]:
    """Return deterministic validation errors; an empty list means valid.

    Local procedure and authority references are required to exist by default.
    Non-file URI authorities are only accepted when explicitly listed in
    ``allowed_authorities``.  Local references may not escape ``base_dir``.
    """

    try:
        normalized = normalize_definition(definition, base_dir=base_dir)
    except (DefinitionError, TypeError) as exc:
        return [str(exc)]

    errors: list[str] = []
    root = Path(base_dir or ".").expanduser().resolve(strict=False)
    authority_allowlist = list(allowed_authorities or []) + list(allowed_authority_refs or [])
    procedure_allowlist = list(allowed_procedures or []) + list(approved_procedure_refs or [])
    allowed_exact_text = {str(item) for item in authority_allowlist}
    allowed_exact_paths = {
        _resolve_local_reference(str(item), root)
        for item in authority_allowlist
        if _resolve_local_reference(str(item), root) is not None
    }
    allowed_roots = [Path(item).expanduser().resolve(strict=False) for item in (allowed_authority_roots or [])]
    if not allowed_roots:
        allowed_roots = [root]
    procedure_roots = [
        Path(item).expanduser().resolve(strict=False) for item in (allowed_procedure_roots or [])
    ]
    if not procedure_roots:
        procedure_roots = [root]
    procedure_exact_text = {str(item) for item in procedure_allowlist}
    procedure_exact_paths = {
        _resolve_local_reference(str(item), root)
        for item in procedure_allowlist
        if _resolve_local_reference(str(item), root) is not None
    }

    references: list[tuple[str, str, bool]] = [
        ("procedure.reference", normalized["procedure"]["reference"], normalized["procedure"]["kind"] != "skill")
    ]
    effect = normalized["procedure"]["external_effect"]
    if effect["mode"] == "reconciliation":
        references.append(("procedure.external_effect.reconciliation_reference", effect["reconciliation_reference"], True))
    references.extend((f"authority_refs[{index}]", ref, True) for index, ref in enumerate(normalized["authority_refs"]))

    for field, reference, needs_file in references:
        resolved = _resolve_local_reference(reference, root)
        is_authority = field.startswith("authority_refs")
        is_procedure = field.startswith("procedure.")
        if is_authority and (allowed_authorities is not None or allowed_authority_refs is not None):
            if reference not in allowed_exact_text and resolved not in allowed_exact_paths:
                errors.append(f"{field} is not an allowed authority: {reference}")
                continue
        if is_procedure and (allowed_procedures is not None or approved_procedure_refs is not None):
            if reference not in procedure_exact_text and resolved not in procedure_exact_paths:
                errors.append(f"{field} is not an approved procedure: {reference}")
                continue
        if resolved is None:
            if field.startswith("authority_refs") and reference not in allowed_exact_text:
                errors.append(f"{field} is not an allowed authority: {reference}")
            continue
        applicable_roots = procedure_roots if is_procedure else allowed_roots
        if not _is_within(resolved, applicable_roots):
            root_kind = "procedure" if is_procedure else "authority"
            errors.append(f"{field} escapes allowed {root_kind} roots: {reference}")
            continue
        if require_existing_refs and needs_file and not resolved.is_file():
            errors.append(f"{field} does not reference an existing file: {reference}")

    allowed_tasks = set(allowed_reporting_tasks or []) | set(allowed_reporting_task_ids or [])
    if reporting_task_id is not None:
        allowed_tasks.add(reporting_task_id)
    if allowed_tasks and normalized["reporting"]["task_id"] not in allowed_tasks:
        errors.append(f"reporting.task_id is outside the allowed dispatcher route: {normalized['reporting']['task_id']}")
    return errors


__all__ = [
    "DefinitionError",
    "WEEKDAYS",
    "definition_hash",
    "load_definition",
    "normalize_dispatcher_id",
    "normalize_definition",
    "normalize_due_rule",
    "validate_definition",
]

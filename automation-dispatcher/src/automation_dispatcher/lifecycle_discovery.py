"""Read-only host discovery and proposal generation for guided lifecycle P3.

This module intentionally consumes caller-supplied observations.  It is not a
host client and cannot mutate tasks, automations, registries, or lifecycle
state.  A future host adapter may feed the same normalized boundary once its
callable schemas have been verified.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from .definitions import DefinitionError, normalize_definition
from .lifecycle_artifacts import LifecycleArtifact, model_for
from .lifecycle_contracts import (
    LifecycleContractError,
    seal_artifact,
    validate_artifact,
    validate_artifact_path,
)
from .scheduling import collection_occurrences_between, normalize_collection_schedule


READ_OPERATIONS = ("tasks.list", "tasks.read", "automations.list", "automations.read")
_COMPATIBILITY_FIELDS = (
    "schedule",
    "timezone",
    "authority_boundary",
    "approved_working_roots",
    "route_identity",
    "host_target",
    "execution_constraints",
)
_TOPOLOGY_ALTERNATIVES = (
    {
        "id": "keep-separate",
        "kind": "topology",
        "description": "Create one proposed collection per selected source.",
    },
    {
        "id": "accept-compatible-groups",
        "kind": "topology",
        "description": "Use the compatible collection groups shown.",
    },
)
_ROUTE_PATTERNS = (
    ("resume", ("resume", "continue setup", "continue the setup")),
    ("inspect", ("status", "inspect", "show", "review")),
    ("schedule_change", ("change schedule", "reschedule", "timezone", "cadence")),
    ("add_workflow", ("add workflow", "add a workflow", "another workflow")),
    ("create_collection", ("create collection", "new collection")),
    ("consolidate", ("consolidate", "combine", "group", "daily tasks", "weekly tasks")),
)


@dataclass(frozen=True)
class DiscoveryPage:
    snapshot: LifecycleArtifact
    next_cursor: int | None
    total_candidates: int


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _stable_id(prefix: str, value: Any) -> str:
    return f"{prefix}-{sha256(_canonical(value)).hexdigest()[:16]}"


def _slug(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:48].strip("-") or fallback


def _bounded_text(value: Any, limit: int = 240) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).split())
    return normalized[:limit] if normalized else None


def route_lifecycle_request(text: str) -> str:
    """Classify ordinary user language without treating it as authority."""

    normalized = " ".join(str(text).lower().split())
    for operation, phrases in _ROUTE_PATTERNS:
        if any(phrase in normalized for phrase in phrases):
            return operation
    return "clarify_goal"


def _capability_map(snapshot: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    if not snapshot:
        return {}
    if snapshot.get("artifact_type") == "host_capability_snapshot":
        validated = validate_artifact("host_capability_snapshot", snapshot)
        capabilities = validated["capabilities"]
    else:
        capabilities = snapshot.get("capabilities", [])
    return {
        str(item.get("name")): item
        for item in capabilities
        if isinstance(item, Mapping) and item.get("name")
    }


def _unsupported_capabilities(snapshot: Mapping[str, Any] | None) -> list[str]:
    by_name = _capability_map(snapshot)
    unsupported: list[str] = []
    for name in READ_OPERATIONS:
        item = by_name.get(name)
        if not item or item.get("supported") is not True or not item.get("surface"):
            unsupported.append(name)
    return unsupported


def _normalized_item(kind: str, raw: Mapping[str, Any]) -> dict[str, Any]:
    stable_id = raw.get("id") or raw.get("stable_id")
    if not isinstance(stable_id, str) or not stable_id.strip():
        raise LifecycleContractError(
            "missing_host_identity", f"{kind} observation requires a stable id"
        )
    schedule_raw = raw.get("schedule")
    schedule = None
    schedule_error = None
    if schedule_raw is not None:
        try:
            schedule = normalize_collection_schedule(schedule_raw)
        except (DefinitionError, ValueError) as exc:
            schedule_error = str(exc)
    prompt = raw.get("prompt")
    prompt_hash = sha256(str(prompt).encode("utf-8")).hexdigest() if prompt else raw.get("prompt_hash")
    enabled = raw.get("enabled")
    paused = raw.get("paused")
    lifecycle_state = "active"
    if raw.get("accessible") is False:
        lifecycle_state = "inaccessible"
    elif raw.get("deleted") is True:
        lifecycle_state = "deleted"
    elif raw.get("supported") is False:
        lifecycle_state = "unsupported"
    elif paused is True or enabled is False:
        lifecycle_state = "paused"
    management_classification = (
        "managed" if raw.get("managed_manifest_id") else "unmanaged"
    )
    status = "already_managed" if management_classification == "managed" else lifecycle_state
    unknown = sorted(
        field
        for field in ("schedule", "timezone", "target_task_id", "revision")
        if raw.get(field) is None
    )
    if schedule_error:
        unknown.append("schedule_invalid")
    return {
        "kind": kind,
        "stable_id": stable_id.strip(),
        "title": _bounded_text(raw.get("title") or raw.get("name") or stable_id, 120),
        "status": status,
        "lifecycle_state": lifecycle_state,
        "management_classification": management_classification,
        "enabled": enabled if isinstance(enabled, bool) else None,
        "paused": paused if isinstance(paused, bool) else None,
        "schedule": schedule,
        "timezone": raw.get("timezone"),
        "target_task_id": raw.get("target_task_id") or raw.get("task_id"),
        "host_target": raw.get("host_target") or raw.get("target_task_id") or raw.get("task_id"),
        "project_id": raw.get("project_id"),
        "working_directory": raw.get("working_directory"),
        "approved_working_roots": sorted(set(raw.get("approved_working_roots") or [])),
        "route_identity": raw.get("route_identity") or raw.get("target_task_id") or raw.get("task_id"),
        "authority_boundary": raw.get("authority_boundary"),
        "execution_constraints": deepcopy(raw.get("execution_constraints") or {}),
        "revision": raw.get("revision"),
        "identity_evidence": deepcopy(raw.get("identity_evidence") or []),
        "raw_reference": raw.get("raw_reference"),
        "prompt_hash": prompt_hash,
        "instruction_summary": _bounded_text(
            raw.get("prompt_summary") or raw.get("instruction_summary")
        ),
        "managed_manifest_id": raw.get("managed_manifest_id"),
        "procedure": deepcopy(raw.get("procedure")),
        "authority_refs": deepcopy(raw.get("authority_refs") or []),
        "reporting": deepcopy(raw.get("reporting")),
        "receipt": deepcopy(raw.get("receipt")),
        "data_sensitivity": raw.get("data_sensitivity"),
        "evidence_retention": deepcopy(raw.get("evidence_retention")),
        "retry": deepcopy(raw.get("retry")),
        "claim_lease_seconds": raw.get("claim_lease_seconds"),
        "unsupported_fields": sorted(set(raw.get("unsupported_fields") or [])),
        "unknown_fields": sorted(set(unknown)),
    }


def discover_host_state(
    observations: Mapping[str, Any],
    *,
    capability_snapshot: Mapping[str, Any] | None,
    actor: str,
    selected_ids: Sequence[str] = (),
    filters: Mapping[str, Any] | None = None,
    cursor: int = 0,
    page_size: int | None = None,
) -> DiscoveryPage:
    """Normalize one explicitly bounded, caller-supplied host observation set."""

    if observations.get("live") is True:
        raise LifecycleContractError(
            "host_capability_unavailable",
            "Q-003 blocks live host discovery; supply read-only host observations",
        )
    if cursor < 0 or page_size is not None and page_size < 1:
        raise LifecycleContractError("invalid_discovery_bound", "cursor and page size are invalid")
    if not isinstance(actor, str) or not actor.strip():
        raise LifecycleContractError("invalid_actor", "discovery actor is required")
    environment_id = observations.get("environment_id")
    observed_at = observations.get("observed_at")
    if not isinstance(environment_id, str) or not environment_id:
        raise LifecycleContractError("missing_environment", "environment_id is required")
    if not isinstance(observed_at, str) or not observed_at:
        raise LifecycleContractError("missing_observation_time", "observed_at is required")
    if capability_snapshot:
        capability_environment = capability_snapshot.get("environment_id")
        if capability_environment and capability_environment != environment_id:
            raise LifecycleContractError(
                "host_environment_drift",
                "capability and observation environment identities differ",
                capability_environment=capability_environment,
                observation_environment=environment_id,
            )
    manifests = list(observations.get("existing_manifests") or [])
    managed_sources: dict[str, str] = {}
    normalized_manifests: list[dict[str, Any]] = []
    for manifest in manifests:
        if not isinstance(manifest, Mapping):
            raise LifecycleContractError(
                "invalid_host_observation", "existing manifest entries must be objects"
            )
        manifest_id = str(manifest.get("manifest_id") or "unknown-manifest")
        source_ids = sorted(
            {
                str(source_id)
                for source_id in (
                    *(manifest.get("source_ids") or ()),
                    *(manifest.get("automation_ids") or ()),
                    *(manifest.get("task_ids") or ()),
                )
            }
        )
        for source_id in source_ids:
            existing_claim = managed_sources.get(source_id)
            if existing_claim is not None and existing_claim != manifest_id:
                raise LifecycleContractError(
                    "ambiguous_managed_source",
                    "multiple manifests claim the same host source",
                    source_id=source_id,
                    manifest_ids=sorted({existing_claim, manifest_id}),
                )
            managed_sources[source_id] = manifest_id
        normalized_manifests.append(
            {
                "manifest_id": manifest_id,
                "dispatcher_id": manifest.get("dispatcher_id"),
                "source_ids": source_ids,
                "content_hash": manifest.get("content_hash"),
                "raw_reference": manifest.get("raw_reference"),
            }
        )
    items: list[dict[str, Any]] = []
    seen_host_ids: dict[str, str] = {}
    for kind, key in (("task", "tasks"), ("automation", "automations")):
        for raw in observations.get(key, []):
            if not isinstance(raw, Mapping):
                raise LifecycleContractError("invalid_host_observation", f"{key} entries must be objects")
            item = _normalized_item(kind, raw)
            previous_kind = seen_host_ids.get(item["stable_id"])
            if previous_kind is not None:
                raise LifecycleContractError(
                    "duplicate_host_identity",
                    "stable host identifiers must be unique across tasks and automations",
                    stable_id=item["stable_id"],
                    first_kind=previous_kind,
                    duplicate_kind=kind,
                )
            seen_host_ids[item["stable_id"]] = kind
            raw_manifest_id = item["managed_manifest_id"]
            discovered_manifest_id = managed_sources.get(item["stable_id"])
            if (
                raw_manifest_id
                and discovered_manifest_id
                and raw_manifest_id != discovered_manifest_id
            ):
                raise LifecycleContractError(
                    "ambiguous_managed_source",
                    "host observation and manifest inventory disagree on source ownership",
                    source_id=item["stable_id"],
                    manifest_ids=sorted({raw_manifest_id, discovered_manifest_id}),
                )
            if not item["managed_manifest_id"] and item["stable_id"] in managed_sources:
                item["managed_manifest_id"] = managed_sources[item["stable_id"]]
                item["status"] = "already_managed"
                item["management_classification"] = "managed"
            items.append(item)
    observed_source_ids = {item["stable_id"] for item in items}
    explicit = set(selected_ids)
    criteria = dict(filters or {})
    missing_selection = sorted(explicit - observed_source_ids)
    if explicit:
        items = [item for item in items if item["stable_id"] in explicit]
    for field, expected in sorted(criteria.items()):
        items = [item for item in items if item.get(field) == expected]
    items.sort(key=lambda item: (item["kind"], item["stable_id"]))
    total = len(items)
    end = total if page_size is None else min(total, cursor + page_size)
    page = items[cursor:end]
    next_cursor = end if end < total else None
    tasks = [item for item in page if item["kind"] == "task"]
    automations = [item for item in page if item["kind"] == "automation"]
    unsupported = _unsupported_capabilities(capability_snapshot)
    warnings = list(observations.get("warnings") or [])
    if missing_selection:
        warnings.append("selected host identifiers were not observed: " + ", ".join(missing_selection))
    stale_manifest_sources = sorted(set(managed_sources) - observed_source_ids)
    if stale_manifest_sources:
        warnings.append("existing manifests reference unobserved sources: " + ", ".join(stale_manifest_sources))
    if unsupported:
        warnings.append("Q-003: callable host discovery is unavailable; snapshot uses supplied observations only")
    scope = {
        "selection": sorted(explicit),
        "filters": criteria,
        "pagination": {"cursor": cursor, "page_size": page_size, "next_cursor": next_cursor, "total": total},
        "input_reference": observations.get("input_reference"),
        "existing_manifests": sorted(
            normalized_manifests,
            key=lambda item: _canonical(item),
        ),
        "read_only": True,
    }
    identity_material = {
        "environment_id": environment_id,
        "scope": scope,
        "tasks": tasks,
        "automations": automations,
        "unsupported_capabilities": unsupported,
    }
    artifact = model_for("discovery_snapshot").seal(
        {
            "schema_version": 1,
            "artifact_type": "discovery_snapshot",
            "snapshot_id": _stable_id("snapshot", identity_material),
            "observed_at": observed_at,
            "actor": actor,
            "environment_id": environment_id,
            "scope": scope,
            "tasks": tasks,
            "automations": automations,
            "unsupported_capabilities": unsupported,
            "warnings": sorted(set(warnings)),
        }
    )
    return DiscoveryPage(artifact, next_cursor, total)


def _group_key(item: Mapping[str, Any]) -> tuple[str, ...] | None:
    values: list[str] = []
    for field in _COMPATIBILITY_FIELDS:
        value = item.get(field)
        if value in (None, "", [], {}):
            return None
        values.append(_canonical(value).decode("utf-8"))
    return tuple(values)


def _draft_definition(item: Mapping[str, Any], dispatcher_id: str) -> dict[str, Any]:
    stable_id = str(item["stable_id"])
    workflow_id = f"{_slug(stable_id, 'workflow')}-{sha256(stable_id.encode()).hexdigest()[:8]}"
    draft = {
        "schema_version": 2,
        "workflow_id": workflow_id,
        "name": str(item.get("title") or stable_id),
        "description": str(item.get("instruction_summary") or f"Run the approved procedure for {stable_id}."),
        "dispatcher_id": dispatcher_id,
        "enabled": item.get("status") != "paused",
        "retry": item.get("retry") or {"max_attempts": 1, "backoff_seconds": 0},
        "claim_lease_seconds": item.get("claim_lease_seconds") or 900,
        "procedure": item.get("procedure"),
        "authority_refs": item.get("authority_refs"),
        "reporting": item.get("reporting") or {"task_id": item.get("target_task_id")},
        "receipt": item.get("receipt") or {"required_fields": ["run_id", "status"]},
        "data_sensitivity": item.get("data_sensitivity") or "internal",
        "evidence_retention": item.get("evidence_retention") or {"policy": "references-only", "days": 30},
        "revision": 1,
    }
    return normalize_definition(draft)


def _cutover_candidate(
    items: Sequence[Mapping[str, Any]],
    collection: Mapping[str, Any],
    observed_at: str,
) -> dict[str, Any]:
    source_ids = [str(item["stable_id"]) for item in items]
    base = {
        "source_ids": source_ids,
        "source_schedule": collection["schedule"],
        "source_timezone": collection["timezone"],
        "reference_time": observed_at,
        "authorized": False,
    }
    try:
        reference = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        if reference.tzinfo is None:
            raise ValueError("observation time requires a timezone offset")
        config = {
            "schedule": collection["schedule"],
            "timezone": collection["timezone"],
            "enabled": True,
        }
        horizon = timedelta(days=1830)
        previous = collection_occurrences_between(config, reference - horizon, reference)
        following = collection_occurrences_between(config, reference, reference + horizon)
        if not following:
            return {
                **base,
                "status": "unknown",
                "boundary_id": None,
                "last_source_scheduled_for": previous[-1]["scheduled_for"] if previous else None,
                "first_dispatcher_scheduled_for": None,
                "disable_source_before": None,
                "reason": "no future occurrence was found within the deterministic five-year window",
            }
        material = {
            "source_ids": source_ids,
            "reference_time": observed_at,
            "first_dispatcher_scheduled_for": following[0]["scheduled_for"],
        }
        return {
            **base,
            "status": "computed",
            "boundary_id": _stable_id("boundary", material),
            "last_source_scheduled_for": previous[-1]["scheduled_for"] if previous else None,
            "first_dispatcher_scheduled_for": following[0]["scheduled_for"],
            "disable_source_before": following[0]["scheduled_for"],
            "reason": None,
        }
    except (DefinitionError, ValueError, TypeError) as exc:
        return {
            **base,
            "status": "unknown",
            "boundary_id": None,
            "last_source_scheduled_for": None,
            "first_dispatcher_scheduled_for": None,
            "disable_source_before": None,
            "reason": _bounded_text(exc, 240),
        }


def propose_collections(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Group only fully compatible observations and produce schema-v2 drafts."""

    source = validate_artifact("discovery_snapshot", snapshot)
    groups: dict[tuple[str, ...], list[Mapping[str, Any]]] = {}
    exclusions: list[dict[str, Any]] = []
    unresolved: list[str] = []
    warnings: list[str] = list(source["warnings"])
    inclusion_decisions: list[dict[str, Any]] = []
    for item in [*source["tasks"], *source["automations"]]:
        if item.get("status") in {"inaccessible", "deleted", "unsupported", "already_managed"}:
            exclusions.append({"source_id": item["stable_id"], "reason": item["status"]})
            continue
        if item.get("lifecycle_state") == "paused":
            unresolved.append(f"decide whether to include paused source {item['stable_id']}")
            inclusion_decisions.append(
                {
                    "source_id": item["stable_id"],
                    "reason": "source is paused and unmanaged",
                    "choices": ["include", "exclude"],
                }
            )
        key = _group_key(item)
        if key is None:
            exclusions.append({"source_id": item["stable_id"], "reason": "incomplete_compatibility_evidence"})
            unresolved.append(f"complete compatibility fields for {item['stable_id']}")
            continue
        groups.setdefault(key, []).append(item)
    collections: list[dict[str, Any]] = []
    mappings: list[dict[str, Any]] = []
    for key, items in sorted(groups.items(), key=lambda pair: pair[0]):
        dispatcher_id = _stable_id("collection", {"compatibility": key})
        first = items[0]
        drafts: list[dict[str, Any]] = []
        for item in sorted(items, key=lambda value: str(value["stable_id"])):
            try:
                definition = _draft_definition(item, dispatcher_id)
            except (DefinitionError, TypeError, ValueError) as exc:
                definition = None
                unresolved.append(f"complete workflow contract for {item['stable_id']}: {exc}")
            drafts.append({"source_id": item["stable_id"], "definition": definition})
            mappings.append(
                {
                    "source_id": item["stable_id"],
                    "dispatcher_id": dispatcher_id,
                    "workflow_id": definition.get("workflow_id") if definition else None,
                    "source_status": item.get("status"),
                }
            )
        collection = {
                "dispatcher_id": dispatcher_id,
                "schedule": first["schedule"],
                "timezone": first["timezone"],
                "target_task_id": first["target_task_id"],
                "route_identity": first["route_identity"],
                "host_target": first["host_target"],
                "authority_boundary": first["authority_boundary"],
                "approved_working_roots": first["approved_working_roots"],
                "execution_constraints": first["execution_constraints"],
                "grouping_rationale": (
                    "Grouped because every source has the same canonical schedule, timezone, "
                    "authority boundary, approved working roots, route identity, host target, "
                    "and execution constraints."
                ),
                "workflow_drafts": drafts,
        }
        collection["cutover_candidate"] = _cutover_candidate(
            items, collection, source["observed_at"]
        )
        collections.append(collection)
    if source["unsupported_capabilities"]:
        unresolved.append("verify callable host discovery schemas (Q-003)")
    if not collections:
        unresolved.append("no compatible unmanaged candidates were proposed")
    grouping_decisions = [
        {
            "collection_id": collection["dispatcher_id"],
            "source_ids": list(collection["cutover_candidate"]["source_ids"]),
            "decision": "grouped",
            "compatible_on": {
                "schedule": collection["schedule"],
                "timezone": collection["timezone"],
                "authority_boundary": collection["authority_boundary"],
                "approved_working_roots": collection["approved_working_roots"],
                "route_identity": collection["route_identity"],
                "host_target": collection["host_target"],
                "execution_constraints": collection["execution_constraints"],
            },
            "rationale": collection["grouping_rationale"],
        }
        for collection in collections
    ] + [
        {
            "collection_id": None,
            "source_ids": [exclusion["source_id"]],
            "decision": "excluded",
            "compatible_on": {},
            "rationale": exclusion["reason"],
        }
        for exclusion in exclusions
    ]
    for left_index, left in enumerate(collections):
        for right in collections[left_index + 1 :]:
            differing_fields = [
                field
                for field in _COMPATIBILITY_FIELDS
                if left.get(field) != right.get(field)
            ]
            grouping_decisions.append(
                {
                    "collection_id": None,
                    "collection_ids": [left["dispatcher_id"], right["dispatcher_id"]],
                    "source_ids": sorted(
                        [
                            *left["cutover_candidate"]["source_ids"],
                            *right["cutover_candidate"]["source_ids"],
                        ]
                    ),
                    "decision": "split",
                    "compatible_on": {},
                    "differing_fields": differing_fields,
                    "rationale": "Split because collection-owned compatibility fields differ: "
                    + ", ".join(differing_fields),
                }
            )
    risks = [
        {
            "code": "cutover_requires_separate_approval",
            "severity": "info",
            "summary": f"{collection['dispatcher_id']} cutover is a candidate only and is not authorized.",
            "source_ids": list(collection["cutover_candidate"]["source_ids"]),
        }
        for collection in collections
    ]
    risks.extend(
        {
            "code": (
                "host_capability_unavailable"
                if "Q-003" in warning
                else "discovery_warning"
            ),
            "severity": "blocking" if "Q-003" in warning else "warning",
            "summary": warning,
            "source_ids": [],
        }
        for warning in sorted(set(warnings))
    )
    risks.extend(
        {
            "code": "excluded_candidate",
            "severity": "warning",
            "summary": f"{exclusion['source_id']} was excluded: {exclusion['reason']}.",
            "source_ids": [exclusion["source_id"]],
        }
        for exclusion in exclusions
    )
    for decision in grouping_decisions:
        if decision["decision"] != "split":
            continue
        differing = set(decision["differing_fields"])
        if differing & {"schedule", "timezone"}:
            code = "mixed_schedule_split"
            summary = "Sources were split because their collection schedules or timezones differ."
        elif differing & {"route_identity", "host_target"}:
            code = "route_target_conflict"
            summary = "Sources were split because their route identities or host targets differ."
        else:
            code = "incompatible_collection_boundary"
            summary = "Sources were split because collection compatibility fields differ."
        risks.append(
            {
                "code": code,
                "severity": "warning",
                "summary": summary,
                "source_ids": decision["source_ids"],
            }
        )
    for collection in collections:
        boundary = collection["cutover_candidate"]
        if boundary["status"] == "unknown":
            risks.append(
                {
                    "code": "cutover_boundary_unknown",
                    "severity": "blocking",
                    "summary": str(boundary["reason"]),
                    "source_ids": boundary["source_ids"],
                }
            )
            unresolved.append(
                "resolve cutover boundary for " + collection["dispatcher_id"]
            )
    risks.extend(
        {
            "code": "unresolved_decision",
            "severity": "blocking",
            "summary": decision,
            "source_ids": [],
        }
        for decision in sorted(set(unresolved))
    )
    risks.sort(key=lambda item: (item["severity"], item["code"], item["summary"]))
    proposal = {
        "proposal_id": _stable_id("proposal", {"snapshot_hash": source["content_hash"], "collections": collections, "mappings": mappings, "exclusions": exclusions}),
        "source_snapshot_id": source["snapshot_id"],
        "source_snapshot_hash": source["content_hash"],
        "collections": collections,
        "grouping_decisions": grouping_decisions,
        "workflow_mappings": mappings,
        "exclusions": exclusions,
        "warnings": sorted(set(warnings)),
        "risks": risks,
        "inclusion_decisions": inclusion_decisions,
        "unresolved_decisions": sorted(set(unresolved)),
        "alternatives": deepcopy(list(_TOPOLOGY_ALTERNATIVES)),
        "mutation_count": 0,
        "next_action": "accept_proposal" if not unresolved else "resolve_questions",
    }
    proposal["proposal_hash"] = sha256(_canonical(proposal)).hexdigest()
    return proposal


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _normalized_acceptance_paths(
    *,
    state_paths: Sequence[str | Path],
    source_paths: Sequence[str | Path],
    state_root: str | Path | None,
    repository_root: str | Path | None,
    source_root: str | Path | None,
    installed_roots: Sequence[str | Path],
) -> tuple[list[str], list[str]]:
    if not state_paths or not source_paths:
        raise LifecycleContractError(
            "plan_paths_required", "accepted plans require explicit state and source paths"
        )
    if state_root is None or repository_root is None or source_root is None:
        raise LifecycleContractError(
            "plan_path_roots_required",
            "accepted plans require explicit state, repository, and source roots",
        )
    resolved_state_root = Path(state_root).expanduser().resolve(strict=False)
    resolved_repository_root = Path(repository_root).expanduser().resolve(strict=False)
    broad_roots = {Path("/"), Path.home().resolve()}
    if resolved_state_root in broad_roots or resolved_repository_root in broad_roots:
        raise LifecycleContractError(
            "forbidden_plan_root", "broad state or repository roots are forbidden"
        )
    normalized_state: list[str] = []
    for value in state_paths:
        resolved = validate_artifact_path(
            value,
            storage_owner="external_state",
            explicit_root=resolved_state_root,
            source_root=source_root,
            installed_roots=installed_roots,
        )
        if not _inside(resolved, resolved_state_root):
            raise LifecycleContractError(
                "state_path_outside_root",
                "accepted state paths must remain inside the explicit state root",
                path=str(resolved),
            )
        normalized_state.append(str(resolved))
    normalized_source: list[str] = []
    for value in source_paths:
        resolved = validate_artifact_path(
            value,
            storage_owner="source_controlled",
            explicit_root=resolved_repository_root,
            installed_roots=installed_roots,
        )
        if not _inside(resolved, resolved_repository_root):
            raise LifecycleContractError(
                "source_path_outside_root",
                "accepted source paths must remain inside the explicit repository root",
                path=str(resolved),
            )
        normalized_source.append(str(resolved))
    return sorted(set(normalized_state)), sorted(set(normalized_source))


def _materialize_topology(
    proposal: Mapping[str, Any],
    topology: str,
    paused_source_decisions: Mapping[str, bool],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    inclusion_ids = {
        str(item["source_id"])
        for item in proposal.get("inclusion_decisions", ())
        if isinstance(item, Mapping)
    }
    supplied_ids = set(paused_source_decisions)
    invalid_decisions = sorted(
        source_id
        for source_id, include in paused_source_decisions.items()
        if not isinstance(include, bool)
    )
    if invalid_decisions:
        raise LifecycleContractError(
            "invalid_paused_source_decision",
            "paused source decisions must be booleans",
            source_ids=invalid_decisions,
        )
    if supplied_ids != inclusion_ids:
        raise LifecycleContractError(
            "paused_source_decision_required",
            "every paused unmanaged source requires exactly one include or exclude decision",
            missing=sorted(inclusion_ids - supplied_ids),
            unexpected=sorted(supplied_ids - inclusion_ids),
        )
    excluded_paused = {
        source_id for source_id, include in paused_source_decisions.items() if not include
    }
    collections: list[dict[str, Any]] = []
    mappings = [
        deepcopy(item)
        for item in proposal["workflow_mappings"]
        if item["source_id"] not in excluded_paused
    ]
    exclusions = deepcopy(list(proposal["exclusions"])) + [
        {"source_id": source_id, "reason": "paused_source_excluded_by_acceptance"}
        for source_id in sorted(excluded_paused)
    ]
    for original in proposal["collections"]:
        retained_drafts = [
            deepcopy(item)
            for item in original["workflow_drafts"]
            if item["source_id"] not in excluded_paused
        ]
        if not retained_drafts:
            continue
        if topology == "accept-compatible-groups":
            collection = deepcopy(original)
            collection["workflow_drafts"] = retained_drafts
            boundary = collection["cutover_candidate"]
            boundary["source_ids"] = [
                item["source_id"] for item in retained_drafts
            ]
            if boundary["status"] == "computed":
                boundary["boundary_id"] = _stable_id(
                    "boundary",
                    {
                        "source_ids": boundary["source_ids"],
                        "reference_time": boundary["reference_time"],
                        "first_dispatcher_scheduled_for": boundary[
                            "first_dispatcher_scheduled_for"
                        ],
                    },
                )
            collections.append(collection)
            continue
        for draft in retained_drafts:
            source_id = draft["source_id"]
            dispatcher_id = _stable_id(
                "collection",
                {
                    "topology": "keep-separate",
                    "compatible_collection_id": original["dispatcher_id"],
                    "source_id": source_id,
                },
            )
            selected_draft = deepcopy(draft)
            if selected_draft["definition"] is not None:
                definition = dict(selected_draft["definition"])
                definition.pop("content_hash", None)
                definition["dispatcher_id"] = dispatcher_id
                selected_draft["definition"] = normalize_definition(definition)
            collection = deepcopy(original)
            collection["dispatcher_id"] = dispatcher_id
            collection["workflow_drafts"] = [selected_draft]
            collection["grouping_rationale"] = (
                "Kept separate because the accepted topology selects one collection per source."
            )
            boundary = collection["cutover_candidate"]
            boundary["source_ids"] = [source_id]
            if boundary["status"] == "computed":
                boundary["boundary_id"] = _stable_id(
                    "boundary",
                    {
                        "source_ids": [source_id],
                        "reference_time": boundary["reference_time"],
                        "first_dispatcher_scheduled_for": boundary[
                            "first_dispatcher_scheduled_for"
                        ],
                    },
                )
            collections.append(collection)
            for mapping in mappings:
                if mapping["source_id"] == source_id:
                    mapping["dispatcher_id"] = dispatcher_id
                    mapping["workflow_id"] = (
                        selected_draft["definition"]["workflow_id"]
                        if selected_draft["definition"] is not None
                        else None
                    )
    paused_questions = {
        f"decide whether to include paused source {source_id}" for source_id in inclusion_ids
    }
    unresolved = [
        item for item in proposal["unresolved_decisions"] if item not in paused_questions
    ]
    return collections, mappings, exclusions, unresolved


def build_accepted_plan(
    snapshot: Mapping[str, Any],
    proposal: Mapping[str, Any],
    *,
    actor: str,
    accepted: bool,
    expires_at: str,
    accepted_at: str | None = None,
    selected_alternatives: Sequence[str] = ("accept-compatible-groups",),
    paused_source_decisions: Mapping[str, bool] | None = None,
    state_paths: Sequence[str | Path] = (),
    source_paths: Sequence[str | Path] = (),
    state_root: str | Path | None = None,
    repository_root: str | Path | None = None,
    source_root: str | Path | None = None,
    installed_roots: Sequence[str | Path] = (),
) -> LifecycleArtifact:
    """Create a hash-bound plan only after explicit proposal acceptance."""

    source = validate_artifact("discovery_snapshot", snapshot)
    if not accepted:
        raise LifecycleContractError("proposal_acceptance_required", "explicit proposal acceptance is required")
    if proposal.get("source_snapshot_hash") != source["content_hash"]:
        raise LifecycleContractError("source_snapshot_drift", "proposal is not bound to this discovery snapshot")
    expected_proposal_hash = sha256(
        _canonical({k: v for k, v in proposal.items() if k != "proposal_hash"})
    ).hexdigest()
    if proposal.get("proposal_hash") != expected_proposal_hash:
        raise LifecycleContractError("proposal_hash_mismatch", "proposal content hash is invalid")
    if not isinstance(actor, str) or not actor.strip() or not expires_at:
        raise LifecycleContractError("invalid_plan_acceptance", "actor and expiry are required")
    acceptance_value = accepted_at or datetime.now(UTC).isoformat()
    try:
        acceptance_time = datetime.fromisoformat(
            acceptance_value.replace("Z", "+00:00")
        )
        expiry_time = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise LifecycleContractError(
            "invalid_plan_expiry", "plan expiry must be an ISO-8601 date-time"
        ) from exc
    if acceptance_time.tzinfo is None or expiry_time.tzinfo is None:
        raise LifecycleContractError(
            "invalid_plan_expiry", "plan acceptance and expiry require timezone offsets"
        )
    if expiry_time <= acceptance_time:
        raise LifecycleContractError(
            "invalid_plan_expiry", "plan expiry must follow the plan acceptance time"
        )
    expected_alternatives = list(_TOPOLOGY_ALTERNATIVES)
    supplied_alternatives = proposal.get("alternatives")
    if supplied_alternatives != expected_alternatives:
        raise LifecycleContractError(
            "invalid_selected_alternative",
            "proposal topology alternatives do not match the implementation-owned contract",
        )
    known_alternatives = {item["id"] for item in _TOPOLOGY_ALTERNATIVES}
    selected = list(selected_alternatives)
    if (
        len(selected) != 1
        or selected[0] not in known_alternatives
        or len(set(selected)) != 1
    ):
        raise LifecycleContractError(
            "invalid_selected_alternative",
            "exactly one mutually exclusive topology alternative must be selected",
        )
    if not proposal.get("collections"):
        raise LifecycleContractError(
            "no_collection_proposal", "an accepted plan requires at least one proposed collection"
        )
    normalized_state_paths, normalized_source_paths = _normalized_acceptance_paths(
        state_paths=state_paths,
        source_paths=source_paths,
        state_root=state_root,
        repository_root=repository_root,
        source_root=source_root,
        installed_roots=installed_roots,
    )
    selected_collections, selected_mappings, selected_exclusions, unresolved = (
        _materialize_topology(
            proposal, selected[0], paused_source_decisions or {}
        )
    )
    if not selected_collections:
        raise LifecycleContractError(
            "no_collection_proposal", "acceptance decisions leave no proposed collection"
        )
    acceptance_text = acceptance_time.astimezone(UTC).isoformat().replace("+00:00", "Z")
    approved_scope = [
        f"proposal_hash:{expected_proposal_hash}",
        f"accepted_at:{acceptance_text}",
        f"expires_at:{expires_at}",
        *[f"alternative:{item}" for item in selected],
        *[
            f"paused_source:{source_id}:{'include' if include else 'exclude'}"
            for source_id, include in sorted((paused_source_decisions or {}).items())
        ],
    ]
    plan_material = {
        "snapshot_hash": source["content_hash"],
        "proposal_hash": expected_proposal_hash,
        "actor": actor,
        "accepted_at": acceptance_text,
        "expires_at": expires_at,
        "selected_alternatives": selected,
    }
    plan = seal_artifact(
        {
            "schema_version": 1,
            "artifact_type": "lifecycle_plan",
            "plan_id": _stable_id("plan", plan_material),
            "created_at": acceptance_text,
            "actor": actor,
            "source_snapshot_id": source["snapshot_id"],
            "source_snapshot_hash": source["content_hash"],
            "collections": selected_collections,
            "workflow_mappings": selected_mappings,
            "exclusions": selected_exclusions,
            "unresolved_decisions": unresolved,
            "approved_scope": approved_scope,
            "state_paths": normalized_state_paths,
            "source_paths": normalized_source_paths,
            "expected_cli_operations": [
                {
                    "stage": "initialize",
                    "operation": "init",
                    "collection_id": collection["dispatcher_id"],
                    "requires_approval": True,
                }
                for collection in selected_collections
            ]
            + [
                {
                    "stage": "initialize",
                    "operation": "register",
                    "collection_id": collection["dispatcher_id"],
                    "workflow_id": draft["definition"]["workflow_id"],
                    "requires_approval": True,
                }
                for collection in selected_collections
                for draft in collection["workflow_drafts"]
                if draft["definition"] is not None
            ],
            "expected_host_operations": [
                {
                    "stage": "cut_over",
                    "operation": "automations.create_or_update_heartbeat",
                    "collection_id": collection["dispatcher_id"],
                    "target_task_id": collection["target_task_id"],
                    "authorized": False,
                }
                for collection in selected_collections
            ]
            + [
                {
                    "stage": "cut_over",
                    "operation": "automations.disable_legacy",
                    "collection_id": collection["dispatcher_id"],
                    "source_ids": collection["cutover_candidate"]["source_ids"],
                    "authorized": False,
                }
                for collection in selected_collections
            ],
            "occurrence_boundaries": [
                {"collection_id": item["dispatcher_id"], **item["cutover_candidate"]}
                for item in selected_collections
            ],
            "rollback_steps": ["leave source automations unchanged", "discard un-applied lifecycle plan"],
            "stage_status": {
                "discover": "completed",
                "propose": "completed" if not unresolved else "blocked",
                "initialize": "pending",
                "shadow_validate": "pending",
                "cut_over": "pending",
                "operate_evolve": "pending",
            },
        }
    )
    return model_for("lifecycle_plan").from_mapping(validate_artifact("lifecycle_plan", plan))

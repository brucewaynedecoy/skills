"""Configured-versus-observed dispatcher route assurance checks."""

from __future__ import annotations

from typing import Any, Mapping


ASSURANCE_RANK = {
    "unknown": 0,
    "declared": 1,
    "verified_config": 2,
    "attested": 3,
}
SOURCE_ASSURANCE = {
    "unknown": "unknown",
    "declared": "declared",
    "prompt": "declared",
    "automation_config": "verified_config",
    "verified_config": "verified_config",
    "runtime": "attested",
    "attested": "attested",
}


def _identity(raw: Any, *, configured: bool) -> dict[str, Any]:
    if isinstance(raw, Mapping) and any(key in raw for key in ("value", "source", "identity_source", "assurance")):
        value = raw.get("value")
        source = str(raw.get("source", raw.get("identity_source", "unknown"))).strip().lower()
        assurance = str(raw.get("assurance", SOURCE_ASSURANCE.get(source, "unknown"))).strip().lower()
    else:
        value = raw
        source = "verified_config" if configured and value is not None else "unknown"
        assurance = "verified_config" if configured and value is not None else "unknown"
    if assurance not in ASSURANCE_RANK:
        assurance = "unknown"
    if source not in SOURCE_ASSURANCE:
        source = "unknown"
    if value is None:
        assurance = "unknown"
        source = "unknown"
    return {"value": value, "source": source, "assurance": assurance}


def _requirement(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        return {"required": True, "minimum_assurance": raw, "allow_unknown": False}
    if isinstance(raw, bool):
        return {
            "required": raw,
            "minimum_assurance": "declared" if raw else "unknown",
            "allow_unknown": not raw,
        }
    if raw is None:
        return {"required": False, "minimum_assurance": "unknown", "allow_unknown": True}
    if not isinstance(raw, Mapping):
        raise ValueError("route requirements must be strings, booleans, or objects")
    required = bool(raw.get("required", True))
    minimum = str(raw.get("minimum_assurance", raw.get("min_assurance", "declared" if required else "unknown"))).lower()
    if minimum not in ASSURANCE_RANK:
        raise ValueError(f"unknown minimum assurance: {minimum}")
    return {
        "required": required,
        "minimum_assurance": minimum,
        "allow_unknown": bool(raw.get("allow_unknown", not required)),
    }


def check_route(
    configured: Mapping[str, Any],
    observed: Mapping[str, Any],
    requirements: Mapping[str, Any] | list[str] | tuple[str, ...],
) -> dict[str, Any]:
    """Compare route identity and return a deterministic fail-closed result.

    Values may be scalars or identity objects with ``value``, ``source`` (or
    ``identity_source``), and ``assurance``.  Requirement values may be a
    minimum-assurance string or an object containing ``required``,
    ``minimum_assurance``, and ``allow_unknown``.
    """

    if not isinstance(configured, Mapping) or not isinstance(observed, Mapping):
        raise TypeError("configured and observed routes must be mappings")
    if isinstance(requirements, (list, tuple)):
        field_requirements: Mapping[str, Any] = {field: "declared" for field in requirements}
    elif isinstance(requirements, Mapping):
        nested = requirements.get("fields")
        field_requirements = nested if isinstance(nested, Mapping) else requirements
    else:
        raise TypeError("requirements must be a mapping or field list")

    checks: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    unattested: list[dict[str, Any]] = []

    for field in sorted(field_requirements):
        # Metadata beside a nested fields map is not itself a route field.
        if field in {"allow_unknown", "allow_unknown_optional", "default_minimum_assurance"}:
            continue
        requirement = _requirement(field_requirements[field])
        expected = _identity(configured.get(field), configured=True)
        actual = _identity(observed.get(field), configured=False)
        actual_rank = ASSURANCE_RANK[actual["assurance"]]
        minimum_rank = ASSURANCE_RANK[requirement["minimum_assurance"]]
        unknown_allowed = requirement["allow_unknown"] and actual["value"] is None

        status = "ok"
        # Only sufficiently assured observations can prove a mismatch.  A
        # conflicting declared prompt value is untrusted evidence, not proof
        # that the dispatcher is on the wrong route.
        if (
            actual["value"] is not None
            and expected["value"] is not None
            and actual["assurance"] != "unknown"
            and actual_rank >= minimum_rank
            and actual["value"] != expected["value"]
        ):
            status = "mismatch"
            mismatches.append(
                {
                    "field": field,
                    "configured": expected,
                    "observed": actual,
                }
            )
        elif not unknown_allowed and (
            (requirement["required"] and (expected["value"] is None or actual["value"] is None))
            or actual_rank < minimum_rank
        ):
            status = "unattested"
            unattested.append(
                {
                    "field": field,
                    "configured": expected,
                    "observed": actual,
                    "minimum_assurance": requirement["minimum_assurance"],
                }
            )
        checks.append(
            {
                "field": field,
                "status": status,
                "required": requirement["required"],
                "minimum_assurance": requirement["minimum_assurance"],
                "configured": expected,
                "observed": actual,
            }
        )

    if mismatches:
        outcome = "route_mismatch"
    elif unattested:
        outcome = "route_unattested"
    else:
        outcome = "ok"
    return {
        "ok": outcome == "ok",
        "outcome": outcome,
        "checks": checks,
        "mismatches": mismatches,
        "unattested": unattested,
    }


__all__ = ["ASSURANCE_RANK", "check_route"]

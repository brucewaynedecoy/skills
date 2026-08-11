from __future__ import annotations

import json
from pathlib import Path

import pytest

from automation_dispatcher.definitions import (
    DefinitionError,
    normalize_definition,
    normalize_dispatcher_id,
)


FIXTURE = Path(__file__).parent / "fixtures" / "daily-workflow.json"


def definition() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_schema_v2_definition_is_workflow_only_and_accepts_arbitrary_dispatcher_slug() -> None:
    normalized = normalize_definition(definition())
    assert normalized["schema_version"] == 2
    assert normalized["dispatcher_id"] == "ops-collection"
    for field in ("timezone", "due_rule", "schedule", "max_lateness_seconds", "catch_up"):
        assert field not in normalized


@pytest.mark.parametrize(
    "value", ["ops-collection", "a", "collection-2026", "daily", "weekly"]
)
def test_dispatcher_slug_grammar_is_arbitrary(value: str) -> None:
    assert normalize_dispatcher_id(value) == value


@pytest.mark.parametrize("value", ["", "Ops", "ops_collection", "-ops", "ops-", "ops--x", 42])
def test_invalid_dispatcher_slugs_fail(value: object) -> None:
    with pytest.raises(DefinitionError):
        normalize_dispatcher_id(value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("timezone", "UTC"),
        ("time_zone", "UTC"),
        ("due_rule", {"frequency": "daily"}),
        ("due", "daily"),
        ("schedule", "0 6 * * *"),
        ("max_lateness_seconds", 60),
        ("maximum_lateness", 60),
        ("max_lateness", 60),
        ("catch_up", {"policy": "none"}),
        ("catchup", "none"),
        ("max_lookback_seconds", 60),
        ("max_lookback", 60),
    ],
)
def test_schema_v2_rejects_every_workflow_schedule_override(field: str, value: object) -> None:
    raw = definition()
    raw[field] = value
    with pytest.raises(DefinitionError, match="inherit dispatcher scheduling"):
        normalize_definition(raw)


def test_legacy_v1_requires_explicit_migration() -> None:
    raw = definition()
    raw["schema_version"] = 1
    with pytest.raises(DefinitionError, match="explicit migration"):
        normalize_definition(raw)

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from automation_dispatcher.definitions import (
    DefinitionError,
    definition_hash,
    load_definition,
    normalize_definition,
    validate_definition,
)


FIXTURES = Path(__file__).parent / "fixtures"
DEFINITION = FIXTURES / "daily-workflow.json"


def test_load_normalize_and_hash_are_canonical() -> None:
    raw = load_definition(DEFINITION)
    normalized = normalize_definition(raw, base_dir=FIXTURES)
    assert normalized["schema_version"] == 2
    assert normalized["dispatcher_id"] == "ops-collection"
    assert "due_rule" not in normalized
    assert "schedule" not in normalized
    assert "timezone" not in normalized
    assert normalized["procedure"] == {
        "kind": "documented",
        "reference": "daily-workflow.json",
        "external_effect": {"mode": "none"},
    }
    assert normalized["reporting"]["task_id"] == "task-daily"
    assert normalized["content_hash"] == definition_hash(normalized)
    reordered = json.loads(json.dumps(raw, sort_keys=True))
    assert normalize_definition(reordered)["content_hash"] == normalized["content_hash"]


def test_validation_checks_files_authorities_and_reporting_route() -> None:
    raw = load_definition(DEFINITION)
    assert validate_definition(
        raw,
        FIXTURES,
        allowed_authority_roots=[FIXTURES],
        allowed_reporting_tasks=["task-daily"],
    ) == []

    escaped = deepcopy(raw)
    escaped["authority_refs"] = ["../outside.md"]
    errors = validate_definition(escaped, FIXTURES)
    assert any("escapes allowed authority roots" in error for error in errors)

    wrong_route = validate_definition(raw, FIXTURES, allowed_reporting_tasks=["another-task"])
    assert any("outside the allowed dispatcher route" in error for error in wrong_route)


def test_hash_mismatch_and_unsafe_effect_contract_are_rejected() -> None:
    raw = load_definition(DEFINITION)
    raw["content_hash"] = "0" * 64
    with pytest.raises(DefinitionError, match="content_hash"):
        normalize_definition(raw)

    raw = load_definition(DEFINITION)
    raw["procedure"]["external_effect"] = {"mode": "idempotency_key", "idempotency_key": "random"}
    with pytest.raises(DefinitionError, match="stable occurrence"):
        normalize_definition(raw)


def test_stable_identifier_and_required_contract_are_enforced() -> None:
    raw = load_definition(DEFINITION)
    raw["workflow_id"] = "Bad_ID"
    assert validate_definition(raw, FIXTURES) == [
        "workflow_id must contain lowercase letters, numbers, and hyphens"
    ]

    raw = load_definition(DEFINITION)
    del raw["evidence_retention"]
    assert validate_definition(raw, FIXTURES) == ["missing required field: evidence_retention"]

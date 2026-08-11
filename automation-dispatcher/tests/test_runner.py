from __future__ import annotations

import sys
from pathlib import Path

import pytest

from automation_dispatcher.runner import ProcedureError, execute_procedure


def test_agent_procedure_returns_host_action(tmp_path: Path) -> None:
    result = execute_procedure(
        {
            "procedure": {"kind": "skill", "reference": "$bear"},
            "authority_refs": ["bear://config"],
        },
        occurrence_key="occurrence",
        run_id="run",
        approved_roots=[tmp_path],
    )
    assert result.status == "action_required"
    assert result.host_action == {
        "kind": "skill",
        "reference": "$bear",
        "run_id": "run",
        "occurrence_key": "occurrence",
        "authority_refs": ["bear://config"],
    }


def test_script_receives_stable_occurrence_key(tmp_path: Path) -> None:
    script = tmp_path / "procedure.py"
    script.write_text(
        "import os\nprint(os.environ['AUTOMATION_DISPATCHER_OCCURRENCE_KEY'])\n",
        encoding="utf-8",
    )
    result = execute_procedure(
        {"procedure": {"kind": "script", "reference": str(script)}},
        occurrence_key="stable-key",
        run_id="run",
        approved_roots=[tmp_path],
    )
    assert result.status == "succeeded"
    assert result.summary == "stable-key"
    assert result.evidence[0].startswith("stdout:sha256:")
    assert "stable-key" not in result.evidence[0]


def test_script_path_must_be_under_approved_root(tmp_path: Path) -> None:
    with pytest.raises(ProcedureError, match="outside approved roots"):
        execute_procedure(
            {"procedure": {"kind": "script", "reference": sys.executable}},
            occurrence_key="key",
            run_id="run",
            approved_roots=[tmp_path],
        )


def test_relative_script_resolves_from_definition_directory(tmp_path: Path, monkeypatch) -> None:
    definition_dir = tmp_path / "definitions"
    definition_dir.mkdir()
    script = definition_dir / "procedure.py"
    script.write_text("print('relative-ok')\n", encoding="utf-8")
    unrelated = tmp_path / "heartbeat-cwd"
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)
    result = execute_procedure(
        {"procedure": {"kind": "script", "reference": "procedure.py"}},
        occurrence_key="key",
        run_id="run",
        approved_roots=[definition_dir],
        base_dir=definition_dir,
    )
    assert unrelated != definition_dir
    assert result.status == "succeeded"
    assert result.summary == "relative-ok"

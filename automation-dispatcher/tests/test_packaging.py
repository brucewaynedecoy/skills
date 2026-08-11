from __future__ import annotations

from pathlib import Path
import argparse
import tomllib

from automation_dispatcher.cli import build_parser


ROOT = Path(__file__).resolve().parents[1]


def test_pep621_and_console_entrypoint() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["requires-python"] == ">=3.11"
    assert project["project"]["scripts"]["automation-dispatcher"] == "automation_dispatcher.cli:main"
    assert project["build-system"]["build-backend"] == "uv_build"


def test_migrations_are_package_resources() -> None:
    migrations = ROOT / "src" / "automation_dispatcher" / "migrations"
    assert (migrations / "__init__.py").is_file()
    assert {path.name for path in migrations.glob("[0-9][0-9][0-9][0-9]_*.sql")} >= {
        "0001_initial.sql",
        "0002_collection_model.sql",
    }


def test_build_config_excludes_runtime_state() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    backend = project["tool"]["uv"]["build-backend"]
    excludes = set(backend["source-exclude"]) & set(backend["wheel-exclude"])
    assert {"*.sqlite3", "*-journal", "*-wal", "*-shm", ".automation-dispatcher/**"} <= excludes
    assert {"SKILL.md", "agents/**", "references/**", "workflows/**"} <= set(backend["source-include"])


def _option_strings(parser: argparse.ArgumentParser) -> set[str]:
    return {
        option
        for action in parser._actions
        for option in action.option_strings
    }


def test_installed_cli_contract_includes_collection_commands() -> None:
    parser = build_parser()
    subcommands = next(
        action.choices
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    assert {"init", "schedule-revise", "route-revise", "register", "run"} <= set(subcommands)

    init_options = _option_strings(subcommands["init"])
    assert {
        "--dispatcher-id",
        "--name",
        "--description",
        "--schedule",
        "--timezone",
        "--max-lateness-seconds",
        "--catch-up",
        "--expected-task-id",
        "--expected-working-directory",
        "--heartbeat-schedule",
        "--actor",
        "--reason",
    } <= init_options
    assert "--cadence" not in init_options

    schedule_options = _option_strings(subcommands["schedule-revise"])
    assert {
        "--dispatcher-id",
        "--schedule",
        "--timezone",
        "--max-lateness-seconds",
        "--catch-up",
        "--heartbeat-schedule",
        "--actor",
        "--reason",
    } <= schedule_options


def test_user_documentation_uses_generic_collection_contract() -> None:
    paths = (
        ROOT / "SKILL.md",
        ROOT / "README.md",
        ROOT / "references" / "operator-runbook.md",
        ROOT / "references" / "registry-contract.md",
        ROOT / "references" / "workflow-definition.md",
    )
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert "workflow collection" in combined.lower()
    assert "schedule-revise" in combined
    assert '"schema_version": 2' in combined
    assert "--cadence" not in combined
    assert "dispatcher_id`: `daily` or `weekly`" not in combined

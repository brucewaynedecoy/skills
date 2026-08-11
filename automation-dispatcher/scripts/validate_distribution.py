#!/usr/bin/env python3
"""Validate automation-dispatcher wheel and source-distribution contents."""

from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
import tarfile
import zipfile


MIGRATION_SUFFIXES = (
    "automation_dispatcher/migrations/0001_initial.sql",
    "automation_dispatcher/migrations/0002_collection_model.sql",
)
SDIST_REQUIRED_SUFFIXES = (
    "README.md",
    "SKILL.md",
    "agents/openai.yaml",
    "references/operator-runbook.md",
    "references/registry-contract.md",
    "references/workflow-definition.md",
)
FORBIDDEN_SUFFIXES = (".sqlite", ".sqlite3", ".db", "-journal", "-wal", "-shm")
FORBIDDEN_PARTS = {".automation-dispatcher", "backups", "exports"}


def archive_names(path: Path) -> list[str]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return archive.namelist()
    if path.name.endswith((".tar.gz", ".tgz")):
        with tarfile.open(path, "r:gz") as archive:
            return archive.getnames()
    raise ValueError(f"unsupported distribution archive: {path}")


def is_forbidden(name: str) -> bool:
    path = PurePosixPath(name)
    basename = path.name.lower()
    return (
        any(basename.endswith(suffix) for suffix in FORBIDDEN_SUFFIXES)
        or basename == ".env"
        or basename.startswith(".env.")
        or bool(FORBIDDEN_PARTS.intersection(path.parts))
    )


def validate(path: Path) -> list[str]:
    names = archive_names(path)
    errors: list[str] = []
    for suffix in MIGRATION_SUFFIXES:
        if not any(name.endswith(suffix) for name in names):
            errors.append(f"{path.name}: missing packaged migration {suffix}")
    forbidden = sorted(name for name in names if is_forbidden(name))
    if forbidden:
        errors.append(f"{path.name}: forbidden runtime state: {', '.join(forbidden)}")
    if not path.suffix == ".whl":
        for suffix in SDIST_REQUIRED_SUFFIXES:
            if not any(name.endswith(suffix) for name in names):
                errors.append(f"{path.name}: missing source skill resource {suffix}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archives", nargs="+", type=Path)
    args = parser.parse_args()
    errors: list[str] = []
    for archive in args.archives:
        errors.extend(validate(archive))
    if errors:
        for error in errors:
            print(error)
        return 1
    print(f"validated {len(args.archives)} distribution archive(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

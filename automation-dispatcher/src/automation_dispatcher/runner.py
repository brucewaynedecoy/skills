"""Low-freedom workflow procedure execution.

The Python process executes only registered deterministic scripts. Agent and
skill procedures are returned as host-adapter actions so the Codex host can
invoke them with the registered authority references.
"""

from __future__ import annotations

import os
import hashlib
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


MAX_CAPTURE_BYTES = 64 * 1024


class ProcedureError(RuntimeError):
    """Raised when a registered procedure cannot be executed safely."""


@dataclass(frozen=True)
class ProcedureResult:
    status: str
    summary: str
    evidence: list[str]
    returncode: int | None = None
    host_action: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _inside(path: Path, roots: Sequence[Path]) -> bool:
    return any(path == root or root in path.parents for root in roots)


def _bounded_text(value: bytes) -> str:
    if len(value) > MAX_CAPTURE_BYTES:
        value = value[:MAX_CAPTURE_BYTES] + b"\n[output truncated]"
    return value.decode("utf-8", errors="replace")


def execute_procedure(
    definition: Mapping[str, Any],
    *,
    occurrence_key: str,
    run_id: str,
    approved_roots: Sequence[str | Path],
    base_dir: str | Path | None = None,
    timeout_seconds: int = 900,
) -> ProcedureResult:
    """Execute a registered procedure or return a host-adapter action.

    Script references are resolved strictly, constrained to ``approved_roots``,
    and invoked without a shell. The stable occurrence key is supplied through
    the environment for external-effect idempotency.
    """

    procedure = definition.get("procedure")
    if not isinstance(procedure, Mapping):
        raise ProcedureError("definition has no normalized procedure")
    kind = str(procedure.get("kind", ""))
    reference = str(procedure.get("reference", ""))
    if kind in {"agent", "skill", "documented"}:
        return ProcedureResult(
            status="action_required",
            summary=f"Host adapter must invoke registered {kind} procedure",
            evidence=[],
            host_action={
                "kind": kind,
                "reference": reference,
                "run_id": run_id,
                "occurrence_key": occurrence_key,
                "authority_refs": list(definition.get("authority_refs", [])),
            },
        )
    if kind != "script":
        raise ProcedureError(f"unsupported procedure kind: {kind!r}")

    roots = [Path(root).expanduser().resolve(strict=True) for root in approved_roots]
    reference_path = Path(reference).expanduser()
    if not reference_path.is_absolute():
        reference_path = Path(base_dir) / reference_path if base_dir is not None else reference_path
    script = reference_path.resolve(strict=True)
    if not roots or not _inside(script, roots):
        raise ProcedureError("procedure reference is outside approved roots")
    if not script.is_file():
        raise ProcedureError("procedure reference is not a regular file")

    command = [str(script)]
    if script.suffix == ".py":
        command.insert(0, sys.executable)
    elif not os.access(script, os.X_OK):
        raise ProcedureError("non-Python procedure is not executable")

    environment = os.environ.copy()
    environment.update(
        {
            "AUTOMATION_DISPATCHER_RUN_ID": run_id,
            "AUTOMATION_DISPATCHER_OCCURRENCE_KEY": occurrence_key,
        }
    )
    try:
        completed = subprocess.run(
            command,
            cwd=str(script.parent),
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ProcedureError(f"procedure timed out after {timeout_seconds}s") from exc

    stdout = _bounded_text(completed.stdout).strip()
    stderr = _bounded_text(completed.stderr).strip()
    evidence = []
    if stdout:
        evidence.append(f"stdout:sha256:{hashlib.sha256(stdout.encode('utf-8')).hexdigest()}")
    if stderr:
        evidence.append(f"stderr:sha256:{hashlib.sha256(stderr.encode('utf-8')).hexdigest()}")
    summary = stdout.splitlines()[-1] if stdout else "procedure produced no stdout"
    status = "succeeded" if completed.returncode == 0 else "failed"
    return ProcedureResult(
        status=status,
        summary=summary[:1000],
        evidence=evidence,
        returncode=completed.returncode,
    )

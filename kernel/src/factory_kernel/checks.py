"""Check runner (spec §11.1).

The kernel — never the agent — runs the project's real commands and records the
raw outcome. An agent's claim that checks pass is not evidence.

``checks.json`` declares a command per check id::

    {"lint": {"cmd": "npm run lint", "required": true}, ...}

``required`` may be a bool or a conditional string such as ``"if_ui_changed"``.
Conditional checks are not treated as required in this reference slice.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Union

from .atomic import read_json
from .cancel import run_cancellable

MAX_OUTPUT_LINES = 40


class CheckError(Exception):
    pass


@dataclass
class CheckResult:
    id: str
    cmd: str
    required: bool
    exit_code: Optional[int]
    passed: bool
    output: str
    duration_s: float
    timed_out: bool = False
    cancelled: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "cmd": self.cmd,
            "required": self.required,
            "exit_code": self.exit_code,
            "passed": self.passed,
            "timed_out": self.timed_out,
            "cancelled": self.cancelled,
            "duration_s": round(self.duration_s, 3),
            "output": self.output,
        }


def _is_required(value: Union[bool, str, None]) -> bool:
    return value is True


def _trim(text: str, max_lines: int = MAX_OUTPUT_LINES) -> str:
    lines = text.rstrip().splitlines()
    if len(lines) <= max_lines:
        return "\n".join(lines)
    half = max_lines // 2
    return "\n".join(lines[:half] + ["… (truncated) …"] + lines[-half:])


def load_checks(project_dir: Union[str, Path]) -> dict:
    checks = read_json(Path(project_dir) / "checks.json")
    if checks is None:
        raise CheckError(f"No checks.json in {project_dir}")
    if not isinstance(checks, dict):
        raise CheckError("checks.json must be an object")
    return checks


def run_one(
    check_id: str,
    spec: dict,
    worktree: Union[str, Path],
    timeout: int = 600,
    extra_env: Optional[dict] = None,
    cancel: Optional[Callable[[], bool]] = None,
) -> CheckResult:
    cmd = spec.get("cmd", "")
    required = _is_required(spec.get("required"))
    start = time.monotonic()
    timed_out = False
    cancelled = False
    outcome = run_cancellable(
        cmd,
        shell=True,
        cwd=str(worktree),
        timeout=timeout,
        env={**os.environ, **(extra_env or {})},
        cancel=cancel,
    )
    if outcome.cancelled:
        # The operator stopped the job: the check's process tree is dead and
        # the result is "cancelled", not a verdict about the code.
        cancelled = True
        exit_code = None
        output = f"check '{check_id}' cancelled by operator"
    elif outcome.timed_out:
        exit_code = None
        timed_out = True
        output = f"check '{check_id}' timed out after {timeout}s"
    else:
        exit_code = outcome.returncode
        output = (outcome.stdout or "") + (outcome.stderr or "")
    duration = time.monotonic() - start
    return CheckResult(
        id=check_id,
        cmd=cmd,
        required=required,
        exit_code=exit_code,
        passed=(exit_code == 0) and not timed_out and not cancelled,
        output=_trim(output),
        duration_s=duration,
        timed_out=timed_out,
        cancelled=cancelled,
    )


def _run_required_checks(
    checks: dict,
    worktree: Union[str, Path],
    timeout: int,
    extra_env: Optional[dict] = None,
    cancel: Optional[Callable[[], bool]] = None,
) -> CheckResult:
    """The ``required_checks`` meta-check passes iff every required check passes."""
    required_ids = [
        cid for cid, spec in checks.items()
        if cid != "required_checks" and spec.get("required") is True
    ]
    inner = [
        run_one(cid, checks[cid], worktree, timeout, extra_env=extra_env,
                cancel=cancel)
        for cid in required_ids
    ]
    failed = [r.id for r in inner if not r.passed]
    return CheckResult(
        id="required_checks",
        cmd="(aggregate of required checks)",
        required=True,
        exit_code=0 if not failed else 1,
        passed=not failed,
        output="required checks: " + (", ".join(failed) if failed else "all passed"),
        duration_s=sum(r.duration_s for r in inner),
        cancelled=any(r.cancelled for r in inner),
    )


def run_checks(
    checks: dict,
    ids: list[str],
    worktree: Union[str, Path],
    timeout: int = 600,
    extra_env: Optional[dict] = None,
    cancel: Optional[Callable[[], bool]] = None,
) -> list[CheckResult]:
    """Run the named checks. A declared-but-undefined check is a failure."""
    results: list[CheckResult] = []
    for check_id in ids:
        if check_id == "required_checks":
            results.append(
                _run_required_checks(checks, worktree, timeout,
                                     extra_env=extra_env, cancel=cancel))
            continue
        spec = checks.get(check_id)
        if spec is None:
            results.append(
                CheckResult(
                    id=check_id,
                    cmd="",
                    required=True,
                    exit_code=None,
                    passed=False,
                    output=f"check '{check_id}' is declared but not defined in checks.json",
                    duration_s=0.0,
                )
            )
            continue
        results.append(
            run_one(check_id, spec, worktree, timeout, extra_env=extra_env,
                    cancel=cancel))
    return results


def summarise(results: list[CheckResult]) -> dict:
    failed = [r.id for r in results if not r.passed]
    required_failed = [r.id for r in results if not r.passed and r.required]
    return {
        "passed": len(required_failed) == 0,
        "failed": failed,
        "required_failed": required_failed,
    }


def fingerprint(results: list[CheckResult], extra: str = "") -> str:
    """Stable failure fingerprint: failing check ids + normalized signatures."""
    import hashlib

    parts = sorted(f"{r.id}:{r.exit_code}:{r.timed_out}" for r in results if not r.passed)
    if extra:
        parts.append(extra.strip().splitlines()[0] if extra.strip() else "")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]

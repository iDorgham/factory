#!/usr/bin/env python3
"""Generic CLI agent adapter (spec §20) — the factory's first live backend.

Two modes:

1. **Deterministic (default).** When ``FACTORY_CLI_AGENT_CMD`` is unset, the
   adapter writes the declared contract files itself with fixed content and
   reports estimated usage. This keeps the kernel test suite hermetic.

2. **Live command.** When ``FACTORY_CLI_AGENT_CMD`` is set, it is executed as
   a shell command with ``cwd`` set to the job worktree, the run request as
   JSON on stdin, and ``FACTORY_ATTEMPT_DIR`` / ``FACTORY_BRIEF`` in the
   environment. Its stdout is parsed as an NDJSON event stream
   (``progress | tool_use | file_written | question | usage | heartbeat |
   done | error``) and forwarded to the kernel; non-JSON lines become
   ``progress`` events. Any agent — ``opencode run``, ``claude -p``, a local
   script — can serve as the backend if it speaks (or is wrapped to speak)
   this protocol and writes the declared contract files.

Honesty rules for live mode: a failed/timed-out command with missing outputs
is reported as an ``error`` (``fatal`` for failures, ``transient`` for
timeouts) so the kernel retries or fails the attempt instead of treating
silence as success. Placeholder backfill is never written.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

EVENT_TYPES = {
    "progress", "tool_use", "file_written", "question",
    "usage", "heartbeat", "done", "error",
}

# Upper bound on forwarded command output lines; beyond this the adapter
# summarizes instead of growing the event stream without bound.
MAX_FORWARDED_LINES = 2000


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _write_deterministic(stage: str, attempt_n: int, outputs: Path, produces: list) -> int:
    """Write the declared contract files with fixed content. Returns count."""
    n = 0
    for name in produces:
        if name.startswith("git:") or name.endswith("/"):
            continue
        p = outputs / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            f"# {name}\n\nCLI agent output for stage {stage} attempt {attempt_n}.\n",
            encoding="utf-8",
        )
        emit({"type": "file_written", "path": str(p)})
        n += 1
    return n


def _emit_usage(model: str, n_in: int, n_out: int, estimated: bool) -> None:
    emit({"type": "usage", "model": model, "input_tokens": n_in,
          "output_tokens": n_out, "estimated": estimated})


def _missing(produces: list, outputs: Path) -> list[str]:
    missing = []
    for name in produces:
        if name.startswith("git:") or name.endswith("/"):
            continue
        if not (outputs / name).exists():
            missing.append(name)
    return missing


def main() -> int:
    try:
        req = json.load(sys.stdin)
    except Exception as e:
        emit({"type": "error", "class": "fatal", "message": str(e)})
        return 1

    attempt_dir = Path(req["attempt_dir"])
    outputs = attempt_dir / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    worktree = Path(req.get("worktree", attempt_dir))

    stage = req.get("stage", "?")
    attempt_n = req.get("attempt", 1)
    run_id = req.get("run_id", "")
    produces = req.get("produces", [])

    emit({"type": "progress", "message": f"cli-agent: stage={stage} attempt={attempt_n}"})

    # Idempotent start: a repeated run_id replays usage + done without
    # re-executing (spec §20.2). Declared as the `resume` capability.
    marker = attempt_dir / ".cli_agent_run_id"
    if run_id and marker.exists() and marker.read_text(encoding="utf-8") == run_id:
        _emit_usage("cli-agent-1", 1, 1, True)
        emit({"type": "done"})
        return 0

    cmd = os.environ.get("FACTORY_CLI_AGENT_CMD")
    if not cmd:
        n = _write_deterministic(stage, attempt_n, outputs, produces)
        if run_id:
            marker.write_text(run_id, encoding="utf-8")
        _emit_usage("cli-agent-1", 10 * max(n, 1), 20 * max(n, 1), True)
        emit({"type": "done"})
        return 0

    return _run_live(cmd, req, stage, attempt_n, run_id, produces,
                     attempt_dir, outputs, worktree)


def _run_live(cmd: str, req: dict, stage: str, attempt_n: int, run_id: str,
              produces: list, attempt_dir: Path, outputs: Path, worktree: Path) -> int:
    budget = req.get("budget") or {}
    try:
        minutes = int(budget.get("minutes", 5))
    except (TypeError, ValueError):
        minutes = 5
    timeout = min(max(minutes * 60, 60), 600)
    override = os.environ.get("FACTORY_CLI_AGENT_TIMEOUT_S")
    if override:
        try:
            timeout = max(int(override), 1)
        except ValueError:
            pass

    prompt_path = attempt_dir / ".cli_agent_prompt.txt"
    prompt_path.write_text(req.get("brief", ""), encoding="utf-8")

    env = dict(os.environ)
    env["FACTORY_ATTEMPT_DIR"] = str(attempt_dir)
    env["FACTORY_BRIEF"] = req.get("brief", "")

    try:
        proc = subprocess.run(
            cmd, shell=True, cwd=str(worktree), env=env,
            input=json.dumps(req), capture_output=True, text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        emit({"type": "error", "class": "transient",
              "message": f"command timed out after {timeout}s"})
        return 2
    except Exception as e:  # e.g. bad cwd — retryable, not a verdict
        emit({"type": "error", "class": "transient", "message": str(e)})
        return 2

    forwarded_done = _forward_stream(proc.stdout or "")
    saw_usage = forwarded_done["usage"]
    saw_done = forwarded_done["done"]

    missing = _missing(produces, outputs)
    if proc.returncode != 0 and missing:
        detail = (proc.stderr or "").strip()[-2000:]
        emit({"type": "error", "class": "fatal",
              "message": f"command exited {proc.returncode}; "
                         f"missing: {', '.join(missing)}"
                         + (f"; stderr: {detail}" if detail else "")})
        return 1
    if proc.returncode == 0 and missing:
        emit({"type": "error", "class": "fatal",
              "message": f"command exited 0 but missing: {', '.join(missing)}"})
        return 1
    if proc.returncode != 0:
        emit({"type": "progress",
              "message": f"command exited {proc.returncode} "
                         "but all contract files are present"})

    if run_id:
        marker = attempt_dir / ".cli_agent_run_id"
        marker.write_text(run_id, encoding="utf-8")
    if not saw_usage:
        n = max(len([p for p in produces
                     if not p.startswith('git:') and not p.endswith('/')]), 1)
        _emit_usage("cli-agent-1", 10 * n, 20 * n, True)
    if not saw_done:
        emit({"type": "done"})
    return 0


def _forward_stream(stdout: str) -> dict:
    """Forward the command's NDJSON stream; non-JSON lines become progress."""
    seen = {"usage": False, "done": False}
    for index, line in enumerate(stdout.splitlines()):
        line = line.strip()
        if not line:
            continue
        if index >= MAX_FORWARDED_LINES:
            emit({"type": "progress",
                  "message": "command output truncated after "
                             f"{MAX_FORWARDED_LINES} lines"})
            break
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            emit({"type": "progress", "message": line[:2000]})
            continue
        if not isinstance(obj, dict) or obj.get("type") not in EVENT_TYPES:
            emit({"type": "progress", "message": line[:2000]})
            continue
        emit(obj)
        if obj["type"] == "usage":
            seen["usage"] = True
        elif obj["type"] == "done":
            seen["done"] = True
    return seen


if __name__ == "__main__":
    sys.exit(main())

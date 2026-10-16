#!/usr/bin/env python3
"""Echo adapter — a deterministic stand-in for a real coding agent.

Reads a run request as JSON on stdin, writes placeholder contract files into
the attempt directory, reports usage, and emits an NDJSON event stream on
stdout. It never touches state files (spec §20.2 output discipline).

Used for kernel conformance tests and for exercising the stage graph without a
model provider.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def main() -> int:
    try:
        request = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as e:
        emit({"type": "error", "class": "fatal", "message": f"bad request: {e}"})
        return 1

    attempt_dir = Path(request["attempt_dir"])
    outputs = attempt_dir / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)

    stage = request.get("stage", "?")
    attempt = request.get("attempt", 1)
    emit({"type": "progress", "message": f"echo: stage={stage} attempt={attempt}"})

    written = 0
    for name in request.get("produces", []):
        if name.startswith("git:") or name.endswith("/"):
            continue
        path = outputs / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"# {name}\n\nEcho output for stage '{stage}' (attempt {attempt}).\n",
            encoding="utf-8",
        )
        written += 1
        emit({"type": "file_written", "path": str(path)})

    emit(
        {
            "type": "usage",
            "model": "echo-1",
            "input_tokens": 10 * max(written, 1),
            "output_tokens": 20 * max(written, 1),
            "estimated": True,
        }
    )
    emit({"type": "done"})
    return 0


if __name__ == "__main__":
    sys.exit(main())

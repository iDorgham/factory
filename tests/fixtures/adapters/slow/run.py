#!/usr/bin/env python3
"""Conformance test fixture adapter.

Behaviours, driven by the run request:
- emits ``heartbeat`` events while it works (so heartbeat loss / cancel are testable)
- is idempotent on a repeated ``run_id`` (resume): it records the run id and, if
  seen again, finishes without re-writing outputs
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def main() -> int:
    request = json.load(sys.stdin)
    attempt_dir = Path(request["attempt_dir"])
    outputs = attempt_dir / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    run_id = request.get("run_id", "")

    marker = attempt_dir / ".slow_run_id"
    emit({"type": "progress", "message": "slow: starting"})

    if marker.exists() and marker.read_text(encoding="utf-8") == run_id:
        # Idempotent start: already executed this run_id — do not re-write outputs.
        emit({"type": "usage", "model": "slow-1", "input_tokens": 1,
              "output_tokens": 1, "estimated": True})
        emit({"type": "done"})
        return 0

    # Work with periodic heartbeats (fast enough for tests, well under 30s).
    for _ in range(20):
        emit({"type": "heartbeat", "ts": time.time()})
        time.sleep(0.05)

    written = 0
    for name in request.get("produces", []):
        if name.startswith("git:") or name.endswith("/"):
            continue
        path = outputs / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {name}\n\nslow output.\n", encoding="utf-8")
        written += 1
        emit({"type": "file_written", "path": str(path)})

    marker.write_text(run_id, encoding="utf-8")
    emit({"type": "usage", "model": "slow-1", "input_tokens": 10 * max(written, 1),
          "output_tokens": 20 * max(written, 1), "estimated": True})
    emit({"type": "done"})
    return 0


if __name__ == "__main__":
    sys.exit(main())

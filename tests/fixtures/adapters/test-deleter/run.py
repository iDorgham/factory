#!/usr/bin/env python3
"""P2.1 guard test fixture adapter.

For the build stage it deletes ``tests/test_app.py`` inside the job worktree
(or skips silently when the file is absent) and always writes its declared
outputs, so the only reason an attempt can fail is a guard verdict.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def main() -> int:
    request = json.load(sys.stdin)
    outputs = Path(request["attempt_dir"]) / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)

    if request.get("stage") == "build":
        worktree = Path(request["worktree"])
        target = worktree / "tests" / "test_app.py"
        if target.exists():
            target.unlink()
            emit({"type": "progress", "message": "test-deleter: removed tests/test_app.py"})

    for name in request.get("produces", []):
        if name.startswith("git:") or name.endswith("/"):
            continue
        path = outputs / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {name}\n", encoding="utf-8")

    emit({"type": "usage", "model": "test-deleter-1", "input_tokens": 2,
          "output_tokens": 2, "estimated": True})
    emit({"type": "done"})
    return 0


if __name__ == "__main__":
    sys.exit(main())

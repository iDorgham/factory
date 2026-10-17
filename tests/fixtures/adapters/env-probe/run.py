#!/usr/bin/env python3
"""P2.3 sandbox test fixture adapter.

Reports what the adapter subprocess can actually see — its process env and
its cwd — inside usage, so tests can assert the sandbox contract end-to-end
without trusting the probe itself (the kernel writes usage.json verbatim).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def main() -> int:
    request = json.load(sys.stdin)
    outputs = Path(request["attempt_dir"]) / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)

    for name in request.get("produces", []):
        if name.startswith("git:") or name.endswith("/"):
            continue
        path = outputs / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {name}\n", encoding="utf-8")

    secret_names = ["GITHUB_TOKEN", "SSH_AUTH_SOCK", "HTTP_PROXY",
                    "SECRET_API_KEY", "AWS_SECRET_ACCESS_KEY"]
    emit({
        "type": "progress",
        "message": f"env-probe: stage={request.get('stage', '?')}",
    })
    emit({
        "type": "usage",
        "model": "probe-1",
        "input_tokens": 1,
        "output_tokens": 1,
        "seen": {name: os.environ.get(name) is not None
                 for name in secret_names},
        "cwd": os.getcwd(),
        "estimated": True,
    })
    emit({"type": "done"})
    return 0


if __name__ == "__main__":
    sys.exit(main())

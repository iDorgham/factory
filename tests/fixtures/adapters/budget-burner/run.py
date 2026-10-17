#!/usr/bin/env python3
"""P2.2 budget test fixture adapter.

Emits usage like a real model backend. Uses tiny token counts everywhere
except the build stage, where the count comes from FACTORY_BUDGET_INPUT_TOKENS
(default 2_000_000 — at the shipped $3/1M default rate that is $6.00 input,
over the build stage's $5.00 hard limit). For the soft case set, e.g.,
1_600_000 ($4.80, between the $4.00 soft and $5.00 hard limits).
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

    stage = request.get("stage", "?")
    input_tokens = (
        int(os.environ.get("FACTORY_BUDGET_INPUT_TOKENS", "2000000"))
        if stage == "build" else 1000
    )

    for name in request.get("produces", []):
        if name.startswith("git:") or name.endswith("/"):
            continue
        path = outputs / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {name}\n", encoding="utf-8")

    emit({"type": "progress", "message": f"budget-burner: stage={stage} "
                                         f"input_tokens={input_tokens}"})
    emit({"type": "usage", "model": "burner-1", "input_tokens": input_tokens,
          "output_tokens": 500, "estimated": True})
    emit({"type": "done"})
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Fixture live agent for the cli-agent adapter (tests + P1 E2E proof).

Speaks the adapter's live-command protocol: reads the run request as JSON on
stdin, writes every declared contract file with substantive content, records a
file in the job worktree, and reports its work as NDJSON on stdout. Stands in
for a real CLI (``opencode run``, ``claude -p``) so the full job loop can be
exercised against a live command while staying hermetic.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _write_synthetic_visual(outputs: Path, stage: str) -> None:
    """Synthetic visual-evidence manifest for plumbing tests (NOT evidence).

    Labeled `"synthetic": true` so the dashboard marks it as a fixture.
    """
    entries = []
    for viewport, theme in (("1280x800", "light"), ("1280x800", "dark"),
                            ("390x844", "light")):
        rel = f"visual/{viewport}-{theme}.png"
        path = outputs / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x89PNG\r\n\x1a\nSYNTHETIC-FIXTURE-NOT-A-SCREENSHOT\n")
        entries.append({"viewport": viewport, "theme": theme, "file": rel})
    (outputs / "visual.json").write_text(
        json.dumps({"synthetic": True, "entries": entries}, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    req = json.load(sys.stdin)
    attempt_dir = Path(os.environ.get("FACTORY_ATTEMPT_DIR", req["attempt_dir"]))
    outputs = attempt_dir / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    worktree = Path(req.get("worktree", attempt_dir))
    stage = req.get("stage", "?")
    attempt = req.get("attempt", 1)

    emit({"type": "progress", "message": f"live-agent: working stage={stage}"})
    emit({"type": "tool_use", "tool": "write", "detail": f"stage {stage}"})

    for name in req.get("produces", []):
        if name.startswith("git:") or name.endswith("/"):
            continue
        path = outputs / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"# {name}\n\nLive agent output for stage '{stage}' "
            f"(attempt {attempt}).\n",
            encoding="utf-8",
        )
        emit({"type": "file_written", "path": str(path)})

    marker = worktree / "src" / f"{stage}.md"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        f"# {stage}\n\nProduced by the live fixture agent (attempt {attempt}).\n",
        encoding="utf-8",
    )
    emit({"type": "file_written", "path": str(marker)})

    if os.environ.get("FACTORY_FIXTURE_HTML") == "1":
        # A tiny real web page (light+dark aware) so the `visual` check has
        # something to capture at declared viewports.
        page = worktree / "index.html"
        page.write_text(
            "<!doctype html><html><head><meta charset=\"utf-8\">"
            "<title>Landing</title>"
            "<style>body{margin:0;font-family:sans-serif;background:#fff;"
            "color:#111;}main{min-height:100vh;display:flex;"
            "flex-direction:column;align-items:center;justify-content:center;}"
            "@media (prefers-color-scheme:dark){body{background:#111;"
            "color:#fff}}</style></head><body><main><h1>Fresh Landing</h1>"
            "<p>Built by the factory (attempt " + str(attempt) + ").</p>"
            "</main></body></html>",
            encoding="utf-8",
        )
        emit({"type": "file_written", "path": str(page)})

    if os.environ.get("FACTORY_FIXTURE_VISUAL") == "1":
        _write_synthetic_visual(outputs, stage)

    emit({"type": "usage", "model": "fixture-live-1", "input_tokens": 120,
          "output_tokens": 240, "estimated": False})
    emit({"type": "done"})
    return 0


if __name__ == "__main__":
    sys.exit(main())

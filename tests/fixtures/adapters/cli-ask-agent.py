#!/usr/bin/env python3
"""Fixture questioning agent for the cli-agent adapter (question-budget tests).

Reads the run request as JSON on stdin and behaves according to
``FACTORY_FIXTURE_QMODE``:

- ``once`` (default): ask one blocking question unless `questions.md` in the
  job dir already contains an answer (`### A:`), in which case do the work.
- ``always``: ask the same blocking question on every attempt (tests repeat
  detection — repeats must not burn the budget twice).
- ``unique``: ask two new blocking questions per attempt (tests budget
  exhaustion).
- ``info``: ask non-blocking (`kind: info`) questions only (never counts).

Question text/options come from ``FACTORY_FIXTURE_QUESTION`` /
``FACTORY_FIXTURE_OPTIONS`` (comma-separated) so tests control repetition.
When asking, no contract files are written, so the attempt honestly fails and
the engine parks the job as `blocked`. When working, all contract files are
written like `cli-echo-agent.py`.
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


def _write_outputs(outputs: Path, produces: list, stage: str, attempt: int) -> None:
    for name in produces:
        if name.startswith("git:") or name.endswith("/"):
            continue
        path = outputs / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"# {name}\n\nAnswered-agent output for stage '{stage}' "
            f"(attempt {attempt}).\n",
            encoding="utf-8",
        )
        emit({"type": "file_written", "path": str(path)})


def _ask(qid: str, text: str, options: list, kind: str = "blocking") -> None:
    emit({"type": "question", "id": qid, "kind": kind, "text": text,
          "options": options})


def main() -> int:
    req = json.load(sys.stdin)
    attempt_dir = Path(req["attempt_dir"])
    outputs = attempt_dir / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    job_dir = attempt_dir.parents[2]
    stage = req.get("stage", "?")
    attempt = req.get("attempt", 1)
    produces = req.get("produces", [])

    mode = os.environ.get("FACTORY_FIXTURE_QMODE", "once")
    base_text = os.environ.get(
        "FACTORY_FIXTURE_QUESTION", "Which layout should the hero use?")
    options = [o.strip() for o in
               os.environ.get("FACTORY_FIXTURE_OPTIONS", "Centered,Split").split(",")
               if o.strip()]

    questions_md = job_dir / "questions.md"
    answered = "### A:" in (questions_md.read_text(encoding="utf-8")
                            if questions_md.exists() else "")

    emit({"type": "progress",
          "message": f"ask-agent: mode={mode} stage={stage} attempt={attempt}"})

    if mode == "info":
        _ask(f"info-{stage}", "Heads up: build takes a while.", [], kind="info")
        _write_outputs(outputs, produces, stage, attempt)
    elif mode == "unique":
        _ask(f"q-{stage}-{attempt}-a", f"{base_text} (a{attempt}.1)", options)
        _ask(f"q-{stage}-{attempt}-b", f"{base_text} (a{attempt}.2)", options)
    elif mode == "always":
        _ask("q-repeat", base_text, options)
        if answered:
            # Repeat after the answer: dedupe must swallow it, work proceeds.
            _write_outputs(outputs, produces, stage, attempt)
    else:  # once
        if answered:
            _write_outputs(outputs, produces, stage, attempt)
        else:
            _ask("q-hero", base_text, options)
            marker = Path(req.get("worktree", attempt_dir)) / "src" / f"{stage}.md"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(f"# {stage}\n\nAsked, awaiting answer.\n",
                              encoding="utf-8")
            emit({"type": "file_written", "path": str(marker)})

    if os.environ.get("FACTORY_FIXTURE_VISUAL") == "1":
        _write_synthetic_visual(outputs, stage)

    emit({"type": "usage", "model": "fixture-ask-1", "input_tokens": 60,
          "output_tokens": 120, "estimated": False})
    emit({"type": "done"})
    return 0


if __name__ == "__main__":
    sys.exit(main())

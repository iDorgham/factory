"""Tests for the Solo question budget (P1): ask → block → answer → resume.

Drives the engine with the `cli-agent` adapter pointed at the fixture
questioning agent (`tests/fixtures/adapters/cli-ask-agent.py`), which stands
in for a real CLI that asks blocking questions.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from factory_kernel.dashboard import build_view
from factory_kernel.schemas import SchemaStore

REPO_ROOT = Path(__file__).resolve().parents[1]
ASK_AGENT = REPO_ROOT / "tests" / "fixtures" / "adapters" / "cli-ask-agent.py"

CMD_ENV = "FACTORY_CLI_AGENT_CMD"
QMODE_ENV = "FACTORY_FIXTURE_QMODE"


@pytest.fixture
def ask_cmd(monkeypatch):
    monkeypatch.setenv(CMD_ENV, f'"{sys.executable}" "{ASK_AGENT}"')
    monkeypatch.delenv("FACTORY_CLI_AGENT_TIMEOUT_S", raising=False)
    monkeypatch.delenv("FACTORY_FIXTURE_QUESTION", raising=False)
    monkeypatch.delenv("FACTORY_FIXTURE_OPTIONS", raising=False)
    return monkeypatch


def _question_event(qid="q1"):
    from factory_kernel.ulid import new_ulid
    return {
        "id": new_ulid(),
        "ts": "2026-01-01T00:00:00Z",
        "job": new_ulid(),
        "type": "job.question_asked",
        "actor": "adapter/cli-agent",
        "fence": 1,
        "data": {"id": qid, "text": "Which layout?", "kind": "blocking",
                 "options": ["A", "B"], "stage": "understand", "attempt": 1},
        "prev": None,
    }


def test_question_event_validates(schemas_dir):
    store = SchemaStore(schemas_dir)
    assert store.is_valid("event", _question_event())


def test_snapshot_with_questions_validates(schemas_dir):
    from factory_kernel.ulid import new_ulid
    store = SchemaStore(schemas_dir)
    job = {
        "id": new_ulid(), "project": "demo", "state": "blocked",
        "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
        "brief": "b", "profile": "lite", "mode": "solo",
        "questions": [{"id": "q1", "text": "Which?", "kind": "blocking",
                       "options": ["A"], "stage": "understand", "attempt": 1,
                       "ts": "2026-01-01T00:00:00Z", "answered": False}],
        "last_event_id": new_ulid(),
    }
    assert store.is_valid("job", job)


def test_blocking_question_parks_job(kernel, ask_cmd):
    kernel.project_create("q", mode="solo", domain="web")
    job = kernel.job_run("q", "Build a landing page")
    ask_cmd.setenv(QMODE_ENV, "once")

    parked = kernel.job_execute(job["id"], adapter_id="cli-agent")
    assert parked["state"] == "blocked"
    assert len(parked["questions"]) == 1
    q = parked["questions"][0]
    assert q["text"] == "Which layout should the hero use?"
    assert q["options"] == ["Centered", "Split"]
    assert q["answered"] is False
    # Parked before accept: no stage was accepted.
    assert parked["current_stage"] == "understand"

    card = build_view(kernel)["needs_you"]
    assert card["kind"] == "question"
    assert card["questions"][0]["id"] == q["id"]
    assert "Centered" in card["questions"][0]["options"]


def test_answer_resumes_to_completed(kernel, ask_cmd):
    kernel.project_create("q", mode="solo", domain="web")
    job = kernel.job_run("q", "Build a landing page")
    ask_cmd.setenv(QMODE_ENV, "once")

    parked = kernel.job_execute(job["id"], adapter_id="cli-agent")
    assert parked["state"] == "blocked"
    qid = parked["questions"][0]["id"]

    done = kernel.job_answer(job["id"], qid, "Split", adapter_id="cli-agent")
    assert done["state"] in ("completed", "awaiting_human")
    assert done["questions"][0]["answered"] is True
    assert done["questions"][0]["answer"] == "Split"
    # The answer reaches the next attempt through the context manifest.
    manifests = sorted(
        (kernel.projects_dir / "q" / "jobs" / job["id"] / "stages").glob(
            "*/attempt-*/context.manifest.json"))
    assert manifests
    last = json.loads(manifests[-1].read_text(encoding="utf-8"))
    paths = [f.get("path") for f in last.get("files", [])]
    assert "questions.md" in paths


def test_repeat_question_does_not_burn_budget(kernel, ask_cmd):
    kernel.project_create("q", mode="solo", domain="web")
    job = kernel.job_run("q", "Build a landing page")
    ask_cmd.setenv(QMODE_ENV, "always")

    parked = kernel.job_execute(job["id"], adapter_id="cli-agent")
    assert parked["state"] == "blocked"
    done = kernel.job_answer(job["id"], parked["questions"][0]["id"], "Centered",
                             adapter_id="cli-agent")
    # The re-asked repeat is deduped: still exactly one recorded question.
    assert len(done["questions"]) == 1
    assert done["state"] in ("completed", "awaiting_human")


def test_budget_exhaustion_fails_job(kernel, ask_cmd):
    kernel.project_create("q", mode="solo", domain="web")
    job = kernel.job_run("q", "Build a landing page")
    ask_cmd.setenv(QMODE_ENV, "unique")

    parked = kernel.job_execute(job["id"], adapter_id="cli-agent")
    assert parked["state"] == "blocked"
    assert len(parked["questions"]) == 2
    # Answering and resuming asks two more: past the budget of 3 the job
    # fails instead of interrogating forever. Nothing is hidden: all four
    # questions stay in the ledger.
    failed = kernel.job_answer(job["id"], parked["questions"][0]["id"], "A",
                               adapter_id="cli-agent")
    assert failed["state"] == "failed"
    assert len(failed["questions"]) == 4


def test_info_questions_never_block(kernel, ask_cmd):
    kernel.project_create("q", mode="solo", domain="web")
    job = kernel.job_run("q", "Build a landing page")
    ask_cmd.setenv(QMODE_ENV, "info")

    done = kernel.job_execute(job["id"], adapter_id="cli-agent")
    assert done["state"] == "awaiting_human"
    assert all(q["kind"] == "info" for q in done["questions"])


def test_answer_validation(kernel, ask_cmd):
    from factory_kernel.kernel import KernelError
    kernel.project_create("q", mode="solo", domain="web")
    job = kernel.job_run("q", "Build a landing page")
    ask_cmd.setenv(QMODE_ENV, "once")

    with pytest.raises(KernelError):  # not blocked yet
        kernel.job_answer(job["id"], "q-hero", "Split")

    parked = kernel.job_execute(job["id"], adapter_id="cli-agent")
    qid = parked["questions"][0]["id"]
    with pytest.raises(KernelError):  # unknown question
        kernel.job_answer(job["id"], "nope", "Split")
    with pytest.raises(KernelError):  # empty answer
        kernel.job_answer(job["id"], qid, "   ")
    done = kernel.job_answer(job["id"], qid, "Split", adapter_id="cli-agent")
    assert done["questions"][0]["answered"] is True
    with pytest.raises(KernelError):  # already answered / not blocked
        kernel.job_answer(job["id"], qid, "Split")


def test_visual_preview_lists_synthetic_manifest(tmp_path):
    from factory_kernel.dashboard import _visual_evidence
    job_dir = tmp_path / "job"
    out = job_dir / "stages" / "00-build" / "attempt-1" / "outputs"
    (out / "visual").mkdir(parents=True)
    (out / "visual" / "a.png").write_bytes(b"\x89PNG\r\n\x1a\nSYNTHETIC\n")
    (out / "visual.json").write_text(json.dumps({
        "synthetic": True,
        "entries": [{"viewport": "1280x800", "theme": "light",
                     "file": "visual/a.png"}]}), encoding="utf-8")
    (out / "other.txt").write_text("x", encoding="utf-8")

    found = _visual_evidence(job_dir)
    assert len(found) == 1
    assert found[0]["synthetic"] is True
    assert found[0]["entries"][0]["viewport"] == "1280x800"

    (out / "visual.json").write_text("not json", encoding="utf-8")
    assert _visual_evidence(job_dir) == []

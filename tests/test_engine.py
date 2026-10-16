"""Tests for the stage-graph execution engine (spec §7–§9)."""
from __future__ import annotations

import json

import pytest

from factory_kernel.engine import EngineError


def test_execute_lite_parks_then_approve_completes(demo_job):
    kernel, job = demo_job
    result = kernel.job_execute(job["id"])
    # lite ends in 'approve', whose gate is required → human gate.
    assert result["state"] == "awaiting_human"

    done = kernel.job_approve(job["id"])
    assert done["state"] == "completed"


def test_execute_creates_attempt_artifacts(demo_job):
    kernel, job = demo_job
    kernel.job_execute(job["id"])
    job_dir = kernel._find_job_dir(job["id"])

    attempt = job_dir / "stages" / "00-understand" / "attempt-1"
    assert (attempt / "context.manifest.json").exists()
    assert (attempt / "usage.json").exists()
    assert (attempt / "checks.json").exists()
    assert (attempt / "outputs" / "brief.md").exists()

    # Context manifest is schema-valid and references the brief.
    manifest = json.loads((attempt / "context.manifest.json").read_text())
    kernel.schemas.validate("context.manifest", manifest)
    assert manifest["stage"] == "understand"
    assert manifest["attempt"] == 1

    # The build stage ran its declared checks.
    build_checks = json.loads(
        (job_dir / "stages" / "02-build" / "attempt-1" / "checks.json").read_text()
    )
    assert build_checks["summary"]["passed"] is True
    assert {r["id"] for r in build_checks["results"]} == {
        "lint", "typecheck", "unit", "build",
    }


def test_stage_accepted_events_recorded(demo_job):
    kernel, job = demo_job
    kernel.job_execute(job["id"])
    state = kernel._job_state(kernel._find_job_dir(job["id"]))
    accepted = [e["data"]["stage"] for e in state.load_events() if e["type"] == "stage.accepted"]
    assert accepted == ["understand", "plan", "build", "verify", "approve"]


def test_no_progress_stalls(demo_job):
    kernel, job = demo_job
    # Make every build-stage check fail identically each round.
    (kernel.projects_dir / job["project"] / "checks.json").write_text(
        json.dumps({"lint": {"cmd": "exit 1", "required": True}}), encoding="utf-8"
    )
    result = kernel.job_execute(job["id"])
    assert result["state"] == "stalled"

    job_dir = kernel._find_job_dir(job["id"])
    # Two attempts: the second repeats the first's fingerprint.
    assert (job_dir / "stages" / "02-build" / "attempt-2").exists()
    assert not (job_dir / "stages" / "02-build" / "attempt-3").exists()


def test_chain_valid_after_execute(demo_job):
    kernel, job = demo_job
    kernel.job_execute(job["id"])
    kernel.job_approve(job["id"])
    report = kernel.doctor()
    assert report["ok"] is True, report["errors"]


def test_execute_rejects_terminal_job(demo_job):
    kernel, job = demo_job
    kernel.job_execute(job["id"])
    kernel.job_approve(job["id"])
    with pytest.raises(EngineError):
        kernel.job_execute(job["id"])


def test_approve_requires_human_state(demo_job):
    kernel, job = demo_job
    from factory_kernel.kernel import KernelError

    with pytest.raises(KernelError):
        kernel.job_approve(job["id"])  # still pending


def test_resume_skips_accepted_stages(demo_job):
    kernel, job = demo_job
    kernel.job_execute(job["id"])
    before = len(list((kernel._find_job_dir(job["id"]) / "stages").glob("*/attempt-*")))
    kernel.job_approve(job["id"])
    after = len(list((kernel._find_job_dir(job["id"]) / "stages").glob("*/attempt-*")))
    # Resume must not re-run any accepted stage.
    assert before == after

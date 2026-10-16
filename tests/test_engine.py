"""Tests for the stage-graph execution engine (spec §7–§9)."""
from __future__ import annotations

import json

import pytest

from factory_kernel.checks import load_checks
from factory_kernel.engine import Engine, EngineError, input_hash
from factory_kernel.kernel import KernelError
from factory_kernel.lease import LeaseManager


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


# ----------------------------------------------------------------------
# Checkpoints + SHA-bound approval (P1 workstreams 1/6)
# ----------------------------------------------------------------------

def test_checkpoints_recorded_per_accepted_stage(demo_job):
    kernel, job = demo_job
    kernel.job_execute(job["id"])
    status = kernel.job_status(job["id"])
    assert [c["stage"] for c in status["checkpoints"]] == [
        "understand", "plan", "build", "verify", "approve",
    ]
    assert all(len(c["sha"]) == 64 for c in status["checkpoints"])
    job_dir = kernel._find_job_dir(job["id"])
    assert (job_dir / "stages" / "00-understand" / "attempt-1" / "checkpoint.json").exists()


def test_approval_binds_to_checkpoint_sha(demo_job):
    kernel, job = demo_job
    kernel.job_execute(job["id"])
    parked = kernel.job_status(job["id"])
    latest = parked["checkpoints"][-1]["sha"]

    done = kernel.job_approve(job["id"])
    assert done["state"] == "completed"
    assert done["approval"] == {"by": "local", "sha": latest, "ts": done["approval"]["ts"]}


def test_approval_invalidated_by_changed_result(demo_job):
    kernel, job = demo_job
    kernel.job_execute(job["id"])
    job_dir = kernel._find_job_dir(job["id"])
    target = job_dir / "stages" / "00-understand" / "attempt-1" / "outputs" / "brief.md"
    target.write_text("tampered\n", encoding="utf-8")

    with pytest.raises(KernelError, match="changed since checkpoint"):
        kernel.job_approve(job["id"])
    assert kernel.job_status(job["id"])["state"] == "awaiting_human"


def test_approval_rejects_wrong_sha(demo_job):
    kernel, job = demo_job
    kernel.job_execute(job["id"])
    with pytest.raises(KernelError, match="does not match checkpoint"):
        kernel.job_approve(job["id"], sha="0" * 64)


# ----------------------------------------------------------------------
# Interrupted attempts + idempotency (P1 workstream 2)
# ----------------------------------------------------------------------

def _start_running(kernel, job):
    job_dir = kernel._find_job_dir(job["id"])
    state = kernel._job_state(job_dir)
    lease = LeaseManager(job_dir, "local")
    fence = lease.acquire()
    state.transition("running", actor="local", fence=fence, reason="simulate")
    return state, lease, fence


def test_interrupted_attempt_is_recorded_and_retried(demo_job):
    kernel, job = demo_job
    state, lease, fence = _start_running(kernel, job)
    # Simulate a process killed after attempt 1 started but before it finished.
    state.append_event("stage.started", actor="local", fence=fence,
                       data={"stage": "understand"}, job_id=job["id"])
    state.append_event("stage.attempt_started", actor="local", fence=fence,
                       data={"stage": "understand", "attempt": 1}, job_id=job["id"])
    lease.release(fence)

    result = kernel.job_execute(job["id"])
    assert result["state"] == "awaiting_human"

    events = state.load_events()
    interrupted = [
        e for e in events
        if e["type"] == "stage.attempt_finished" and e["data"].get("status") == "interrupted"
    ]
    assert len(interrupted) == 1
    assert interrupted[0]["data"]["attempt"] == 1
    # Recovery re-ran attempt 1 to a real verdict.
    accepted = [e for e in events if e["type"] == "stage.accepted"
                and e["data"]["stage"] == "understand"]
    assert accepted and accepted[0]["data"]["attempt"] == 1


def test_attempt_input_hash_reuse(demo_job):
    kernel, job = demo_job
    state, lease, fence = _start_running(kernel, job)
    engine = Engine(kernel)
    profile = kernel.load_stage_profile("lite")
    stage = profile["stages"][0]
    adapters = _adapters(kernel)
    project_dir = kernel.projects_dir / job["project"]
    worktree = kernel.work_dir / job["id"]
    attempt_dir = kernel._find_job_dir(job["id"]) / "stages" / "00-understand" / "attempt-1"
    checks = load_checks(project_dir)

    first, _ = engine._run_attempt(
        job, kernel._find_job_dir(job["id"]), state, stage, 1, attempt_dir, project_dir,
        worktree, None, adapters, checks, fence, 600,
    )
    assert first == "passed"
    brief = attempt_dir / "outputs" / "brief.md"
    mtime = brief.stat().st_mtime_ns

    second, _ = engine._run_attempt(
        job, kernel._find_job_dir(job["id"]), state, stage, 1, attempt_dir, project_dir,
        worktree, None, adapters, checks, fence, 600,
    )
    lease.release(fence)
    assert second == "passed"
    assert brief.stat().st_mtime_ns == mtime  # reused, not re-produced
    reused = [e for e in state.load_events()
              if e["type"] == "stage.attempt_finished" and e["data"].get("reused")]
    assert len(reused) == 1


def test_input_hash_stable_and_sensitive():
    base = {"stage": "build", "files": [{"path": "a", "tokens": 1}], "summaries": {}}
    assert input_hash(base, "echo") == input_hash(dict(base), "echo")
    assert input_hash(base, "echo") != input_hash(base, "other")
    changed = {"stage": "build", "files": [{"path": "a", "tokens": 2}], "summaries": {}}
    assert input_hash(base, "echo") != input_hash(changed, "echo")


def _adapters(kernel):
    from factory_kernel.adapters import discover_adapters

    return discover_adapters(kernel.adapters_dir)

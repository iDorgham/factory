"""Kernel lifecycle tests (project/job/reindex)."""
from __future__ import annotations

import pytest

from factory_kernel.atomic import read_json
from factory_kernel.kernel import KernelError
from factory_kernel.state import StateError


def test_project_create_scaffolds_tree(kernel):
    proj = kernel.project_create("demo", mode="solo", domain="web")
    assert proj["name"] == "demo"
    assert proj["stage_profile"] == "lite"
    root = kernel.projects_dir / "demo"
    for path in (
        "project.json",
        "checks.json",
        "memory/decisions.md",
        "memory/conventions.md",
        "memory/repo-map.json",
        "memory/lessons.jsonl",
    ):
        assert (root / path).exists(), path
    for d in ("memory", "jobs", "epics", "issues"):
        assert (root / d).is_dir()


def test_project_name_validation(kernel):
    with pytest.raises(KernelError):
        kernel.project_create("bad name!")


def test_duplicate_project_rejected(kernel):
    kernel.project_create("demo")
    with pytest.raises(KernelError):
        kernel.project_create("demo")


def test_unknown_mode_rejected(kernel):
    with pytest.raises(KernelError):
        kernel.project_create("demo", mode="galactic")


def test_project_list_and_get(kernel):
    kernel.project_create("a")
    kernel.project_create("b")
    names = {p["name"] for p in kernel.project_list()}
    assert names == {"a", "b"}
    assert kernel.project_get("a")["name"] == "a"
    with pytest.raises(KernelError):
        kernel.project_get("missing")


def test_job_run_creates_job_artifacts(kernel):
    kernel.project_create("demo")
    job = kernel.job_run("demo", "Build a landing page")
    assert job["state"] == "pending"
    assert job["profile"] == "lite"
    job_dir = kernel.projects_dir / "demo" / "jobs" / job["id"]
    for path in ("events.jsonl", "job.json", "brief.md", "assumptions.md", "questions.md"):
        assert (job_dir / path).exists(), path
    assert (job_dir / "artifacts").is_dir()
    assert (kernel.work_dir / job["id"] / ".factory_job").read_text() == job["id"]


def test_job_run_on_missing_project(kernel):
    with pytest.raises(KernelError):
        kernel.job_run("ghost", "x")


def test_job_status_and_list(kernel, demo_job):
    k, job = demo_job
    assert k.job_status(job["id"])["id"] == job["id"]
    assert [j["id"] for j in k.job_list("demo")] == [job["id"]]


def test_job_transition_appends_event(kernel, demo_job):
    k, job = demo_job
    event = k.job_transition(job["id"], "running", reason="start")
    assert event["type"] == "job.state_changed"
    assert k.job_status(job["id"])["state"] == "running"


def test_illegal_kernel_transition(kernel, demo_job):
    k, job = demo_job
    with pytest.raises(StateError):
        k.job_transition(job["id"], "archived")


def test_cancel_job(kernel, demo_job):
    k, job = demo_job
    k.job_cancel(job["id"])
    assert k.job_status(job["id"])["state"] == "cancelled"


def test_reindex_builds_state_index(kernel, demo_job):
    k, job = demo_job
    index = k.reindex()
    assert job["id"] in index["projects"]["demo"]["jobs"]
    assert job["id"] in index["jobs_by_state"]["pending"]
    on_disk = read_json(k.state_dir / "index.json")
    assert on_disk["projects"]["demo"]["mode"] == "solo"


def test_load_stage_profile(kernel):
    profile = kernel.load_stage_profile("lite")
    assert profile["profile"] == "lite"
    assert [s["id"] for s in profile["stages"]][:2] == ["understand", "plan"]

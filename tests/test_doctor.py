"""doctor + reindex integrity tests (spec §5.2, §7)."""
from __future__ import annotations

import json
import shutil

from factory_kernel.atomic import atomic_write_json, read_json, read_jsonl


def _job_dir(kernel, job_id):
    return kernel.projects_dir / "demo" / "jobs" / job_id


def test_doctor_clean_tree(kernel, demo_job):
    k, job = demo_job
    report = k.doctor()
    assert report["ok"] is True
    assert report["errors"] == []
    assert report["jobs"] == 1
    assert report["projects"] == 1
    assert report["network_fs"] is False


def test_doctor_repairs_snapshot_drift(kernel, demo_job):
    k, job = demo_job
    job_json = _job_dir(k, job["id"]) / "job.json"
    drifted = read_json(job_json)
    drifted["state"] = "completed"
    atomic_write_json(job_json, drifted)

    report = k.doctor()
    assert any("Repaired" in r for r in report["repairs"])
    assert read_json(job_json)["state"] == "pending"


def test_doctor_detects_tampered_chain(kernel, demo_job):
    k, job = demo_job
    k.job_transition(job["id"], "running")
    events_path = _job_dir(k, job["id"]) / "events.jsonl"
    events = read_jsonl(events_path)
    events[0]["data"]["brief"] = "tampered"
    events_path.write_text(
        "\n".join(json.dumps(e, sort_keys=True) for e in events) + "\n", encoding="utf-8"
    )

    report = k.doctor()
    assert report["ok"] is False
    assert any("chain" in e for e in report["errors"])


def test_doctor_warns_on_missing_worktree(kernel, demo_job):
    k, job = demo_job
    shutil.rmtree(k.work_dir / job["id"])
    report = k.doctor()
    assert any("no worktree" in w for w in report["warnings"])


def test_doctor_warns_on_orphan_worktree(kernel, demo_job):
    k, _ = demo_job
    orphan = k.work_dir / "ORPHAN"
    orphan.mkdir()
    report = k.doctor()
    assert any("Orphan worktree" in w for w in report["warnings"])


def test_doctor_reports_invalid_project(kernel, demo_job):
    k, _ = demo_job
    atomic_write_json(k.projects_dir / "demo" / "project.json", {"name": "demo"})
    report = k.doctor()
    assert report["ok"] is False
    assert any("project.json" in e for e in report["errors"])

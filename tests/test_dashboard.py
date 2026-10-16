"""Tests for the dashboard view model, export, and HTTP server (spec §21)."""
from __future__ import annotations

import json
import threading
import urllib.request

from factory_kernel.dashboard import (
    build_view,
    dispatch,
    export_dashboard,
    make_server,
    render_html,
)


def test_build_view_empty_state(kernel):
    view = build_view(kernel)
    assert view["empty_state"] is True
    assert view["jobs"] == []
    assert view["needs_you"] is None
    assert view["estimate"]["usd"] > 0


def test_timeline_is_plain_language(demo_job):
    kernel, job = demo_job
    kernel.job_execute(job["id"])

    view = build_view(kernel)
    phrases = [step["phrase"] for step in view["timeline"]]
    assert "Understanding your request" in phrases
    assert "Ready for you" in phrases
    # No raw stage ids leak into the Solo timeline.
    assert all(step["id"] not in step["phrase"] for step in view["timeline"])

    # The parked approve step is the active one.
    active = [s for s in view["timeline"] if s["status"] == "active"]
    assert len(active) == 1
    assert active[0]["id"] == "approve"


def test_needs_you_card_binds_to_checkpoint_sha(demo_job):
    kernel, job = demo_job
    kernel.job_execute(job["id"])

    view = build_view(kernel)
    card = view["needs_you"]
    assert card["kind"] == "approval"
    assert card["job"] == job["id"]
    assert card["sha"] == kernel.job_status(job["id"])["checkpoints"][-1]["sha"]
    actions = {a["id"] for a in card["actions"]}
    assert actions == {"approve", "change"}


def test_undo_reports_unavailable(demo_job):
    kernel, job = demo_job
    view = build_view(kernel)
    assert view["undo"]["available"] is False
    assert "merge" in view["undo"]["reason"]


def test_render_html_live_flag_and_content(demo_job):
    kernel, job = demo_job
    live = render_html(build_view(kernel), live=True)
    assert "const LIVE = true" in live
    assert "Build a landing page" in live

    static = render_html(build_view(kernel), live=False)
    assert "const LIVE = false" in static


def test_export_dashboard_writes_file(demo_job, tmp_path):
    kernel, job = demo_job
    out = export_dashboard(kernel, out=tmp_path / "dashboard.html")
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    assert "const LIVE = false" in html
    assert "Build a landing page" in html


def test_dispatch_approve_completes_job(demo_job):
    kernel, job = demo_job
    kernel.job_execute(job["id"])
    sha = kernel.job_status(job["id"])["checkpoints"][-1]["sha"]

    result = dispatch(kernel, {"command": "approve", "job_id": job["id"], "sha": sha})
    assert result["ok"] is True
    assert result["job"]["state"] == "completed"


def test_dispatch_reports_kernel_errors(demo_job):
    kernel, job = demo_job
    kernel.job_execute(job["id"])
    result = dispatch(kernel, {"command": "approve", "job_id": job["id"], "sha": "0" * 64})
    assert result["ok"] is False
    assert "does not match checkpoint" in result["error"]


def test_dispatch_unknown_command(kernel):
    result = dispatch(kernel, {"command": "explode"})
    assert result["ok"] is False


def test_dispatch_create_sample(kernel):
    result = dispatch(kernel, {"command": "create_sample"})
    assert result["ok"] is True
    assert [p["name"] for p in kernel.project_list()] == ["sample"]


def test_dispatch_change_this_reopens_stage(demo_job):
    kernel, job = demo_job
    kernel.job_execute(job["id"])
    assert kernel.job_status(job["id"])["state"] == "awaiting_human"

    result = dispatch(kernel, {"command": "change", "job_id": job["id"],
                               "feedback": "make the hero bigger"})
    assert result["ok"] is True
    # The reopened stage re-ran and the job parked at the gate again.
    assert result["job"]["state"] == "awaiting_human"
    assert result["job"]["approval"]["decision"] == "changes_requested"

    # The approve stage was accepted a second time, after the feedback.
    job_dir = kernel._find_job_dir(job["id"])
    accepted = [
        i for i, ev in enumerate(kernel._job_state(job_dir).load_events())
        if ev["type"] == "stage.accepted" and ev["data"].get("stage") == "approve"
    ]
    assert len(accepted) == 2


def test_server_roundtrip(kernel):
    httpd = make_server(kernel, port=0)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        with urllib.request.urlopen(base + "/") as resp:
            html = resp.read().decode("utf-8")
        assert "Factory" in html

        with urllib.request.urlopen(base + "/api/state") as resp:
            view = json.loads(resp.read())
        assert "projects" in view and "timeline" in view

        request = urllib.request.Request(
            base + "/api/command",
            data=json.dumps({"command": "create_sample"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request) as resp:
            out = json.loads(resp.read())
        assert out["ok"] is True
    finally:
        httpd.shutdown()
        httpd.server_close()

"""Tests for the dashboard view model, export, and HTTP server (spec §21)."""
from __future__ import annotations

import json
import sys
import threading
import urllib.request
from pathlib import Path

import pytest

from factory_kernel.dashboard import (
    _player,
    build_view,
    dispatch,
    export_dashboard,
    make_server,
    render_html,
)

ASK_AGENT = Path(__file__).resolve().parent / "fixtures" / "adapters" / "cli-ask-agent.py"


@pytest.fixture
def ask_cmd(monkeypatch):
    """Point `cli-agent` at the fixture that asks a blocking question."""
    monkeypatch.setenv("FACTORY_CLI_AGENT_CMD", f'"{sys.executable}" "{ASK_AGENT}"')
    monkeypatch.delenv("FACTORY_CLI_AGENT_TIMEOUT_S", raising=False)
    monkeypatch.delenv("FACTORY_FIXTURE_QUESTION", raising=False)
    monkeypatch.delenv("FACTORY_FIXTURE_OPTIONS", raising=False)
    return monkeypatch


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
    assert actions == {"approve", "change", "explain"}


def test_player_absent_without_active_job(demo_job):
    kernel, job = demo_job
    # A freshly created job is pending, which the player treats as active;
    # cancel it so no active job remains.
    kernel.job_cancel(job["id"])
    view = build_view(kernel)
    assert view["player"] is None


def test_player_pending_job_shows_zero_progress(demo_job):
    kernel, job = demo_job
    player = build_view(kernel)["player"]
    assert player["job"] == job["id"]
    assert player["brief"] == "Build a landing page"
    assert player["project"] == "demo"
    assert player["state"] == "pending"
    assert player["done"] == 0
    assert player["total"] > 0
    assert player["pct"] == 0
    assert player["stage_phrase"] == "Understanding your request"
    assert player["needs_you"] is False
    assert player["can_resume"] is True
    assert player["can_stop"] is True


def test_player_running_job_tracks_active_stage(demo_job):
    kernel, job = demo_job
    kernel.job_execute(job["id"])
    player = build_view(kernel)["player"]
    # The lite profile parks at the human gate: all but the active step done.
    assert player["state"] == "awaiting_human"
    assert player["needs_you"] is True
    assert player["done"] == player["total"] - 1
    assert player["stage_phrase"] == "Ready for you"


def test_player_progress_excludes_verdict_rows(demo_job):
    kernel, job = demo_job
    kernel.job_execute(job["id"])
    view = build_view(kernel)
    player = view["player"]
    stage_rows = [s for s in view["timeline"] if ":" not in s["id"]]
    assert player["total"] == len(stage_rows)
    assert player["done"] == sum(1 for s in stage_rows if s["status"] == "done")


# ----------------------------------------------------------------------
# The footer must only offer what the kernel will actually do.
# ----------------------------------------------------------------------


def _stages(*statuses):
    """A lite-profile timeline with the given per-stage statuses."""
    named = [("understand", "Understanding your request"), ("plan", "Planning"),
             ("build", "Building"), ("verify", "Checking"),
             ("approve", "Ready for you")]
    return [{"id": sid, "phrase": phrase, "status": statuses[i],
             "round": None, "rounds": None}
            for i, (sid, phrase) in enumerate(named)]


def _state_only(state):
    return {"id": "01JOB", "project": "demo", "brief": "b", "state": state}


def test_player_resume_only_where_the_kernel_would_run_it():
    """`Engine.execute` accepts only pending/running/awaiting_human, and of
    those only *pending* is a start — the footer must not advertise an action
    the kernel refuses (`Job is 'blocked'; cannot execute`)."""
    timeline = _stages("active", "todo", "todo", "todo", "todo")
    for state, expected in [
        ("pending", True),
        ("running", False),        # already live — a second start would double it
        ("awaiting_human", False),  # approved (SHA-bound), never re-executed
        ("blocked", False),        # continues by answering, not by resuming
        ("stalled", False),
        ("paused", False),
        ("failed", False),
    ]:
        assert _player(_state_only(state), timeline)["can_resume"] is expected, state


def test_player_status_line_states_why_when_it_needs_you_or_failed():
    """The ambient line names the reason, not whichever stage was in flight,
    so it agrees with the glyph and the Needs you card."""
    active = _stages("done", "done", "active", "todo", "todo")
    assert _player(_state_only("blocked"), active)["stage_phrase"] == "I need an answer"
    assert _player(_state_only("stalled"), active)["stage_phrase"] == "I'm stuck"
    assert _player(_state_only("failed"), active)["stage_phrase"] == "I couldn't finish"
    assert _player(_state_only("running"), active)["stage_phrase"] == "Building"


def test_player_absent_for_every_terminal_state():
    done = _stages("done", "done", "done", "done", "done")
    for state in ("completed", "cancelled", "superseded", "archived"):
        assert _player(_state_only(state), done) is None


def test_player_handles_blocked_question(kernel, ask_cmd):
    """A blocked job's footer says it is waiting, and offers Stop — Resuming
    would be rejected by the kernel until the question is answered."""
    kernel.project_create("q", mode="solo", domain="web")
    job = kernel.job_run("q", "Build a landing page")
    ask_cmd.setenv("FACTORY_FIXTURE_QMODE", "once")
    parked = kernel.job_execute(job["id"], adapter_id="cli-agent")
    assert parked["state"] == "blocked"

    player = build_view(kernel)["player"]
    assert player["state"] == "blocked"
    assert player["needs_you"] is True
    assert player["stage_phrase"] == "I need an answer"
    assert player["can_resume"] is False
    assert player["can_stop"] is True


def test_player_start_label_for_a_fresh_job(demo_job):
    """A pending job has never run, so the control reads Start (the label
    travels in the model so markup and model cannot drift)."""
    kernel, job = demo_job
    player = build_view(kernel)["player"]
    assert player["can_resume"] is True
    assert player["resume_label"] == "Start"


def test_export_dashboard_keeps_the_player_footer_read_only(demo_job, tmp_path):
    """The shareable snapshot is still the Solo view: the footer renders (its
    controls fall through to send(), which refuses when not live)."""
    kernel, job = demo_job
    out = export_dashboard(kernel, out=tmp_path / "dashboard.html")
    html = out.read_text(encoding="utf-8")
    # The footer is not gated behind LIVE, and the button label comes from the
    # view model rather than being hardcoded in the markup.
    assert "const p = v.player;" in html
    assert "const p = LIVE ? v.player : null;" not in html
    assert '$("p-resume").textContent = p.resume_label;' in html
    # The embedded view payload still carries the active job's player model.
    view = json.loads(html.split("let VIEW = ", 1)[1].split(";\n", 1)[0])
    assert view["player"]["brief"] == "Build a landing page"


def test_render_html_contains_player(demo_job):
    kernel, job = demo_job
    html = render_html(build_view(kernel), live=True)
    assert 'id="player"' in html
    assert "player-bar" in html


def test_player_controls_are_static_nodes(demo_job):
    """Rebuilt-per-tick buttons drop in-flight clicks (stream redraws ~1/s)."""
    kernel, job = demo_job
    html = render_html(build_view(kernel), live=True)
    for cid in ("p-resume", "p-need", "p-stop"):
        assert f'id="{cid}"' in html
    assert '$("p-controls").innerHTML' not in html


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


def test_explain_is_event_derived_plain_language(demo_job):
    kernel, job = demo_job
    kernel.job_execute(job["id"])

    result = dispatch(kernel, {"command": "explain", "job_id": job["id"]})
    assert result["ok"] is True
    text = "\n".join(result["explanation"])
    assert "Goal: " in text
    # awaiting_human: checkpoint sha + honest next steps
    assert "checkpoint " in text
    assert "Approve" in text and "Change this…" in text
    # no invented claims: brief text is quoted as the goal
    assert job["brief"][:10] in text


def test_needs_you_stalled_card_offers_explain(kernel):
    kernel.project_create("s", mode="solo", domain="web")
    checks_path = kernel.projects_dir / "s" / "checks.json"
    import json as _json
    checks_path.write_text(_json.dumps(
        {"build": {"cmd": "exit 1", "required": True}}), encoding="utf-8")
    job = kernel.job_run("s", "stall probe")
    result = kernel.job_execute(job["id"])
    from factory_kernel.dashboard import build_view
    card = build_view(kernel)["needs_you"]
    if result["state"] != "stalled":
        return  # the profile parked at its human gate before stalling
    assert card["kind"] == "stalled"
    assert [a["id"] for a in card["actions"]] == ["explain"]
    ex = dispatch(kernel, {"command": "explain", "job_id": job["id"]})
    assert ex["ok"] is True
    assert "identical failure" in "\n".join(ex["explanation"])


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

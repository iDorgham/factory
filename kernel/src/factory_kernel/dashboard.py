"""Dashboard and operator experience (spec §21).

`factory serve` runs a local HTTP server (standard library only) that streams the
view to the browser; `factory export-dashboard` writes a static read-only
snapshot for sharing. The dashboard is a *client*: every action is a kernel
command, never a direct file edit (§21, §4).

Solo view — three elements only (§21.2):
  1. a prompt box (with an estimated cost and time),
  2. a plain-language timeline (no stage jargon),
  3. a single "Needs you" card (question, or the approval card with preview).
Also present: a preview link, Undo (disabled until merge lands), and a hidden
Details drawer showing the raw event timeline.
"""
from __future__ import annotations

import json
import time
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

STAGE_PHRASES = {
    "understand": "Understanding your request",
    "define": "Defining the solution",
    "plan": "Planning",
    "design": "Designing",
    "build": "Building",
    "verify": "Checking",
    "review": "Reviewing",
    "polish": "Polishing",
    "approve": "Ready for you",
    "merge": "Finishing up",
}

STATE_PHRASES = {
    "pending": "Waiting to start",
    "running": "Working",
    "awaiting_human": "Ready for you",
    "blocked": "I need an answer",
    "stalled": "I'm stuck",
    "paused": "Paused",
    "failed": "I couldn't finish",
    "completed": "Done",
    "cancelled": "Cancelled",
    "superseded": "Replaced",
    "archived": "Archived",
}

NEEDS_YOU_STATES = ("awaiting_human", "blocked", "stalled")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _state_phrase(state: str) -> str:
    return STATE_PHRASES.get(state, state.replace("_", " ").capitalize())


def _stage_phrase(stage: str) -> str:
    return STAGE_PHRASES.get(stage, stage.replace("_", " ").capitalize())


def _estimate(kernel, profile: str = "lite") -> dict:
    """Total budget of a profile, shown in the prompt box as a rough estimate."""
    try:
        stages = kernel.load_stage_profile(profile)["stages"]
    except Exception:
        return {"usd": 0.0, "minutes": 0}
    usd = sum(float(s.get("budget", {}).get("usd", 0) or 0) for s in stages)
    minutes = sum(int(s.get("budget", {}).get("minutes", 0) or 0) for s in stages)
    return {"usd": round(usd, 2), "minutes": minutes}


def _job_summary(job: dict) -> dict:
    return {
        "id": job["id"],
        "project": job.get("project"),
        "state": job.get("state"),
        "state_phrase": _state_phrase(job.get("state", "")),
        "brief": job.get("brief", ""),
        "profile": job.get("profile"),
        "current_stage": job.get("current_stage"),
        "updated_at": job.get("updated_at"),
        "needs_you": job.get("state") in NEEDS_YOU_STATES,
    }


def _pick_active(jobs: list[dict]) -> Optional[dict]:
    if not jobs:
        return None
    priority = {"awaiting_human": 0, "blocked": 1, "stalled": 2, "running": 3, "paused": 4}
    ordered = sorted(
        jobs,
        key=lambda j: (priority.get(j.get("state"), 9), _neg(j.get("updated_at"))),
    )
    return ordered[0]


def _neg(ts: Optional[str]) -> str:
    # Sort descending by ISO timestamp without parsing.
    return "".join(chr(255 - ord(c)) for c in (ts or ""))


def _events(kernel, job) -> list[dict]:
    job_dir = kernel._find_job_dir(job["id"])
    return kernel._job_state(job_dir).load_events()


def _accepted_and_reopened(kernel, job):
    from .engine import Engine

    job_dir = kernel._find_job_dir(job["id"])
    state = kernel._job_state(job_dir)
    accepted = Engine._accepted_stages(state)
    reopened = Engine._reopened_stage(state)
    return accepted, reopened


def _timeline(kernel, job) -> list[dict]:
    stages = kernel.load_stage_profile(job["profile"])["stages"]
    order = {s["id"]: i for i, s in enumerate(stages)}
    accepted, reopened = _accepted_and_reopened(kernel, job)
    if reopened is not None and reopened in order:
        accepted = {s for s in accepted if order.get(s, -1) < order[reopened]}

    events = _events(kernel, job)
    rounds: dict[str, int] = {}
    guard_notes: dict[str, dict] = {}
    budget_notes: dict[str, dict] = {}
    injection_notes: dict[str, dict] = {}
    for ev in events:
        if ev["type"] == "stage.attempt_started":
            sid = ev["data"].get("stage")
            rounds[sid] = max(rounds.get(sid, 0), ev["data"].get("attempt", 0))
        elif ev["type"] in ("guard.violation", "guards.completed"):
            # Latest guard verdict per stage, by attempt number: a later
            # attempt supersedes what the earlier diff showed (spec §9.3).
            data = ev["data"]
            sid = data.get("stage")
            note = {"attempt": data.get("attempt", 0),
                    "violation": ev["type"] == "guard.violation", "data": data}
            prev = guard_notes.get(sid)
            if not prev or data.get("attempt", 0) >= prev["attempt"]:
                guard_notes[sid] = note
        elif ev["type"] in ("budget.soft_exceeded", "budget.hard_exceeded"):
            # Latest budget verdict per stage, like guard notes (§12.2).
            data = ev["data"]
            sid = data.get("stage")
            prev = budget_notes.get(sid)
            if not prev or data.get("attempt", 0) >= prev["attempt"]:
                budget_notes[sid] = {
                    "hard": ev["type"] == "budget.hard_exceeded", "data": data}
        elif ev["type"] == "injection.detected":
            # Latest injection verdict per stage, by attempt number.
            data = ev["data"]
            sid = data.get("stage")
            prev = injection_notes.get(sid)
            if not prev or data.get("attempt", 0) >= prev["attempt"]:
                injection_notes[sid] = {
                    "attempt": data.get("attempt", 0), "data": data}

    accepted_ids = [s["id"] for s in stages if s["id"] in accepted]
    if job.get("state") == "awaiting_human" and accepted_ids:
        active_sid = accepted_ids[-1]
    else:
        active_sid = next((s["id"] for s in stages if s["id"] not in accepted), None)

    timeline = []
    for stage in stages:
        sid = stage["id"]
        if sid == active_sid:
            status = "active"
        elif sid in accepted:
            status = "done"
        else:
            status = "todo"
        phrase = _stage_phrase(sid)
        round_no, max_rounds = rounds.get(sid), stage.get("max_rounds")
        if status == "active" and sid in ("build", "verify") and round_no:
            phrase = f"{phrase} (round {round_no} of {max_rounds})"
        timeline.append({
            "id": sid, "phrase": phrase, "status": status,
            "round": round_no, "rounds": max_rounds,
        })
    # Guard verdicts read as plain-language lines against the guarded stage
    # (Solo promise, spec §10): what was flagged, where, or explicit "clean".
    for sid, note in sorted(guard_notes.items(),
                            key=lambda item: order.get(item[0], len(stages))):
        if note["violation"]:
            phrase, status = _guard_violation_phrase(note["data"]), "failed"
        else:
            phrase, status = "✓ Guards clean", "done"
        timeline.append({
            "id": f"{sid}:guards", "phrase": phrase, "status": status,
            "round": None, "rounds": None,
        })
    # Budget verdicts read the same way (P2.2): the cost, the limit, whether
    # the journey stopped or kept going.
    for sid, note in sorted(budget_notes.items(),
                            key=lambda item: order.get(item[0], len(stages))):
        data, cost = note["data"], note["data"].get("current_cost", 0.0)
        if note["hard"]:
            if data.get("error"):
                phrase = f"⚠ Budget configuration is broken: {data['error']}"
            else:
                phrase = (f"⚠ Hard budget exceeded in stage '{sid}' "
                          f"(${_usd(cost)} ≥ ${_usd(data.get('hard_limit'))})")
            status = "failed"
        else:
            phrase = (f"⚠ Soft budget crossed in stage '{sid}' "
                      f"(${_usd(cost)} ≥ ${_usd(data.get('soft_limit'))}); keeping going")
            status = "active"
        timeline.append({
            "id": f"{sid}:budget", "phrase": phrase, "status": status,
            "round": None, "rounds": None,
        })
    # Injection verdicts read the same way (P2 injection handling): what was
    # flagged, where, in plain language with a red dot.
    for sid, note in sorted(injection_notes.items(),
                            key=lambda item: order.get(item[0], len(stages))):
        data = note["data"]
        phrase = _injection_violation_phrase(data)
        timeline.append({
            "id": f"{sid}:injection", "phrase": phrase, "status": "failed",
            "round": None, "rounds": None,
        })
    return timeline


def _usd(value) -> str:
    """Compact dollars for human lines, as the operator thinks of them."""
    return f"{float(value or 0.0):.2f}"


# Plain-language words per (guard, kind). Unknown kinds fall back to the raw
# kind id, so a new guard is never rendered as an empty sentence.
GUARD_KIND_WORDS = {
    ("no_test_deletion", "deleted"): "deleted tests",
    ("no_lockfile_surprise", "deleted"): "a deleted lockfile",
    ("no_lockfile_surprise", "manifest_without_lockfile"):
        "an unauthorized dependency change",
    ("no_lockfile_surprise", "lockfile_without_manifest"):
        "an unauthorized dependency change",
    ("no_secret_in_diff", "secret"): "a secret",
    ("guard_config", "unknown_guard"): "a broken guard configuration",
    ("guard_config", "invalid_authorization"):
        "a broken authorizations file",
}


def _guard_violation_phrase(data: dict) -> str:
    what = GUARD_KIND_WORDS.get((data.get("guard"), data.get("kind")),
                                data.get("kind") or "unwanted changes")
    paths = data.get("paths") or []
    if paths:
        return f"⚠ Guard flagged {what} in {paths[0]}"
    return f"⚠ Guard flagged {what}"


# Plain-language words per injection pattern id. Unknown ids fall back to the
# raw pattern id, so a new pattern is never rendered as an empty sentence.
INJECTION_PATTERN_WORDS = {
    "ignore-previous-instructions": "an attempt to override prior instructions",
    "system-prompt-leak": "a request to reveal the system prompt",
    "do-not-follow": "an instruction to ignore prior guidance",
    "pretend-to-be": "an attempt to impersonate a different assistant",
}


def _injection_violation_phrase(data: dict) -> str:
    what = INJECTION_PATTERN_WORDS.get(
        data.get("pattern_id"), data.get("pattern_id") or "unwanted instruction")
    item_path = data.get("item_path") or ""
    excerpt = data.get("matched_excerpt") or ""
    stage = data.get("stage") or ""
    if item_path and excerpt:
        return (f"⚠ Injection pattern flagged in stage '{stage}' "
                f"({item_path}: '{excerpt}')")
    if item_path:
        return (f"⚠ Injection pattern flagged in stage '{stage}' "
                f"({item_path}: {what})")
    return f"⚠ Injection pattern flagged in stage '{stage}' ({what})"


def _needs_you(kernel, job) -> Optional[dict]:
    state = job.get("state")
    if state == "awaiting_human":
        checkpoints = job.get("checkpoints") or []
        sha = checkpoints[-1]["sha"] if checkpoints else None
        return {
            "kind": "approval",
            "job": job["id"],
            "title": "Ready for you",
            "body": f"I finished: {job.get('brief', '')}. "
                    "Approve to keep it, or tell me what to change.",
            "sha": sha,
            "actions": [
                {"id": "approve", "label": "Approve", "primary": True},
                {"id": "change", "label": "Change this…", "primary": False},
                {"id": "explain", "label": "Explain this", "primary": False},
            ],
            "feedback_label": "What should change?",
        }
    if state == "blocked":
        open_q = [q for q in (job.get("questions") or []) if not q.get("answered")]
        return {
            "kind": "question", "job": job["id"], "title": "I need an answer",
            "body": "I paused because this is expensive to change later. "
                    "Answer below, then I resume.",
            "sha": None,
            "actions": [{"id": "explain", "label": "Explain this",
                         "primary": False}],
            "questions": [
                {"id": q["id"], "text": q["text"], "options": q.get("options") or [],
                 "stage": q.get("stage", "")}
                for q in open_q
            ],
            "feedback_label": None,
        }
    if state == "stalled":
        return {
            "kind": "stalled", "job": job["id"], "title": "I'm stuck",
            "body": "Trying again isn't making progress, so I stopped rather than "
                    "waste your budget.",
            "sha": None,
            "actions": [{"id": "explain", "label": "Explain this",
                         "primary": False}],
            "feedback_label": None,
        }
    return None


def _explain(kernel, job) -> list[str]:
    """Deferred plain-language explanation ("Explain this" card action).

    Honesty rule: every line is derived from kernel-visible state, the event
    log, and the attempt artifacts on disk — never from agent self-report.
    """
    state = job.get("state")
    lines: list[str] = []
    brief = (job.get("brief") or "").strip() or "(no brief)"
    lines.append(f"Goal: {brief}.")

    timeline = _timeline(kernel, job)
    done = [t["phrase"] for t in timeline if t["status"] == "done"]
    active = next((t for t in timeline if t["status"] == "active"), None)
    if done:
        lines.append("Progress: " + " → ".join(done) + ".")
    if active:
        lines.append(f"Now at: {active['phrase']}.")

    real_captures = 0
    synth_captures = 0
    for m in _visual_evidence(kernel._find_job_dir(job["id"])):
        n = len(m.get("entries") or [])
        if m.get("synthetic"):
            synth_captures += n
        else:
            real_captures += n

    if state == "awaiting_human":
        checkpoints = job.get("checkpoints") or []
        sha = (checkpoints[-1]["sha"][:12] + "…") if checkpoints else "?"
        lines.append(
            "All stages finished and every required check ran through the "
            f"kernel (the agent cannot claim otherwise); the result is "
            f"checkpoint {sha}, content-addressed so approval binds exactly "
            "these bytes.")
        if real_captures:
            lines.append(
                f"Evidence: {real_captures} real screenshot capture(s) in the "
                "latest attempt outputs.")
        if synth_captures:
            lines.append(
                f"(+{synth_captures} synthetic-fixture capture(s), labeled "
                "and not evidence.)")
        lines.append(
            "Next: Approve keeps the work and merges it into your project; "
            "'Change this…' tells me what to redo; Undo (after approval) "
            "reverts the merge.")
    elif state == "blocked":
        questions = job.get("questions") or []
        open_q = [q for q in questions if not q.get("answered")]
        lines.append(
            "I stopped because a decision is expensive to change later — "
            "this is a blocking question, and the kernel parks the job so "
            "nothing runs while it waits.")
        if questions:
            lines.append(
                f"Budget: {len(questions)} of at most 3 blocking questions "
                "for this job (a 4th would fail the job instead of asking "
                "forever).")
        for q in open_q:
            lines.append(f"Open Q: {q['text']}")
        lines.append("Next: answer here and I resume from the same spot.")
    elif state == "stalled":
        lines.append(
            "The last attempts of this stage produced the identical failure "
            "fingerprint, so further retries would only burn budget — "
            "honest no-progress detection stopped the loop.")
        lines.append(
            "Next: cancel the job, or use 'Change this…' with new "
            "instructions (it reopens the stage from your feedback).")
    elif state == "completed":
        lines.append(
            "Approved and merged; the merge is recorded and reversible via "
            "Undo while nothing else has advanced.")
    elif state == "cancelled":
        lines.append(
            "Cancelled by you; the event log keeps an exact record of what "
            "was done before the cancel.")
    elif state == "failed":
        lines.append(
            "Failed: the last attempt broke a required check (or another "
            "hard gate). The raw check output is in the attempt's "
            "checks.json — a claim is not evidence, the log is.")
    elif state == "running":
        lines.append("The agent is working now; this view updates live.")
    else:
        lines.append(f"State: {state}.")
    return lines


def _preview(kernel, job) -> dict:
    job_dir = kernel._find_job_dir(job["id"])
    outputs = sorted((job_dir / "stages").glob("*/attempt-*/outputs/*"))
    worktree = kernel.work_dir / job["id"]
    return {
        "available": bool(outputs),
        "worktree": str(worktree),
        "note": "No dev server in this slice — artifacts live under the job outputs.",
        "visual": _visual_evidence(job_dir),
    }


def _visual_evidence(job_dir) -> list[dict]:
    """Collect `visual.json` manifests from attempt outputs (P1 visual contract).

    Each manifest lists screenshot evidence entries produced by a
    screenshot-capable adapter/command. Entries are surfaced as-is; manifests
    marked `"synthetic": true` (test fixtures) are labeled so nobody mistakes
    them for real captures. No manifest → empty list (not an error).
    """
    import json

    found = []
    for manifest_path in sorted((job_dir / "stages").glob("*/attempt-*/outputs/visual.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if not isinstance(manifest, dict):
            continue
        entries = manifest.get("entries") or []
        if not isinstance(entries, list):
            continue
        rel = manifest_path.parent.relative_to(job_dir).as_posix()
        kept = []
        for e in entries[:20]:
            if not isinstance(e, dict) or not e.get("file"):
                continue
            kept.append({
                "viewport": str(e.get("viewport", "?")),
                "theme": str(e.get("theme", "?")),
                "file": str(e.get("file"))[:200],
                **({"changed_pct": e["changed_pct"]}
                   if isinstance(e.get("changed_pct"), (int, float)) else {}),
            })
        if kept:
            try:
                stage = manifest_path.parts[-4]
            except IndexError:
                stage = "?"
            found.append({"stage": stage, "attempt_dir": rel,
                          "synthetic": bool(manifest.get("synthetic", False)),
                          "entries": kept})
    return found


def _sandbox(kernel) -> dict:
    sandbox = kernel.factory_cfg.get("sandbox", {})
    return {
        "type": sandbox.get("type", "process"),
        "network_allowlist": sandbox.get("network_allowlist", []),
        "protections": "restricted working directory + network allowlist "
                       "(not a full container)",
    }


def build_view(kernel, project: Optional[str] = None) -> dict:
    """Fold current state into the dashboard view model (a pure read)."""
    projects = kernel.project_list()
    jobs = kernel.job_list(project)
    view = {
        "generated_at": _now(),
        "projects": [
            {"name": p["name"], "mode": p["mode"],
             "stage_profile": p.get("stage_profile"), "status": p["status"]}
            for p in projects
        ],
        "jobs": [_job_summary(j) for j in jobs],
        "estimate": _estimate(kernel),
        "active_job": None,
        "timeline": [],
        "player": None,
        "needs_you": None,
        "preview": None,
        "undo": {"available": False,
                 "reason": "no active job"},
        "sandbox": _sandbox(kernel),
        "empty_state": len(projects) == 0,
    }
    active = _pick_active(jobs)
    if active is not None:
        detail = kernel.job_status(active["id"])
        view["active_job"] = _job_summary(detail)
        view["timeline"] = _timeline(kernel, detail)
        view["player"] = _player(_job_summary(detail), view["timeline"])
        view["needs_you"] = _needs_you(kernel, detail)
        view["preview"] = _preview(kernel, detail)
        view["undo"] = _undo_state(detail)
    return view


def _player(job: dict, timeline: list[dict]) -> Optional[dict]:
    """Sticky-footer player model for the active job (Spotify-style).

    Progress counts only real stages — guard/budget/injection verdict rows
    carry a ":" in their id and never move the bar.

    The controls and the status line mirror what the *kernel* permits, not what
    would look reassuring: Resume appears only when `Engine.execute` would run
    the job, and a job that is waiting on the human (or has stopped) names the
    reason instead of the stage that happened to be in flight.
    """
    if not job:
        return None
    if job.get("state") in ("completed", "cancelled", "superseded", "archived"):
        return None
    stages = [s for s in timeline if ":" not in s["id"]]
    total = len(stages)
    done = sum(1 for s in stages if s["status"] == "done")
    active = next((s for s in stages if s["status"] == "active"), None)
    if active is not None:
        done = min(done, total - 1)
    pct = round(done * 100 / total) if total else 0
    state = job.get("state", "")
    if state in NEEDS_YOU_STATES or state == "failed":
        stage_phrase = _state_phrase(state)
    else:
        stage_phrase = active["phrase"] if active else _state_phrase(state)
    # Resume is offered only where the kernel would actually run the job:
    # `Engine.execute` accepts pending/running/awaiting_human, and of those
    # only *pending* is a start — awaiting_human is approved (SHA-bound),
    # and a running job is already live, so starting it again would double
    # it up. Blocked jobs continue by answering their question; stalled and
    # failed jobs have no retry path in this slice.
    can_resume = state == "pending"
    return {
        "job": job["id"],
        "brief": job.get("brief", ""),
        "project": job.get("project"),
        "state": state,
        "state_phrase": _state_phrase(state),
        "stage_phrase": stage_phrase,
        "done": done,
        "total": total,
        "pct": pct,
        "needs_you": state in NEEDS_YOU_STATES,
        "can_resume": can_resume,
        # A pending job has never run, so the control reads "Start"; the label
        # travels in the model so the markup and the model cannot drift.
        "resume_label": "Start" if can_resume else "Resume",
        "can_stop": state in ("pending", "running", "awaiting_human",
                              "blocked", "stalled", "paused", "failed"),
    }


def _undo_state(job: dict) -> dict:
    """Undo is available when the job has a merge that has not been reverted."""
    merge = job.get("merge") or {}
    if merge.get("event") == "merge.completed" and merge.get("merge_commit"):
        return {"available": True, "job": job["id"],
                "reason": "revert this merge"}
    if merge.get("event") == "merge.undone":
        return {"available": False, "reason": "merge already reverted"}
    return {"available": False, "reason": "nothing merged yet"}


# ----------------------------------------------------------------------
# Commands (the dashboard never edits files directly)
# ----------------------------------------------------------------------

def dispatch(kernel, body: dict) -> dict:
    command = body.get("command")
    try:
        if command == "create_project":
            kernel.project_create(body["name"], mode=body.get("mode", "solo"))
            return {"ok": True}
        if command == "create_sample":
            return _create_sample(kernel)
        if command == "create_job":
            job = kernel.job_run(body["project"], body["brief"])
            return {"ok": True, "job": job["id"]}
        if command == "execute":
            return {"ok": True, "job": kernel.job_execute(body["job_id"])}
        if command == "approve":
            return {"ok": True, "job": kernel.job_approve(body["job_id"], sha=body.get("sha"))}
        if command == "change":
            return {"ok": True, "job": kernel.job_request_changes(
                body["job_id"], body.get("feedback", ""),
                adapter_id=body.get("adapter"))}
        if command == "cancel":
            return {"ok": True, "job": kernel.job_cancel(body["job_id"])}
        if command == "answer":
            return {"ok": True, "job": kernel.job_answer(
                body["job_id"], body["question_id"], body.get("answer", ""),
                adapter_id=body.get("adapter"))}
        if command == "undo":
            return {"ok": True, "job": kernel.job_undo(body["job_id"])}
        if command == "explain":
            job = kernel.job_status(body["job_id"])
            return {"ok": True, "explanation": _explain(kernel, job)}
        return {"ok": False, "error": f"unknown command '{command}'"}
    except Exception as e:  # report, never crash the server
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def _create_sample(kernel) -> dict:
    existing = {p["name"] for p in kernel.project_list()}
    name = "sample" if "sample" not in existing else "sample-2"
    kernel.project_create(name, mode="solo")
    job = kernel.job_run(name, "A friendly landing page with a hero and a contact form")
    return {"ok": True, "job": job["id"]}


# ----------------------------------------------------------------------
# Static export
# ----------------------------------------------------------------------

def export_dashboard(kernel, out: Optional[Path] = None, project: Optional[str] = None) -> Path:
    out = Path(out) if out else (kernel.root / "dashboard.html")
    view = build_view(kernel, project=project)
    out.write_text(render_html(view, live=False), encoding="utf-8")
    return out


# ----------------------------------------------------------------------
# HTTP server
# ----------------------------------------------------------------------

def make_server(kernel, host: str = "127.0.0.1", port: int = 8787) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), _make_handler(kernel))


def serve(kernel, host: str = "127.0.0.1", port: int = 8787, open_browser: bool = True) -> None:
    httpd = make_server(kernel, host, port)
    url = f"http://{host}:{httpd.server_address[1]}/"
    print(f"factory dashboard: {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def _make_handler(kernel):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # keep the console quiet
            return

        def _send(self, code: int, body, ctype: str = "application/json") -> None:
            data = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                self._send(200, render_html(build_view(kernel), live=True),
                           "text/html; charset=utf-8")
            elif path == "/api/state":
                self._send(200, json.dumps(build_view(kernel)))
            elif path == "/api/stream":
                self._stream()
            else:
                self._send(404, json.dumps({"error": "not found"}))

        def _stream(self):
            """Server-sent events: push the whole view whenever it changes."""
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            last = None
            try:
                while True:
                    view = build_view(kernel)
                    payload = json.dumps(view, sort_keys=True)
                    if payload != last:
                        self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                        self.wfile.flush()
                        last = payload
                    time.sleep(1.0)
            except (BrokenPipeError, ConnectionResetError, OSError):
                return

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                body = {}
            result = dispatch(kernel, body)
            self._send(200 if result.get("ok") else 400, json.dumps(result))

    return Handler


def render_html(view: dict, live: bool = False) -> str:
    """Self-contained dashboard page. `live=True` streams from /api/stream."""
    payload = json.dumps(view)
    return _TEMPLATE.replace("__VIEW__", payload).replace("__LIVE__", "true" if live else "false")


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Factory</title>
<style>
  :root { color-scheme: light dark; --bg:#0f1115; --card:#1a1d24; --ink:#e8eaed;
          --muted:#9aa0a6; --line:#2a2e37; --accent:#7c9cff; --good:#4caf7d; --warn:#e0a458; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font:16px/1.5 system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }
  .wrap { max-width: 860px; margin: 0 auto; padding: 28px 20px 64px; }
  h1 { font-size: 20px; margin: 0 0 4px; }
  .muted { color: var(--muted); font-size: 13px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:14px;
          padding:18px 20px; margin:14px 0; }
  .row { display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
  input, select, textarea { background:#12151b; color:var(--ink); border:1px solid var(--line);
          border-radius:10px; padding:10px 12px; font:inherit; }
  input.brief { flex:1; min-width:220px; }
  textarea { width:100%; min-height:64px; }
  button { background:var(--accent); color:#0b0d12; border:0; border-radius:10px;
           padding:10px 16px; font:inherit; font-weight:600; cursor:pointer; }
  button.secondary { background:transparent; color:var(--ink); border:1px solid var(--line); }
  button:disabled { opacity:.5; cursor:not-allowed; }
  ol.timeline { list-style:none; margin:0; padding:0; }
  ol.timeline li { display:flex; align-items:center; gap:12px; padding:8px 0; color:var(--muted); }
  ol.timeline li .dot { width:12px; height:12px; border-radius:50%; border:2px solid var(--line); }
  li.done { color:var(--ink); } li.done .dot { background:var(--good); border-color:var(--good); }
  li.active { color:var(--ink); font-weight:600; }
  li.active .dot { background:var(--accent); border-color:var(--accent); box-shadow:0 0 0 4px #7c9cff33; }
  li.failed .dot { background:#d64545; border-color:#d64545; }
  .needs { border-color:var(--accent); }
  .pill { font-size:12px; padding:2px 9px; border-radius:999px; border:1px solid var(--line); color:var(--muted); }
  details summary { cursor:pointer; color:var(--muted); }
  table { width:100%; border-collapse:collapse; font-size:14px; }
  td, th { text-align:left; padding:7px 8px; border-bottom:1px solid var(--line); }
  .err { color:var(--warn); font-size:13px; min-height:18px; }
  code { background:#12151b; padding:1px 6px; border-radius:6px; font-size:12px; }
  .player { position:fixed; left:0; right:0; bottom:0; background:#161920;
            border-top:1px solid var(--line); padding:10px 16px; z-index:50; }
  .player-bar { max-width:1100px; margin:0 auto; display:flex; align-items:center;
                gap:18px; }
  .p-track { display:flex; align-items:center; gap:10px; width:280px; min-width:0; }
  .p-glyph { width:34px; height:34px; border-radius:8px; background:var(--accent);
             display:flex; align-items:center; justify-content:center;
             color:#0b0d12; font-size:16px; flex:none; }
  .p-glyph.needs { background:var(--warn); }
  .p-glyph.stalled { background:#d64545; }
  .p-meta { min-width:0; }
  .p-brief { font-size:13px; font-weight:600; white-space:nowrap; overflow:hidden;
             text-overflow:ellipsis; }
  .p-progress { flex:1; min-width:120px; }
  .p-bar { height:6px; border-radius:999px; background:var(--line); overflow:hidden; }
  .p-fill { height:100%; background:var(--accent); width:0%; transition:width .4s; }
  .p-stage { font-size:12px; color:var(--muted); margin-top:4px; }
  .p-controls { display:flex; gap:8px; flex:none; }
  .p-controls button { padding:7px 12px; font-size:13px; }
  @media (prefers-reduced-motion: no-preference) {
    .p-glyph.spin { animation:pulse 1.4s ease-in-out infinite; }
    @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:.55; } }
  }
</style>
</head>
<body>
<div class="wrap">
  <div class="row" style="justify-content:space-between">
    <div>
      <h1>Factory</h1>
      <div class="muted" id="sub">Solo view · live</div>
    </div>
    <div class="row">
      <span class="pill" id="sandbox">sandbox: —</span>
      <button class="secondary" id="undo" disabled>Undo</button>
    </div>
  </div>

  <div class="card" id="prompt-card">
    <div class="row">
      <select id="project"></select>
      <input class="brief" id="brief" placeholder="Describe what you want…" />
      <button id="go">Start</button>
    </div>
    <div class="muted" id="estimate" style="margin-top:8px"></div>
  </div>

  <div id="empty" class="card" style="display:none">
    <strong>No projects yet.</strong>
    <div class="muted" style="margin:8px 0">Start with a sample to see how this works.</div>
    <button id="sample">Create a sample project</button>
  </div>

  <div class="card" id="timeline-card" style="display:none">
    <div class="muted" id="tl-title">Progress</div>
    <ol class="timeline" id="timeline"></ol>
    <div class="row" id="preview-row" style="margin-top:6px"></div>
    <div class="row" id="visual-row" style="margin-top:6px"></div>
  </div>

  <div class="card needs" id="needs-card" style="display:none">
    <div class="row" style="justify-content:space-between">
      <strong id="needs-title">Needs you</strong>
      <span class="pill" id="needs-kind"></span>
    </div>
    <p id="needs-body"></p>
    <div class="muted" id="needs-sha"></div>
    <div class="row" id="needs-actions" style="margin-top:10px"></div>
    <div class="muted" id="explain-box" style="display:none;margin-top:10px;white-space:pre-wrap"></div>
    <textarea id="feedback" placeholder="What should change?" style="display:none;margin-top:10px"></textarea>
  </div>

  <div class="card">
    <details>
      <summary>Details</summary>
      <table style="margin-top:10px">
        <thead><tr><th>Job</th><th>Project</th><th>State</th><th>Updated</th></tr></thead>
        <tbody id="jobs"></tbody>
      </table>
    </details>
  </div>

  <div class="err" id="err"></div>
</div>

<footer class="player" id="player" role="region" aria-label="Active task" style="display:none">
  <div class="player-bar">
    <div class="p-track">
      <div class="p-glyph" id="p-glyph" aria-hidden="true">▶</div>
      <div class="p-meta">
        <div class="p-brief" id="p-brief"></div>
        <span class="pill" id="p-project"></span>
      </div>
    </div>
    <div class="p-progress">
      <div class="p-bar" id="p-bar" role="progressbar" aria-label="Task progress"
           aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
        <div class="p-fill" id="p-fill" aria-hidden="true"></div>
      </div>
      <div class="p-stage" id="p-stage" role="status" aria-live="polite"></div>
    </div>
    <div class="p-controls">
      <button id="p-resume">Resume</button>
      <button id="p-need" class="secondary">Needs you</button>
      <button id="p-stop" class="secondary">Stop</button>
    </div>
  </div>
</footer>

<script>
const LIVE = __LIVE__;
let VIEW = __VIEW__;
let PLAYER = null;
const $ = (id) => document.getElementById(id);
const api = (path) => path;
const esc = (s) => (s == null ? "" : String(s)).replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));

function render(v) {
  VIEW = v;
  $("sandbox").textContent = "sandbox: " + (v.sandbox ? v.sandbox.type : "—");
  $("undo").disabled = !(v.undo && v.undo.available);
  $("undo").title = v.undo ? v.undo.reason : "";
  $("estimate").textContent = v.estimate
    ? `Estimated: up to $${v.estimate.usd} and about ${v.estimate.minutes} min`
    : "";
  $("empty").style.display = v.empty_state ? "block" : "none";

  const projects = $("project");
  projects.innerHTML = v.projects.map(p => `<option>${esc(p.name)}</option>`).join("");

  const job = v.active_job;
  const tl = $("timeline-card");
  if (job && v.timeline.length) {
    tl.style.display = "block";
    $("tl-title").textContent = `${esc(job.state_phrase)} · ${esc(job.brief)}`;
    $("timeline").innerHTML = v.timeline.map(s =>
      `<li class="${s.status}"><span class="dot"></span><span>${esc(s.phrase)}</span></li>`).join("");
    const pv = v.preview || {};
    $("preview-row").innerHTML = pv.available
      ? `<span class="pill">preview ready</span><span class="muted">${esc(pv.note)}</span>`
      : "";
    const vv = $("visual-row");
    if (vv) {
      const vis = pv.visual || [];
      vv.innerHTML = vis.map(m =>
        `<div class="muted" style="margin-top:6px">${esc(m.stage)}` +
        (m.synthetic ? ` <span class="pill">synthetic fixture — not a real screenshot</span>` : "") +
        `<ul>` + m.entries.map(e =>
          `<li>${esc(e.viewport)} · ${esc(e.theme)} · ${esc(e.file)}` +
          (typeof e.changed_pct === "number"
            ? ` · <b>changed ${e.changed_pct}%</b>` : "") +
          `</li>`).join("") +
        `</ul></div>`
      ).join("");
    }
  } else {
    tl.style.display = "none";
  }

  const card = $("needs-card");
  if (v.needs_you) {
    const n = v.needs_you;
    card.style.display = "block";
    $("needs-title").textContent = n.title;
    $("needs-kind").textContent = n.kind;
    $("needs-body").textContent = n.body;
    $("needs-sha").textContent = n.sha ? ("checkpoint " + n.sha.slice(0, 12) + "…") : "";
    $("needs-actions").innerHTML = "";
    $("explain-box").style.display = "none";
    (n.actions || []).forEach(a => {
      const b = document.createElement("button");
      b.textContent = a.label;
      if (!a.primary) b.className = "secondary";
      b.onclick = () => onAction(a.id, n.job);
      $("needs-actions").appendChild(b);
    });
    if (n.kind === "question") {
      (n.questions || []).forEach(q => {
        const wrap = document.createElement("div");
        wrap.style.marginTop = "10px";
        const qt = document.createElement("div");
        qt.innerHTML = "<b>Q:</b> ";
        qt.appendChild(document.createTextNode(q.text));
        wrap.appendChild(qt);
        const opts = document.createElement("div");
        opts.style.marginTop = "6px";
        (q.options || []).forEach(o => {
          const b = document.createElement("button");
          b.className = "secondary";
          b.textContent = o;
          b.onclick = () => send({command: "answer", job_id: n.job,
                                  question_id: q.id, answer: o});
          opts.appendChild(b);
        });
        const box = document.createElement("input");
        box.placeholder = "Or type your answer…";
        box.style.marginTop = "6px";
        box.onkeydown = (e) => {
          if (e.key === "Enter" && box.value.trim())
            send({command: "answer", job_id: n.job,
                  question_id: q.id, answer: box.value.trim()});
        };
        wrap.appendChild(opts);
        wrap.appendChild(box);
        $("needs-actions").appendChild(wrap);
      });
    }
    $("feedback").style.display = "none";
  } else {
    card.style.display = "none";
  }

  $("jobs").innerHTML = v.jobs.map(j =>
    `<tr><td>${esc(j.brief).slice(0,48)}</td><td>${esc(j.project)}</td>` +
    `<td>${esc(j.state_phrase)}</td><td class="muted">${esc((j.updated_at||"").slice(0,19))}</td></tr>`
  ).join("");

  renderPlayer(v);
}

function renderPlayer(v) {
  const el = $("player");
  const p = v.player;
  PLAYER = p;
  if (!p) { el.style.display = "none"; document.body.style.paddingBottom = ""; return; }
  el.style.display = "block";
  document.body.style.paddingBottom = "84px";

  const glyph = $("p-glyph");
  glyph.textContent = p.needs_you ? "!" : (p.state === "running" ? "▶" : "⏸");
  glyph.className = "p-glyph" + (p.needs_you ? " needs" : "")
    + (p.state === "running" ? " spin" : "")
    + (p.state === "stalled" || p.state === "failed" ? " stalled" : "");
  $("p-brief").textContent = p.brief;
  $("p-brief").title = p.state_phrase;
  $("p-project").textContent = p.project || "";
  $("p-fill").style.width = p.pct + "%";
  // The bar is decorative; the progressbar role carries the value so a screen
  // reader hears "3 of 5 stages" rather than an unlabelled coloured strip.
  $("p-bar").setAttribute("aria-valuenow", String(p.pct));
  $("p-bar").setAttribute("aria-valuetext", `${p.done} of ${p.total} stages`);
  $("p-stage").textContent = `${p.stage_phrase} · ${p.done}/${p.total}`;

  // Controls are static nodes toggled by visibility: rebuilding them per
  // stream tick would drop an in-flight click. In a read-only export they
  // still render (the footer is the ambient signal) and a click falls through
  // to send(), which refuses with the "Read-only export" note.
  $("p-resume").textContent = p.resume_label;
  $("p-resume").hidden = !p.can_resume;
  $("p-need").hidden = !p.needs_you;
  $("p-stop").hidden = !p.can_stop;
}

async function send(payload, then) {
  $("err").textContent = "";
  if (!LIVE) { $("err").textContent = "Read-only export — run `factory serve` to act."; return; }
  try {
    const r = await fetch(api("/api/command"), {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    });
    const out = await r.json();
    if (!out.ok) $("err").textContent = out.error || "action failed";
    else if (then) then(out);
    refresh();
  } catch (e) { $("err").textContent = String(e); }
}

function onAction(id, jobId) {
  if (id === "approve") return send({command: "approve", job_id: jobId,
                                     sha: VIEW.needs_you && VIEW.needs_you.sha});
  if (id === "change") {
    const box = $("feedback");
    if (box.style.display === "none") { box.style.display = "block"; box.focus(); return; }
    return send({command: "change", job_id: jobId, feedback: box.value});
  }
  if (id === "explain") {
    const box = $("explain-box");
    if (box.style.display === "block") { box.style.display = "none"; return; }
    if (!LIVE) { box.textContent = "Read-only export — run `factory serve` to act."; box.style.display = "block"; return; }
    return send({command: "explain", job_id: jobId}, (out) => {
      box.textContent = (out.explanation || []).join("\n");
      box.style.display = "block";
    });
  }
}

$("go").onclick = () => {
  const brief = $("brief").value.trim();
  if (!brief) return;
  send({command: "create_job", project: $("project").value, brief});
};
$("sample").onclick = () => send({command: "create_sample"});
$("undo").onclick = () => {
  if (VIEW.undo && VIEW.undo.available) send({command: "undo", job_id: VIEW.undo.job});
};
$("p-resume").onclick = () => PLAYER && send({command: "execute", job_id: PLAYER.job});
$("p-stop").onclick = () => PLAYER && send({command: "cancel", job_id: PLAYER.job});
$("p-need").onclick = () => $("needs-card").scrollIntoView({behavior:"smooth", block:"center"});

async function refresh() {
  try {
    const r = await fetch(api("/api/state"));
    if (r.ok) render(await r.json());
  } catch (e) { /* ignore */ }
}

render(VIEW);
if (LIVE) {
  try {
    const es = new EventSource("/api/stream");
    es.onmessage = (e) => render(JSON.parse(e.data));
    es.onerror = () => { es.close(); setInterval(refresh, 3000); };
  } catch (e) { setInterval(refresh, 3000); }
}
</script>
</body>
</html>
"""

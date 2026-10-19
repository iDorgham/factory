"""Tests for operator cancellation of work in flight.

Stopping a job has to stop the *work*: the adapter process (and anything it
spawned) must be dead, and the pipeline must not run checks or write events
after the operator pressed Stop.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

from factory_kernel.adapters import Adapter
from factory_kernel.cancel import run_cancellable
from factory_kernel.checks import run_one

REPO_ROOT = Path(__file__).resolve().parents[1]


def _fake_adapter(directory: Path, adapter_id: str, body: str) -> Path:
    d = directory / adapter_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(
        json.dumps({"id": adapter_id, "entrypoint": "run.py", "capabilities": []}),
        encoding="utf-8",
    )
    (d / "run.py").write_text(body, encoding="utf-8")
    return d


def test_run_cancellable_reports_a_cancelled_run():
    outcome = run_cancellable(
        f'"{sys.executable}" -c "import time; time.sleep(30)"',
        shell=True,
        timeout=60,
        cancel=lambda: True,
    )
    assert outcome.cancelled
    assert not outcome.timed_out


def test_run_cancellable_reports_a_timeout():
    outcome = run_cancellable(
        f'"{sys.executable}" -c "import time; time.sleep(30)"',
        shell=True,
        timeout=0.5,
    )
    assert outcome.timed_out
    assert not outcome.cancelled


def test_run_cancellable_returns_the_output_of_a_normal_run():
    outcome = run_cancellable(
        f'"{sys.executable}" -c "print(\'hello\')"',
        shell=True,
        timeout=30,
    )
    assert not outcome.timed_out and not outcome.cancelled
    assert "hello" in outcome.stdout
    assert outcome.returncode == 0


def test_run_cancellable_collects_the_last_output(tmp_path):
    """A process that exits between two polls must not lose its last lines:
    the adapter's final NDJSON event is exactly the one that says "done"."""
    script = tmp_path / "chatty.py"
    script.write_text(
        "import sys\n"
        "for i in range(500):\n"
        "    print('line-%d' % i)\n"
        "sys.stdout.flush()\n",
        encoding="utf-8",
    )
    outcome = run_cancellable(
        f'"{sys.executable}" "{script}"', shell=True, timeout=30
    )
    assert outcome.returncode == 0
    assert outcome.stdout.count("line-") == 500
    assert "line-499" in outcome.stdout


def test_cancelling_an_adapter_kills_it(tmp_path):
    """The adapter is gone: it never gets to write the file it would have
    written three seconds later."""
    marker = tmp_path / "written-later.txt"
    body = (
        "import json,sys,time\n"
        "sys.stdin.read()\n"
        "time.sleep(3)\n"
        f"open({str(marker)!r}, 'w').write('done')\n"
        "print(json.dumps({'type':'done'}))\n"
    )
    d = _fake_adapter(tmp_path, "slow", body)
    adapter = Adapter(d)
    request = {"stage": "understand", "attempt": 1, "attempt_dir": str(tmp_path / "a"),
               "produces": []}
    result = adapter.run(request, timeout=60, cancel=lambda: True)
    assert result.error_class == "cancelled"
    assert not result.ok
    time.sleep(4.0)
    assert not marker.exists()


def test_cancelling_a_check_kills_it(tmp_path):
    result = run_one(
        "slow",
        {"cmd": f'"{sys.executable}" -c "import time; time.sleep(30)"'},
        tmp_path,
        timeout=60,
        cancel=lambda: True,
    )
    assert result.cancelled
    assert not result.passed
    assert "cancelled" in result.output


def test_run_cancellable_kills_the_whole_tree(tmp_path):
    """A grandchild process dies with its parent: the tree is killed, not
    just the process the kernel started."""
    marker = tmp_path / "grandchild.txt"
    pidfile = tmp_path / "grandchild.pid"
    grandchild = tmp_path / "grandchild.py"
    grandchild.write_text(
        "import os, sys, time\n"
        "open(sys.argv[1], 'w').write(str(os.getpid()))\n"
        "time.sleep(3)\n"
        "open(sys.argv[2], 'w').write('x')\n",
        encoding="utf-8",
    )
    script = tmp_path / "spawner.py"
    script.write_text(
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable] + sys.argv[1:])\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )

    def cancel() -> bool:
        # Cancel only once the grandchild exists, so the tree is really there
        # to be killed.
        return pidfile.exists()

    outcome = run_cancellable(
        [sys.executable, str(script), str(grandchild), str(pidfile), str(marker)],
        timeout=60, cancel=cancel,
    )
    assert outcome.cancelled
    time.sleep(4.0)
    assert not marker.exists()


def test_cancelling_a_running_job_stops_the_adapter(kernel, tmp_path):
    """End to end: a job that is cancelled while its adapter runs ends
    ``cancelled`` — and the adapter does not get to finish its work."""
    kernel.project_create("demo", mode="solo", domain="web")
    job = kernel.job_run("demo", "Build a landing page")
    job_id = job["id"]

    marker = tmp_path / "adapter-finished.txt"
    started = tmp_path / "adapter-started.txt"
    _fake_adapter(
        kernel.adapters_dir,
        "slow-adapter",
        "import json,sys,time\n"
        "req = json.loads(sys.stdin.read())\n"
        f"open({str(started)!r}, 'w').write('running')\n"
        "time.sleep(20)\n"
        f"open({str(marker)!r}, 'w').write('done')\n"
        "print(json.dumps({'type':'done'}))\n",
    )

    done = threading.Event()

    def run():
        try:
            kernel.job_execute(job_id, adapter_id="slow-adapter")
        finally:
            done.set()

    worker = threading.Thread(target=run, daemon=True)
    worker.start()

    # Wait until the adapter is actually running, then stop the job.
    deadline = time.monotonic() + 30
    while not started.exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert started.exists(), "the adapter never started"
    kernel.job_cancel(job_id)
    assert done.wait(timeout=30), "the engine did not stop after the cancel"

    status = kernel.job_status(job_id)
    assert status["state"] == "cancelled"
    time.sleep(1.0)
    assert not marker.exists(), "the adapter kept working after the cancel"


def test_the_engine_notices_a_cancelled_job(kernel):
    """The cancel signal the engine reads is the job's own state."""
    from factory_kernel.engine import Engine

    kernel.project_create("demo", mode="solo", domain="web")
    job = kernel.job_run("demo", "Build a landing page")
    job_id = job["id"]

    engine = Engine(kernel)
    job_dir = kernel._find_job_dir(job_id)
    assert engine._cancel_requested(job_dir, fence=1) is False

    kernel.job_cancel(job_id)
    assert engine._cancel_requested(job_dir, fence=1) is True

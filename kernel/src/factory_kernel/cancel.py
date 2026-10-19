"""Operator cancellation of work in flight (the kernel's Stop control).

Stopping a job has to actually stop the work. A job marked ``cancelled`` while
its adapter process keeps running leaves the agent editing files and spending
money long after the operator was told it stopped — so the kernel needs two
primitives:

* :func:`kill_tree` — terminates a subprocess *and its children*, so an agent
  that spawned a shell does not outlive the adapter it belongs to.
* :func:`run_cancellable` — runs a subprocess under a deadline and a cancel
  predicate, and reports which of the two ended the run.

Both are platform-aware: POSIX kills the whole process group, Windows uses
``taskkill /T`` (``terminate`` alone would leave grandchildren running).
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Callable, Optional, Sequence, Union

# How often the run loop wakes to check the deadline and the cancel predicate.
POLL_SECONDS = 0.2

# How long a killed process is given to die before it is killed outright.
KILL_GRACE_SECONDS = 2.0


@dataclass
class ProcOutcome:
    """What a subprocess run produced, and what ended it."""

    returncode: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    cancelled: bool = False


def _kill_tree_posix(proc: subprocess.Popen) -> None:
    try:
        pgid = os.getpgid(proc.pid)
    except (OSError, AttributeError):
        pgid = None
    try:
        if pgid is not None:
            os.killpg(pgid, signal.SIGTERM)
        else:
            proc.terminate()
    except (OSError, ProcessLookupError):
        return
    deadline = time.monotonic() + KILL_GRACE_SECONDS
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return
        time.sleep(0.05)
    try:
        if pgid is not None:
            os.killpg(pgid, signal.SIGKILL)
        else:
            proc.kill()
    except (OSError, ProcessLookupError):
        pass


def _kill_tree_windows(proc: subprocess.Popen) -> None:
    try:
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        proc.kill()
    except (OSError, ProcessLookupError):
        pass


def kill_tree(proc: subprocess.Popen) -> None:
    """Terminate a subprocess and everything it started."""
    if sys.platform == "win32":
        _kill_tree_windows(proc)
    else:
        _kill_tree_posix(proc)


def _popen_kwargs(cwd, env, shell: bool) -> dict:
    kwargs: dict = {
        "cwd": cwd,
        "env": env,
        "text": True,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "stdin": subprocess.PIPE,
    }
    if shell:
        kwargs["shell"] = True
    if sys.platform == "win32":
        # A process group of its own, so a console interrupt aimed at the
        # kernel does not reach the adapter — and vice versa.
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        # A new session makes the child a process-group leader, so killpg
        # takes down the whole tree.
        kwargs["start_new_session"] = True
    return kwargs


def run_cancellable(
    cmd: Union[str, Sequence[str]],
    *,
    input: Optional[str] = None,
    cwd: Optional[str] = None,
    env: Optional[dict] = None,
    timeout: Optional[float] = None,
    cancel: Optional[Callable[[], bool]] = None,
    shell: bool = False,
) -> ProcOutcome:
    """Run a command, honouring a cancel predicate and a timeout.

    ``cancel`` is polled between waits; when it returns True the process tree
    is killed and the outcome is marked ``cancelled``. A timeout kills the tree
    too — a timed-out adapter that keeps running is the same problem as an
    uncancelled one.
    """
    proc = subprocess.Popen(cmd, **_popen_kwargs(cwd, env, shell))
    if input is not None:
        try:
            proc.stdin.write(input)
            proc.stdin.close()
        except (OSError, ValueError):
            pass

    deadline = None if timeout is None else time.monotonic() + timeout
    out, err = "", ""
    while True:
        if proc.poll() is not None:
            break
        if cancel is not None and cancel():
            kill_tree(proc)
            out, err = _drain(proc, out, err)
            return ProcOutcome(returncode=proc.returncode, stdout=out, stderr=err,
                               cancelled=True)
        if deadline is not None and time.monotonic() >= deadline:
            kill_tree(proc)
            out, err = _drain(proc, out, err)
            return ProcOutcome(returncode=proc.returncode, stdout=out, stderr=err,
                               timed_out=True)
        out, err = _drain(proc, out, err, wait=POLL_SECONDS)
    # The process has exited: one last read collects everything it wrote.
    # Without it, output produced between the last poll and the exit would be
    # lost — and the adapter's last NDJSON event is exactly what says "done".
    out, err = _drain(proc, out, err)
    return ProcOutcome(returncode=proc.returncode, stdout=out, stderr=err)


def _drain(proc: subprocess.Popen, out: str, err: str,
           wait: Optional[float] = None) -> tuple[str, str]:
    """Read whatever the process has produced, waiting up to ``wait`` seconds.

    ``communicate`` after a timeout keeps the already-read output, so a
    cancelled run still reports what the adapter managed to say.
    """
    try:
        new_out, new_err = proc.communicate(timeout=wait)
    except subprocess.TimeoutExpired:
        return out, err
    except (OSError, ValueError):
        return out, err
    if new_out is None and new_err is None:
        return out, err
    return (new_out if new_out is not None else out,
            new_err if new_err is not None else err)

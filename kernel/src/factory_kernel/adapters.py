"""Adapter runtime (spec §20).

An adapter is a folder under ``adapters/`` with a ``manifest.json`` and an
entrypoint. The kernel invokes the entrypoint as a subprocess, passes the run
request as JSON on stdin, and reads an NDJSON event stream on stdout.

Events: progress | tool_use | file_written | question | usage | heartbeat |
done | error. Errors are classified transient | capability | budget | fatal |
cancelled.

The kernel owns retries; adapters only report.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Union

from .atomic import read_json
from .cancel import run_cancellable

# Highest-severity error class seen in a run (used for retry/routing decisions).
ERROR_CLASSES = {"transient", "capability", "budget", "fatal", "cancelled"}


class AdapterError(Exception):
    pass


@dataclass
class RunResult:
    ok: bool
    events: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    error: Optional[str] = None
    error_class: Optional[str] = None

    @property
    def written_files(self) -> list[str]:
        return [e["path"] for e in self.events if e.get("type") == "file_written" and "path" in e]

    @property
    def questions(self) -> list[dict]:
        return [e for e in self.events if e.get("type") == "question"]


class Adapter:
    def __init__(self, directory: Union[str, Path]):
        self.dir = Path(directory)
        manifest = read_json(self.dir / "manifest.json")
        if not isinstance(manifest, dict) or "id" not in manifest or "entrypoint" not in manifest:
            raise AdapterError(f"Invalid adapter manifest in {self.dir}")
        self.manifest = manifest
        self.id = manifest["id"]

    @property
    def capabilities(self) -> list[str]:
        return list(self.manifest.get("capabilities", []))

    @property
    def roles_supported(self) -> list[str]:
        return list(self.manifest.get("roles_supported", []))

    def run(self, request: dict, timeout: int = 600,
            cwd: Optional[Path] = None, env: Optional[dict] = None,
            cancel: Optional[Callable[[], bool]] = None) -> RunResult:
        """Run the adapter entrypoint.

        ``cwd``/``env`` are the sandbox channel (P2.3): the engine passes a
        sanitized environment and, under ``strict_cwd``, the job worktree.
        Defaults preserve the pre-sandbox behavior — adapter directory and
        the inheriting process env — which the operator-side conformance
        harness (a trusted tool run by the operator) keeps using.

        ``cancel`` is polled while the adapter runs: when it returns True the
        adapter process *and its children* are killed and the run reports the
        ``cancelled`` error class. Without it, a stopped job would keep its
        agent working and billing after the operator pressed Stop.
        """
        entry = (self.dir / self.manifest["entrypoint"]).resolve()
        if not entry.exists():
            raise AdapterError(f"Adapter entrypoint missing: {entry}")

        outcome = run_cancellable(
            [sys.executable, str(entry)],
            input=json.dumps(request),
            cwd=str(cwd) if cwd is not None else str(self.dir),
            env=dict(env) if env is not None else None,
            timeout=timeout,
            cancel=cancel,
        )
        if outcome.cancelled:
            return RunResult(
                ok=False,
                error="cancelled by operator",
                error_class="cancelled",
            )
        if outcome.timed_out:
            return RunResult(
                ok=False,
                error=f"adapter '{self.id}' timed out",
                error_class="transient",
            )

        events: list[dict] = []
        for line in (outcome.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                events.append({"type": "progress", "message": line})

        usage: dict = {}
        error = None
        error_class = None
        ok = False
        for ev in events:
            etype = ev.get("type")
            if etype == "usage":
                usage = ev
            elif etype == "done":
                ok = True
            elif etype == "error":
                ok = False
                error = ev.get("message", "adapter error")
                cls = ev.get("class") or ev.get("error_class") or "fatal"
                error_class = cls if cls in ERROR_CLASSES else "fatal"

        if outcome.returncode != 0 and not ok:
            if error is None:
                error = (outcome.stderr or "").strip() or f"adapter exited {outcome.returncode}"
                # A negative return code means the process was killed by a signal
                # (or, on Windows, terminated) — treat as a transient interruption.
                error_class = error_class or ("transient" if outcome.returncode < 0 else "fatal")

        return RunResult(ok=ok, events=events, usage=usage, error=error, error_class=error_class)


def discover_adapters(adapters_dir: Union[str, Path]) -> dict[str, Adapter]:
    adapters: dict[str, Adapter] = {}
    directory = Path(adapters_dir)
    if not directory.exists():
        return adapters
    for entry in sorted(directory.iterdir()):
        if entry.is_dir() and (entry / "manifest.json").exists():
            try:
                adapter = Adapter(entry)
            except AdapterError:
                continue
            adapters[adapter.id] = adapter
    return adapters


def select_adapter(
    adapters: dict[str, Adapter],
    adapter_id: Optional[str] = None,
    capabilities: Optional[list[str]] = None,
    role: Optional[str] = None,
) -> Adapter:
    if adapter_id:
        if adapter_id not in adapters:
            raise AdapterError(f"Adapter '{adapter_id}' not found")
        return adapters[adapter_id]

    required = set(capabilities or [])
    # Prefer echo when no explicit adapter_id is given (backward compatibility)
    echo = adapters.get("echo")
    if echo and required.issubset(set(echo.capabilities)):
        if not role or not echo.roles_supported or role in echo.roles_supported:
            return echo
    for adapter in adapters.values():
        if adapter.id == "echo":
            continue
        if not required.issubset(set(adapter.capabilities)):
            continue
        if role and adapter.roles_supported and role not in adapter.roles_supported:
            continue
        return adapter
    if echo:
        return echo
    if adapters:
        return next(iter(adapters.values()))
    raise AdapterError("No adapter available")

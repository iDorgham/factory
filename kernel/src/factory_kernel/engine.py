"""Stage-graph execution engine (spec §7, §8, §9).

Drives a job through its profile: for each stage it creates an attempt
directory, builds the context manifest, invokes an adapter, runs the declared
checks, and decides accept / retry / gate. The kernel owns every transition and
every event; the agent only writes files.
"""
from __future__ import annotations

import json
from typing import Optional

from .adapters import AdapterError, RunResult, discover_adapters, select_adapter
from .atomic import atomic_write_json, read_json
from .checkpoint import record_checkpoint
from .checks import fingerprint, load_checks, run_checks, summarise
from .context import collect_stage_context
from .hashing import sha256_hex
from .lease import LeaseManager
from .ulid import new_ulid

# Maximum time the engine will wait for one adapter run, regardless of budget.
ADAPTER_TIMEOUT_CAP = 3600


class EngineError(Exception):
    pass


def input_hash(manifest: dict, adapter_id: Optional[str]) -> str:
    """Content hash of an attempt's inputs (idempotency key for accepted work).

    Excludes volatile fields (job_id, attempt number) so a resume with identical
    inputs maps to the same key and can reuse an already-accepted result.
    """
    core = {
        "stage": manifest.get("stage"),
        "adapter": adapter_id,
        "files": [
            {"path": f.get("path"), "tokens": f.get("tokens")}
            for f in manifest.get("files", [])
        ],
        "summaries": manifest.get("summaries", {}),
    }
    return sha256_hex(json.dumps(core, sort_keys=True, separators=(",", ":")))


class Engine:
    """Executes jobs against a stage profile using the kernel's primitives."""

    def __init__(self, kernel):
        self.k = kernel

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def execute(
        self,
        job_id: str,
        adapter_id: Optional[str] = None,
        check_timeout: int = 600,
    ) -> dict:
        job = self.k.job_status(job_id)
        job_dir = self.k._find_job_dir(job_id)
        if job["state"] not in ("pending", "running", "awaiting_human"):
            raise EngineError(f"Job is '{job['state']}'; cannot execute")

        lease = LeaseManager(job_dir, self.k.actor)
        fence = lease.acquire()
        state = self.k._job_state(job_dir)
        try:
            if job["state"] in ("pending", "awaiting_human"):
                state.transition("running", actor=self.k.actor, fence=fence, reason="execute")
            profile = self.k.load_stage_profile(job["profile"])
            adapters = discover_adapters(self.k.adapters_dir)
            if not adapters:
                raise EngineError("No adapters installed under adapters/")
            return self._run_profile(
                job, job_dir, state, profile, adapters, adapter_id, fence, check_timeout
            )
        finally:
            if lease.current_token() == fence:
                lease.release(fence)

    # ------------------------------------------------------------------
    # Profile / stage
    # ------------------------------------------------------------------

    def _run_profile(
        self, job, job_dir, state, profile, adapters, adapter_id, fence, check_timeout
    ) -> dict:
        accepted = self._accepted_stages(state)
        stages = profile["stages"]
        for index, stage in enumerate(stages):
            if stage["id"] in accepted:
                continue
            next_stage = stages[index + 1]["id"] if index + 1 < len(stages) else None
            outcome = self._run_stage(
                job, job_dir, state, stage, index, next_stage, adapters, adapter_id, fence,
                check_timeout,
            )
            if outcome != "accepted":
                return state.fold()

        state.transition("completed", actor=self.k.actor, fence=fence, reason="all stages accepted")
        return state.fold()

    def _run_stage(
        self, job, job_dir, state, stage, index, next_stage, adapters, adapter_id, fence,
        check_timeout,
    ) -> str:
        sid = stage["id"]
        project_dir = self.k.projects_dir / job["project"]
        worktree = self.k.work_dir / job["id"]
        base = job_dir / "stages" / f"{index:02d}-{sid}"
        base.mkdir(parents=True, exist_ok=True)
        checks_cfg = load_checks(project_dir)

        started, last_status = self._attempts(state, sid)
        # An attempt that started but never finished was killed mid-flight:
        # record it as 'interrupted' (never success) before resuming.
        for attempt in [a for a in started if a not in last_status]:
            state.append_event(
                "stage.attempt_finished", actor=self.k.actor, fence=fence,
                data={"stage": sid, "attempt": attempt, "status": "interrupted",
                      "fingerprint": None, "missing": [], "adapter_error": "interrupted"},
                job_id=job["id"],
            )
            last_status[attempt] = "interrupted"

        state.append_event("stage.started", actor=self.k.actor, fence=fence,
                           data={"stage": sid}, job_id=job["id"])

        # Rounds already consumed by attempts that reached a verdict. Interrupted
        # attempts do not consume a round: they are retried at the same index.
        used = [a for a, s in last_status.items() if s in ("passed", "failed")]
        prev_fingerprint = self._last_fingerprint(state, sid)
        start = (max(used) + 1) if used else 1

        for attempt in range(start, stage["max_rounds"] + 1):
            attempt_dir = base / f"attempt-{attempt}"
            status, fp = self._run_attempt(
                job, job_dir, state, stage, attempt, attempt_dir, project_dir, worktree,
                adapter_id, adapters, checks_cfg, fence, check_timeout,
            )
            if status == "passed":
                sha = record_checkpoint(
                    state, attempt_dir, job_dir, worktree, sid, attempt,
                    self.k.actor, fence,
                )
                state.append_event(
                    "stage.accepted", actor=self.k.actor, fence=fence,
                    data={"stage": sid, "attempt": attempt, "next_stage": next_stage,
                          "sha": sha},
                    job_id=job["id"],
                )
                return self._apply_gate(job, state, stage, fence)

            # Failed/interrupted attempt: detect no-progress (spec §9.2).
            if prev_fingerprint is not None and fp == prev_fingerprint:
                state.transition("stalled", actor=self.k.actor, fence=fence,
                                 reason=f"no progress in stage '{sid}'")
                return "stalled"
            prev_fingerprint = fp

        # Rounds exhausted. 'fail' stops the job; 'loop'/'escalate' hand to a human.
        if stage["on_fail"] == "fail":
            state.transition("failed", actor=self.k.actor, fence=fence,
                             reason=f"stage '{sid}' failed after {stage['max_rounds']} rounds")
            return "failed"
        state.transition("awaiting_human", actor=self.k.actor, fence=fence,
                         reason=f"stage '{sid}' exhausted {stage['max_rounds']} rounds")
        return "awaiting_human"

    def _run_attempt(
        self, job, job_dir, state, stage, attempt, attempt_dir, project_dir, worktree,
        adapter_id, adapters, checks_cfg, fence, check_timeout,
    ):
        sid = stage["id"]
        (attempt_dir / "outputs").mkdir(parents=True, exist_ok=True)

        manifest = collect_stage_context(
            project_dir, job_dir, stage, attempt, stage["budget"].get("tokens", 100000)
        )
        self.k.schemas.validate("context.manifest", manifest)
        atomic_write_json(attempt_dir / "context.manifest.json", manifest)

        state.append_event("stage.attempt_started", actor=self.k.actor, fence=fence,
                           data={"stage": sid, "attempt": attempt}, job_id=job["id"])

        adapter = select_adapter(adapters, adapter_id=adapter_id, role=stage["role"])
        key = input_hash(manifest, adapter.id)
        atomic_write_json(attempt_dir / "input.json", {"input_hash": key})

        # Idempotency: identical inputs that already produced an accepted result
        # are reused rather than re-run.
        previous = read_json(attempt_dir / "result.json")
        if previous and previous.get("input_hash") == key and previous.get("status") == "passed":
            state.append_event(
                "stage.attempt_finished", actor=self.k.actor, fence=fence,
                data={"stage": sid, "attempt": attempt, "status": "passed",
                      "fingerprint": previous.get("fingerprint"), "missing": [],
                      "reused": True},
                job_id=job["id"],
            )
            return "passed", previous.get("fingerprint")

        run = self._invoke_adapter(
            adapter, job, stage, attempt, attempt_dir, worktree, manifest, fence
        )
        usage = {k: v for k, v in run.usage.items() if k != "type"}
        usage["events"] = len(run.events)
        atomic_write_json(attempt_dir / "usage.json", usage)

        missing = self._missing_outputs(stage, attempt_dir)
        results = run_checks(checks_cfg, stage["checks"], worktree, timeout=check_timeout)
        summary = summarise(results)
        atomic_write_json(attempt_dir / "checks.json", {
            "results": [r.to_dict() for r in results],
            "summary": summary,
        })
        state.append_event(
            "checks.completed", actor=self.k.actor, fence=fence,
            data={"stage": sid, "attempt": attempt, "passed": summary["passed"],
                  "failed": summary["failed"]},
            job_id=job["id"],
        )

        if run.ok and not missing and summary["passed"]:
            status = "passed"
        elif not run.ok and (run.error_class == "transient"):
            status = "interrupted"
        else:
            status = "failed"

        extra = run.error or ""
        if missing:
            extra = (extra + " " if extra else "") + "missing:" + ",".join(missing)
        fp = fingerprint(results, extra=extra)

        atomic_write_json(attempt_dir / "result.json", {
            "input_hash": key, "status": status, "fingerprint": fp,
        })
        state.append_event(
            "stage.attempt_finished", actor=self.k.actor, fence=fence,
            data={"stage": sid, "attempt": attempt, "status": status,
                  "fingerprint": fp, "missing": missing,
                  "adapter_error": run.error},
            job_id=job["id"],
        )
        return status, fp

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _invoke_adapter(self, adapter, job, stage, attempt, attempt_dir, worktree, manifest, fence):
        budget = stage["budget"]
        timeout = min(int(budget.get("minutes", 30) * 60) or 600, ADAPTER_TIMEOUT_CAP)
        request = {
            "run_id": new_ulid(),
            "job_id": job["id"],
            "project": job["project"],
            "stage": stage["id"],
            "role": stage["role"],
            "attempt": attempt,
            "brief": job.get("brief", ""),
            "worktree": str(worktree),
            "attempt_dir": str(attempt_dir),
            "manifest_path": str(attempt_dir / "context.manifest.json"),
            "produces": stage["produces"],
            "budget": budget,
            "fence": fence,
        }
        try:
            return adapter.run(request, timeout=timeout)
        except AdapterError as e:
            return RunResult(ok=False, error=str(e), error_class="fatal")

    @staticmethod
    def _missing_outputs(stage, attempt_dir) -> list[str]:
        missing = []
        for name in stage["produces"]:
            if name.startswith("git:") or name.endswith("/"):
                continue
            if not (attempt_dir / "outputs" / name).exists():
                missing.append(name)
        return missing

    @staticmethod
    def _accepted_stages(state) -> set[str]:
        return {
            ev["data"].get("stage")
            for ev in state.load_events()
            if ev["type"] == "stage.accepted"
        }

    @staticmethod
    def _attempts(state, sid: str):
        """(started attempt numbers, latest recorded status per attempt) for a stage."""
        started: list[int] = []
        last_status: dict[int, str] = {}
        for ev in state.load_events():
            data = ev.get("data", {})
            if data.get("stage") != sid:
                continue
            if ev["type"] == "stage.attempt_started":
                started.append(data["attempt"])
            elif ev["type"] == "stage.attempt_finished":
                last_status[data["attempt"]] = data.get("status")
        return started, last_status

    @staticmethod
    def _last_fingerprint(state, sid: str) -> Optional[str]:
        seen = None
        for ev in state.load_events():
            data = ev.get("data", {})
            if (ev["type"] == "stage.attempt_finished"
                    and data.get("stage") == sid
                    and data.get("status") == "failed"):
                seen = data.get("fingerprint")
        return seen

    def _apply_gate(self, job, state, stage, fence) -> str:
        sid = stage["id"]
        decision = self._gate_decision(stage["gate"])
        state.append_event(
            "gate.evaluated", actor=self.k.actor, fence=fence,
            data={"stage": sid, "gate": stage["gate"], "decision": decision},
            job_id=job["id"],
        )
        if decision == "require_human":
            state.transition("awaiting_human", actor=self.k.actor, fence=fence,
                             reason=f"gate '{stage['gate']}' on stage '{sid}'")
            return "awaiting_human"
        return "accepted"

    @staticmethod
    def _gate_decision(gate: str) -> str:
        """Risk scoring arrives in P2; risk is treated as 0 for now."""
        risk = 0.0
        if gate == "none":
            return "auto"
        if gate == "required":
            return "require_human"
        if gate == "risk_scored":
            return "auto" if risk < 50 else "require_human"
        if gate.startswith("if_risk_above:"):
            thresholds = {"low": 10, "medium": 40, "high": 70}
            level = gate.split(":", 1)[1]
            return "require_human" if risk > thresholds.get(level, 40) else "auto"
        return "auto"

"""Stage-graph execution engine (spec §7, §8, §9).

Drives a job through its profile: for each stage it creates an attempt
directory, builds the context manifest, invokes an adapter, runs the declared
checks, and decides accept / retry / gate. The kernel owns every transition and
every event; the agent only writes files.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from .adapters import AdapterError, RunResult, discover_adapters, select_adapter
from .atomic import atomic_write_json, read_json
from .budgets import BudgetContext, BudgetError, check_budget, stage_limits
from .checkpoint import record_checkpoint
from .checks import fingerprint, load_checks, run_checks, summarise
from .sandbox import SandboxError, SandboxPolicy, load_sandbox_policy, \
    resolve_under, sanitize_env
from .context import collect_stage_context
from .gitrepo import collect_diff, head
from .guards import GuardContext, GuardError, run_guards
from .hashing import sha256_hex
from .lease import LeaseManager
from .risk import RiskError, assess, load_risk_config
from .schemas import SchemaError
from .injection import InjectionError, load_injection_config, scan_item
from .ulid import new_ulid

# Maximum time the engine will wait for one adapter run, regardless of budget.
ADAPTER_TIMEOUT_CAP = 3600

# Solo question budget (P1): at most this many blocking questions per job.
# The next blocking question parks the job as `blocked` until a human answers.
MAX_BLOCKING_QUESTIONS = 3


class EngineError(Exception):
    pass


class Cancelled(Exception):
    """The operator cancelled the job; the pipeline unwinds without writing.

    Raised when the job's state says "cancelled" (the operator pressed Stop)
    or when the lease was taken over — a newer fencing token means this run
    has been fenced out and must not write anything else.
    """


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


def _normalize_question(text: str) -> str:
    """Normalized question text for repeat detection (case/space-insensitive)."""
    return " ".join(str(text or "").lower().split())


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
        on_complete=None,
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
            # Resume restores the worktree to the last accepted checkpoint SHA
            # rather than rerunning on a possibly dirty tree (spec §239).
            self._restore_worktree(state, self.k.work_dir / job_id)
            return self._run_profile(
                job, job_dir, state, profile, adapters, adapter_id, fence, check_timeout,
                on_complete,
            )
        except Cancelled:
            # The operator stopped the job. Its state already says "cancelled"
            # and the work in flight has been killed — the pipeline unwinds
            # here without writing another event, because every write from
            # here on would carry a fencing token the operator has superseded.
            return self.k.job_status(job_id)
        finally:
            if lease.current_token() == fence:
                lease.release(fence)

    # ------------------------------------------------------------------
    # Profile / stage
    # ------------------------------------------------------------------

    def _run_profile(
        self, job, job_dir, state, profile, adapters, adapter_id, fence, check_timeout,
        on_complete=None,
    ) -> dict:
        accepted = self._accepted_stages(state)
        stages = profile["stages"]
        order = {s["id"]: i for i, s in enumerate(stages)}

        # A "Change this…" decision re-opens the last accepted stage (and every
        # stage after it) so the work is redone with the human's feedback.
        reopened = self._reopened_stage(state)
        reopen_index = order[reopened] if reopened in order else None
        if reopen_index is not None:
            accepted = {s for s in accepted if order.get(s, -1) < reopen_index}

        for index, stage in enumerate(stages):
            if stage["id"] in accepted:
                continue
            if self._cancel_requested(job_dir, fence):
                raise Cancelled()
            next_stage = stages[index + 1]["id"] if index + 1 < len(stages) else None
            # A human-requested redo restarts attempts from the reopened stage
            # onward at attempt 1 (discarding the superseded results).
            reset = reopen_index is not None and index >= reopen_index
            outcome = self._run_stage(
                job, job_dir, state, stage, index, next_stage, adapters, adapter_id, fence,
                check_timeout, reset=reset,
            )
            if outcome != "accepted":
                return state.fold()

        # All required stages are accepted. The merge hook (if any) integrates the
        # job branch before the job is marked completed; a conflict blocks it.
        if on_complete is not None and on_complete(job, state, fence) == "conflict":
            state.transition("blocked", actor=self.k.actor, fence=fence,
                             reason="merge conflict")
            return state.fold()

        state.transition("completed", actor=self.k.actor, fence=fence, reason="all stages accepted")
        return state.fold()

    @staticmethod
    def _reopened_stage(state) -> Optional[str]:
        """The stage re-opened by the latest unanswered 'changes_requested'."""
        accepted_at: dict[str, int] = {}
        reopened = None
        for index, ev in enumerate(state.load_events()):
            if ev["type"] == "stage.accepted":
                accepted_at[ev["data"].get("stage")] = index
            elif (ev["type"] == "human.approval"
                    and ev["data"].get("decision") == "changes_requested"):
                reopened = (ev["data"].get("stage"), index)
        if not reopened:
            return None
        stage, index = reopened
        if accepted_at.get(stage, -1) > index:
            return None  # already re-accepted after the feedback
        return stage

    def _run_stage(
        self, job, job_dir, state, stage, index, next_stage, adapters, adapter_id, fence,
        check_timeout, reset=False,
    ) -> str:
        sid = stage["id"]
        project_dir = self.k.projects_dir / job["project"]
        worktree = self.k.work_dir / job["id"]
        base = job_dir / "stages" / f"{index:02d}-{sid}"
        base.mkdir(parents=True, exist_ok=True)
        checks_cfg = load_checks(project_dir)

        started, last_status = self._attempts(state, sid)
        # A human-requested redo ignores the superseded attempts of this stage
        # so it begins again at attempt 1.
        if reset:
            started, last_status = {}, {}
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
            if self._cancel_requested(job_dir, fence):
                raise Cancelled()
            attempt_dir = base / f"attempt-{attempt}"
            status, fp, new_blocking = self._run_attempt(
                job, job_dir, state, stage, attempt, attempt_dir, project_dir, worktree,
                adapter_id, adapters, checks_cfg, fence, check_timeout, reset=reset,
            )
            # A hard budget breach is an absolute stop (§543): the attempt
            # records its refusal in budget.json and the retry loop must not
            # re-spend on on_fail: loop. The job fails decisively; raising
            # the budget and re-executing is the operator's way forward.
            budget_doc = read_json(attempt_dir / "budget.json", {}) or {}
            if budget_doc.get("status") == "hard_exceeded":
                state.transition(
                    "failed", actor=self.k.actor, fence=fence,
                    reason=f"hard budget exceeded in stage '{sid}': "
                           f"${budget_doc.get('current_cost', 0.0)} >= "
                           f"${budget_doc.get('limit', 0.0)}",
                )
                return "failed"
            # A new blocking question parks the job before any accept: the
            # stage re-runs with the human's answer in context. Past the
            # per-job budget the job fails instead of interrogating forever.
            if new_blocking:
                total = self._blocking_question_count(state)
                if total > MAX_BLOCKING_QUESTIONS:
                    state.transition("failed", actor=self.k.actor, fence=fence,
                                     reason="blocking question budget exhausted "
                                            f"({MAX_BLOCKING_QUESTIONS} per job)")
                    return "failed"
                state.transition("blocked", actor=self.k.actor, fence=fence,
                                 reason="blocking question needs a human answer")
                return "blocked"
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
                return self._apply_gate(job, state, stage, attempt,
                                        attempt_dir,
                                        budget_doc.get("status") or "ok",
                                        fence)

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
        adapter_id, adapters, checks_cfg, fence, check_timeout, reset=False,
    ):
        sid = stage["id"]
        (attempt_dir / "outputs").mkdir(parents=True, exist_ok=True)
        # Guards measure "what this round changed" against the HEAD at attempt
        # start (spec §9.3: guards run after every round), so record it before
        # anything can mutate the worktree.
        attempt_base = head(worktree) or ""

        manifest = collect_stage_context(
            project_dir, job_dir, stage, attempt, stage["budget"].get("tokens", 100000)
        )
        self.k.schemas.validate("context.manifest", manifest)
        atomic_write_json(attempt_dir / "context.manifest.json", manifest)

        state.append_event("stage.attempt_started", actor=self.k.actor, fence=fence,
                           data={"stage": sid, "attempt": attempt,
                                 "base_sha": attempt_base}, job_id=job["id"])

        adapter = select_adapter(adapters, adapter_id=adapter_id, role=stage["role"])
        key = input_hash(manifest, adapter.id)
        atomic_write_json(attempt_dir / "input.json",
                          {"input_hash": key, "base_sha": attempt_base})

        # Injection detection on manifest untrusted items (P2 injection
        # handling). Runs before the adapter sees the manifest. Both labeling
        # (injection_flags on manifest entries) and event emission
        # (injection.detected) happen together; the real enforcement is the
        # risk signal fed into _stage_signals.
        injection_config_error = None
        try:
            injection_config = load_injection_config(
                (self.k.factory_cfg or {}).get("injection")
            )
            patterns = injection_config["patterns"]
            for entry in manifest.get("untrusted_content") or []:
                item_path = entry["path"]
                item_path_full = Path(job_dir) / item_path
                if item_path_full.exists():
                    text = item_path_full.read_text(encoding="utf-8")
                    flags = scan_item(text, patterns)
                    if flags:
                        entry["injection_flags"] = [
                            flag["pattern_id"] for flag in flags]
                        for flag in flags:
                            state.append_event(
                                "injection.detected",
                                actor=self.k.actor,
                                fence=fence,
                                data={
                                    "stage": sid,
                                    "attempt": attempt,
                                    "item_path": item_path,
                                    "pattern_id": flag["pattern_id"],
                                    "matched_excerpt": flag["matched_excerpt"],
                                    "confidence": flag["confidence"],
                                },
                                job_id=job["id"],
                            )
        except InjectionError as e:
            injection_config_error = str(e)

        # Re-write manifest with injection_flags attached (even when empty).
        atomic_write_json(attempt_dir / "context.manifest.json", manifest)

        # Config error → fail the attempt deterministically (same policy as
        # budget/guard config errors). Never silently degrades.
        if injection_config_error:
            fp = fingerprint([], extra="injection:config_error")
            atomic_write_json(attempt_dir / "injection.json", {
                "status": "config_error", "error": injection_config_error,
            })
            atomic_write_json(attempt_dir / "result.json", {
                "input_hash": key, "status": "failed", "fingerprint": fp,
            })
            state.append_event(
                "stage.attempt_finished", actor=self.k.actor, fence=fence,
                data={"stage": sid, "attempt": attempt, "status": "failed",
                      "fingerprint": fp, "missing": [],
                      "adapter_error": f"injection:config_error: "
                      f"{injection_config_error}"},
                job_id=job["id"],
            )
            return "failed", fp, 0

        # Idempotent start: identical inputs that already produced an accepted result
        # are reused rather than re-run. A human-requested redo opts out.
        previous = read_json(attempt_dir / "result.json")
        if (not reset and previous and previous.get("input_hash") == key
                and previous.get("status") == "passed"):
            state.append_event(
                "stage.attempt_finished", actor=self.k.actor, fence=fence,
                data={"stage": sid, "attempt": attempt, "status": "passed",
                      "fingerprint": previous.get("fingerprint"), "missing": [],
                      "reused": True},
                job_id=job["id"],
            )
            return "passed", previous.get("fingerprint"), 0

        # A cached hard breach is a refusal, not a result to improve on:
        # re-running the adapter would re-spend (§543 "budgets stop at the
        # next safe point"). Resume returns the cached failure untouched;
        # a human redo (reset=True) explicitly re-opens the attempt.
        cached_budget = read_json(attempt_dir / "budget.json", {}) or {}
        if not reset and cached_budget.get("status") == "hard_exceeded":
            fp = fingerprint([], extra="budget:hard_exceeded")
            atomic_write_json(attempt_dir / "result.json", {
                "input_hash": key, "status": "failed", "fingerprint": fp,
            })
            state.append_event(
                "stage.attempt_finished", actor=self.k.actor, fence=fence,
                data={"stage": sid, "attempt": attempt, "status": "failed",
                      "fingerprint": fp, "missing": [],
                      "adapter_error": "budget hard_exceeded (cached refusal)"},
                job_id=job["id"],
            )
            return "failed", fp, 0

        run = self._invoke_adapter(
            adapter, job, stage, attempt, attempt_dir, worktree, manifest, fence
        )
        if run.error_class == "cancelled":
            # The operator stopped the job while the adapter was running: the
            # process tree is already dead. Unwind before anything else runs.
            raise Cancelled()
        # Adapter questions are durable first-class events: they survive
        # resume, count against the per-job budget, and surface on the
        # dashboard question card (P1 Solo question budget).
        new_blocking = self._record_questions(
            job, job_dir, state, stage, attempt, run.questions,
            fence, actor=f"adapter/{adapter.id}")
        usage = {k: v for k, v in run.usage.items() if k != "type"}
        usage["events"] = len(run.events)
        atomic_write_json(attempt_dir / "usage.json", usage)

        missing = self._missing_outputs(stage, attempt_dir)
        # Checks (e.g. visual capture) learn where this attempt's outputs
        # live via env paths, absolute so tools run from anywhere.
        checks_env = {
            "FACTORY_ATTEMPT_DIR": str(attempt_dir.absolute()),
            "FACTORY_VISUAL_OUT": str((attempt_dir / "outputs").absolute()),
        }
        results = run_checks(checks_cfg, stage["checks"], worktree,
                             timeout=check_timeout, extra_env=checks_env,
                             cancel=self._cancel_watch(job, fence))
        if any(r.cancelled for r in results):
            # Stopped while the checks were running: the pipeline unwinds
            # instead of recording a verdict nobody asked for.
            raise Cancelled()
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

        # Guards run after every round, after checks, before accept (§9.3).
        # A violation fails the attempt even when every check passed: the
        # guards are ground truth over the diff, not advice.
        guards_clean, guards_extra = self._run_guards(
            job, job_dir, state, stage, attempt, attempt_dir, worktree, fence
        )

        # Budgets price the attempt's reported usage against the stage limits
        # (§12.2: enforced by the kernel at the stage boundary, every round,
        # like guards). A breach fails the attempt even when every check and
        # guard passed; a hard breach additionally stops the stage's retry
        # loop (see _run_stage) — retrying would only re-spend.
        budget_clean, budget_extra = self._run_budget(
            state, stage, attempt, attempt_dir, job["id"], fence
        )

        if not guards_clean:
            status = "failed"  # guards trump everything, including transients
        elif not budget_clean:
            status = "failed"  # budgets are ground truth over reported usage
        elif run.ok and not missing and summary["passed"]:
            status = "passed"
        elif not run.ok and (run.error_class == "transient"):
            status = "interrupted"
        else:
            status = "failed"

        extra = run.error or ""
        if missing:
            extra = (extra + " " if extra else "") + "missing:" + ",".join(missing)
        if guards_extra:
            extra = (extra + " " if extra else "") + guards_extra
        if budget_extra:
            extra = (extra + " " if extra else "") + budget_extra
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
        return status, fp, new_blocking

    # ------------------------------------------------------------------
    # Guards (P2.1 — spec §9.3, §12.1)
    # ------------------------------------------------------------------

    def _run_guards(self, job, job_dir, state, stage, attempt, attempt_dir, worktree,
                    fence) -> tuple[bool, str]:
        """Run the stage's declared guards over this attempt's diff.

        Returns ``(clean, fingerprint_extra)``. Emits ``guard.violation`` /
        ``guards.completed`` events (kernel-actor, hash-chained like every
        event) and writes ``guards.json`` (same shape as ``checks.json``).

        Purposely never raises: an unknown guard id or an invalid
        ``authorizations.json`` becomes a violation of the pseudo-guard
        ``guard_config`` — recorded as a real event, failing the attempt
        deterministically (same policy as a check missing from checks.json).
        Returns ``("", "")``-clean with no events when the stage declares no
        guards (empty list → no enforcement, per §9.3).
        """
        ids = list(stage.get("guards") or [])
        sid = stage["id"]
        if not ids:
            return True, ""

        attempt_base = (read_json(attempt_dir / "input.json", {}) or {}).get(
            "base_sha") or ""
        diff = collect_diff(worktree, attempt_base)
        authorizations, config_violations = self._load_authorizations(job_dir)
        if config_violations:
            results = [{"guard": "guard_config", "violations": config_violations}]
        else:
            ctx = GuardContext(step=sid, commits={}, diff=diff,
                               authorizations=authorizations, worktree=worktree)
            try:
                results = [{"guard": r.guard, "violations": list(r.violations)}
                           for r in run_guards(ids, ctx)]
            except GuardError as e:
                results = [{"guard": "guard_config", "violations": [{
                    "path": "guards", "kind": "unknown_guard",
                    "evidence": str(e)}]}]

        atomic_write_json(attempt_dir / "guards.json", {"results": results})
        violated = [r for r in results if r.get("violations")]

        if violated:
            for result in violated:
                self._emit_guard_violations(
                    state, job["id"], sid, attempt, result["guard"],
                    result["violations"], fence)
            extra = "guards:" + "|".join(
                f"{r['guard']}({','.join(sorted({v['path'] for v in r['violations']}))})"
                for r in violated)
            return False, extra

        state.append_event(
            "guards.completed", actor=self.k.actor, fence=fence,
            data={"stage": sid, "attempt": attempt, "guards": ids,
                  "violations": 0},
            job_id=job["id"],
        )
        return True, ""

    def _emit_guard_violations(self, state, job_id, sid, attempt, guard,
                               violations, fence) -> None:
        """One ``guard.violation`` event per (guard, kind) group.

        The event data carries both the compact view (``kind`` + ``paths``)
        and the full violation records, so dashboards get the small shape and
        the audit chain keeps the evidence.
        """
        groups: dict[str, list] = {}
        for v in violations:
            groups.setdefault(str(v.get("kind") or "unknown"), []).append(v)
        for kind, items in sorted(groups.items()):
            state.append_event(
                "guard.violation", actor=self.k.actor, fence=fence,
                data={"stage": sid, "attempt": attempt, "guard": guard,
                      "kind": kind, "paths": [it["path"] for it in items],
                      "violations": items},
                job_id=job_id,
            )

    def _load_authorizations(self, job_dir):
        """Job-level ``authorizations.json``, validated at every use.

        Lives at the job level (not the attempt directory): attempts are
        disposable caches (§5.2) while authorization is kernel-owned job
        state. Invalid or malformed documents are returned as ``guard_config``
        violations instead of being silently read as "no authorization".
        """
        doc = read_json(job_dir / "authorizations.json")
        if doc is None:
            return {}, []
        if not isinstance(doc, dict):
            return {}, [{
                "path": "authorizations.json", "kind": "invalid_authorization",
                "evidence": "authorizations.json must be a JSON object",
            }]
        try:
            self.k.schemas.validate("authorizations", doc)
        except SchemaError as e:
            return {}, [{
                "path": "authorizations.json", "kind": "invalid_authorization",
                "evidence": str(e),
            }]
        return doc, []

    # ------------------------------------------------------------------
    # Budgets and metering (P2.2 — spec §3.9, §12.2, §543)
    # ------------------------------------------------------------------

    def _run_budget(self, state, stage, attempt, attempt_dir, job_id, fence):
        """Price this attempt's reported usage against the stage limits.

        Returns ``(clean, fingerprint_extra)``. Writes ``budget.json`` (the
        runtime verdict: status, current_cost, the decisive limit) and emits
        ``budget.soft_exceeded`` / ``budget.hard_exceeded`` only on breach —
        per-attempt cost stays in the file (no ``budget.checked`` event, per
        the Solo three-element promise: no per-round timeline noise).

        Stages without a ``budget:`` declaration skip entirely (no events,
        no files) — budgets are declared proposals, enforced by the kernel
        where they exist (spec §3: agents propose, kernel enforces).

        Purposely never raises: an invalid budget document (missing ``usd``,
        ``soft_usd >= usd``) or unpriced usage becomes a deterministic failed
        attempt through the pseudo-status ``config_error`` — recorded in
        ``budget.json`` and one event, never a silent $0 cost.
        """
        sid = stage["id"]
        budget = stage.get("budget")
        if not isinstance(budget, dict) or not budget:
            return True, ""  # no declaration, no enforcement

        usage = read_json(attempt_dir / "usage.json", {}) or {}
        price_table = (self.k.factory_cfg or {}).get("price_table") or {}

        try:
            soft_limit, hard_limit = stage_limits(budget)
            result = check_budget(BudgetContext(
                usage=usage, price_table=price_table,
                soft_limit=soft_limit, hard_limit=hard_limit,
            ))
        except BudgetError as e:
            atomic_write_json(attempt_dir / "budget.json", {
                "status": "config_error", "current_cost": 0.0,
                "limit": None, "error": str(e),
            })
            state.append_event(
                "budget.hard_exceeded", actor=self.k.actor, fence=fence,
                data={"stage": sid, "attempt": attempt, "current_cost": 0.0,
                      "hard_limit": None, "error": str(e)},
                job_id=job_id,
            )
            return False, "budget:config_error"

        atomic_write_json(attempt_dir / "budget.json", {
            "status": result.status, "current_cost": result.current_cost,
            "limit": result.limit,
        })
        if result.status == "hard_exceeded":
            state.append_event(
                "budget.hard_exceeded", actor=self.k.actor, fence=fence,
                data={"stage": sid, "attempt": attempt,
                      "current_cost": result.current_cost,
                      "hard_limit": result.limit},
                job_id=job_id,
            )
            return False, (f"budget:hard_exceeded(${result.current_cost} "
                           f">= ${result.limit})")
        if result.status == "soft_exceeded":
            state.append_event(
                "budget.soft_exceeded", actor=self.k.actor, fence=fence,
                data={"stage": sid, "attempt": attempt,
                      "current_cost": result.current_cost,
                      "soft_limit": result.limit},
                job_id=job_id,
            )
        return True, ""

    def _invoke_adapter(self, adapter, job, stage, attempt, attempt_dir, worktree, manifest, fence):
        budget = stage["budget"]
        timeout = min(int(budget.get("minutes", 30) * 60) or 600, ADAPTER_TIMEOUT_CAP)
        # Sandboxing (P2.3): the contract is read from config per call and
        # both paths the subprocess will receive are proven contained before
        # anything can see them. An escape fails this adapter run as 'fatal'.
        policy = self._sandbox_policy()
        try:
            self._check_sandbox_paths(attempt_dir, worktree)
        except SandboxError as e:
            return RunResult(ok=False, error=f"sandbox: {e}", error_class="fatal")
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
            return adapter.run(request, timeout=timeout,
                               cwd=self._sandbox_cwd(policy, worktree),
                               env=self._sandbox_env(policy, job, stage,
                                                     attempt, attempt_dir,
                                                     worktree),
                               cancel=self._cancel_watch(job, fence))
        except AdapterError as e:
            return RunResult(ok=False, error=str(e), error_class="fatal")

    def _cancel_watch(self, job, fence):
        """A predicate the adapter run polls: True once the job was stopped.

        Polled by the adapter's process loop, so pressing Stop kills the
        adapter (and its children) instead of merely marking the job.
        """
        job_dir = self.k._find_job_dir(job["id"])

        def cancelled() -> bool:
            return self._cancel_requested(job_dir, fence)

        return cancelled

    def _cancel_requested(self, job_dir, fence) -> bool:
        """True when the operator stopped the job, or this run was fenced out.

        Two independent signals, both read from disk (the engine runs in
        another thread than the dashboard that serves Stop):
        * the job snapshot says "cancelled";
        * the lease carries a newer fencing token — somebody else owns the
          job now, so this run must not write anything.
        """
        snap = read_json(Path(job_dir) / "job.json") or {}
        if snap.get("state") == "cancelled":
            return True
        token = LeaseManager(job_dir, self.k.actor).current_token()
        return token is not None and token != fence

    def _sandbox_policy(self) -> SandboxPolicy:
        """Parse the sandbox contract from the kernel's config (pure).

        Loaded per invocation so the policy always matches the config the
        tree carries now; deterministic — same config, same policy.
        """
        return load_sandbox_policy((self.k.factory_cfg or {}).get("sandbox")
                                   or {})

    @staticmethod
    def _sandbox_env(policy: SandboxPolicy, job, stage, attempt, attempt_dir,
                     worktree) -> dict:
        """The subprocess sees only the allowlist intersection of the
        kernel's env (P2.3: isolation by default), plus the kernel-reserved
        ``FACTORY_*`` attribution the kernel injects — it owns that
        namespace and overrides anything an operator may carry under it.
        """
        env = sanitize_env(dict(os.environ), policy.env_allowlist)
        env["FACTORY_JOB_ID"] = job["id"]
        env["FACTORY_STAGE"] = stage["id"]
        env["FACTORY_ATTEMPT"] = str(attempt)
        env["FACTORY_ATTEMPT_DIR"] = str(Path(attempt_dir).absolute())
        env["FACTORY_WORKTREE"] = str(Path(worktree).absolute())
        return env

    @staticmethod
    def _sandbox_cwd(policy: SandboxPolicy, worktree) -> Optional[Path]:
        """Adapter cwd: the job worktree under ``strict_cwd``, else the
        adapter's own directory (legacy default, never a player choice)."""
        return Path(worktree) if policy.strict_cwd else None

    def _check_sandbox_paths(self, attempt_dir, worktree):
        """Assert both sandbox roots sit inside the factory tree.

        A path the kernel itself builds is player-untrusted input once it
        travels; lexical containment (pure ``resolve_under``) proves it
        stays inside the root before any subprocess sees it. Escapes raise
        ``SandboxError`` and fail the attempt deterministically.
        """
        resolve_under(self.k.root, str(attempt_dir))
        resolve_under(self.k.root, str(worktree))

    @staticmethod
    def _missing_outputs(stage, attempt_dir) -> list[str]:
        missing = []
        for name in stage["produces"]:
            if name.startswith("git:") or name.endswith("/"):
                continue
            if not (attempt_dir / "outputs" / name).exists():
                missing.append(name)
        return missing

    def _record_questions(self, job, job_dir, state, stage, attempt,
                          questions, fence, actor="kernel") -> int:
        """Persist adapter questions as `job.question_asked` events.

        Returns the number of newly recorded *blocking* questions. Repeats
        (same id or same normalized text as an already-recorded question) are
        not recorded twice, so a stuck agent cannot burn the per-job budget by
        re-asking. Malformed questions without text are ignored. Asked
        questions are also appended to `questions.md` so they (and later
        answers) reach future attempts through the context manifest.
        """
        asked: list[tuple[str, str]] = [
            (str(ev["data"].get("id") or ""),
             _normalize_question(str(ev["data"].get("text") or "")))
            for ev in state.load_events()
            if ev["type"] == "job.question_asked"
        ]
        lines = []
        new_blocking = 0
        for index, q in enumerate(questions or []):
            text = str(q.get("text") or q.get("message") or "").strip()[:2000]
            if not text:
                continue
            qid = str(q.get("id") or f"{stage['id']}-{attempt}-{index + 1}")
            norm = _normalize_question(text)
            if any(eid == qid or (enorm and enorm == norm) for eid, enorm in asked):
                continue
            kind = str(q.get("kind") or "blocking")
            options = [str(o)[:500] for o in (q.get("options") or [])][:8]
            state.append_event(
                "job.question_asked", actor=actor, fence=fence,
                data={"id": qid, "text": text, "kind": kind, "options": options,
                      "stage": stage["id"], "attempt": attempt},
                job_id=job["id"],
            )
            asked.append((qid, norm))
            if kind == "blocking":
                new_blocking += 1
            lines.append(f"## Q: {qid} (stage {stage['id']}, attempt {attempt}, {kind})\n"
                         f"{text}\n" +
                         (f"Options: {' | '.join(options)}\n" if options else ""))
        if lines:
            path = job_dir / "questions.md"
            previous = path.read_text(encoding="utf-8") if path.exists() else ""
            path.write_text(previous + "".join(lines), encoding="utf-8")
        return new_blocking

    @staticmethod
    def _blocking_question_count(state) -> int:
        """Blocking `job.question_asked` events recorded for this job."""
        return sum(
            1 for ev in state.load_events()
            if ev["type"] == "job.question_asked"
            and ev["data"].get("kind", "blocking") == "blocking"
        )

    @staticmethod
    def _restore_worktree(state, worktree) -> None:
        """Restore the worktree to the last accepted checkpoint commit (§239)."""
        from .gitrepo import is_repo, reset_hard

        commit = None
        for ev in state.load_events():
            if ev["type"] == "checkpoint.created" and ev["data"].get("commit"):
                commit = ev["data"]["commit"]
        if commit and is_repo(worktree):
            reset_hard(worktree, commit)

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

    def _apply_gate(self, job, state, stage, attempt, attempt_dir,
                    budget_status: str, fence) -> str:
        """Evaluate the stage's gate over a *passed* attempt and decide.

        Deterministic gates first (spec §5): ``risk_scored`` and
        ``if_risk_above:*`` gates are decided by pure arithmetic
        (``risk.assess``) over kernel-observed signals - guards, budget
        verdict, checks, retries - recorded in a ``risk.computed`` event so
        score -> band -> action all cite the same stored numbers. Gates that
        don't consume risk keep their P0 semantics.
        """
        sid = stage["id"]
        gate = stage["gate"]
        verdict = None
        if gate == "risk_scored" or gate.startswith("if_risk_above:"):
            try:
                decision, verdict = self._risk_gate(
                    state, stage, attempt, attempt_dir, budget_status,
                    gate, fence, job["id"],
                )
            except RiskError as e:
                # A broken risk config must never degrade into a silently
                # loosened gate: fail the attempt-to-accept boundary
                # deterministically (same policy as an unpriced usage).
                state.transition(
                    "failed", actor=self.k.actor, fence=fence,
                    reason=f"risk gate config error on stage '{sid}': {e}",
                )
                return "failed"
        else:
            decision = self._gate_decision(gate)
        state.append_event(
            "gate.evaluated", actor=self.k.actor, fence=fence,
            data={"stage": sid, "gate": gate, "decision": decision},
            job_id=job["id"],
        )
        if decision == "require_human":
            state.transition("awaiting_human", actor=self.k.actor, fence=fence,
                             reason=f"gate '{gate}' on stage '{sid}'")
            return "awaiting_human"
        if decision == "blocked":
            score = verdict["score"]
            band = verdict["band"]
            state.transition(
                "failed", actor=self.k.actor, fence=fence,
                reason=f"risk gate '{gate}' on stage '{sid}' scored "
                       f"{score} ({band}) - blocked pending operator rerun",
            )
            return "failed"
        return "accepted"

    _IF_RISK_AUTO_BANDS = {
        # "if_risk_above:L" keeps the stage automatic while the computed band
        # does not rise above the named level; anything strictly above waits
        # for a human. An unknown level falls to "medium" (the behavior the
        # P0 placeholder encoded via thresholds.get(level, 40); profiles are
        # kernel-owned, doctor (step 4) flags drift).
        "low": ("low",),
        "medium": ("low", "medium"),
        "high": ("low", "medium", "high"),
    }

    def _risk_gate(self, state, stage, attempt, attempt_dir,
                   budget_status: str, gate: str, fence, job_id: str) -> tuple[str, dict]:
        """Score the stage's road-to-this-pass and resolve the gate decision.

        Signals are stage-scoped, not attempt-scoped (see the docstring of
        `_stage_signals` for why). The computed verdict lands in the event
        log verbatim — `risk.computed` carries score, band, action and the
        exact signals dict, so the decision is auditable end-to-end.
        """
        sid = stage["id"]
        config = load_risk_config(
            (self.k.factory_cfg or {}).get("risk_scoring"))
        signals = self._stage_signals(state, sid, attempt, budget_status)
        verdict = assess(signals, config)
        state.append_event(
            "risk.computed", actor=self.k.actor, fence=fence,
            data={"stage": sid, **verdict, "signals": signals},
            job_id=job_id,
        )
        if gate == "risk_scored":
            decision = {"auto_advance": "auto",
                        "awaiting_human": "require_human",
                        "blocked": "blocked"}[verdict["action"]]
            return decision, verdict
        level = gate.split(":", 1)[1]
        auto_bands = self._IF_RISK_AUTO_BANDS.get(
            level, self._IF_RISK_AUTO_BANDS["medium"])
        return ("auto" if verdict["band"] in auto_bands else "require_human",
                verdict)

    @staticmethod
    def _stage_signals(state, sid: str, attempt: int, budget_status: str) -> dict:
        """Kernel-built signals for the gate, stage-scoped (see _risk_gate).

        The gate evaluates a *passed* attempt, so check/guard failures of
        the winning attempt are impossible by definition - what is real is
        the road that got here. Guard violations and check failures are
        summed across the stage's recorded rounds (they made the stage
        retry), the winning attempt number carries the retries, and the
        caller passes the winning attempt's budget verdict (possible soft
        breach - a soft breach notifies yet the attempt still stands, P2.2).
        """
        guard_violations = 0
        check_failures = 0
        injection_flagged = 0
        for ev in state.load_events():
            data = ev.get("data", {})
            if ev["type"] == "injection.detected":
                # Any injection detected in the job raises the signal for
                # all downstream scored stages.
                injection_flagged = 1
            if data.get("stage") != sid:
                continue
            if ev["type"] == "guard.violation":
                # One event per (guard, kind) group; 'violations' holds the
                # full records - each individual violation counts.
                guard_violations += len(data.get("violations") or [])
            elif ev["type"] == "checks.completed":
                # summarise() lists failed check *ids*; count them.
                failed = data.get("failed") or []
                check_failures += len(failed) if isinstance(failed, list) \
                    else int(failed)
        return {
            "guard_violations": guard_violations,
            "budget_status": budget_status,
            "check_failures": check_failures,
            "attempt_number": attempt,
            "injection_flagged": injection_flagged,
        }

    @staticmethod
    def _gate_decision(gate: str) -> str:
        """Gates that do not consume risk: none -> auto, required -> human.

        Risk gates ('risk_scored', 'if_risk_above:*') are decided by
        `_risk_gate` over the computed band; this static method keeps only
        the P0 cases (the old placeholder risk-0 effectively exits here).
        """
        if gate == "required":
            return "require_human"
        return "auto"

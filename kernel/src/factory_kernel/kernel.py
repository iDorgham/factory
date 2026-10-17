"""Enterprise AI Software Factory — Kernel (P0 core).

The kernel is deterministic. It owns locks, transitions, validation,
checks, budgets, and audit. Agents never mutate state.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from .atomic import atomic_write_json, read_json
from .checkpoint import result_hash
from .gitrepo import add_worktree, git_available, init_repo, is_repo, merge_branch, revert_merge
from .guards import GUARDS
from .lease import LeaseManager, LeaseError
from .profiles import load_profile
from .schemas import SchemaError, SchemaStore
from .state import JobState, StateError, verify_chain
from .ulid import new_ulid

TERMINAL_STATES = {"completed", "cancelled", "superseded", "archived"}


class KernelError(Exception):
    pass


class Kernel:
    """Single-process kernel for the factory."""

    def __init__(self, root: Path | str, actor: str = "local"):
        self.root = Path(root).resolve()
        self.actor = actor
        self.factory_cfg = read_json(self.root / "factory.json", {})
        self.projects_dir = self.root / "projects"
        self.state_dir = self.root / "state"
        self.work_dir = self.root / ".work"
        self.presets_dir = self.root / "kernel" / "presets"
        self.stages_dir = self.root / "kernel" / "stages"
        self.schemas_dir = self.root / "kernel" / "schemas"
        self.adapters_dir = self.root / "adapters"
        self.schemas = SchemaStore(self.schemas_dir)

        # Ensure core dirs exist
        for d in (self.projects_dir, self.state_dir, self.work_dir):
            d.mkdir(parents=True, exist_ok=True)

    def _job_state(self, job_dir: Path) -> JobState:
        return JobState(job_dir, schemas_dir=self.schemas_dir)

    # ------------------------------------------------------------------
    # Project lifecycle
    # ------------------------------------------------------------------

    def project_create(
        self,
        name: str,
        mode: str = "solo",
        domain: str = "web",
        brand: Optional[str] = None,
    ) -> dict:
        if not name or not name.replace("-", "").replace("_", "").isalnum():
            raise KernelError("Project name must be alphanumeric with - or _")
        proj_dir = self.projects_dir / name
        if proj_dir.exists():
            raise KernelError(f"Project '{name}' already exists")

        preset = read_json(self.presets_dir / f"{mode}.json")
        if not preset:
            raise KernelError(f"Unknown mode: {mode}")

        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        project = {
            "name": name,
            "mode": mode,
            "domain": domain,
            "stage_profile": preset.get("stage_profile", "lite"),
            "brand": brand,
            "created_at": now,
            "updated_at": now,
            "base_commit": None,
            "policy_overrides": {},
            "status": "active",
        }

        proj_dir.mkdir(parents=True)
        (proj_dir / "memory").mkdir()
        (proj_dir / "jobs").mkdir()
        (proj_dir / "epics").mkdir()
        (proj_dir / "issues").mkdir()

        # The factory-managed repository jobs branch from. Its initial commit is
        # the project's base commit (spec §6: worktree per job from base commit).
        if git_available():
            project["base_commit"] = init_repo(proj_dir / "repo", project=name)

        self.schemas.validate("project", project)
        atomic_write_json(proj_dir / "project.json", project)

        # Minimal memory files
        (proj_dir / "memory" / "decisions.md").write_text(
            "# Architecture Decision Records\n\n", encoding="utf-8"
        )
        (proj_dir / "memory" / "conventions.md").write_text(
            "# Code & Design Conventions\n\n", encoding="utf-8"
        )
        atomic_write_json(
            proj_dir / "memory" / "repo-map.json", {"symbols": {}, "entry_points": []}
        )
        (proj_dir / "memory" / "lessons.jsonl").touch()

        # Default checks
        checks = {
            "lint": {"cmd": "echo 'lint placeholder'", "required": True},
            "typecheck": {"cmd": "echo 'typecheck placeholder'", "required": False},
            "unit": {"cmd": "echo 'unit tests placeholder'", "required": True},
            "build": {"cmd": "echo 'build placeholder'", "required": True},
            "a11y": {"cmd": "echo 'a11y placeholder'", "required": False},
            "visual": {"cmd": self._visual_check_cmd(), "required": False},
        }
        atomic_write_json(proj_dir / "checks.json", checks)

        self._reindex()
        return project

    def _visual_check_cmd(self) -> str:
        """The `visual` check command: the real screenshot producer (§7).

        The capture runs with `cwd` = job worktree and takes the attempt
        outputs dir from `FACTORY_VISUAL_OUT` (exported by the engine).
        Missing page → the manifest records `skipped`, exit 0.
        """
        capture = self.adapters_dir / "visual-capture" / "capture.py"
        return f'python "{capture}" --url index.html --diff-previous'

    def project_list(self) -> list[dict]:
        projects = []
        for p in sorted(self.projects_dir.iterdir()):
            if p.is_dir() and (p / "project.json").exists():
                projects.append(read_json(p / "project.json"))
        return projects

    def project_get(self, name: str) -> dict:
        path = self.projects_dir / name / "project.json"
        proj = read_json(path)
        if not proj:
            raise KernelError(f"Project '{name}' not found")
        return proj

    # ------------------------------------------------------------------
    # Job lifecycle
    # ------------------------------------------------------------------

    def job_run(
        self,
        project: str,
        description: str,
        epic: Optional[str] = None,
        profile: Optional[str] = None,
    ) -> dict:
        proj = self.project_get(project)
        if proj["status"] != "active":
            raise KernelError(f"Project is {proj['status']}")

        mode = proj["mode"]
        profile = profile or proj.get("stage_profile", "lite")
        job_id = new_ulid()
        job_dir = self.projects_dir / project / "jobs" / job_id
        job_dir.mkdir(parents=True)

        # A real git worktree on branch `factory/<job-id>` from the project's
        # base commit (spec §198). Falls back to a plain directory when git is
        # unavailable so the kernel still runs without a repository.
        worktree = self.work_dir / job_id
        repo_dir = self.projects_dir / project / "repo"
        if is_repo(repo_dir) and proj.get("base_commit"):
            add_worktree(repo_dir, worktree, f"factory/{job_id}", proj["base_commit"])
        else:
            worktree.mkdir(parents=True, exist_ok=True)
        (worktree / ".factory_job").write_text(job_id, encoding="utf-8")

        state = self._job_state(job_dir)
        state.create_job(
            job_id=job_id,
            project=project,
            brief=description,
            profile=profile,
            mode=mode,
            epic=epic,
            actor=self.actor,
        )

        # Write the human-readable brief
        (job_dir / "brief.md").write_text(
            f"# Brief\n\n**Goal:** {description}\n\n"
            f"**Source:** human\n**Created:** {datetime.now(timezone.utc).isoformat()}Z\n",
            encoding="utf-8",
        )
        (job_dir / "assumptions.md").write_text("# Assumptions Ledger\n\n", encoding="utf-8")
        (job_dir / "questions.md").write_text("# Open Questions\n\n", encoding="utf-8")
        (job_dir / "artifacts").mkdir()

        self._reindex()
        return state.fold()

    def job_status(self, job_id: str) -> dict:
        job_dir = self._find_job_dir(job_id)
        state = self._job_state(job_dir)
        return state.fold()

    def job_list(self, project: Optional[str] = None) -> list[dict]:
        jobs = []
        if project:
            projects = [project]
        else:
            projects = [p.name for p in self.projects_dir.iterdir() if p.is_dir()]
        for pname in projects:
            jobs_dir = self.projects_dir / pname / "jobs"
            if not jobs_dir.exists():
                continue
            for jdir in sorted(jobs_dir.iterdir()):
                if (jdir / "job.json").exists():
                    jobs.append(read_json(jdir / "job.json"))
        return jobs

    def job_transition(
        self,
        job_id: str,
        to_state: str,
        reason: str = "",
        fence: Optional[int] = None,
    ) -> dict:
        job_dir = self._find_job_dir(job_id)
        lease = LeaseManager(job_dir, self.actor)
        if fence is None:
            fence = lease.acquire()
        else:
            # Verify we still hold the token
            current = lease.current_token()
            if current != fence:
                raise LeaseError(f"Fencing token mismatch: expected {fence}, have {current}")

        state = self._job_state(job_dir)
        event = state.transition(to_state, actor=self.actor, fence=fence, reason=reason)
        self._reindex()
        return event

    def job_cancel(self, job_id: str, reason: str = "user cancelled") -> dict:
        return self.job_transition(job_id, "cancelled", reason=reason)

    def job_execute(
        self,
        job_id: str,
        adapter_id: Optional[str] = None,
        check_timeout: int = 600,
        on_complete=None,
    ) -> dict:
        """Run (or resume) a job through its stage profile."""
        from .engine import Engine

        result = Engine(self).execute(
            job_id, adapter_id=adapter_id, check_timeout=check_timeout,
            on_complete=on_complete,
        )
        self._reindex()
        return result

    def job_approve(
        self,
        job_id: str,
        adapter_id: Optional[str] = None,
        sha: Optional[str] = None,
    ) -> dict:
        """Approve a job parked at a human gate and resume execution.

        Approval is bound to the latest checkpoint SHA. If the produced
        artifacts changed since that checkpoint the approval is refused — the
        result no longer hashes to the approved SHA.
        """
        job = self.job_status(job_id)
        if job["state"] != "awaiting_human":
            raise KernelError(f"Job is '{job['state']}'; nothing to approve")

        job_dir = self._find_job_dir(job_id)
        worktree = self.work_dir / job_id

        checkpoints = job.get("checkpoints") or []
        if not checkpoints:
            raise KernelError("No checkpoint recorded; cannot approve")
        approved_sha = checkpoints[-1]["sha"]

        current = result_hash(job_dir, worktree)
        if current != approved_sha:
            raise KernelError(
                f"Job result changed since checkpoint {approved_sha[:12]}…; approval invalid"
            )
        if sha is not None and sha != approved_sha:
            raise KernelError(
                f"Provided sha {sha[:12]}… does not match checkpoint {approved_sha[:12]}…"
            )

        lease = LeaseManager(job_dir, self.actor)
        fence = lease.acquire()
        try:
            state = self._job_state(job_dir)
            state.append_event(
                "human.approval", actor=self.actor, fence=fence,
                data={"decision": "approved", "sha": approved_sha}, job_id=job_id,
            )
        finally:
            if lease.current_token() == fence:
                lease.release(fence)
        return self.job_execute(job_id, adapter_id=adapter_id, on_complete=self._merge_on_complete)

    def _merge_on_complete(self, job, state, fence) -> str:
        """Engine completion hook: merge the approved job branch (spec §199).

        Runs while the job is still ``running`` so a conflict can move it to
        ``blocked`` instead of ``completed``. Returns ``"ok"`` or ``"conflict"``.
        """
        repo_dir = self.projects_dir / job["project"] / "repo"
        proj = self.project_get(job["project"])
        branch = f"factory/{job['id']}"
        if not is_repo(repo_dir) or not proj.get("base_commit"):
            return "ok"

        result = merge_branch(repo_dir, branch, f"factory: merge {job['id']}")
        if result["ok"]:
            state.append_event(
                "merge.completed", actor=self.actor, fence=fence,
                data={"branch": branch, "base": result.get("base"),
                      "merge_commit": result.get("merge_commit")},
                job_id=job["id"],
            )
            return "ok"
        state.append_event(
            "merge.conflict", actor=self.actor, fence=fence,
            data={"branch": branch, "base": result.get("base"),
                  "conflicts": result.get("conflicts", [])},
            job_id=job["id"],
        )
        return "conflict"

    def job_undo(self, job_id: str) -> dict:
        """Revert the merge of an approved job (spec §21.2, §23: `job undo`)."""
        job = self.job_status(job_id)
        job_dir = self._find_job_dir(job_id)
        merge = job.get("merge") or {}
        if merge.get("event") != "merge.completed" or not merge.get("merge_commit"):
            raise KernelError("Job has not been merged; nothing to undo")
        if self._merge_undone_since(job_dir, merge.get("merge_commit")):
            raise KernelError("Merge already undone")

        repo_dir = self.projects_dir / job["project"] / "repo"
        if not is_repo(repo_dir):
            raise KernelError("Project repository is missing; cannot undo")

        lease = LeaseManager(job_dir, self.actor)
        fence = lease.acquire()
        try:
            outcome = revert_merge(repo_dir, merge["merge_commit"], merge.get("base"))
            state = self._job_state(job_dir)
            state.append_event(
                "merge.undone", actor=self.actor, fence=fence,
                data={"branch": merge.get("branch"),
                      "merge_commit": merge["merge_commit"],
                      "mode": outcome["mode"], "sha": outcome["sha"]},
                job_id=job_id,
            )
        finally:
            if lease.current_token() == fence:
                lease.release(fence)
        self._reindex()
        return self.job_status(job_id)

    @staticmethod
    def _merge_undone_since(job_dir: Path, merge_commit: Optional[str]) -> bool:
        for ev in Kernel._read_events(job_dir):
            if ev["type"] == "merge.undone" and ev["data"].get("merge_commit") == merge_commit:
                return True
        return False

    @staticmethod
    def _read_events(job_dir: Path) -> list[dict]:
        from .atomic import read_jsonl

        return read_jsonl(Path(job_dir) / "events.jsonl")

    def job_request_changes(self, job_id: str, feedback: str, stage: Optional[str] = None,
                            adapter_id: Optional[str] = None) -> dict:
        """Send feedback from the approval card: re-open the last stage and redo it."""
        job = self.job_status(job_id)
        if job["state"] not in ("awaiting_human", "blocked"):
            raise KernelError(f"Job is '{job['state']}'; nothing to change")
        job_dir = self._find_job_dir(job_id)
        target = stage or self._last_accepted_stage(job_dir)
        if target is None:
            raise KernelError("No accepted stage to re-open")

        lease = LeaseManager(job_dir, self.actor)
        fence = lease.acquire()
        try:
            state = self._job_state(job_dir)
            state.append_event(
                "human.approval", actor=self.actor, fence=fence,
                data={"decision": "changes_requested", "feedback": feedback, "stage": target},
                job_id=job_id,
            )
        finally:
            if lease.current_token() == fence:
                lease.release(fence)
        return self.job_execute(job_id, adapter_id=adapter_id)

    def job_answer(self, job_id: str, question_id: str, answer: str,
                   adapter_id: Optional[str] = None) -> dict:
        """Answer an open blocking question and resume the job.

        Records `human.answer`, appends the answer to `questions.md` (so the
        next attempt sees it in its context manifest), and resumes execution.
        Pass the same `adapter_id` the job ran with — the kernel does not
        assume the default adapter on resume.
        """
        job = self.job_status(job_id)
        if job["state"] != "blocked":
            raise KernelError(f"Job is '{job['state']}'; nothing to answer")
        open_q = [q for q in job.get("questions", [])
                  if q["id"] == question_id and not q.get("answered")]
        if not open_q:
            raise KernelError(f"No open question '{question_id}' on job '{job_id}'")
        if not (answer or "").strip():
            raise KernelError("Answer must not be empty")

        job_dir = self._find_job_dir(job_id)
        lease = LeaseManager(job_dir, self.actor)
        fence = lease.acquire()
        try:
            state = self._job_state(job_dir)
            state.append_event(
                "human.answer", actor=self.actor, fence=fence,
                data={"question_id": question_id, "answer": answer.strip()[:2000]},
                job_id=job_id,
            )
            path = job_dir / "questions.md"
            previous = path.read_text(encoding="utf-8") if path.exists() else ""
            path.write_text(
                previous + f"### A: {question_id}\n{answer.strip()[:2000]}\n",
                encoding="utf-8",
            )
            state.transition("running", actor=self.actor, fence=fence,
                             reason=f"human answered '{question_id}'")
        finally:
            if lease.current_token() == fence:
                lease.release(fence)
        return self.job_execute(job_id, adapter_id=adapter_id)

    def _last_accepted_stage(self, job_dir: Path) -> Optional[str]:
        stage = None
        for ev in self._job_state(job_dir).load_events():
            if ev["type"] == "stage.accepted":
                stage = ev["data"].get("stage")
        return stage

    # ------------------------------------------------------------------
    # Doctor & reindex
    # ------------------------------------------------------------------

    def doctor(self) -> dict:
        """Verify integrity of the factory tree and repair snapshots.

        Checks: project/job schema validity, event-log hash chain, that the
        snapshot equals the event fold (repairs if not), expired leases, and
        missing/orphan worktrees. Warns when the root is a network path.
        """
        now = datetime.now(timezone.utc)
        report = {
            "ok": True,
            "root": str(self.root),
            "network_fs": self._is_network_path(self.root),
            "projects": 0,
            "jobs": 0,
            "repairs": [],
            "warnings": [],
            "errors": [],
            "active_leases": [],
        }
        if report["network_fs"]:
            report["warnings"].append(
                f"Factory root looks like a network path ({self.root}); "
                "concurrent mode is unsupported on network filesystems."
            )

        self._doctor_profile_guards(report)

        for proj_dir in sorted(self.projects_dir.iterdir()):
            if not proj_dir.is_dir():
                continue
            report["projects"] += 1

            proj = read_json(proj_dir / "project.json")
            if proj is None:
                report["warnings"].append(f"{proj_dir.name}: missing project.json")
            else:
                try:
                    self.schemas.validate("project", proj)
                except SchemaError as e:
                    self._fail(report, f"{proj_dir.name}/project.json: {e}")

            jobs_dir = proj_dir / "jobs"
            if not jobs_dir.exists():
                continue
            for job_dir in sorted(jobs_dir.iterdir()):
                if not job_dir.is_dir():
                    continue
                if not (job_dir / "events.jsonl").exists():
                    report["warnings"].append(
                        f"{proj_dir.name}/{job_dir.name}: no events.jsonl"
                    )
                    continue
                report["jobs"] += 1
                self._doctor_job(report, proj_dir, job_dir, now)

        # Orphan worktrees (present without a marker)
        for wt in sorted(self.work_dir.iterdir()):
            if wt.is_dir() and not (wt / ".factory_job").exists():
                report["warnings"].append(f"Orphan worktree: {wt.name}")

        return report

    def _doctor_profile_guards(self, report: dict) -> None:
        """Advisory: every guard id declared by a stage profile must exist.

        Read-only and order-stable: findings are emitted sorted by stage name,
        then guard id, each naming the profile file that declares it. Doctor
        is advisory here — the runtime already hard-fails unknown ids through
        the ``guard_config`` pseudo-guard (spec §5.3: invariants the kernel
        enforces); doctor surfaces a typo at boot instead of mid-job.
        """
        if not self.stages_dir.exists():
            return
        missing = []
        for path in sorted(self.stages_dir.glob("*.yaml")):
            try:
                doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except (yaml.YAMLError, OSError) as e:
                self._fail(report, f"stages/{path.name}: unreadable YAML ({e})")
                continue
            if not isinstance(doc, dict):
                self._fail(report, f"stages/{path.name}: malformed profile")
                continue
            for stage in doc.get("stages") or []:
                stage_name = str(stage.get("id") or "?")
                for guard_id in stage.get("guards") or []:
                    if guard_id not in GUARDS:
                        missing.append((stage_name, str(guard_id), path.name))
        for stage_name, guard_id, filename in sorted(missing, key=lambda m: (m[0], m[1])):
            report["warnings"].append(
                f"Stage {stage_name} declares guard {guard_id} but it is not "
                f"registered (fix stages/{filename})"
            )

    def _doctor_job(self, report: dict, proj_dir: Path, job_dir: Path, now: datetime) -> None:
        label = f"{proj_dir.name}/{job_dir.name}"
        try:
            state = self._job_state(job_dir)
            events = state.load_events()

            for i, ev in enumerate(events):
                try:
                    self.schemas.validate("event", ev)
                except SchemaError as e:
                    raise StateError(f"event {i} invalid: {e}")

            problems = verify_chain(events)
            if problems:
                raise StateError("event chain broken: " + "; ".join(problems))

            folded = state.fold(events)
            on_disk = read_json(job_dir / "job.json")
            if on_disk != folded:
                state.write_snapshot(folded)
                report["repairs"].append(f"Repaired snapshot for job {folded['id']}")

            lease = read_json(job_dir / ".lease.json")
            if lease:
                expires = datetime.fromisoformat(lease["expires"].replace("Z", "+00:00"))
                if expires < now:
                    report["warnings"].append(
                        f"Job {folded['id']}: expired lease (owner {lease.get('owner')})"
                    )
                else:
                    report["active_leases"].append(
                        {
                            "job": folded["id"],
                            "owner": lease.get("owner"),
                            "expires": lease["expires"],
                        }
                    )

            if folded["state"] not in TERMINAL_STATES:
                wt = self.work_dir / job_dir.name
                if not wt.exists():
                    report["warnings"].append(
                        f"Job {folded['id']}: no worktree at {wt}"
                    )

            # Kernel-owned guard authorization file: a corrupt or malformed
            # one must never be silently read as "no authorization" (spec
            # §9.3 authorizations are structural, never plan-prose).
            auth_path = job_dir / "authorizations.json"
            if auth_path.exists():
                auth_doc = None
                try:
                    auth_doc = read_json(auth_path, default=None)
                    if auth_doc is not None:
                        self.schemas.validate("authorizations", auth_doc)
                except (ValueError, SchemaError) as e:
                    self._fail(report,
                               f"Job {folded['id']} has invalid "
                               f"authorizations.json: {e}")
                if auth_doc is None:
                    self._fail(
                        report,
                        f"Job {folded['id']} has invalid authorizations.json: "
                        "not a JSON object",
                    )
        except Exception as e:
            self._fail(report, f"{label}: {e}")

    @staticmethod
    def _fail(report: dict, message: str) -> None:
        report["ok"] = False
        report["errors"].append(message)

    @staticmethod
    def _is_network_path(path: Path) -> bool:
        s = str(path)
        if s.startswith("\\\\"):
            return True
        if os.name == "nt":
            try:
                import ctypes

                drive = os.path.splitdrive(s)[0] + "\\"
                if not drive:
                    return False
                DRIVE_REMOTE = 4
                return ctypes.windll.kernel32.GetDriveTypeW(drive) == DRIVE_REMOTE
            except Exception:
                return False
        return False

    def reindex(self) -> dict:
        return self._reindex()

    def _reindex(self) -> dict:
        index = {
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "projects": {},
            "jobs_by_state": {},
        }
        for proj in self.project_list():
            name = proj["name"]
            index["projects"][name] = {
                "mode": proj["mode"],
                "domain": proj["domain"],
                "status": proj["status"],
                "jobs": [],
            }
            for job in self.job_list(name):
                index["projects"][name]["jobs"].append(job["id"])
                st = job["state"]
                index["jobs_by_state"].setdefault(st, []).append(job["id"])

        atomic_write_json(self.state_dir / "index.json", index)
        return index

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_job_dir(self, job_id: str) -> Path:
        for proj_dir in self.projects_dir.iterdir():
            candidate = proj_dir / "jobs" / job_id
            if candidate.exists():
                return candidate
        raise KernelError(f"Job '{job_id}' not found")

    def load_stage_profile(self, profile: str) -> dict:
        """Load and validate a stage profile from ``kernel/stages/<profile>.yaml``."""
        path = self.stages_dir / f"{profile}.yaml"
        return load_profile(path)

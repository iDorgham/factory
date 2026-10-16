"""Enterprise AI Software Factory — Kernel (P0 core).

The kernel is deterministic. It owns locks, transitions, validation,
checks, budgets, and audit. Agents never mutate state.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .atomic import atomic_write_json, read_json
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
            "visual": {"cmd": "echo 'visual placeholder'", "required": False},
        }
        atomic_write_json(proj_dir / "checks.json", checks)

        self._reindex()
        return project

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

        # Create worktree placeholder (real git worktree would go here)
        worktree = self.work_dir / job_id
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

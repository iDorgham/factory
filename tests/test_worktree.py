"""Tests for git worktrees, checkpoints-as-commits, the merge queue, and undo.

Covers spec §6 (isolation), §7.1 (checkpoints and recovery), and §21.2/§23
(Undo). Skipped entirely when no ``git`` executable is available.
"""
from __future__ import annotations

import shutil
import subprocess

import pytest

from factory_kernel.gitrepo import IDENTITY, current_branch, head, is_repo

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git is not installed"
)


def _git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *IDENTITY, *args],
        capture_output=True, text=True, check=True,
    )


def test_project_creates_repo_and_base_commit(kernel):
    proj = kernel.project_create("demo", mode="solo", domain="web")
    repo = kernel.projects_dir / "demo" / "repo"
    assert is_repo(repo)
    assert proj["base_commit"] and len(proj["base_commit"]) == 40
    assert proj["base_commit"] == head(repo)
    assert current_branch(repo) == "main"


def test_job_run_creates_branch_worktree(demo_job):
    kernel, job = demo_job
    worktree = kernel.work_dir / job["id"]
    assert is_repo(worktree)
    assert current_branch(worktree) == f"factory/{job['id']}"
    # The placeholder marker survives next to the real worktree.
    assert (worktree / ".factory_job").read_text() == job["id"]
    # Branch starts at the project base commit.
    base = kernel.project_get("demo")["base_commit"]
    assert head(worktree) == base


def test_checkpoint_records_a_git_commit(demo_job):
    kernel, job = demo_job
    kernel.job_execute(job["id"])
    status = kernel.job_status(job["id"])
    assert all(c.get("commit") for c in status["checkpoints"])
    worktree = kernel.work_dir / job["id"]
    # The worktree HEAD is the last recorded checkpoint commit.
    assert head(worktree) == status["checkpoints"][-1]["commit"]


def test_approve_merges_job_branch_into_main(demo_job):
    kernel, job = demo_job
    kernel.job_execute(job["id"])
    done = kernel.job_approve(job["id"])

    assert done["state"] == "completed"
    assert done["merge"]["event"] == "merge.completed"
    assert done["merge"]["merge_commit"]

    repo = kernel.projects_dir / "demo" / "repo"
    # The worktree's produced file is now on the main branch.
    assert (repo / "src" / "build.md").exists()
    assert head(repo) == done["merge"]["merge_commit"]


def test_undo_reverts_the_merge(demo_job):
    kernel, job = demo_job
    kernel.job_execute(job["id"])
    merged = kernel.job_approve(job["id"])
    repo = kernel.projects_dir / "demo" / "repo"
    base = kernel.project_get("demo")["base_commit"]
    assert head(repo) == merged["merge"]["merge_commit"]

    undone = kernel.job_undo(job["id"])
    assert undone["merge"]["event"] == "merge.undone"
    assert undone["merge"]["mode"] in ("reset", "revert")
    # The merged file is gone again.
    assert not (repo / "src" / "build.md").exists()
    assert head(repo) == base


def test_undo_refused_when_not_merged(demo_job):
    kernel, job = demo_job
    kernel.job_execute(job["id"])  # parked, not approved/merged
    with pytest.raises(kernel_error()):
        kernel.job_undo(job["id"])


def test_double_undo_refused(demo_job):
    kernel, job = demo_job
    kernel.job_execute(job["id"])
    kernel.job_approve(job["id"])
    kernel.job_undo(job["id"])
    with pytest.raises(kernel_error()):
        kernel.job_undo(job["id"])


def test_merge_conflict_blocks_the_job(demo_job):
    kernel, job = demo_job
    kernel.job_execute(job["id"])

    # Diverge main on the same path the job branch produced → add/add conflict.
    repo = kernel.projects_dir / "demo" / "repo"
    (repo / "src").mkdir(exist_ok=True)
    (repo / "src" / "build.md").write_text("main-side content\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "main: conflicting change")

    result = kernel.job_approve(job["id"])
    assert result["state"] == "blocked"
    assert result["merge"]["event"] == "merge.conflict"
    assert "src/build.md" in result["merge"]["conflicts"]
    # The failed merge was aborted: the repo is not mid-merge.
    assert subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "-q", "--verify", "MERGE_HEAD"],
        capture_output=True,
    ).returncode != 0


def test_resume_restores_worktree_to_checkpoint(demo_job):
    kernel, job = demo_job
    kernel.job_execute(job["id"])
    status = kernel.job_status(job["id"])
    checkpoint_commit = status["checkpoints"][-1]["commit"]

    worktree = kernel.work_dir / job["id"]
    # Simulate a dirty tree left behind by a crashed process.
    (worktree / "junk.txt").write_text("uncommitted\n", encoding="utf-8")
    (worktree / "src" / "build.md").write_text("tampered\n", encoding="utf-8")

    # Re-running restores the worktree to the last accepted checkpoint first.
    kernel.job_execute(job["id"])
    assert not (worktree / "junk.txt").exists()
    assert "tampered" not in (worktree / "src" / "build.md").read_text(encoding="utf-8")
    assert head(worktree) == checkpoint_commit


def kernel_error():
    from factory_kernel.kernel import KernelError

    return KernelError

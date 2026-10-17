"""Git repositories, worktrees, checkpoints, and the merge queue (spec §5.1, §6, §7.1, §199).

Each project owns a repository at ``projects/<name>/repo`` (the factory-managed
repo). Creating a job adds a git **worktree** at ``.work/<job-id>/`` on branch
``factory/<job-id>`` from the project's base commit (§198). Each accepted stage
attempt records a **checkpoint** commit (§237). Approval merges the job branch
back into the project's main branch (§199); ``job undo`` reverts that merge.

Everything here shells out to ``git`` with a fixed identity so the kernel never
depends on a developer's global git configuration (hermetic, reproducible).
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional, Union

# A fixed committer identity: the factory, not the host user. Passed on every
# invocation so tests and CI do not depend on global git config.
IDENTITY = ["-c", "user.name=factory", "-c", "user.email=factory@localhost"]

GITIGNORE = """\
# Factory job bookkeeping (never part of the produced software)
.factory_job

# Language / tooling noise
__pycache__/
*.py[cod]
node_modules/
.work/
"""


class GitError(Exception):
    pass


_available: Optional[bool] = None


def git_available() -> bool:
    """Whether a usable ``git`` executable is on PATH (checked once)."""
    global _available
    if _available is None:
        try:
            proc = subprocess.run(["git", "--version"], capture_output=True, text=True)
            _available = proc.returncode == 0
        except (OSError, ValueError):
            _available = False
    return _available


def _git(cwd: Union[str, Path], *args: str, check: bool = True) -> subprocess.CompletedProcess:
    cmd = ["git", "-C", str(cwd), *IDENTITY, *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise GitError(
            f"git {' '.join(args)} failed ({proc.returncode}): {proc.stderr.strip()}"
        )
    return proc


def is_repo(path: Union[str, Path]) -> bool:
    """True if ``path`` is itself a git repository root or a linked worktree.

    Only a ``.git`` entry directly under ``path`` counts (a directory for a
    repository root, a file for a linked worktree). Unlike
    ``rev-parse --is-inside-work-tree`` this never walks up to a parent
    repository, so a plain job directory nested inside some outer checkout
    (e.g. a legacy repo-less project's worktree inside the factory's own
    clone) is NOT mistaken for a worktree. The walk-up behavior caused
    checkpoint commits to land in the outer repo and ``reset --hard`` to
    rewrite it, silently dropping job events (spec §239 isolation).
    """
    path = Path(path)
    if not path.is_dir() or not git_available():
        return False
    return (path / ".git").exists()


def head(path: Union[str, Path]) -> Optional[str]:
    """The current commit SHA, or None if the repo has no commits yet."""
    proc = _git(path, "rev-parse", "HEAD", check=False)
    return proc.stdout.strip() if proc.returncode == 0 else None


def current_branch(path: Union[str, Path]) -> Optional[str]:
    proc = _git(path, "rev-parse", "--abbrev-ref", "HEAD", check=False)
    return proc.stdout.strip() if proc.returncode == 0 else None


def commit_all(path: Union[str, Path], message: str) -> Optional[str]:
    """Stage everything and commit if there is anything to commit.

    Returns the resulting HEAD SHA. If the tree is already clean there is
    nothing to commit, so the current HEAD (the "recorded clean-tree SHA") is
    returned instead — the checkpoint is still valid.
    """
    _git(path, "add", "-A")
    staged = _git(path, "diff", "--cached", "--quiet", check=False)
    if staged.returncode == 0:
        return head(path)
    _git(path, "commit", "-m", message)
    return head(path)


def init_repo(path: Union[str, Path], project: str = "project") -> str:
    """Create a factory-managed repository with an initial commit.

    Returns the base commit SHA the project's jobs branch from.
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    if _git(path, "init", "-b", "main", check=False).returncode != 0:
        # Older git without `init -b`: init then point HEAD at main.
        _git(path, "init")
        _git(path, "symbolic-ref", "HEAD", "refs/heads/main")
    (path / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
    (path / "README.md").write_text(
        f"# {project}\n\nManaged by the AI Software Factory.\n", encoding="utf-8"
    )
    return commit_all(path, "chore: initialize project repository")


def add_worktree(repo: Union[str, Path], worktree: Union[str, Path], branch: str,
                 base: str) -> None:
    """Add ``worktree`` on a new ``branch`` from ``base`` (spec §198)."""
    worktree = Path(worktree)
    worktree.parent.mkdir(parents=True, exist_ok=True)
    _git(repo, "worktree", "add", "-b", branch, str(worktree), base)


def remove_worktree(repo: Union[str, Path], worktree: Union[str, Path]) -> None:
    _git(repo, "worktree", "remove", "--force", str(worktree), check=False)


def merge_branch(repo: Union[str, Path], branch: str, message: str) -> dict:
    """Merge ``branch`` into the repo's current branch (the merge queue, §199).

    Returns ``{"ok": True, "base", "merge_commit"}`` on success, or
    ``{"ok": False, "base", "conflicts"}`` when the merge conflicts (the merge
    is aborted first so the repo is left clean).
    """
    base = head(repo)
    proc = _git(repo, "merge", "--no-ff", "-m", message, branch, check=False)
    if proc.returncode == 0:
        return {"ok": True, "base": base, "merge_commit": head(repo),
                "detail": proc.stdout.strip()}
    conflicts = _git(
        repo, "diff", "--name-only", "--diff-filter=U", check=False
    ).stdout.split()
    _git(repo, "merge", "--abort", check=False)
    return {"ok": False, "base": base, "conflicts": conflicts,
            "detail": proc.stderr.strip()}


def reset_hard(path: Union[str, Path], commit: str) -> None:
    """Restore a worktree to a commit, discarding local and untracked changes.

    ``git clean -fd`` removes untracked files and directories but not ignored
    ones, so the ``.factory_job`` marker survives (spec §239).
    """
    _git(path, "reset", "--hard", commit)
    _git(path, "clean", "-fd")


def revert_merge(repo: Union[str, Path], merge_commit: str, base_sha: str) -> dict:
    """Undo a merge: reset if it is still HEAD, otherwise revert the merge commit."""
    if head(repo) == merge_commit:
        _git(repo, "reset", "--hard", base_sha)
        return {"mode": "reset", "sha": base_sha}
    proc = _git(repo, "revert", "-m", "1", "--no-edit", merge_commit, check=False)
    if proc.returncode != 0:
        _git(repo, "revert", "--abort", check=False)
        raise GitError(f"could not revert merge {merge_commit[:12]}…: {proc.stderr.strip()}")
    return {"mode": "revert", "sha": head(repo)}

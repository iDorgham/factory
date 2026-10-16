"""Content-addressed job checkpoints (spec §5.1, §9; P1 plan workstream 1/6).

A checkpoint records a deterministic content hash of everything a job has
produced — every accepted attempt's ``outputs/`` tree plus the job worktree.
This is the "recorded clean-tree SHA" the P1 plan allows in place of a git
commit SHA while no target repository is wired in. When a real git worktree
lands (P1 workstream 1), the same field carries the commit SHA and the
SHA-bound approval logic below is unchanged.

Because the hash is content-addressed, approval bound to a checkpoint SHA is
automatically invalidated by any change to the produced artifacts: the current
result no longer hashes to the approved SHA.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable, Union

IGNORE_DIR_NAMES = {"__pycache__", ".git", ".mypy_cache", ".pytest_cache", ".ruff_cache"}


def _iter_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        if any(part in IGNORE_DIR_NAMES for part in path.parts):
            continue
        yield path


def tree_hash(roots: Union[str, Path, Iterable[Union[str, Path]]]) -> str:
    """Deterministic hash of the files under each root (relative path + bytes)."""
    if isinstance(roots, (str, Path)):
        roots = [roots]
    digest = hashlib.sha256()
    for root in roots:
        root = Path(root)
        for path in _iter_files(root):
            rel = path.relative_to(root).as_posix()
            digest.update(rel.encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def output_roots(job_dir: Union[str, Path]) -> list[Path]:
    """Every attempt ``outputs/`` directory in the job, in stable order."""
    job_dir = Path(job_dir)
    return sorted((job_dir / "stages").glob("*/attempt-*/outputs"))


def result_hash(job_dir: Union[str, Path], worktree: Union[str, Path]) -> str:
    """Content hash of the job's produced artifacts plus its worktree."""
    roots: list[Path] = output_roots(job_dir)
    roots.append(Path(worktree))
    return tree_hash(roots)


def record_checkpoint(state, attempt_dir, job_dir, worktree, stage: str, attempt: int,
                      actor: str, fence: int) -> str:
    """Record a checkpoint for an accepted attempt: write it and emit the event.

    The ``sha`` is the content hash used for SHA-bound approval (unchanged). The
    ``commit`` is a git commit of the worktree (spec §237: "a commit ... saved in
    the attempt record") used to restore the worktree on resume; it is None when
    no repository is wired in.
    """
    from .atomic import atomic_write_json
    from .gitrepo import commit_all, is_repo

    sha = result_hash(job_dir, worktree)
    commit = None
    if is_repo(worktree):
        commit = commit_all(worktree, f"factory: {stage} attempt {attempt}")
    atomic_write_json(
        Path(attempt_dir) / "checkpoint.json",
        {"stage": stage, "attempt": attempt, "sha": sha, "commit": commit},
    )
    state.append_event(
        "checkpoint.created",
        actor=actor,
        fence=fence,
        data={"stage": stage, "attempt": attempt, "sha": sha, "commit": commit},
    )
    return sha

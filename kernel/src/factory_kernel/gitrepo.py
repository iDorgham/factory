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


def _git_bytes(cwd: Union[str, Path], *args: str) -> subprocess.CompletedProcess:
    """Like ``_git`` but returns raw bytes so the caller controls decoding."""
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True)


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace")


# Common binary assets: never read as text and never scanned for secrets.
BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".avif",
    ".pdf", ".zip", ".gz", ".tgz", ".tar", ".7z", ".rar", ".jar",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp3", ".mp4", ".avi", ".mov", ".flac", ".ogg", ".wav",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".class", ".obj", ".lib",
    ".pyc", ".pyd", ".sqlite", ".db",
}


def _looks_binary(raw: bytes) -> bool:
    """NUL bytes are the practical tell for binary content (same rule as git)."""
    return b"\x00" in raw[:8192]


def _unquote(path: str) -> str:
    path = path.strip()
    if len(path) >= 2 and path.startswith('"') and path.endswith('"'):
        path = path[1:-1]
    return path


def _strip_prefix(path: str) -> str:
    return path[2:] if len(path) > 2 and path[1] == "/" else path


def _name_statuses(wt: Path, base_sha: str) -> dict[str, str]:
    """Per-file status (``A`` | ``M`` | ``D``) of ``git diff <base>``."""
    proc = _git_bytes(wt, "diff", "--no-renames", "-z", "--name-status", base_sha)
    statuses: dict[str, str] = {}
    if proc.returncode != 0:
        return statuses
    fields = _decode(proc.stdout).split("\0")
    i = 0
    while i < len(fields) - 1:
        code, path = fields[i], fields[i + 1]
        if not code or not path:
            break
        if code[0] == "T":
            statuses[path] = "M"  # type change: treat as modification
        elif code in ("A", "M", "D"):
            statuses[path] = code
        i += 2
    return statuses


def _binary_paths(wt: Path, base_sha: str) -> set[str]:
    """Paths whose diff is binary (``numstat`` reports ``-`` for line counts)."""
    proc = _git_bytes(wt, "diff", "--no-renames", "--numstat", "-z", base_sha)
    paths: set[str] = set()
    if proc.returncode != 0:
        return paths
    for record in _decode(proc.stdout).split("\0"):
        if not record:
            continue
        counts, _sep, path = record.partition("\t")
        added, _tab, removed = counts.partition("\t")
        if added == "-" or removed == "-":
            paths.add(path.strip())
    return paths


def _parse_patch(text: str) -> dict[str, tuple[list[str], list[str]]]:
    """Line content (added, removed) per path from a unified diff.

    Only lines inside ``@@`` hunks are treated as content, so header lines
    (``---``/``+++``/``old mode``) never leak in. ``\\ No newline`` markers
    are skipped. Renames are disabled upstream, so one path per section.
    """
    added: list[str] = []
    removed: list[str] = []
    a_path = b_path = None
    in_hunk = False
    current = None
    content: dict[str, tuple[list[str], list[str]]] = {}
    for line in text.splitlines():
        if line.startswith("diff --git "):
            if current is not None:
                content[current] = (added, removed)
            a_path = b_path = current = None
            in_hunk, added, removed = False, [], []
        elif line.startswith("--- "):
            a_path = None if line == "--- /dev/null" else _strip_prefix(
                _unquote(line[4:]))
        elif line.startswith("+++ "):
            b_path = None if line == "+++ /dev/null" else _strip_prefix(
                _unquote(line[4:]))
            current = b_path or a_path
        elif line.startswith("@@"):
            in_hunk = True
        elif in_hunk and current is not None:
            if line.startswith("+"):
                added.append(line[1:])
            elif line.startswith("-"):
                removed.append(line[1:])
            # "\ No newline at end of file" and context lines are skipped.
    if current is not None:
        content[current] = (added, removed)
    return content


def _untracked_files(wt: Path) -> list[str]:
    """Untracked paths (respecting .gitignore), NUL-separated for safety."""
    proc = _git_bytes(wt, "ls-files", "--others", "--exclude-standard", "-z")
    if proc.returncode != 0:
        return []
    return [p for p in _decode(proc.stdout).split("\0") if p]


def collect_diff(worktree: Union[str, Path], base_sha: str) -> dict:
    """Everything the attempt changed relative to ``base_sha`` (spec §9.3).

    Guards run after every round, so this must capture the whole round: files
    the adapter committed, staged or merely edited, and untracked files. Line
    content is read from the unified diff text; binary files are marked
    ``binary: True`` with no content so secret scanning never decodes bytes.
    Returns ``{}`` for a clean worktree.
    """
    wt = Path(worktree)
    if not is_repo(wt) or not head(wt) or not base_sha:
        return {}

    diff: dict[str, dict] = {}
    statuses = _name_statuses(wt, base_sha)
    binaries = _binary_paths(wt, base_sha)
    content = _parse_patch(_decode(
        _git_bytes(wt, "diff", "--no-renames", "-p", "--no-color", base_sha).stdout))
    for path, status in statuses.items():
        if path in binaries:
            diff[path] = {"status": status, "binary": True}
            continue
        added, removed = content.get(path, ([], []))
        diff[path] = {"status": status, "added": added, "removed": removed,
                      "binary": False}

    for path in _untracked_files(wt):
        if path in diff:
            continue
        raw = (wt / path).read_bytes()
        if Path(path).suffix.lower() in BINARY_EXTENSIONS or _looks_binary(raw):
            diff[path] = {"status": "A", "binary": True}
            continue
        text = _decode(raw)
        diff[path] = {"status": "A", "added": text.splitlines(),
                      "removed": [], "binary": False}
    return diff


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

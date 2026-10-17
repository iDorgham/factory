"""Build provenance — verify that commits carry the required AI trailers.

Every change is meant to record which tool and model produced it (see
``docs/development/CONTRIBUTING.md`` §3.1 and ``docs/context/AI-PROVENANCE.md``).
This module is the deterministic checker behind ``factory provenance verify``.

Design: parsing and policy are **pure functions** over commit records, so they
are testable without a git binary. :func:`read_commits` is the only part that
shells out to git.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence, Union

# Trailers every non-skippable commit must carry.
DEFAULT_REQUIRED: tuple[str, ...] = ("AI-Tool", "AI-Model")

# Commits that legitimately carry no body: merges, reverts, and autosquash.
_SKIP_SUBJECT = re.compile(r"^(?:Merge|Revert)\b|^(?:fixup!|squash!)(?:\s|$)")

# A git trailer line: "Key: value" (key = leading letter, then alnum/dash).
_TRAILER = re.compile(r"^([A-Za-z][A-Za-z0-9-]*):[ \t]+(.+?)\s*$")

# git log record/field separators (unprintable, so they never appear in text).
_RECORD_SEP = "\x1e"
_FIELD_SEP = "\x1f"


class ProvenanceError(Exception):
    """Raised when provenance cannot be determined (e.g. git is unavailable)."""


@dataclass
class Commit:
    """A commit as far as provenance cares: identity, subject, full message."""

    sha: str
    subject: str
    message: str

    @property
    def trailers(self) -> dict[str, str]:
        return parse_trailers(self.message)


@dataclass
class Violation:
    """A commit that is missing one or more required trailers."""

    sha: str
    subject: str
    missing: list[str]

    def to_dict(self) -> dict:
        return {"sha": self.sha, "subject": self.subject, "missing": self.missing}


def parse_trailers(message: str) -> dict[str, str]:
    """Return the trailer block of a commit message as ``{key: value}``.

    Trailers live in the final paragraph: a run of ``Key: value`` lines. Keys
    are returned as written; callers should look them up case-insensitively.
    Returns an empty dict when there is no trailer block.
    """
    lines = message.replace("\r\n", "\n").split("\n")
    while lines and not lines[-1].strip():
        lines.pop()

    block: list[str] = []
    for line in reversed(lines):
        if not line.strip():
            break
        block.append(line)
    block.reverse()

    trailers: dict[str, str] = {}
    for line in block:
        match = _TRAILER.match(line)
        if match:
            trailers[match.group(1)] = match.group(2)
    return trailers


def _lookup(trailers: dict[str, str], key: str) -> Optional[str]:
    wanted = key.lower()
    for k, v in trailers.items():
        if k.lower() == wanted:
            return v
    return None


def is_skippable(commit: Commit) -> bool:
    """True for merge/revert/autosquash commits that need no trailers."""
    return bool(_SKIP_SUBJECT.match(commit.subject))


def _matches(sha: str, allow: set[str]) -> bool:
    sha = sha.lower()
    return sha in allow or any(sha.startswith(a) for a in allow)


def check_commits(
    commits: Sequence[Commit],
    required: Sequence[str] = DEFAULT_REQUIRED,
    allow: Iterable[str] = (),
    *,
    allow_all_before: Optional[str] = None,
) -> list[Violation]:
    """Pure policy check over commits ordered newest-first (as ``git log`` emits).

    - ``allow``: exact or abbreviated SHAs that are exempt (the grandfather list).
    - ``allow_all_before``: a baseline SHA; it and every older commit are
      grandfathered, while anything newer is still enforced.

    Returns the violations; an empty list means the history is clean.
    """
    allowed = {a.lower() for a in allow}
    baseline = allow_all_before.lower() if allow_all_before else None
    grandfathered = False

    violations: list[Violation] = []
    for commit in commits:
        if baseline is not None and not grandfathered:
            if commit.sha.lower().startswith(baseline):
                grandfathered = True  # this commit and all older ones are exempt
            # else: newer than the baseline -> still enforced
        if grandfathered or _matches(commit.sha, allowed):
            continue
        if is_skippable(commit):
            continue
        trailers = commit.trailers
        missing = [
            key for key in required
            if not (_lookup(trailers, key) or "").strip()
        ]
        if missing:
            violations.append(Violation(commit.sha, commit.subject, missing))
    return violations


def load_allowlist(path: Union[str, Path]) -> set[str]:
    """Load an allowlist file: one SHA per line, ``#`` starts a comment."""
    p = Path(path)
    if not p.exists():
        return set()
    out: set[str] = set()
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip().lower()
        if line:
            out.add(line)
    return out


def read_commits(
    cwd: Union[str, Path] = ".",
    rev_range: Optional[str] = None,
    *,
    git: str = "git",
) -> list[Commit]:
    """Read commits (newest-first) from a git repository via ``git log``."""
    fmt = f"%H{_FIELD_SEP}%s{_FIELD_SEP}%B{_RECORD_SEP}"
    args = [git, "log", f"--format={fmt}", "--no-color"]
    if rev_range:
        args.append(rev_range)

    try:
        proc = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True)
    except FileNotFoundError as e:  # git not installed
        raise ProvenanceError(f"git not found: {e}") from e

    if proc.returncode != 0:
        raise ProvenanceError(proc.stderr.strip() or f"git log failed ({proc.returncode})")

    commits: list[Commit] = []
    for record in proc.stdout.split(_RECORD_SEP):
        record = record.strip("\n")
        if not record.strip():
            continue
        parts = record.split(_FIELD_SEP)
        if len(parts) < 3:
            continue
        commits.append(
            Commit(sha=parts[0].strip(), subject=parts[1], message=parts[2])
        )
    return commits


def verify(
    cwd: Union[str, Path] = ".",
    *,
    required: Sequence[str] = DEFAULT_REQUIRED,
    rev_range: Optional[str] = None,
    allow: Iterable[str] = (),
    allow_all_before: Optional[str] = None,
    allowlist_path: Optional[Union[str, Path]] = None,
    git: str = "git",
) -> dict:
    """Verify provenance across a repository's history and return a report."""
    commits = read_commits(cwd, rev_range, git=git)

    allowed = {a.lower() for a in allow}
    if allowlist_path is not None:
        allowed |= load_allowlist(allowlist_path)

    violations = check_commits(
        commits, required=required, allow=allowed, allow_all_before=allow_all_before
    )
    return {
        "ok": not violations,
        "checked": len(commits),
        "required": list(required),
        "allowlist_size": len(allowed),
        "violations": [v.to_dict() for v in violations],
    }

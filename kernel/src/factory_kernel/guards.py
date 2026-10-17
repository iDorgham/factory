"""Guards (anti-cheating) — deterministic checks over the attempt diff (§9.3).

Guards are pure kernel functions: no subprocesses, no LLM calls, no network.
They receive a :class:`GuardContext` — the attempt's diff plus structural,
kernel-validated authorizations — and return violations as data.

Guards never *decide* anything about the job; the engine turns their output
into attempt verdicts and events. That keeps the "kernel enforces, agents
propose" split: the diff is ground truth read by the kernel, not evidence
claimed by an agent.

Authorization is structural: an ``authorizations.json`` per job, referenced by
exact path (no globs, no plan-prose parsing). Membership in the allowlists is
the only way a guard stays silent.

A stage profile declaring a guard id that is not in :data:`GUARDS` is a hard
failure of the attempt (same policy as ``checks.py``): a typo can never
silently skip a safeguard.
"""
from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path

# ----------------------------------------------------------------------
# Shape knowledge (deterministic, conservative)
# ----------------------------------------------------------------------

# A path segment equal to one of these marks everything under it as test code.
TEST_DIRNAMES = {"tests", "__tests__"}

# Basename patterns for test files, per language.
TEST_PATTERNS = (
    "test_*.py", "*_test.py", "test_*.ts", "*_test.ts",
    "test_*.js", "*_test.js", "test_*.mjs", "*_test.mjs",
    "test_*.mts", "*_test.mts", "test_*.cts", "*_test.cts",
    "*.test.js", "*.test.jsx", "*.test.mjs", "*.test.ts",
    "*.test.tsx", "*.test.mts", "*.test.cts",
    "*.spec.js", "*.spec.jsx", "*.spec.mjs", "*.spec.ts",
    "*.spec.tsx", "*.spec.mts", "*.spec.cts",
)

# Dependency manifests and lockfiles. A change to either side is only allowed
# when the other side changed too (or the path is explicitly authorized).
MANIFESTS = frozenset({
    "package.json", "pyproject.toml", "requirements.txt",
    "Cargo.toml", "go.mod", "Gemfile", "composer.json",
})
LOCKFILES = frozenset({
    "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "uv.lock", "Pipfile.lock", "requirements.lock",
    "Cargo.lock", "go.sum", "Gemfile.lock", "composer.lock",
})

# Secret patterns, checked against added lines only (first hit per line wins).
_SECRET_AWS_KEY = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_SECRET_GITHUB_TOKEN = re.compile(r"\bghp_[A-Za-z0-9]{36}\b")
_SECRET_PEM = re.compile(r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----")
_SECRET_CREDENTIAL = re.compile(
    r"(?i)\b(password|passwd|secret|token|api_key|apikey)\b\s*=\s*"
    r"(\"|')([^\"']{8,})\3")
SECRET_PATTERNS: tuple = (
    ("aws_access_key", _SECRET_AWS_KEY),
    ("github_token", _SECRET_GITHUB_TOKEN),
    ("private_key_block", _SECRET_PEM),
    ("credential_assignment", _SECRET_CREDENTIAL),
)

# Benign high-entropy data: base64 blobs (images/data URIs) and hex hashes.
BENIGN_BASE64 = re.compile(r"[A-Za-z0-9+/=]{100,}")
BENIGN_HEX_HASH = re.compile(r"\b[0-9a-fA-F]{64}\b")


class GuardError(Exception):
    pass


@dataclass
class GuardContext:
    """Everything a guard may look at: the attempt's diff and nothing else."""
    step: str
    commits: dict = field(default_factory=dict)
    diff: dict = field(default_factory=dict)          # collect_diff output
    authorizations: dict = field(default_factory=dict)
    worktree: Path = field(default_factory=Path)


@dataclass
class GuardResult:
    guard: str
    violations: list = field(default_factory=list)


# ----------------------------------------------------------------------
# Authorization (structural, exact-path)
# ----------------------------------------------------------------------

def _posix(path: str) -> str:
    """Worktree-relative path in POSIX form (the form git reports paths in)."""
    text = str(path).replace("\\", "/").strip()
    while text.startswith("./"):
        text = text[2:]
    return text


def _is_wildcard(entry: str) -> bool:
    """True if the entry tries to widen its own match; wildcards never match."""
    return any(ch in entry for ch in "*?[")


def authorized(authorizations: dict, kind: str, path: str) -> bool:
    """True iff ``path`` is explicitly authorized under ``kind``.

    Exact string equality on the POSIX path. Wildcard entries are never
    matched: a human authorizing must name the exact file, so one entry can
    never cover a whole directory tree.
    """
    if not isinstance(authorizations, dict):
        return False
    allowed = authorizations.get(kind)
    if not isinstance(allowed, list):
        return False
    target = _posix(path)
    for entry in allowed:
        if not isinstance(entry, str) or not entry or _is_wildcard(entry):
            continue
        if _posix(entry) == target:
            return True
    return False


# ----------------------------------------------------------------------
# Guard 1: no_test_deletion
# ----------------------------------------------------------------------

def is_test_path(path: str) -> bool:
    """Conservative test-file detection: tests/ dirs plus basename globs."""
    posix = _posix(path)
    parts = posix.split("/")
    if any(part in TEST_DIRNAMES for part in parts[:-1]):
        return True
    name = parts[-1]
    return any(fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(posix, pattern)
               for pattern in TEST_PATTERNS)


def no_test_deletion(ctx: GuardContext) -> GuardResult:
    """Tests may not be deleted without an explicit, exact-path authorization."""
    violations = []
    for path, change in ctx.diff.items():
        if change.get("status") != "D" or not is_test_path(path):
            continue
        if authorized(ctx.authorizations, "allowed_test_deletions", path):
            continue
        violations.append({
            "path": path,
            "kind": "deleted",
            "evidence": "Test file deleted without authorization",
        })
    return GuardResult("no_test_deletion", violations)


# ----------------------------------------------------------------------
# Guard 2: no_lockfile_surprise
# ----------------------------------------------------------------------

def _basename(path: str) -> str:
    return _posix(path).split("/")[-1]


def no_lockfile_surprise(ctx: GuardContext) -> GuardResult:
    """Dependency changes must move manifest and lockfile together."""
    added_or_modified = {
        path for path, change in ctx.diff.items()
        if change.get("status") in ("A", "M")
    }
    deleted = {path for path, change in ctx.diff.items()
               if change.get("status") == "D"}
    man_changed = {p for p in added_or_modified if _basename(p) in MANIFESTS}
    lock_changed = {p for p in added_or_modified if _basename(p) in LOCKFILES}
    lock_deleted = {p for p in deleted if _basename(p) in LOCKFILES}

    violations = []
    for path in sorted(lock_deleted):
        violations.append({
            "path": path, "kind": "deleted", "evidence": "Lockfile deleted",
        })
    for path in sorted(man_changed):
        if lock_changed:
            continue  # some lockfile moved too: the pair is consistent
        if authorized(ctx.authorizations, "allowed_dep_changes", path):
            continue
        violations.append({
            "path": path, "kind": "manifest_without_lockfile",
            "evidence": "Manifest changed without corresponding lockfile change",
        })
    for path in sorted(lock_changed):
        if man_changed:
            continue  # paired: the manifest explaining the lockfile changed
        if authorized(ctx.authorizations, "allowed_dep_changes", path):
            continue
        violations.append({
            "path": path, "kind": "lockfile_without_manifest",
            "evidence": "Lockfile changed without corresponding manifest change",
        })
    return GuardResult("no_lockfile_surprise", violations)


# ----------------------------------------------------------------------
# Guard 3: no_secret_in_diff
# ----------------------------------------------------------------------

def _is_benign_line(line: str) -> bool:
    """Long base64 runs (images/data URIs) and hex hashes are not secrets."""
    return bool(BENIGN_BASE64.search(line) or BENIGN_HEX_HASH.search(line))


def _is_reference_like(value: str) -> bool:
    """A quoted RHS that is clearly an expression/reference, not a literal."""
    return bool(re.search(r"[.()[\]{}$]", value))


def no_secret_in_diff(ctx: GuardContext) -> GuardResult:
    """Scan added lines for known secret shapes; removed lines are irrelevant."""
    violations = []
    for path, change in ctx.diff.items():
        if change.get("binary"):
            continue
        for line in change.get("added") or []:
            if _is_benign_line(line):
                continue
            for pattern_id, pattern in SECRET_PATTERNS:
                match = pattern.search(line)
                if match is None:
                    continue
                if pattern_id == "credential_assignment":
                    value = match.group(3)
                    if (_is_reference_like(value)
                            or BENIGN_HEX_HASH.search(value)
                            or BENIGN_BASE64.search(value)):
                        continue
                violations.append({
                    "path": path,
                    "kind": "secret",
                    "evidence": ("Potential secret detected in added lines "
                                 f"({pattern_id}; line: {line.strip()[:120]})"),
                })
                break  # one finding per line; first (highest-priority) hit
    return GuardResult("no_secret_in_diff", violations)


# ----------------------------------------------------------------------
# Registry + entry point
# ----------------------------------------------------------------------

GUARDS: dict[str, GuardResult] = {
    "no_test_deletion": no_test_deletion,
    "no_lockfile_surprise": no_lockfile_surprise,
    "no_secret_in_diff": no_secret_in_diff,
}


def run_guards(ids: list, ctx: GuardContext) -> list:
    """Run the named guards in declaration order (spec §9.3).

    An empty list runs nothing. An unknown id raises :class:`GuardError` —
    the same fail-hard policy as a check id missing from ``checks.json``.
    Results never carry ``None``: a clean guard reports an empty violations
    list, so callers can always distinguish "ran and clean" from "not run".
    """
    results = []
    for guard_id in ids:
        guard = GUARDS.get(guard_id)
        if guard is None:
            raise GuardError(f"Unknown guard: {guard_id}")
        results.append(guard(ctx))
    return results

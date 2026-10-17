"""P2.1: guards (anti-cheating, spec §9.3).

Guards are pure kernel functions over an attempt's diff. They run after every
round (per attempt), flip the attempt to failed on violation, and record their
verdicts as events. A guard id declared by a stage profile but absent from the
registry is a hard failure — a typo can never silently skip a safeguard.

Authorization is structural: a kernel-validated ``authorizations.json`` per job
(exact-path allowlists), never prose parsed out of the plan.
"""
from __future__ import annotations

import pytest

from factory_kernel.schemas import SchemaStore


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _ctx(diff: dict, authorizations: dict | None = None, tmp_path=None):
    """Build a GuardContext without touching git (pure-guard unit tests)."""
    from pathlib import Path

    from factory_kernel.guards import GuardContext

    return GuardContext(
        step="build",
        commits={},
        diff=diff,
        authorizations=authorizations or {},
        worktree=tmp_path or Path("."),
    )


def _mod(path: str, added=(), removed=()) -> tuple[str, dict]:
    return path, {"status": "M", "added": list(added), "removed": list(removed),
                  "binary": False}


def _add(path: str, added=()) -> tuple[str, dict]:
    return path, {"status": "A", "added": list(added), "removed": [],
                  "binary": False}


def _del(path: str, removed=()) -> tuple[str, dict]:
    return path, {"status": "D", "added": [], "removed": list(removed),
                  "binary": False}


# ----------------------------------------------------------------------
# authorizations.json — strictly validated structure
# ----------------------------------------------------------------------

class TestAuthorizationsSchema:
    def test_valid_document(self, schemas_dir):
        store = SchemaStore(schemas_dir)
        assert store.is_valid("authorizations", {
            "allowed_test_deletions": ["tests/test_app.py"],
            "allowed_dep_changes": ["package.json"],
            "reason": "superseded by a suite rewrite",
            "authorized_by": "owner",
        })

    def test_missing_document_rejected(self, schemas_dir):
        store = SchemaStore(schemas_dir)
        assert not store.is_valid("authorizations", None)
        assert not store.is_valid("authorizations", [])
        assert not store.is_valid("authorizations", "nonsense")

    def test_unknown_keys_rejected(self, schemas_dir):
        store = SchemaStore(schemas_dir)
        # A typo'd authorization key must fail validation, never be read as
        # an (empty) authorization.
        assert not store.is_valid("authorizations", {
            "allow_test_deletions": ["tests/test_app.py"],
        })

    def test_duplicate_entries_rejected(self, schemas_dir):
        store = SchemaStore(schemas_dir)
        assert not store.is_valid("authorizations", {
            "allowed_test_deletions": ["tests/a.py", "tests/a.py"],
        })

    def test_wildcard_entries_never_authorize(self, schemas_dir):
        # Structural strictness: the schema keeps paths opaque, so the guard
        # code is what refuses to ever match a wildcard. A human has to name
        # the exact file they authorize.
        store = SchemaStore(schemas_dir)
        doc = {"allowed_test_deletions": ["tests/**", "tests/*"]}
        assert store.is_valid("authorizations", doc)  # shape is valid…
        from factory_kernel.guards import authorized
        assert authorized(doc, "tests/test_app.py") is False  # …matching is not


# ----------------------------------------------------------------------
# Guard surface / registry policy
# ----------------------------------------------------------------------

class TestRegistry:
    def test_declared_guards_exist(self):
        from factory_kernel.guards import GUARDS

        for gid in ("no_test_deletion", "no_lockfile_surprise", "no_secret_in_diff"):
            assert gid in GUARDS

    def test_unknown_guard_fails_hard(self, tmp_path):
        from factory_kernel.guards import GuardContext, GuardError, run_guards

        ctx = GuardContext(step="build", commits={}, diff={},
                           authorizations={}, worktree=tmp_path)
        with pytest.raises(GuardError):
            run_guards(["no_such_guard"], ctx)

    def test_empty_guard_list_is_clean(self, tmp_path):
        from factory_kernel.guards import GuardContext, run_guards

        ctx = GuardContext(step="build", commits={}, diff={},
                           authorizations={}, worktree=tmp_path)
        assert run_guards([], ctx) == []


# ----------------------------------------------------------------------
# no_test_deletion
# ----------------------------------------------------------------------

class TestNoTestDeletion:
    def test_deleting_a_test_is_flagged(self, tmp_path):
        from factory_kernel.guards import run_guards

        diff = dict([_del("tests/test_app.py", ["def test_a(): ..."])])
        results = run_guards(["no_test_deletion"], _ctx(diff, tmp_path=tmp_path))
        violations = results[0].violations
        assert len(violations) == 1
        assert violations[0]["path"] == "tests/test_app.py"
        assert violations[0]["kind"] == "deleted"

    @pytest.mark.parametrize("path", [
        "test_top.py",
        "src/pkg/test_inner.py",
        "src/pkg/foo_test.py",
        "web/app.test.jsx",
        "web/app.spec.ts",
    ])
    def test_deleting_test_glob_matches(self, tmp_path, path):
        from factory_kernel.guards import run_guards

        diff = dict([_del(path)])
        results = run_guards(["no_test_deletion"], _ctx(diff, tmp_path=tmp_path))
        assert results[0].violations, path

    def test_authorized_deletion_is_clean(self, tmp_path):
        from factory_kernel.guards import run_guards

        auth = {"allowed_test_deletions": ["tests/test_app.py"]}
        diff = dict([_del("tests/test_app.py", ["def test_a(): ..."])])
        results = run_guards(["no_test_deletion"], _ctx(diff, auth, tmp_path))
        assert results[0].violations == []

    def test_modifying_a_test_without_weakening_is_clean(self, tmp_path):
        from factory_kernel.guards import run_guards

        diff = dict([_mod("tests/test_app.py",
                          added=["def test_b(): ..."],
                          removed=["def test_a(): ..."])])
        # Touching/modifying test code is legitimate development work; only
        # deletion is guarded this round (weakening detection is a follow-up).
        results = run_guards(["no_test_deletion"], _ctx(diff, tmp_path=tmp_path))
        assert results[0].violations == []

    def test_deleting_a_non_test_file_is_clean(self, tmp_path):
        from factory_kernel.guards import run_guards

        diff = dict([_del("src/globals.py")])
        results = run_guards(["no_test_deletion"], _ctx(diff, tmp_path=tmp_path))
        assert results[0].violations == []

    def test_authorization_is_exact_path(self, tmp_path):
        from factory_kernel.guards import run_guards

        # Authorizing one test file must not cover another.
        auth = {"allowed_test_deletions": ["tests/test_other.py"]}
        diff = dict([_del("tests/test_app.py")])
        results = run_guards(["no_test_deletion"], _ctx(diff, auth, tmp_path))
        assert len(results[0].violations) == 1
        assert results[0].violations[0]["path"] == "tests/test_app.py"


# ----------------------------------------------------------------------
# no_lockfile_surprise
# ----------------------------------------------------------------------

class TestNoLockfileSurprise:
    def test_manifest_changed_without_lockfile_is_flagged(self, tmp_path):
        from factory_kernel.guards import run_guards

        diff = dict([_mod("package.json", added=["\"lodash\""])])
        results = run_guards(["no_lockfile_surprise"], _ctx(diff, tmp_path=tmp_path))
        kinds = {v["kind"] for v in results[0].violations}
        assert "manifest_without_lockfile" in kinds

    def test_manifest_and_lockfile_changed_is_clean(self, tmp_path):
        from factory_kernel.guards import run_guards

        diff = dict([
            _mod("package.json", added=["\"lodash\""]),
            _mod("package-lock.json", added=["\"lodash\":"]),
        ])
        results = run_guards(["no_lockfile_surprise"], _ctx(diff, tmp_path=tmp_path))
        assert results[0].violations == []

    def test_lockfile_deleted_is_flagged(self, tmp_path):
        from factory_kernel.guards import run_guards

        diff = dict([_del("package-lock.json")])
        results = run_guards(["no_lockfile_surprise"], _ctx(diff, tmp_path=tmp_path))
        violations = results[0].violations
        assert violations and violations[0]["path"] == "package-lock.json"

    def test_lockfile_changed_without_manifest_is_flagged(self, tmp_path):
        from factory_kernel.guards import run_guards

        diff = dict([_mod("package-lock.json", added=["\"lodash\":"])])
        results = run_guards(["no_lockfile_surprise"], _ctx(diff, tmp_path=tmp_path))
        assert results[0].violations

    def test_unrelated_changes_are_clean(self, tmp_path):
        from factory_kernel.guards import run_guards

        diff = dict([_mod("src/app.py", added=["x = 1"]), _add("README.md", ["hi"])])
        results = run_guards(["no_lockfile_surprise"], _ctx(diff, tmp_path=tmp_path))
        assert results[0].violations == []

    def test_authorized_dep_change_is_clean(self, tmp_path):
        from factory_kernel.guards import run_guards

        auth = {"allowed_dep_changes": ["package.json"]}
        diff = dict([_mod("package.json", added=["\"lodash\""])])
        results = run_guards(["no_lockfile_surprise"], _ctx(diff, auth, tmp_path))
        assert results[0].violations == []

    def test_python_pair_covered(self, tmp_path):
        from factory_kernel.guards import run_guards

        diff = dict([_mod("pyproject.toml", added=["httpx"])])
        results = run_guards(["no_lockfile_surprise"], _ctx(diff, tmp_path=tmp_path))
        assert results[0].violations, "python manifests are covered too"


# ----------------------------------------------------------------------
# no_secret_in_diff
# ----------------------------------------------------------------------

class TestNoSecretInDiff:
    @pytest.mark.parametrize("needle", [
        "AKIAABCDEFGHIJKLMNOP",                                  # AWS access key
        "ghp_0123456789abcdef0123456789abcdef01234567",           # GitHub PAT
        "-----BEGIN RSA PRIVATE KEY-----",                        # PEM key block
    ])
    def test_secrets_are_flagged(self, tmp_path, needle):
        from factory_kernel.guards import run_guards

        diff = dict([_add("src/app.py", [f"CONFIG = '{needle}'"])])
        results = run_guards(["no_secret_in_diff"], _ctx(diff, tmp_path=tmp_path))
        violations = results[0].violations
        assert len(violations) == 1, needle
        assert violations[0]["kind"] == "secret"
        assert violations[0]["path"] == "src/app.py"

    @pytest.mark.parametrize("benign", [
        "img: data:image/png;base64," + "QUFB" * 400,
        "sha256: " + "a1b2c3d4" * 8,
        "hash bun2 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    ])
    def test_high_entropy_non_secrets_are_not_flagged(self, tmp_path, benign):
        from factory_kernel.guards import run_guards

        diff = dict([_add("src/app.py", [benign])])
        results = run_guards(["no_secret_in_diff"], _ctx(diff, tmp_path=tmp_path))
        assert results[0].violations == [], benign[:60]

    def test_removed_lines_are_not_scanned(self, tmp_path):
        # Only lines the attempt *adds* can leak new secrets.
        from factory_kernel.guards import run_guards

        diff = dict([_mod(
            "src/app.py",
            removed=["token = 'ghp_0123456789abcdef0123456789abcdef01234567'"])])
        results = run_guards(["no_secret_in_diff"], _ctx(diff, tmp_path=tmp_path))
        assert results[0].violations == []


# ----------------------------------------------------------------------
# Diff extraction (gitrepo.collect_diff) — real git, hermetic
# ----------------------------------------------------------------------

class TestCollectDiff:
    @pytest.fixture
    def wt(self, tmp_path):
        from factory_kernel.gitrepo import init_repo

        worktree = tmp_path / "wt"
        init_repo(worktree, project="t")
        return worktree

    def _write(self, wt, rel: str, text: str):
        path = wt / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_base_diff_is_empty_on_clean_tree(self, wt):
        from factory_kernel.gitrepo import collect_diff, head

        assert collect_diff(wt, head(wt)) == {}

    def test_modified_and_uncommitted(self, wt):
        from factory_kernel.gitrepo import collect_diff, commit_all, head

        base = head(wt)
        self._write(wt, "src/app.py", "x = 1\n")
        commit_all(wt, "seed")
        self._write(wt, "src/app.py", "x = 2\n")  # uncommitted edit
        diff = collect_diff(wt, base)
        entry = diff["src/app.py"]
        assert entry["status"] == "M"
        assert entry["added"] == ["x = 2"]
        assert entry["removed"] == ["x = 1"]
        assert entry["binary"] is False

    def test_untracked_files_count_as_added(self, wt):
        from factory_kernel.gitrepo import collect_diff, head

        base = head(wt)
        self._write(wt, "newfile.py", "print('new')\n")
        diff = collect_diff(wt, base)
        assert diff["newfile.py"]["status"] == "A"
        assert diff["newfile.py"]["added"] == ["print('new')"]

    def test_committed_changes_since_base_count(self, wt):
        from factory_kernel.gitrepo import collect_diff, commit_all, head

        base = head(wt)
        self._write(wt, "src/app.py", "x = 1\n")
        commit_all(wt, "during attempt")
        diff = collect_diff(wt, base)
        assert diff["src/app.py"]["status"] == "A"
        assert diff["src/app.py"]["added"] == ["x = 1"]

    def test_deleted_file(self, wt):
        from factory_kernel.gitrepo import collect_diff, commit_all, head

        self._write(wt, "src/gone.py", "x = 1\n")
        commit_all(wt, "seed")
        base = head(wt)
        (wt / "src" / "gone.py").unlink()
        diff = collect_diff(wt, base)
        assert diff["src/gone.py"]["status"] == "D"

    def test_binary_file_has_no_content(self, wt):
        from factory_kernel.gitrepo import collect_diff, head

        base = head(wt)
        (wt / "blob.bin").write_bytes(bytes(range(256)) * 40 + b"\x00")
        diff = collect_diff(wt, base)
        entry = diff["blob.bin"]
        assert entry["binary"] is True
        assert not entry.get("added")


# ----------------------------------------------------------------------
# Guard verdicts over a real worktree (integration of the two layers)
# ----------------------------------------------------------------------

class TestGuardsOverRealDiff:
    def test_deletion_committed_in_worktree_is_flagged(self, tmp_path):
        """Commit a test file, delete it, collect the diff, run the guard."""
        from factory_kernel.guards import GuardContext, run_guards
        from factory_kernel.gitrepo import collect_diff, commit_all, head, init_repo

        worktree = tmp_path / "wt"
        init_repo(worktree, project="t")
        tests_dir = worktree / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_app.py").write_text("def test_a(): ...\n", encoding="utf-8")
        commit_all(worktree, "seed tests")

        (tests_dir / "test_app.py").unlink()
        ctx = GuardContext(
            step="build", commits={},
            diff=collect_diff(worktree, head(worktree)),
            authorizations={}, worktree=worktree,
        )
        results = run_guards(["no_test_deletion", "no_secret_in_diff"], ctx)
        flagged = results[0].violations
        assert len(flagged) == 1
        assert flagged[0]["path"] == "tests/test_app.py"

    def test_no_violations_when_clean(self, tmp_path):
        from factory_kernel.guards import GuardContext, run_guards
        from factory_kernel.gitrepo import collect_diff, head, init_repo

        worktree = tmp_path / "wt"
        init_repo(worktree, project="t")
        (worktree / "src").mkdir()
        (worktree / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
        base = head(worktree)
        ctx = GuardContext(
            step="build", commits={}, diff=collect_diff(worktree, base),
            authorizations={}, worktree=worktree,
        )
        results = run_guards(["no_test_deletion", "no_lockfile_surprise",
                              "no_secret_in_diff"], ctx)
        assert all(r.violations == [] for r in results)

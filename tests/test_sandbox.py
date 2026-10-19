"""P2.3: sandbox hardening (P2 gap #5, spec §20.2 write boundaries, §3).

Today adapters inherit the kernel's full environment and run from the
adapter directory. This slice pins the contract before the wiring exists:

- ``sandbox.sanitize_env`` — pure filter: an adapter subprocess's env is
  exactly the allowlist intersection of the kernel's env. Case-insensitive
  name matching (Windows), prefix wildcards ending in ``*``, lone ``*`` as
  the explicit keep-everything opt-out. Unlisted secrets
  (``GITHUB_TOKEN``, ``SSH_AUTH_SOCK``, ``HTTP_PROXY``, …) die here.
- ``sandbox.resolve_under`` — pure path containment: paths a player hands
  the kernel resolve *under* the sandbox base or not at all.
- ``SandboxPolicy.from_config`` — parses the ``factory.json`` sandbox
  object; unknown isolation type or an empty allowlist raise
  ``SandboxError`` (fail hard, never "just run it anyway").
- ``factory.schema.json`` — the config the policy reads is schema-defined;
  an invalid sandbox config is caught by the validator, not by luck.

Runtime wiring (SandboxError-free defaults): when ``factory.json`` names no
``env_allowlist`` the kernel's documented default allowlist applies; when
``strict_cwd`` is absent the legacy adapter-directory cwd is kept.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

from factory_kernel.atomic import read_json
from factory_kernel.schemas import SchemaStore
from factory_kernel.adapters import Adapter

# The shipped hardening (factory.json): no third-party secrets get through.
SHIPPED_ALLOWLIST = ["PATH", "SYSTEMDRIVE", "SYSTEMROOT", "HOME", "TEMP",
                     "TMP", "USERPROFILE", "FACTORY_*"]

LEAKY_ENV = {
    "PATH": "/usr/bin",
    "GITHUB_TOKEN": "ghs_secret",
    "SSH_AUTH_SOCK": "/tmp/agent.sock",
    "HTTP_PROXY": "http://proxy:8080",
    "SECRET_API_KEY": "sk_live",
    "AWS_SECRET_ACCESS_KEY": "aws_secret",
    "FACTORY_JOB_ID": "01TEST",
}


def _install_adapter(kernel, name: str):
    src = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / \
        "adapters" / name
    dst = kernel.adapters_dir / name
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy(src / "run.py", dst / "run.py")
    shutil.copy(src / "manifest.json", dst / "manifest.json")


# ----------------------------------------------------------------------
# Schema: the sandbox config the policy reads is well-defined
# ----------------------------------------------------------------------

class TestFactorySchema:
    def test_shipped_factory_json_validates(self, schemas_dir, repo_root):
        cfg = json.loads((repo_root / "factory.json").read_text(encoding="utf-8"))
        SchemaStore(schemas_dir).validate("factory", cfg)

    def test_shipped_sandbox_is_hardened(self, repo_root):
        cfg = json.loads((repo_root / "factory.json").read_text(encoding="utf-8"))
        sandbox = cfg["sandbox"]
        assert sandbox["type"] == "process"
        assert sandbox["strict_cwd"] is True
        assert "FACTORY_*" in sandbox["env_allowlist"]
        # The kernel's reserved prefix must be allowlisted: the engine injects
        # FACTORY_JOB_ID etc. and the probe test below depends on it.
        assert "PATH" in sandbox["env_allowlist"]

    def test_sandbox_key_shape_is_locked(self, schemas_dir, repo_root):
        cfg = json.loads((repo_root / "factory.json").read_text(encoding="utf-8"))
        store = SchemaStore(schemas_dir)

        bad_sandboxes = [
            # provider deltas: unknown vars, wrong types, negative limits
            {**cfg["sandbox"], "type": "container"},          # not implemented
            {**cfg["sandbox"], "env_allowlist": "PATH"},      # not a list
            {**cfg["sandbox"], "env_allowlist": []},          # nothing allowed? no: minItems
            {**cfg["sandbox"], "env_allowlist": [42]},        # non-string entries
            {**cfg["sandbox"], "strict_cwd": "yes"},          # not a boolean
            {**cfg["sandbox"],
             "resource_limits": {"cpu_seconds": -1, "memory_mb": 4096,
                                 "disk_mb": 10240}},
            {**cfg["sandbox"], "unknown_key": True},
        ]
        for sandbox in bad_sandboxes:
            candidate = {**cfg, "sandbox": sandbox}
            assert not store.is_valid("factory", candidate), sandbox

    def test_unnamed_keys_rejected_at_top_level(self, schemas_dir, repo_root):
        cfg = json.loads((repo_root / "factory.json").read_text(encoding="utf-8"))
        store = SchemaStore(schemas_dir)
        assert not store.is_valid("factory", {**cfg, "mystery": 1})
        assert not store.is_valid("factory", {**cfg, "version": "2.0"})


# ----------------------------------------------------------------------
# sanitize_env — the pure env filter (red: wiring lands in Step 3)
# ----------------------------------------------------------------------

class TestSanitizeEnv:
    def test_leaky_env_is_stripped_to_allowlist(self):
        from factory_kernel.sandbox import sanitize_env

        kept = sanitize_env(LEAKY_ENV, SHIPPED_ALLOWLIST)
        # The kernel's reserved attribution (FACTORY_JOB_ID) survives by
        # design; none of the leaked secrets do (declared fix: my Step 2
        # expectation forgot the reserved prefix).
        assert sorted(kept) == ["FACTORY_JOB_ID", "PATH"]
        assert kept["PATH"] == "/usr/bin"

    def test_factory_prefix_kept_by_wildcard(self):
        from factory_kernel.sandbox import sanitize_env

        env = {**LEAKY_ENV, "FACTORY_JOB_ID": "01TEST",
               "FACTORY_STAGE": "build"}
        kept = sanitize_env(env, SHIPPED_ALLOWLIST)
        assert kept["FACTORY_JOB_ID"] == "01TEST"
        assert kept["FACTORY_STAGE"] == "build"

    def test_exact_names_and_wildcards_together(self):
        from factory_kernel.sandbox import sanitize_env

        allowlist = ["TOKEN_SMALL", "FACTORY_*"]
        env = {"TOKEN_SMALL": "ok", "TOKEN_BIG": "no",
               "FACTORY_X": "yes", "FACTORY": "prefix_only_no"}
        kept = sanitize_env(env, allowlist)
        assert kept == {"TOKEN_SMALL": "ok", "FACTORY_X": "yes"}

    def test_case_insensitive_matching(self):
        # Windows env is case-insensitive; determinism beats platform drift.
        from factory_kernel.sandbox import sanitize_env

        kept = sanitize_env({"path": r"C:\bin", "home": r"C:\u"},
                            ["PATH", "HOME"])
        assert kept == {"path": r"C:\bin", "home": r"C:\u"}
        # ...and the allowlist is matched case-insensitively too.
        kept = sanitize_env({"Path": "x"}, ["path"])
        assert kept == {"Path": "x"}

    def test_lone_star_is_explicit_allow_all(self):
        from factory_kernel.sandbox import sanitize_env

        kept = sanitize_env(LEAKY_ENV, ["*"])
        assert kept == LEAKY_ENV

    def test_empty_allowlist_is_default_deny(self):
        from factory_kernel.sandbox import sanitize_env

        assert sanitize_env(LEAKY_ENV, []) == {}

    def test_order_of_original_env_preserved(self):
        from factory_kernel.sandbox import sanitize_env

        kept = sanitize_env({"A": "1", "PATH": "2", "B": "3", "HOME": "4"},
                            ["PATH", "HOME"])
        assert list(kept) == ["PATH", "HOME"]

    def test_prefix_wildcard_case_insensitive(self):
        from factory_kernel.sandbox import sanitize_env

        kept = sanitize_env({"factory_a": "1", "FACTORY_B": "2"},
                            ["factory_*"])
        assert kept == {"factory_a": "1", "FACTORY_B": "2"}

    def test_dangerous_secrets_never_pass_by_lookup_confusion(self):
        # An allowlist name appearing as a *substring* of a secret name
        # keeps the secret out: only exact/prefix rules match.
        from factory_kernel.sandbox import sanitize_env

        kept = sanitize_env({"GITHUB_TOKEN": "x", "PATH_TOKEN": "y"},
                            ["PATH"])
        assert kept == {}


# ----------------------------------------------------------------------
# resolve_under — path containment (red: Step 3)
# ----------------------------------------------------------------------

class TestResolveUnder:
    # `resolve_under` is pure lexical path math, so the base never has to
    # exist — but it must be an absolute path in the *running platform's*
    # syntax. A hard-coded `C:\work\job` is a relative path on POSIX, so the
    # containment rule under test would not be the one that ships.
    BASE = Path(tempfile.gettempdir()) / "factory-sandbox-base" / "job"

    def test_relative_path_resolves_inside_base(self):
        from factory_kernel.sandbox import resolve_under

        base = self.BASE
        assert resolve_under(base, "outputs/a.txt") == base / "outputs" / "a.txt"

    def test_absolute_path_inside_base_is_kept(self):
        from factory_kernel.sandbox import resolve_under

        base = self.BASE
        target = base / "outputs" / "a.txt"
        assert resolve_under(base, str(target)) == target

    def test_relative_escape_is_rejected(self):
        from factory_kernel.sandbox import resolve_under, SandboxError

        with pytest.raises(SandboxError):
            resolve_under(self.BASE, "../outside.txt")

    def test_absolute_path_outside_base_is_rejected(self):
        from factory_kernel.sandbox import resolve_under, SandboxError

        outside = self.BASE.parent / "outside" / "evil.txt"
        with pytest.raises(SandboxError):
            resolve_under(self.BASE, str(outside))

    def test_mixed_dotdot_escape_is_rejected(self):
        from factory_kernel.sandbox import resolve_under, SandboxError

        # `outputs/../../secret` — the separators must be the platform's own,
        # or the ".." segments are part of a filename and never escape.
        escape = os.path.join("outputs", "..", "..", "secret")
        with pytest.raises(SandboxError):
            resolve_under(self.BASE, escape)

    def test_deep_but_contained_path_is_kept(self):
        from factory_kernel.sandbox import resolve_under

        base = self.BASE
        target = base / "a" / "b" / "c" / "d.txt"
        assert resolve_under(base, str(target)) == target


# ----------------------------------------------------------------------
# SandboxPolicy — config parsing (red: Step 3)
# ----------------------------------------------------------------------

class TestSandboxPolicy:
    def test_from_shipped_config(self, repo_root):
        from factory_kernel.sandbox import SandboxPolicy

        cfg = json.loads((repo_root / "factory.json").read_text(encoding="utf-8"))
        policy = SandboxPolicy.from_config(cfg["sandbox"])
        assert policy.env_allowlist == SHIPPED_ALLOWLIST
        assert policy.strict_cwd is True

    def test_absent_keys_use_documented_defaults(self):
        from factory_kernel.sandbox import SandboxPolicy

        policy = SandboxPolicy.from_config({"type": "process"})
        assert policy.strict_cwd is False  # legacy cwd, back-compat default
        assert "PATH" in policy.env_allowlist
        assert "FACTORY_*" in policy.env_allowlist

    def test_unknown_isolation_type_fails_hard(self):
        from factory_kernel.sandbox import SandboxError, SandboxPolicy

        with pytest.raises(SandboxError):
            SandboxPolicy.from_config({"type": "container"})

    def test_empty_allowlist_in_config_fails_hard(self):
        from factory_kernel.sandbox import SandboxError, SandboxPolicy

        with pytest.raises(SandboxError):
            SandboxPolicy.from_config({"type": "process", "env_allowlist": []})

    def test_bad_config_type_fails_hard(self):
        from factory_kernel.sandbox import SandboxError, SandboxPolicy

        with pytest.raises(SandboxError):
            SandboxPolicy.from_config("process")
        with pytest.raises(SandboxError):
            SandboxPolicy.from_config({"type": "process", "strict_cwd": "yes"})


# ----------------------------------------------------------------------
# Adapter subprocess contract (red: Step 3 wiring)
# ----------------------------------------------------------------------

class TestAdapterSubprocess:
    def _adapter(self, tmp_path: Path) -> Adapter:
        adapter_dir = tmp_path / "probe"
        adapter_dir.mkdir()
        (adapter_dir / "manifest.json").write_text(
            json.dumps({"id": "probe", "entrypoint": "run.py"}),
            encoding="utf-8")
        (adapter_dir / "run.py").write_text("print('')", encoding="utf-8")
        return Adapter(adapter_dir)

    def test_explicit_env_replaces_inherited_env(self, tmp_path, monkeypatch):
        from types import SimpleNamespace

        import json as _json

        captured = {}

        def fake_run(cmd, **kwargs):
            captured.update(kwargs)
            # CompletedProcess-like: the adapter parses stdout as NDJSON.
            return SimpleNamespace(
                stdout=_json.dumps({"type": "done"}) + "\n",
                stderr="", returncode=0)

        monkeypatch.setattr("factory_kernel.adapters.subprocess.run", fake_run)
        adapter = self._adapter(tmp_path)
        request = {"attempt_dir": str(tmp_path / "attempt")}

        adapter.run(request, cwd=Path(r"C:\work\job"),
                    env={"PATH": "/usr/bin"})

        assert captured["cwd"] == str(Path(r"C:\work\job"))
        assert captured["env"] == {"PATH": "/usr/bin"}

    def test_defaults_preserve_today_behavior(self, tmp_path, monkeypatch):
        from types import SimpleNamespace

        import json as _json

        captured = {}

        def fake_run(cmd, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                stdout=_json.dumps({"type": "done"}) + "\n",
                stderr="", returncode=0)

        monkeypatch.setattr("factory_kernel.adapters.subprocess.run", fake_run)
        adapter = self._adapter(tmp_path)

        adapter.run({"attempt_dir": str(tmp_path / "attempt")})

        assert captured["cwd"] == str(adapter.dir)
        assert "env" not in captured  # operator-side conformance inherits


# ----------------------------------------------------------------------
# Doctor sandbox-integrity checks (red: Step 4)
# ----------------------------------------------------------------------

class TestDoctorSandbox:
    def test_shipped_tree_reports_clean_sandbox(self, kernel):
        report = kernel.doctor()
        assert report["ok"] is True
        assert not any("factory.json" in e for e in report["errors"]), \
            report["errors"]
        assert not any(w.startswith("Sandbox") for w in report["warnings"]), \
            report["warnings"]

    def test_doctor_flags_invalid_factory_config(self, kernel):
        cfg = read_json(kernel.root / "factory.json")
        cfg["sandbox"]["type"] = "container"  # not implemented
        (kernel.root / "factory.json").write_text(
            json.dumps(cfg, indent=2), encoding="utf-8")

        report = kernel.doctor()
        assert report["ok"] is False
        assert any(e.startswith("factory.json is schema-invalid:")
                   for e in report["errors"]), report["errors"]

    def test_doctor_warns_on_sandbox_footguns(self, kernel):
        cfg = read_json(kernel.root / "factory.json")
        cfg["sandbox"]["env_allowlist"] = ["*"]  # explicit opt-out
        (kernel.root / "factory.json").write_text(
            json.dumps(cfg, indent=2), encoding="utf-8")

        report = kernel.doctor()
        assert report["ok"] is True  # valid config, honest foot-gun warning
        assert any(w.startswith("Sandbox env_allowlist contains '*' ")
                   and "explicit opt-out of secret stripping" in w
                   for w in report["warnings"]), report["warnings"]
        # strict_cwd is still true: no cwd warning on top.
        assert not any("strict_cwd" in w for w in report["warnings"])

    def test_doctor_warns_when_strict_cwd_absent_or_false(self, kernel):
        common = "adapter processes are not confined to the job worktree"

        cfg = read_json(kernel.root / "factory.json")
        cfg["sandbox"].pop("strict_cwd", None)
        (kernel.root / "factory.json").write_text(
            json.dumps(cfg, indent=2), encoding="utf-8")
        report = kernel.doctor()
        assert report["ok"] is True
        assert any("strict_cwd is absent" in w and common in w
                   for w in report["warnings"]), report["warnings"]

        cfg["sandbox"]["strict_cwd"] = False
        (kernel.root / "factory.json").write_text(
            json.dumps(cfg, indent=2), encoding="utf-8")
        report = kernel.doctor()
        assert report["ok"] is True
        assert any("strict_cwd is false" in w and common in w
                   for w in report["warnings"]), report["warnings"]


# ----------------------------------------------------------------------
# Engine integration — the whole path, end-to-end (red: Step 3)
# ----------------------------------------------------------------------

def test_engine_runs_adapters_sandboxed_and_in_the_worktree(kernel, demo_job,
                                                            monkeypatch):
    kernel, job = demo_job
    _install_adapter(kernel, "env-probe")

    # Secrets the kernel just happens to hold in its own env...
    monkeypatch.setenv("GITHUB_TOKEN", "ghs_secret")
    monkeypatch.setenv("SECRET_API_KEY", "sk_live")
    monkeypatch.setenv("SSH_AUTH_SOCK", "/tmp/agent.sock")

    result = kernel.job_execute(job["id"], adapter_id="env-probe")
    assert result["state"] == "awaiting_human"  # ran through to approval

    attempt = (kernel._find_job_dir(job["id"]) / "stages" / "00-understand"
               / "attempt-1")
    usage = json.loads((attempt / "usage.json").read_text(encoding="utf-8"))

    # ...never reach agent code:
    assert usage["seen"]["GITHUB_TOKEN"] is False
    assert usage["seen"]["SECRET_API_KEY"] is False
    assert usage["seen"]["SSH_AUTH_SOCK"] is False
    # ...while the kernel's reserved attribution does:
    assert usage["seen"]["FACTORY_JOB_ID"] is True

    # strict_cwd: the adapter process started in the job worktree.
    assert Path(usage["cwd"]).resolve() == (kernel.work_dir / job["id"]).resolve()

"""Tests for build provenance (``factory provenance verify``).

The parsing/policy functions are pure and tested directly. One integration test
exercises the git wrapper against a throwaway repository (skipped if git is
absent).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from factory_kernel.provenance import (
    DEFAULT_REQUIRED,
    Commit,
    ProvenanceError,
    check_commits,
    load_allowlist,
    parse_trailers,
    read_commits,
    verify,
)

GIT = shutil.which("git")


# --------------------------------------------------------------------------- #
# parse_trailers
# --------------------------------------------------------------------------- #

def test_parse_trailers_reads_final_block():
    msg = "subject\n\nwhy\n\nAI-Tool: opencode\nAI-Model: big-pickle\n"
    assert parse_trailers(msg) == {"AI-Tool": "opencode", "AI-Model": "big-pickle"}


def test_parse_trailers_none_when_absent():
    assert parse_trailers("subject\n\njust a body\n") == {}


def test_parse_trailers_ignores_body_lines_with_colons():
    msg = "subject\n\nnote: this is body\n\nAI-Tool: opencode\n"
    assert parse_trailers(msg) == {"AI-Tool": "opencode"}


def test_parse_trailers_value_may_contain_colon():
    msg = "subject\n\nAI-Tool: opencode\nAI-Session: ses:1234\n"
    assert parse_trailers(msg) == {"AI-Tool": "opencode", "AI-Session": "ses:1234"}


def test_parse_trailers_tolerates_trailing_blank_lines():
    msg = "subject\n\nAI-Tool: x\nAI-Model: y\n\n\n"
    assert parse_trailers(msg) == {"AI-Tool": "x", "AI-Model": "y"}


def test_parse_trailers_handles_crlf():
    msg = "subject\r\n\r\nAI-Tool: x\r\nAI-Model: y\r\n"
    assert parse_trailers(msg) == {"AI-Tool": "x", "AI-Model": "y"}


# --------------------------------------------------------------------------- #
# check_commits
# --------------------------------------------------------------------------- #

def _c(sha: str, subject: str = "subject", body: str = "") -> Commit:
    return Commit(sha=sha, subject=subject, message=f"{subject}\n\n{body}".rstrip() + "\n")


def test_check_clean_history():
    commits = [
        Commit("a" * 40, "ok", "subject\n\nAI-Tool: opencode\nAI-Model: big-pickle\n"),
    ]
    assert check_commits(commits) == []


def test_check_reports_missing_each_key():
    commits = [Commit("b" * 40, "bad", "subject\n\nonly body\n")]
    violations = check_commits(commits)
    assert len(violations) == 1
    assert violations[0].missing == list(DEFAULT_REQUIRED)
    assert violations[0].sha == "b" * 40


def test_check_is_case_insensitive_for_keys():
    commits = [Commit("c" * 40, "ok", "s\n\nai-tool: opencode\nAI-MODEL: big-pickle\n")]
    assert check_commits(commits) == []


def test_check_empty_value_counts_as_missing():
    commits = [Commit("d" * 40, "bad", "s\n\nAI-Tool:   \nAI-Model: big-pickle\n")]
    violations = check_commits(commits)
    assert violations and violations[0].missing == ["AI-Tool"]


@pytest.mark.parametrize("subject", ["Merge branch 'x'", "Revert \"y\"", "fixup! z", "squash! w"])
def test_check_skips_meta_commits(subject):
    commits = [Commit("e" * 40, subject, subject + "\n")]
    assert check_commits(commits) == []


def test_check_allow_exact_and_abbreviated():
    sha = "f" * 40
    commits = [Commit(sha, "old", "no trailers\n")]
    assert check_commits(commits, allow=[sha]) == []
    assert check_commits(commits, allow=[sha[:10]]) == []


def test_check_allow_all_before_grandfathers_older_only():
    new = Commit("1" * 40, "new", "no trailers\n")
    baseline = Commit("2" * 40, "old", "no trailers\n")
    older = Commit("3" * 40, "older", "no trailers\n")
    # newest-first order
    violations = check_commits([new, baseline, older], allow_all_before="2" * 40)
    assert [v.sha for v in violations] == ["1" * 40]


def test_check_custom_required():
    commits = [Commit("a" * 40, "s", "s\n\nAI-Tool: x\n")]
    violations = check_commits(commits, required=["AI-Tool", "Ticket"])
    assert violations[0].missing == ["Ticket"]


# --------------------------------------------------------------------------- #
# load_allowlist
# --------------------------------------------------------------------------- #

def test_load_allowlist_comments_and_blanks(tmp_path: Path):
    p = tmp_path / ".provenance-allow"
    p.write_text(
        "# a comment\n\nABCDEF123  # inline\n  deadbeef  \n", encoding="utf-8"
    )
    assert load_allowlist(p) == {"abcdef123", "deadbeef"}


def test_load_allowlist_missing_file_is_empty(tmp_path: Path):
    assert load_allowlist(tmp_path / "nope") == set()


# --------------------------------------------------------------------------- #
# git integration
# --------------------------------------------------------------------------- #

pytestmark = pytest.mark.skipif(GIT is None, reason="git not installed")


def _env(tmp_path: Path) -> dict:
    return {
        **os.environ,
        "GIT_CONFIG_GLOBAL": str(tmp_path / "no-global-config"),
        "GIT_CONFIG_SYSTEM": str(tmp_path / "no-system-config"),
        "GIT_AUTHOR_NAME": "Tester",
        "GIT_AUTHOR_EMAIL": "tester@example.com",
        "GIT_COMMITTER_NAME": "Tester",
        "GIT_COMMITTER_EMAIL": "tester@example.com",
    }


def _git(cwd: Path, *args: str, env: dict) -> str:
    proc = subprocess.run(
        [GIT, *args], cwd=str(cwd), capture_output=True, text=True, env=env, check=True
    )
    return proc.stdout.strip()


def _commit(repo: Path, message: str, env: dict) -> str:
    (repo / "f.txt").write_text(message + os.urandom(4).hex(), encoding="utf-8")
    _git(repo, "add", "-A", env=env)
    _git(repo, "commit", "-q", "-m", message, env=env)
    return _git(repo, "rev-parse", "HEAD", env=env)


def test_read_commits_newest_first(tmp_path: Path):
    env = _env(tmp_path)
    _git(tmp_path, "init", "-q", "-b", "main", env=env)
    first = _commit(tmp_path, "first", env=env)
    second = _commit(tmp_path, "second", env=env)

    commits = read_commits(tmp_path)
    assert [c.sha for c in commits] == [second, first]
    assert commits[0].subject == "second"


def test_verify_end_to_end(tmp_path: Path):
    env = _env(tmp_path)
    _git(tmp_path, "init", "-q", "-b", "main", env=env)
    _commit(tmp_path, "good\n\nAI-Tool: opencode\nAI-Model: big-pickle", env=env)
    bad_sha = _commit(tmp_path, "bad commit with no trailers", env=env)

    report = verify(tmp_path)
    assert report["ok"] is False
    assert report["checked"] == 2
    assert [v["sha"] for v in report["violations"]] == [bad_sha]

    # Grandfather the bad commit -> clean.
    report2 = verify(tmp_path, allow=[bad_sha])
    assert report2["ok"] is True


def test_verify_uses_allowlist_file(tmp_path: Path):
    env = _env(tmp_path)
    _git(tmp_path, "init", "-q", "-b", "main", env=env)
    bad_sha = _commit(tmp_path, "no trailers", env=env)

    allow = tmp_path / ".provenance-allow"
    allow.write_text(f"{bad_sha}\n", encoding="utf-8")

    report = verify(tmp_path, allowlist_path=allow)
    assert report["ok"] is True
    assert report["allowlist_size"] == 1


def test_read_commits_raises_without_repo(tmp_path: Path):
    with pytest.raises(ProvenanceError):
        read_commits(tmp_path)

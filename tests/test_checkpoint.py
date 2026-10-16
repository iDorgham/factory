"""Tests for content-addressed checkpoints (spec §5.1, §9; P1 workstream 1/6)."""
from __future__ import annotations

from factory_kernel.checkpoint import output_roots, result_hash, tree_hash


def test_tree_hash_deterministic_and_sensitive(tmp_path):
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    h1 = tree_hash(tmp_path)
    assert h1 == tree_hash(tmp_path)

    (tmp_path / "b.txt").write_text("y", encoding="utf-8")
    h2 = tree_hash(tmp_path)
    assert h2 != h1

    (tmp_path / "a.txt").write_text("changed", encoding="utf-8")
    assert tree_hash(tmp_path) != h2


def test_tree_hash_ignores_cache_dirs(tmp_path):
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    before = tree_hash(tmp_path)
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "a.pyc").write_bytes(b"\x00\x01")
    assert tree_hash(tmp_path) == before


def test_tree_hash_missing_root_is_empty(tmp_path):
    assert tree_hash(tmp_path / "nope") == tree_hash(tmp_path / "also-nope")


def test_result_hash_tracks_outputs(tmp_path):
    job_dir = tmp_path / "job"
    outputs = job_dir / "stages" / "00-x" / "attempt-1" / "outputs"
    outputs.mkdir(parents=True)
    (outputs / "out.md").write_text("one", encoding="utf-8")
    worktree = tmp_path / "wt"
    worktree.mkdir()

    a = result_hash(job_dir, worktree)
    assert output_roots(job_dir) == [outputs]
    (outputs / "out.md").write_text("two", encoding="utf-8")
    assert result_hash(job_dir, worktree) != a


def test_result_hash_tracks_worktree(tmp_path):
    job_dir = tmp_path / "job"
    (job_dir / "stages").mkdir(parents=True)
    worktree = tmp_path / "wt"
    worktree.mkdir()
    (worktree / "code.py").write_text("print(1)", encoding="utf-8")
    a = result_hash(job_dir, worktree)
    (worktree / "code.py").write_text("print(2)", encoding="utf-8")
    assert result_hash(job_dir, worktree) != a

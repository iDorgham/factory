"""Atomic write / JSON helper tests (spec §5.2)."""
from __future__ import annotations

import os

from factory_kernel.atomic import (
    append_jsonl,
    atomic_write,
    atomic_write_json,
    read_json,
    read_jsonl,
)


def test_atomic_write_json_roundtrip(tmp_path):
    path = tmp_path / "sub" / "x.json"
    atomic_write_json(path, {"b": 2, "a": 1})
    assert read_json(path) == {"a": 1, "b": 2}


def test_atomic_write_creates_parent_dirs(tmp_path):
    path = tmp_path / "a" / "b" / "c.json"
    atomic_write_json(path, {"ok": True})
    assert path.exists()


def test_atomic_write_overwrites_existing(tmp_path):
    """os.replace must overwrite an existing destination (Windows-safe)."""
    path = tmp_path / "x.json"
    atomic_write_json(path, {"v": 1})
    atomic_write_json(path, {"v": 2})
    assert read_json(path) == {"v": 2}


def test_atomic_write_leaves_no_temp_files(tmp_path):
    path = tmp_path / "x.json"
    atomic_write_json(path, {"v": 1})
    atomic_write(path, "text")
    leftovers = [f for f in os.listdir(tmp_path) if f.startswith(".tmp_")]
    assert leftovers == []


def test_atomic_write_bytes(tmp_path):
    path = tmp_path / "x.bin"
    atomic_write(path, b"\x00\x01\x02")
    assert path.read_bytes() == b"\x00\x01\x02"


def test_read_json_missing_returns_default(tmp_path):
    assert read_json(tmp_path / "nope.json") is None
    assert read_json(tmp_path / "nope.json", {}) == {}


def test_append_jsonl_appends_lines(tmp_path):
    path = tmp_path / "log.jsonl"
    append_jsonl(path, {"i": 1})
    append_jsonl(path, {"i": 2})
    assert read_jsonl(path) == [{"i": 1}, {"i": 2}]


def test_read_jsonl_missing_returns_empty(tmp_path):
    assert read_jsonl(tmp_path / "nope.jsonl") == []

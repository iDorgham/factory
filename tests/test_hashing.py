"""Hashing / event-chain tests (spec §5.2: prev = hash of previous event)."""
from __future__ import annotations

from factory_kernel.hashing import content_hash, event_hash, sha256_hex


def test_sha256_hex_deterministic():
    assert sha256_hex("hello") == sha256_hex(b"hello")
    assert len(sha256_hex("hello")) == 64


def test_event_hash_changes_with_content():
    e1 = {"id": "A", "type": "job.created", "data": {"n": 1}}
    e2 = {"id": "A", "type": "job.created", "data": {"n": 2}}
    assert event_hash(e1) != event_hash(e2)


def test_event_hash_is_key_order_independent():
    e1 = {"a": 1, "b": 2}
    e2 = {"b": 2, "a": 1}
    assert event_hash(e1) == event_hash(e2)


def test_content_hash_bytes_and_file(tmp_path):
    path = tmp_path / "f.bin"
    path.write_bytes(b"payload")
    assert content_hash(b"payload") == content_hash(str(path))

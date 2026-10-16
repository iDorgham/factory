"""ULID tests (spec §5.2: id is a ULID)."""
from __future__ import annotations

from factory_kernel.ulid import ALPHABET, is_ulid, new_ulid


def test_ulid_shape():
    u = new_ulid()
    assert len(u) == 26
    assert all(c in ALPHABET for c in u)


def test_ulid_is_recognised():
    assert is_ulid(new_ulid())
    assert not is_ulid("short")
    assert not is_ulid("I" * 26)  # I is not in the alphabet


def test_ulid_uniqueness():
    ids = {new_ulid() for _ in range(1000)}
    assert len(ids) == 1000


def test_ulid_time_ordering():
    a = new_ulid(timestamp_ms=1_000_000)
    b = new_ulid(timestamp_ms=2_000_000)
    assert a < b


def test_ulid_encodes_timestamp_prefix():
    # Same millisecond timestamp -> same 10-char prefix.
    a = new_ulid(timestamp_ms=1_700_000_000_000)
    b = new_ulid(timestamp_ms=1_700_000_000_000)
    assert a[:10] == b[:10]

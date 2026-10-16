"""Lease + fencing token tests (spec §5.2)."""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

import pytest

from factory_kernel.atomic import atomic_write_json, read_json
from factory_kernel.lease import LeaseError, LeaseManager


def _make(job_dir, owner="alice", ttl=120):
    job_dir.mkdir(parents=True, exist_ok=True)
    return LeaseManager(job_dir, owner, ttl_seconds=ttl)


def _expire(manager):
    lease = read_json(manager.lock_path)
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    lease["expires"] = past
    atomic_write_json(manager.lock_path, lease)


def test_first_acquire_token_is_one(tmp_path):
    m = _make(tmp_path)
    assert m.acquire() == 1
    assert m.current_token() == 1
    assert m.is_held_by("alice")


def test_second_owner_blocked_while_held(tmp_path):
    _make(tmp_path, "alice").acquire()
    with pytest.raises(LeaseError):
        _make(tmp_path, "bob").acquire()


def test_same_owner_reacquire_increments_token(tmp_path):
    m = _make(tmp_path, "alice")
    assert m.acquire() == 1
    assert m.acquire() == 2


def test_renew_requires_current_token(tmp_path):
    m = _make(tmp_path, "alice")
    token = m.acquire()
    assert m.renew(token) == token
    with pytest.raises(LeaseError):
        m.renew(token + 99)


def test_renew_by_other_owner_rejected(tmp_path):
    _make(tmp_path, "alice").acquire()
    with pytest.raises(LeaseError):
        _make(tmp_path, "bob").renew(1)


def test_release_requires_matching_token(tmp_path):
    m = _make(tmp_path, "alice")
    token = m.acquire()
    with pytest.raises(LeaseError):
        m.release(token + 1)
    m.release(token)
    assert m.current_token() is None


def test_expired_lease_can_be_taken(tmp_path):
    alice = _make(tmp_path, "alice")
    alice.acquire()
    _expire(alice)
    assert alice.current_token() is None
    bob = _make(tmp_path, "bob")
    assert bob.acquire() == 2  # fencing token keeps marching forward


def test_fencing_token_is_monotonic(tmp_path):
    m = _make(tmp_path, "alice")
    tokens = [m.acquire() for _ in range(5)]
    assert tokens == [1, 2, 3, 4, 5]


# -- exclusive-create guard (spec §5.2) -------------------------------------


def test_guard_removed_after_acquire(tmp_path):
    m = _make(tmp_path, "alice")
    m.acquire()
    assert not (tmp_path / ".lease.guard").exists()


def test_guard_removed_after_release(tmp_path):
    m = _make(tmp_path, "alice")
    token = m.acquire()
    m.release(token)
    assert not (tmp_path / ".lease.guard").exists()


def test_stale_guard_is_stolen(tmp_path):
    m = _make(tmp_path, "alice")
    guard = tmp_path / ".lease.guard"
    guard.write_text("left by a crashed process", encoding="utf-8")
    old = time.time() - 3600
    os.utime(guard, (old, old))
    assert m.acquire() == 1


def test_fresh_guard_times_out(tmp_path):
    m = _make(tmp_path, "alice")
    (tmp_path / ".lease.guard").write_text("held", encoding="utf-8")
    with pytest.raises(LeaseError):
        m._guard(timeout=0.05)

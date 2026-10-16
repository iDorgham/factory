"""Lease locks with fencing tokens (spec §5.2).

Cross-process safety does not rely on advisory flock: every mutation of the
lease file is bracketed by an **exclusive-create guard file** (``O_CREAT|O_EXCL``),
which is the portable "create-exclusive file semantics" the specification calls
for. A guard left behind by a crashed process is stolen once it is stale.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from .atomic import atomic_write_json, read_json

# How long to wait for the guard before giving up, and how old a guard must be
# before we assume its owner crashed and steal it.
GUARD_TIMEOUT_SECONDS = 5.0
GUARD_STALE_SECONDS = 10.0


class LeaseError(Exception):
    pass


class LeaseManager:
    """Per-job lease with heartbeat and monotonic fencing token."""

    def __init__(self, job_dir: Path, owner: str, ttl_seconds: int = 120):
        self.job_dir = Path(job_dir)
        self.owner = owner
        self.ttl = ttl_seconds
        self.lock_path = self.job_dir / ".lease.json"
        self.guard_path = self.job_dir / ".lease.guard"

    # -- guard (create-exclusive critical section) --------------------------

    def _guard(self, timeout: float = GUARD_TIMEOUT_SECONDS) -> None:
        """Acquire the exclusive-create guard, or raise LeaseError on timeout."""
        self.job_dir.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + timeout
        while True:
            try:
                fd = os.open(str(self.guard_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                return
            except FileExistsError:
                # Steal a stale guard left by a crashed writer.
                try:
                    age = time.time() - self.guard_path.stat().st_mtime
                    if age > GUARD_STALE_SECONDS:
                        self.guard_path.unlink()
                        continue
                except OSError:
                    pass
                if time.monotonic() >= deadline:
                    raise LeaseError("Timed out acquiring lease guard")
                time.sleep(0.02)

    def _unguard(self) -> None:
        try:
            self.guard_path.unlink()
        except OSError:
            pass

    # -- helpers ------------------------------------------------------------

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _iso(self, dt: datetime) -> str:
        return dt.isoformat().replace("+00:00", "Z")

    # -- lease operations ---------------------------------------------------

    def acquire(self) -> int:
        """Acquire or renew lease. Returns the fencing token."""
        self._guard()
        try:
            current = read_json(self.lock_path)
            now = self._now()

            if current:
                expires = datetime.fromisoformat(current["expires"].replace("Z", "+00:00"))
                if expires > now and current["owner"] != self.owner:
                    raise LeaseError(
                        f"Job is locked by {current['owner']} until {current['expires']}"
                    )
                # Same owner or expired → we can take it
                token = current.get("token", 0) + 1
            else:
                token = 1

            lease = {
                "owner": self.owner,
                "token": token,
                "expires": self._iso(now + timedelta(seconds=self.ttl)),
                "acquired_at": self._iso(now),
            }
            atomic_write_json(self.lock_path, lease)
            return token
        finally:
            self._unguard()

    def renew(self, expected_token: int) -> int:
        """Renew lease. Must supply the current fencing token."""
        self._guard()
        try:
            current = read_json(self.lock_path)
            if not current:
                raise LeaseError("No lease exists")
            if current["owner"] != self.owner:
                raise LeaseError("Not the lease owner")
            if current["token"] != expected_token:
                raise LeaseError(
                    f"Stale fencing token: expected {expected_token}, have {current['token']}"
                )
            now = self._now()
            current["expires"] = self._iso(now + timedelta(seconds=self.ttl))
            atomic_write_json(self.lock_path, current)
            return expected_token
        finally:
            self._unguard()

    def release(self, expected_token: int) -> None:
        self._guard()
        try:
            current = read_json(self.lock_path)
            if not current:
                return
            if current["owner"] != self.owner or current["token"] != expected_token:
                raise LeaseError("Cannot release: ownership or token mismatch")
            if self.lock_path.exists():
                self.lock_path.unlink()
        finally:
            self._unguard()

    def current_token(self) -> Optional[int]:
        current = read_json(self.lock_path)
        if not current:
            return None
        expires = datetime.fromisoformat(current["expires"].replace("Z", "+00:00"))
        if expires < self._now():
            return None
        return current["token"]

    def is_held_by(self, owner: str) -> bool:
        current = read_json(self.lock_path)
        if not current:
            return False
        expires = datetime.fromisoformat(current["expires"].replace("Z", "+00:00"))
        return current["owner"] == owner and expires > self._now()

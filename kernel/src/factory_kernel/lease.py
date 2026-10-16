"""Lease locks with fencing tokens."""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from .atomic import atomic_write_json, read_json


class LeaseError(Exception):
    pass


class LeaseManager:
    """Per-job lease with heartbeat and monotonic fencing token."""

    def __init__(self, job_dir: Path, owner: str, ttl_seconds: int = 120):
        self.job_dir = Path(job_dir)
        self.owner = owner
        self.ttl = ttl_seconds
        self.lock_path = self.job_dir / ".lease.json"

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _iso(self, dt: datetime) -> str:
        return dt.isoformat().replace("+00:00", "Z")

    def acquire(self) -> int:
        """Acquire or renew lease. Returns the fencing token."""
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

    def renew(self, expected_token: int) -> int:
        """Renew lease. Must supply the current fencing token."""
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

    def release(self, expected_token: int) -> None:
        current = read_json(self.lock_path)
        if not current:
            return
        if current["owner"] != self.owner or current["token"] != expected_token:
            raise LeaseError("Cannot release: ownership or token mismatch")
        if self.lock_path.exists():
            self.lock_path.unlink()

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

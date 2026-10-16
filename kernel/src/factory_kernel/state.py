"""Job state machine and event fold."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .atomic import atomic_write_json, append_jsonl, read_json, read_jsonl
from .hashing import event_hash
from .schemas import SchemaError, SchemaStore
from .ulid import new_ulid


VALID_TRANSITIONS = {
    "pending": {"running", "cancelled"},
    "running": {"awaiting_human", "blocked", "stalled", "paused", "failed", "completed", "cancelled"},
    "awaiting_human": {"running", "cancelled", "blocked"},
    "blocked": {"running", "cancelled"},
    "stalled": {"running", "awaiting_human", "failed", "cancelled"},
    "paused": {"running", "cancelled"},
    "failed": {"running", "cancelled"},
    "completed": {"archived"},
    "cancelled": {"archived"},
    "superseded": {"archived"},
    "archived": set(),
}


class StateError(Exception):
    pass


def verify_chain(events: list[dict]) -> list[str]:
    """Verify the ``prev`` hash links between consecutive events.

    Returns a list of human-readable problems; an empty list means the chain is
    intact. Detects tampering and missing/out-of-order events.
    """
    problems: list[str] = []
    prev: Optional[str] = None
    for i, ev in enumerate(events):
        if ev.get("prev") != prev:
            problems.append(
                f"event {i} ({ev.get('id', '?')}): prev={ev.get('prev')!r} "
                f"expected {prev!r}"
            )
        try:
            prev = event_hash(ev)
        except (TypeError, ValueError) as e:  # malformed event
            problems.append(f"event {i} ({ev.get('id', '?')}): not hashable: {e}")
            prev = None
    return problems


class JobState:
    """Manages the event log and derived job.json for a single job."""

    def __init__(self, job_dir: Path, schemas_dir: Optional[Path | str] = None):
        self.job_dir = Path(job_dir)
        self.events_path = self.job_dir / "events.jsonl"
        self.job_path = self.job_dir / "job.json"
        self.schemas = SchemaStore(schemas_dir) if schemas_dir else None

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def load_events(self) -> list[dict]:
        return read_jsonl(self.events_path)

    def fold(self, events: Optional[list[dict]] = None) -> dict:
        """Reconstruct current job snapshot from the event log."""
        if events is None:
            events = self.load_events()
        if not events:
            raise StateError("No events; job does not exist")

        # Start from the first event (job.created)
        first = events[0]
        if first["type"] != "job.created":
            raise StateError("First event must be job.created")

        snap = {
            "id": first["job"],
            "project": first["data"]["project"],
            "state": "pending",
            "created_at": first["ts"],
            "updated_at": first["ts"],
            "brief": first["data"].get("brief", ""),
            "profile": first["data"].get("profile", "lite"),
            "mode": first["data"].get("mode", "solo"),
            "epic": first["data"].get("epic"),
            "current_stage": None,
            "current_attempt": None,
            "risk_score": 0.0,
            "cost_usd": 0.0,
            "tokens_used": 0,
            "lease": None,
            "checkpoints": [],
            "last_event_id": first["id"],
        }

        for ev in events[1:]:
            snap["updated_at"] = ev["ts"]
            snap["last_event_id"] = ev["id"]
            t = ev["type"]
            d = ev.get("data", {})

            if t == "job.state_changed":
                snap["state"] = d["to"]
            elif t == "stage.started":
                snap["current_stage"] = d["stage"]
                snap["current_attempt"] = 0
            elif t == "stage.attempt_started":
                snap["current_attempt"] = d["attempt"]
                snap["state"] = "running"
            elif t == "stage.accepted":
                snap["current_stage"] = d.get("next_stage")
            elif t == "checkpoint.created":
                snap["checkpoints"].append({
                    "stage": d["stage"],
                    "attempt": d["attempt"],
                    "sha": d["sha"],
                    "ts": ev["ts"],
                })
            elif t == "lease.acquired" or t == "lease.renewed":
                snap["lease"] = {
                    "owner": d["owner"],
                    "token": d["token"],
                    "expires": d["expires"],
                }
            elif t == "lease.released":
                snap["lease"] = None
            elif t in ("job.completed", "job.failed", "job.cancelled"):
                snap["state"] = t.split(".")[1]
            elif t == "job.archived":
                snap["state"] = "archived"
            elif t == "budget.soft_exceeded" or t == "budget.hard_exceeded":
                pass  # informational
            # cost aggregation could be added here from usage events

        return snap

    def verify(self) -> list[str]:
        """Verify the event log's schema + hash chain. Empty list means clean."""
        events = self.load_events()
        problems = verify_chain(events)
        if self.schemas:
            for i, ev in enumerate(events):
                try:
                    self.schemas.validate("event", ev)
                except SchemaError as e:
                    problems.append(f"event {i}: {e}")
        return problems

    def write_snapshot(self, snap: dict) -> None:
        if self.schemas:
            self.schemas.validate("job", snap)
        atomic_write_json(self.job_path, snap)

    def append_event(
        self,
        event_type: str,
        actor: str,
        fence: int,
        data: dict,
        job_id: Optional[str] = None,
    ) -> dict:
        """Append a validated event and refresh the snapshot."""
        events = self.load_events()
        prev_hash = None
        if events:
            prev_hash = event_hash(events[-1])
            job_id = job_id or events[-1]["job"]
        else:
            if not job_id:
                raise StateError("job_id required for first event")

        event = {
            "id": new_ulid(),
            "ts": self._now(),
            "job": job_id,
            "type": event_type,
            "actor": actor,
            "fence": fence,
            "data": data,
            "prev": prev_hash,
        }
        if self.schemas:
            self.schemas.validate("event", event)
        append_jsonl(self.events_path, event)

        # Re-fold and write snapshot
        all_events = events + [event]
        snap = self.fold(all_events)
        self.write_snapshot(snap)
        return event

    def transition(self, to_state: str, actor: str, fence: int, reason: str = "") -> dict:
        """Perform a legal state transition."""
        snap = self.fold()
        from_state = snap["state"]
        allowed = VALID_TRANSITIONS.get(from_state, set())
        if to_state not in allowed:
            raise StateError(f"Illegal transition: {from_state} → {to_state}")
        return self.append_event(
            "job.state_changed",
            actor=actor,
            fence=fence,
            data={"from": from_state, "to": to_state, "reason": reason},
            job_id=snap["id"],
        )

    def create_job(
        self,
        job_id: str,
        project: str,
        brief: str,
        profile: str = "lite",
        mode: str = "solo",
        epic: Optional[str] = None,
        actor: str = "kernel",
    ) -> dict:
        """Create the initial job.created event and snapshot."""
        if self.events_path.exists():
            raise StateError(f"Job already exists at {self.job_dir}")
        self.job_dir.mkdir(parents=True, exist_ok=True)
        event = self.append_event(
            "job.created",
            actor=actor,
            fence=0,
            data={
                "project": project,
                "brief": brief,
                "profile": profile,
                "mode": mode,
                "epic": epic,
            },
            job_id=job_id,
        )
        return event

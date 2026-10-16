"""Executable audit of the job state machine against spec §7.

The kernel's transition table must match the specification exactly, and the
live machine must accept precisely the legal edges and reject the rest.
"""
from __future__ import annotations

from collections import deque

import pytest

from factory_kernel.state import VALID_TRANSITIONS, JobState, StateError
from factory_kernel.ulid import new_ulid

# The transition table transcribed directly from spec §7.
SPEC_LEGAL: dict[str, set[str]] = {
    "pending": {"running", "cancelled"},
    "running": {
        "awaiting_human",
        "blocked",
        "stalled",
        "paused",
        "failed",
        "completed",
        "cancelled",
    },
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

ALL_STATES = sorted(SPEC_LEGAL)


def _path_to(target: str) -> list[str] | None:
    """Shortest legal transition path from 'pending' to ``target``."""
    if target == "pending":
        return []
    queue: deque[tuple[str, list[str]]] = deque([("pending", [])])
    seen = {"pending"}
    while queue:
        node, path = queue.popleft()
        for nxt in sorted(SPEC_LEGAL[node]):
            if nxt in seen:
                continue
            if nxt == target:
                return path + [nxt]
            seen.add(nxt)
            queue.append((nxt, path + [nxt]))
    return None


def _drive(tmp_path, schemas_dir, name: str, path: list[str]) -> JobState:
    state = JobState(tmp_path / name, schemas_dir=schemas_dir)
    state.create_job(job_id=new_ulid(), project="demo", brief="x")
    for step in path:
        state.transition(step, actor="t", fence=0)
    return state


def test_table_matches_spec_exactly():
    normalised = {k: set(v) for k, v in VALID_TRANSITIONS.items()}
    assert normalised == SPEC_LEGAL


def test_all_states_present():
    assert set(VALID_TRANSITIONS) == set(SPEC_LEGAL)


def test_terminal_states_are_closed():
    for state in ("archived",):
        assert VALID_TRANSITIONS[state] == set()


@pytest.mark.parametrize("target", ALL_STATES)
def test_live_legal_edges_accepted(tmp_path, schemas_dir, target):
    path = _path_to(target)
    if path is None:
        pytest.skip(f"{target} is unreachable from pending")
    for i, to in enumerate(sorted(SPEC_LEGAL[target])):
        state = _drive(tmp_path, schemas_dir, f"ok-{target}-{i}", path)
        assert state.fold()["state"] == target
        state.transition(to, actor="t", fence=0)
        assert state.fold()["state"] == to


@pytest.mark.parametrize("target", ALL_STATES)
def test_live_illegal_edges_rejected(tmp_path, schemas_dir, target):
    path = _path_to(target)
    if path is None:
        pytest.skip(f"{target} is unreachable from pending")
    illegal = set(ALL_STATES) - SPEC_LEGAL[target]
    for i, to in enumerate(sorted(illegal)):
        state = _drive(tmp_path, schemas_dir, f"bad-{target}-{i}", path)
        with pytest.raises(StateError):
            state.transition(to, actor="t", fence=0)


def test_superseded_is_unreachable_but_non_terminal():
    assert _path_to("superseded") is None
    assert VALID_TRANSITIONS["superseded"] == {"archived"}

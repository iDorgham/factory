"""Job state machine + event fold tests (spec §5.2, §7)."""
from __future__ import annotations

import pytest

from factory_kernel.atomic import atomic_write_json, read_json, read_jsonl
from factory_kernel.schemas import SchemaError
from factory_kernel.state import JobState, StateError, verify_chain
from factory_kernel.ulid import new_ulid


def _state(tmp_path, schemas_dir):
    return JobState(tmp_path / "job", schemas_dir=schemas_dir)


def test_create_job_writes_event_and_snapshot(tmp_path, schemas_dir):
    s = _state(tmp_path, schemas_dir)
    jid = new_ulid()
    s.create_job(job_id=jid, project="demo", brief="hi")
    events = read_jsonl(s.events_path)
    assert len(events) == 1
    assert events[0]["type"] == "job.created"
    assert events[0]["prev"] is None
    snap = read_json(s.job_path)
    assert snap["id"] == jid
    assert snap["state"] == "pending"
    assert snap["project"] == "demo"


def test_create_job_twice_rejected(tmp_path, schemas_dir):
    s = _state(tmp_path, schemas_dir)
    s.create_job(job_id=new_ulid(), project="demo", brief="hi")
    with pytest.raises(StateError):
        s.create_job(job_id=new_ulid(), project="demo", brief="again")


def test_fold_requires_job_created_first(tmp_path, schemas_dir):
    s = _state(tmp_path, schemas_dir)
    s.job_dir.mkdir(parents=True)
    s.events_path.write_text('{"id":"x","type":"other"}\n', encoding="utf-8")
    with pytest.raises(StateError):
        s.fold()


def test_illegal_transition_rejected(tmp_path, schemas_dir):
    s = _state(tmp_path, schemas_dir)
    s.create_job(job_id=new_ulid(), project="demo", brief="hi")
    with pytest.raises(StateError):
        s.transition("completed", actor="t", fence=0)


def test_legal_transition_updates_snapshot(tmp_path, schemas_dir):
    s = _state(tmp_path, schemas_dir)
    s.create_job(job_id=new_ulid(), project="demo", brief="hi")
    s.transition("running", actor="t", fence=0)
    assert s.fold()["state"] == "running"
    assert read_json(s.job_path)["state"] == "running"


def test_full_lifecycle(tmp_path, schemas_dir):
    s = _state(tmp_path, schemas_dir)
    s.create_job(job_id=new_ulid(), project="demo", brief="hi")
    for to in ("running", "completed", "archived"):
        s.transition(to, actor="t", fence=0)
    assert s.fold()["state"] == "archived"


def test_chain_is_clean_after_transitions(tmp_path, schemas_dir):
    s = _state(tmp_path, schemas_dir)
    s.create_job(job_id=new_ulid(), project="demo", brief="hi")
    s.transition("running", actor="t", fence=0)
    assert s.verify() == []


def test_tampered_event_breaks_chain(tmp_path, schemas_dir):
    s = _state(tmp_path, schemas_dir)
    s.create_job(job_id=new_ulid(), project="demo", brief="hi")
    s.transition("running", actor="t", fence=0)
    events = read_jsonl(s.events_path)
    events[0]["data"]["brief"] = "tampered"
    s.events_path.write_text(
        "\n".join(__import__("json").dumps(e, sort_keys=True) for e in events) + "\n",
        encoding="utf-8",
    )
    problems = s.verify()
    assert problems  # chain must detect the edit


def test_verify_chain_empty_is_clean():
    assert verify_chain([]) == []


def test_invalid_event_type_rejected_by_schema(tmp_path, schemas_dir):
    s = _state(tmp_path, schemas_dir)
    s.create_job(job_id=new_ulid(), project="demo", brief="hi")
    with pytest.raises(SchemaError):
        s.append_event("not.a.real.event", actor="t", fence=0, data={})

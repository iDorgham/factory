"""JSON Schema validation tests (spec §4.1, §27)."""
from __future__ import annotations

import pytest

from factory_kernel.schemas import SchemaError, SchemaStore
from factory_kernel.ulid import new_ulid


@pytest.fixture
def store(schemas_dir):
    return SchemaStore(schemas_dir)


def _valid_event():
    return {
        "id": new_ulid(),
        "ts": "2026-01-01T00:00:00Z",
        "job": new_ulid(),
        "type": "job.created",
        "actor": "kernel",
        "fence": 0,
        "data": {},
        "prev": None,
    }


def test_valid_event_passes(store):
    assert store.is_valid("event", _valid_event())


def test_event_bad_type_rejected(store):
    with pytest.raises(SchemaError):
        store.validate("event", {**_valid_event(), "type": "nope"})


def test_event_missing_field_rejected(store):
    ev = _valid_event()
    del ev["actor"]
    with pytest.raises(SchemaError):
        store.validate("event", ev)


def test_event_extra_field_rejected(store):
    with pytest.raises(SchemaError):
        store.validate("event", {**_valid_event(), "extra": 1})


def test_event_bad_ulid_rejected(store):
    with pytest.raises(SchemaError):
        store.validate("event", {**_valid_event(), "id": "not-a-ulid"})


def test_valid_job_passes(store):
    job = {
        "id": new_ulid(),
        "project": "demo",
        "state": "pending",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "brief": "do a thing",
        "profile": "lite",
        "mode": "solo",
    }
    assert store.is_valid("job", job)


def test_job_bad_state_rejected(store):
    job = {
        "id": new_ulid(),
        "project": "demo",
        "state": "exploded",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "brief": "x",
        "profile": "lite",
        "mode": "solo",
    }
    with pytest.raises(SchemaError):
        store.validate("job", job)


def test_valid_project_passes(store):
    project = {
        "name": "demo",
        "mode": "solo",
        "domain": "web",
        "stage_profile": "lite",
        "created_at": "2026-01-01T00:00:00Z",
    }
    assert store.is_valid("project", project)


def test_project_bad_name_rejected(store):
    project = {
        "name": "Not Valid!",
        "mode": "solo",
        "domain": "web",
        "stage_profile": "lite",
        "created_at": "2026-01-01T00:00:00Z",
    }
    with pytest.raises(SchemaError):
        store.validate("project", project)


def test_unknown_kind_raises(store):
    with pytest.raises(SchemaError):
        store.validate("does-not-exist", {})

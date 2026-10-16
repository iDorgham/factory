"""Tests for the context manifest builder (spec §10.2)."""
from __future__ import annotations

import pytest

from factory_kernel.context import (
    build_manifest,
    collect_stage_context,
    estimate_tokens,
    file_entry,
)
from factory_kernel.schemas import SchemaStore, SchemaError


@pytest.fixture
def store(schemas_dir):
    return SchemaStore(schemas_dir)


def test_file_entry_roles():
    entry = file_entry("brief.md", "required", "hello world")
    assert entry["path"] == "brief.md"
    assert entry["role"] == "required"
    assert entry["tokens"] >= 1
    with pytest.raises(ValueError):
        file_entry("x", "bogus", "")


def test_token_estimate():
    assert estimate_tokens("") == 1
    assert estimate_tokens("a" * 400) == 100


def test_build_manifest_validates(store):
    manifest = build_manifest(
        job_id="01ABC",
        stage="build",
        attempt=1,
        token_budget=500,  # below the schema floor of 1000
        files=[file_entry("brief.md", "required", "hi")],
    )
    assert manifest["token_budget"] == 1000
    store.validate("context.manifest", manifest)  # must not raise


def test_collect_stage_context_includes_brief(store, kernel, demo_job):
    kernel, job = demo_job
    project_dir = kernel.projects_dir / job["project"]
    job_dir = kernel._find_job_dir(job["id"])
    stage = {"id": "plan", "requires": ["brief.md"]}
    manifest = collect_stage_context(project_dir, job_dir, stage, 1, 100000)
    store.validate("context.manifest", manifest)
    paths = [f["path"] for f in manifest["files"]]
    assert "brief.md" in paths
    # memory files were created by project_create
    assert "memory/conventions.md" in paths


def test_collect_stage_context_unknown_requirement(store, kernel, demo_job):
    kernel, job = demo_job
    project_dir = kernel.projects_dir / job["project"]
    job_dir = kernel._find_job_dir(job["id"])
    manifest = collect_stage_context(
        project_dir, job_dir, {"id": "x", "requires": ["nope.md"]}, 1, 100000
    )
    store.validate("context.manifest", manifest)
    assert "nope.md" not in [f["path"] for f in manifest["files"]]


def test_manifest_rejects_bad_role(store):
    manifest = build_manifest("j", "s", 1, 1000, files=[])
    manifest["files"] = [{"path": "x", "role": "nope", "tokens": 1}]
    with pytest.raises(SchemaError):
        store.validate("context.manifest", manifest)

"""Tests for the cli-agent adapter: hermetic default, resume, and live mode.

The live-command tests point ``FACTORY_CLI_AGENT_CMD`` at the fixture agent
(``tests/fixtures/adapters/cli-echo-agent.py``), which stands in for a real
coding CLI while keeping the suite hermetic.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from factory_kernel.adapters import Adapter
from factory_kernel.conformance import overall_ok, run_suite

REPO_ROOT = Path(__file__).resolve().parents[1]
CLI_AGENT_DIR = REPO_ROOT / "adapters" / "cli-agent"
FIXTURE_AGENT = REPO_ROOT / "tests" / "fixtures" / "adapters" / "cli-echo-agent.py"

CMD_ENV = "FACTORY_CLI_AGENT_CMD"
TIMEOUT_ENV = "FACTORY_CLI_AGENT_TIMEOUT_S"


@pytest.fixture
def no_cmd(monkeypatch):
    monkeypatch.delenv(CMD_ENV, raising=False)
    monkeypatch.delenv(TIMEOUT_ENV, raising=False)
    return monkeypatch


def _request(attempt: Path, **over) -> dict:
    worktree = attempt.parent / "worktree"
    worktree.mkdir(parents=True, exist_ok=True)
    req = {
        "run_id": "run-1",
        "job_id": "J",
        "project": "p",
        "stage": "build",
        "role": "builder",
        "attempt": 1,
        "brief": "build it",
        "worktree": str(worktree),
        "attempt_dir": str(attempt),
        "manifest_path": str(attempt / "context.manifest.json"),
        "produces": ["build.md"],
        "budget": {"tokens": 10000, "usd": 1.0, "minutes": 5},
        "fence": 1,
    }
    req.update(over)
    return req


def _live_cmd(monkeypatch) -> str:
    monkeypatch.setenv(CMD_ENV, f'"{sys.executable}" "{FIXTURE_AGENT}"')
    return monkeypatch


def test_manifest_declares_resume():
    assert "resume" in Adapter(CLI_AGENT_DIR).capabilities


def test_default_path_is_deterministic(tmp_path, no_cmd):
    attempt = tmp_path / "attempt-1"
    result = Adapter(CLI_AGENT_DIR).run(_request(attempt))
    assert result.ok
    assert (attempt / "outputs" / "build.md").exists()
    assert result.usage["estimated"] is True
    assert any(e["type"] == "done" for e in result.events)


def test_repeated_run_id_does_not_reexecute(tmp_path, no_cmd):
    attempt = tmp_path / "attempt-1"
    adapter = Adapter(CLI_AGENT_DIR)
    first = adapter.run(_request(attempt, run_id="same"))
    assert first.ok
    assert any(e["type"] == "file_written" for e in first.events)
    second = adapter.run(_request(attempt, run_id="same"))
    assert second.ok
    assert not any(e["type"] == "file_written" for e in second.events)


def test_live_command_events_are_forwarded(tmp_path, no_cmd):
    _live_cmd(no_cmd)
    attempt = tmp_path / "attempt-1"
    result = Adapter(CLI_AGENT_DIR).run(_request(attempt))
    assert result.ok, result.error
    kinds = {e["type"] for e in result.events}
    assert {"progress", "tool_use", "file_written", "usage", "done"} <= kinds
    # Real (non-estimated) usage from the command is preserved.
    assert result.usage["model"] == "fixture-live-1"
    assert result.usage["estimated"] is False
    assert (attempt / "outputs" / "build.md").exists()


def test_live_command_failure_with_missing_outputs_is_fatal(tmp_path, no_cmd):
    no_cmd.setenv(CMD_ENV, f'"{sys.executable}" -c "import sys; sys.exit(1)"')
    result = Adapter(CLI_AGENT_DIR).run(_request(tmp_path / "attempt-1"))
    assert not result.ok
    assert result.error_class == "fatal"
    assert "missing" in (result.error or "")


def test_live_command_success_with_missing_outputs_is_fatal(tmp_path, no_cmd):
    no_cmd.setenv(CMD_ENV, f'"{sys.executable}" -c "print(0)"')
    result = Adapter(CLI_AGENT_DIR).run(_request(tmp_path / "attempt-1"))
    assert not result.ok
    assert result.error_class == "fatal"


def test_live_command_timeout_is_transient(tmp_path, no_cmd):
    no_cmd.setenv(
        CMD_ENV, f'"{sys.executable}" -c "import time; time.sleep(30)"')
    no_cmd.setenv(TIMEOUT_ENV, "1")
    result = Adapter(CLI_AGENT_DIR).run(_request(tmp_path / "attempt-1"))
    assert not result.ok
    assert result.error_class == "transient"


def test_live_command_emits_synthetic_visual_manifest(tmp_path, no_cmd):
    from factory_kernel.dashboard import _visual_evidence
    _live_cmd(no_cmd)
    no_cmd.setenv("FACTORY_FIXTURE_VISUAL", "1")
    attempt = tmp_path / "job" / "stages" / "00-build" / "attempt-1"
    result = Adapter(CLI_AGENT_DIR).run(_request(attempt))
    assert result.ok, result.error
    manifest = attempt / "outputs" / "visual.json"
    assert json.loads(manifest.read_text(encoding="utf-8"))["synthetic"] is True
    found = _visual_evidence(tmp_path / "job")
    assert len(found) == 1
    assert len(found[0]["entries"]) == 3
    assert found[0]["synthetic"] is True


def test_conformance_passes_with_resume_exercised(tmp_path, no_cmd):
    results = run_suite(Adapter(CLI_AGENT_DIR), tmp_path / "cli-agent")
    by_id = {r.id: r for r in results}
    assert overall_ok(results), [r.to_dict() for r in results]
    for case in ("start", "contract_file", "usage", "write_boundary",
                 "injected_instruction", "resume"):
        assert by_id[case].status == "pass", by_id[case]
    assert by_id["resume"].status == "pass"  # declared capability: exercised
    json.dumps({k: v.to_dict() for k, v in by_id.items()})  # serializable

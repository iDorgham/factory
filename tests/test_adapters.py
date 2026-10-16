"""Tests for the adapter runtime (spec §20)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from factory_kernel.adapters import (
    Adapter,
    AdapterError,
    discover_adapters,
    select_adapter,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_DIR = REPO_ROOT / "adapters" / "echo"


def _fake_adapter(tmp_path: Path, adapter_id: str, body: str) -> Path:
    d = tmp_path / adapter_id
    d.mkdir()
    (d / "manifest.json").write_text(
        json.dumps({"id": adapter_id, "entrypoint": "run.py", "capabilities": []}),
        encoding="utf-8",
    )
    (d / "run.py").write_text(body, encoding="utf-8")
    return d


def test_echo_manifest_loads():
    adapter = Adapter(ECHO_DIR)
    assert adapter.id == "echo"
    assert "text" in adapter.capabilities


def test_missing_manifest_raises(tmp_path):
    with pytest.raises(AdapterError):
        Adapter(tmp_path)


def test_discover(tmp_path):
    _fake_adapter(tmp_path, "one", "print('')")
    _fake_adapter(tmp_path, "two", "print('')")
    found = discover_adapters(tmp_path)
    assert set(found) == {"one", "two"}


def test_echo_run_writes_outputs(tmp_path):
    adapter = Adapter(ECHO_DIR)
    attempt = tmp_path / "attempt-1"
    request = {
        "stage": "understand",
        "attempt": 1,
        "attempt_dir": str(attempt),
        "produces": ["brief.md", "git:commits"],
    }
    result = adapter.run(request)
    assert result.ok
    assert (attempt / "outputs" / "brief.md").exists()
    assert result.usage["input_tokens"] > 0
    assert any(e["type"] == "file_written" for e in result.events)
    assert any(e["type"] == "done" for e in result.events)


def test_error_classification(tmp_path):
    body = (
        "import json,sys\n"
        "print(json.dumps({'type':'progress','message':'x'}))\n"
        "print(json.dumps({'type':'error','class':'transient','message':'boom'}))\n"
        "sys.exit(1)\n"
    )
    d = _fake_adapter(tmp_path, "bad", body)
    result = Adapter(d).run({"stage": "s", "attempt": 1, "attempt_dir": str(tmp_path / "a")})
    assert not result.ok
    assert result.error == "boom"
    assert result.error_class == "transient"


def test_non_json_line_is_progress(tmp_path):
    body = "print('plain text line')\nprint('{\"type\":\"done\"}')\n"
    d = _fake_adapter(tmp_path, "noisy", body)
    result = Adapter(d).run({"stage": "s", "attempt": 1, "attempt_dir": str(tmp_path / "a")})
    assert result.ok
    assert any(
        e.get("type") == "progress" and e.get("message") == "plain text line"
        for e in result.events
    )


def test_exit_without_done_is_failure(tmp_path):
    d = _fake_adapter(tmp_path, "quiet", f"import sys; sys.exit({2})\n")
    result = Adapter(d).run({"stage": "s", "attempt": 1, "attempt_dir": str(tmp_path / "a")})
    assert not result.ok
    assert result.error


def test_select_by_id_and_capability():
    adapters = discover_adapters(REPO_ROOT / "adapters")
    assert select_adapter(adapters, adapter_id="echo").id == "echo"
    assert select_adapter(adapters, capabilities=["text"]).id == "echo"
    assert select_adapter(adapters).id == "echo"


def test_select_missing_id_raises():
    adapters = discover_adapters(REPO_ROOT / "adapters")
    with pytest.raises(AdapterError):
        select_adapter(adapters, adapter_id="nope")


def test_entrypoint_missing_raises(tmp_path):
    d = tmp_path / "broken"
    d.mkdir()
    (d / "manifest.json").write_text(
        json.dumps({"id": "broken", "entrypoint": "run.py"}), encoding="utf-8"
    )
    with pytest.raises(AdapterError):
        Adapter(d).run({})

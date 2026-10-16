"""Tests for the check runner (spec §11.1)."""
from __future__ import annotations

import sys

from factory_kernel.checks import (
    CheckResult,
    _trim,
    fingerprint,
    load_checks,
    run_checks,
    run_one,
    summarise,
)


def _py(code: str) -> str:
    return f'"{sys.executable}" -c "{code}"'


def test_run_one_pass(tmp_path):
    result = run_one("ok", {"cmd": "echo ok", "required": True}, tmp_path)
    assert result.passed
    assert result.exit_code == 0
    assert result.required


def test_run_one_fail(tmp_path):
    result = run_one("bad", {"cmd": "exit 1", "required": True}, tmp_path)
    assert not result.passed
    assert result.exit_code == 1


def test_required_normalization(tmp_path):
    # Conditional strings ("if_ui_changed") are not required in this slice.
    result = run_one("cond", {"cmd": "exit 1", "required": "if_ui_changed"}, tmp_path)
    assert result.required is False
    assert not result.passed


def test_undefined_check_is_failure(tmp_path):
    results = run_checks({}, ["lint"], tmp_path)
    assert len(results) == 1
    assert not results[0].passed
    assert results[0].required
    assert "not defined" in results[0].output


def test_required_checks_aggregate(tmp_path):
    checks = {
        "lint": {"cmd": "echo lint", "required": True},
        "unit": {"cmd": "echo unit", "required": True},
        "visual": {"cmd": "exit 1", "required": False},
    }
    results = run_checks(checks, ["required_checks"], tmp_path)
    assert results[0].id == "required_checks"
    assert results[0].passed

    checks["unit"] = {"cmd": "exit 1", "required": True}
    results = run_checks(checks, ["required_checks"], tmp_path)
    assert not results[0].passed
    assert "unit" in results[0].output


def test_summarise(tmp_path):
    checks = {
        "lint": {"cmd": "exit 1", "required": True},
        "visual": {"cmd": "exit 1", "required": False},
    }
    results = run_checks(checks, ["lint", "visual"], tmp_path)
    summary = summarise(results)
    assert summary["passed"] is False
    assert set(summary["failed"]) == {"lint", "visual"}
    assert summary["required_failed"] == ["lint"]


def test_fingerprint_stable_and_sensitive(tmp_path):
    a = [CheckResult("lint", "x", True, 1, False, "", 0.0)]
    b = [CheckResult("lint", "x", True, 1, False, "", 0.0)]
    c = [CheckResult("lint", "x", True, 2, False, "", 0.0)]
    assert fingerprint(a) == fingerprint(b)
    assert fingerprint(a) != fingerprint(c)
    assert fingerprint(a, extra="boom") != fingerprint(a)


def test_output_trimming():
    lines = [f"line {i}" for i in range(100)]
    trimmed = _trim("\n".join(lines))
    assert "truncated" in trimmed
    assert len(trimmed.splitlines()) <= 41


def test_load_checks(tmp_path):
    (tmp_path / "checks.json").write_text('{"lint": {"cmd": "echo", "required": true}}')
    checks = load_checks(tmp_path)
    assert "lint" in checks

"""Tests for the adapter conformance suite (spec §20.3)."""
from __future__ import annotations

from pathlib import Path

from factory_kernel.adapters import Adapter
from factory_kernel.conformance import overall_ok, record_results, run_suite

REPO_ROOT = Path(__file__).resolve().parents[1]
ECHO_DIR = REPO_ROOT / "adapters" / "echo"
SLOW_DIR = REPO_ROOT / "tests" / "fixtures" / "adapters" / "slow"


def _by_id(results):
    return {r.id: r for r in results}


def test_echo_passes_required_cases(tmp_path):
    results = run_suite(Adapter(ECHO_DIR), tmp_path / "echo")
    by_id = _by_id(results)
    assert overall_ok(results)

    for case in ("start", "contract_file", "usage", "write_boundary",
                 "injected_instruction"):
        assert by_id[case].status == "pass", by_id[case]

    # echo declares no cancel/resume/heartbeat capability → those are skipped.
    for case in ("cancel", "resume", "heartbeat"):
        assert by_id[case].status == "skip"


def test_slow_fixture_exercises_capability_cases(tmp_path):
    results = run_suite(Adapter(SLOW_DIR), tmp_path / "slow")
    by_id = _by_id(results)
    assert overall_ok(results), [r.to_dict() for r in results]
    assert by_id["cancel"].status == "pass"
    assert by_id["resume"].status == "pass"
    assert by_id["heartbeat"].status == "pass"


def test_record_results_writes_conformance_json(tmp_path):
    import json
    import shutil

    adapter_dir = tmp_path / "echo"
    shutil.copytree(ECHO_DIR, adapter_dir)
    adapter = Adapter(adapter_dir)

    results = run_suite(adapter, tmp_path / "run")
    path = record_results(adapter, results)
    assert path == adapter_dir / "conformance.json"

    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["adapter"] == "echo"
    assert report["passed"] is True
    assert {r["id"] for r in report["results"]} >= {"start", "usage", "write_boundary"}


def test_broken_adapter_fails_start(tmp_path):
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "manifest.json").write_text(
        '{"id": "broken", "entrypoint": "run.py"}', encoding="utf-8"
    )
    (broken / "run.py").write_text("import sys; sys.exit(3)\n", encoding="utf-8")

    results = run_suite(Adapter(broken), tmp_path / "broken-run")
    assert not overall_ok(results)
    assert _by_id(results)["start"].status == "fail"


def test_adapter_that_writes_outside_sandbox_fails_boundary(tmp_path):
    rogue = tmp_path / "rogue"
    rogue.mkdir()
    (rogue / "manifest.json").write_text(
        '{"id": "rogue", "entrypoint": "run.py"}', encoding="utf-8"
    )
    (rogue / "run.py").write_text(
        "import json, sys, os\n"
        "req = json.load(sys.stdin)\n"
        "open(os.path.join(os.path.dirname(req['attempt_dir']), 'escape.txt'), 'w').write('x')\n"
        "print(json.dumps({'type': 'usage', 'input_tokens': 1, 'output_tokens': 1,"
        " 'estimated': True}))\n"
        "print(json.dumps({'type': 'done'}))\n",
        encoding="utf-8",
    )
    results = run_suite(Adapter(rogue), tmp_path / "rogue-run")
    # attempt_dir is <case_dir>/attempt-1, so escaping to <case_dir> is outside
    # the allow-list (attempt dir + worktree).
    assert _by_id(results)["write_boundary"].status == "fail"

"""P2.4 risk-scored gates — schema contracts + TDD specs (red).

The risk gate is arithmetic over kernel-observed signals (guards, budget
verdict, checks, retries) — no model output plays any part in it (spec §5
principle 5: "deterministic gates first. LLM review informs; it never solely
approves"). This file pins, in order:

- the `risk_scoring` config contract: schema-valid shapes, the kernel-owned
  band-to-action mapping (operators re-weight the score, never the actions),
  fail-hard loading with documented defaults;
- the pure functions of the future `risk.py`: `compute_score`, `resolve_band`,
  `gate_action`, `assess`, `load_risk_config`;
- the engine wiring: `risk.computed` on the record at the gate, the computed
  band — not the hardcoded zero — driving the gate decision.

The pure-function and engine cases are deliberately red at this commit: they
are the specification for the next slices. The schema cases are green now
(the schema is the first slice of the contract).

Two declared contract deviations from the phase sketch, both from "kernel
enforces": (1) `gate_actions` is not operator-configurable — the kernel owns
low->auto_advance / medium->awaiting_human / high->blocked, because a
config-settable `high -> auto_advance` would let tuning negotiate the safety
floor away; (2) thresholds are band ceilings and clamp cap (`score < low ->
low`, `< medium -> medium`, else high), because floor semantics would make a
`high: 100` threshold nearly unreachable. Loader adds what the schema cannot
express: cross-key monotonic ordering and strict-integer weights.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from factory_kernel.atomic import read_json, read_jsonl
from factory_kernel.schemas import SchemaError, SchemaStore

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_WEIGHTS = {
    "guard_violation": 40,
    "budget_soft_exceeded": 20,
    "budget_hard_exceeded": 50,
    "check_failure": 15,
    "retry_attempt": 10,
}
DEFAULT_THRESHOLDS = {"low": 25, "medium": 50, "high": 100}

DEFAULT_CONFIG = {"weights": DEFAULT_WEIGHTS, "thresholds": DEFAULT_THRESHOLDS}


def signals(**overrides):
    """The kernel-built signals dict for a clean first attempt."""
    base = {
        "guard_violations": 0,
        "budget_status": "ok",
        "check_failures": 0,
        "attempt_number": 1,
    }
    base.update(overrides)
    return base


# ----------------------------------------------------------------------
# Schema and config contracts (green: schema slice)
# ----------------------------------------------------------------------

class TestRiskSchema:
    def test_shipped_factory_json_with_risk_block_is_schema_valid(
            self, schemas_dir):
        SchemaStore(schemas_dir).validate("factory",
                                          read_json(REPO_ROOT / "factory.json"))

    def test_factory_json_without_risk_section_stays_valid(self, schemas_dir):
        cfg = read_json(REPO_ROOT / "factory.json")
        cfg.pop("risk_scoring")
        # Optional section: pre-P2.4 configs stay valid unchanged.
        SchemaStore(schemas_dir).validate("factory", cfg)

    def test_risk_kind_is_registered(self, schemas_dir):
        SchemaStore(schemas_dir).validate("risk", DEFAULT_CONFIG)

    def test_unknown_weight_key_rejected(self, schemas_dir):
        weights = {**DEFAULT_WEIGHTS, "agent_drama": 100}
        with pytest.raises(SchemaError):
            SchemaStore(schemas_dir).validate(
                "risk", {"weights": weights, "thresholds": DEFAULT_THRESHOLDS})

    def test_negative_weight_rejected(self, schemas_dir):
        weights = {**DEFAULT_WEIGHTS, "check_failure": -15}
        with pytest.raises(SchemaError):
            SchemaStore(schemas_dir).validate(
                "risk", {"weights": weights, "thresholds": DEFAULT_THRESHOLDS})

    def test_fractional_weight_rejected(self, schemas_dir):
        weights = {**DEFAULT_WEIGHTS, "retry_attempt": 1.5}
        with pytest.raises(SchemaError):
            SchemaStore(schemas_dir).validate(
                "risk", {"weights": weights, "thresholds": DEFAULT_THRESHOLDS})

    def test_gate_actions_not_configurable(self, schemas_dir):
        # Declared deviation: the band-to-action mapping is kernel-owned.
        # Tuning may re-weight the score; it must never renegotiate what a
        # band does (a config-settable `high -> auto_advance` would lower
        # the safety floor the kernel is supposed to hold regardless).
        doc = {
            "weights": DEFAULT_WEIGHTS,
            "thresholds": DEFAULT_THRESHOLDS,
            "gate_actions": {
                "low": "auto_advance",
                "medium": "awaiting_human",
                "high": "blocked",
            },
        }
        with pytest.raises(SchemaError):
            SchemaStore(schemas_dir).validate("risk", doc)

    def test_non_monotonic_thresholds_are_type_valid_but_fail_at_load(
            self, schemas_dir):
        # JSON Schema cannot express cross-key strict ordering, so this
        # document passes the *schema*; the loader (red below) must fail
        # hard on it. Recorded here so the contract has both halves named.
        doc = {"weights": DEFAULT_WEIGHTS,
               "thresholds": {"low": 50, "medium": 50, "high": 100}}
        SchemaStore(schemas_dir).validate("risk", doc)


# ----------------------------------------------------------------------
# Pure scoring (red: risk.py slice)
# ----------------------------------------------------------------------

class TestComputeScore:
    def test_zero_signals_score_zero(self):
        from factory_kernel.risk import compute_score

        assert compute_score(signals(), DEFAULT_CONFIG) == 0

    def test_each_guard_violation_adds_its_weight(self):
        from factory_kernel.risk import compute_score

        assert compute_score(signals(guard_violations=1), DEFAULT_CONFIG) == 40
        assert compute_score(signals(guard_violations=2), DEFAULT_CONFIG) == 80

    def test_each_check_failure_adds_its_weight(self):
        from factory_kernel.risk import compute_score

        assert compute_score(signals(check_failures=2), DEFAULT_CONFIG) == 30

    def test_budget_soft_exceeded_adds_once(self):
        from factory_kernel.risk import compute_score

        assert compute_score(signals(budget_status="soft_exceeded"),
                             DEFAULT_CONFIG) == 20

    def test_budget_hard_exceeded_adds_once(self):
        from factory_kernel.risk import compute_score

        assert compute_score(signals(budget_status="hard_exceeded"),
                             DEFAULT_CONFIG) == 50

    def test_retries_count_attempts_beyond_the_first(self):
        from factory_kernel.risk import compute_score

        assert compute_score(signals(attempt_number=1), DEFAULT_CONFIG) == 0
        assert compute_score(signals(attempt_number=2), DEFAULT_CONFIG) == 10
        assert compute_score(signals(attempt_number=3), DEFAULT_CONFIG) == 20

    def test_combined_signals_sum(self):
        from factory_kernel.risk import compute_score

        s = signals(guard_violations=1, budget_status="soft_exceeded",
                    check_failures=1, attempt_number=2)
        assert compute_score(s, DEFAULT_CONFIG) == 40 + 20 + 15 + 10

    def test_score_clamps_at_threshold_cap(self):
        from factory_kernel.risk import compute_score

        s = signals(guard_violations=3, check_failures=2)  # 120 + 30 = 150
        assert compute_score(s, DEFAULT_CONFIG) == 100  # thresholds.high

    def test_custom_config_weights_apply(self):
        from factory_kernel.risk import compute_score

        cfg = {
            "weights": {**DEFAULT_WEIGHTS, "guard_violation": 5},
            "thresholds": {"low": 10, "medium": 20, "high": 50},
        }
        assert compute_score(signals(guard_violations=2), cfg) == 10

    def test_zeroed_weights_zero_the_score(self):
        from factory_kernel.risk import compute_score

        cfg = {
            "weights": {k: 0 for k in DEFAULT_WEIGHTS},
            "thresholds": DEFAULT_THRESHOLDS,
        }
        assert compute_score(signals(guard_violations=9), cfg) == 0

    def test_malformed_signals_fail_hard(self):
        from factory_kernel.risk import RiskError, compute_score

        with pytest.raises(RiskError):
            compute_score(signals(budget_status="vibes"), DEFAULT_CONFIG)
        with pytest.raises(RiskError):
            compute_score(signals(guard_violations=-1), DEFAULT_CONFIG)
        with pytest.raises(RiskError):
            compute_score(signals(guard_violations="1"), DEFAULT_CONFIG)
        with pytest.raises(RiskError):
            compute_score(signals(guard_violations=1.5), DEFAULT_CONFIG)
        with pytest.raises(RiskError):
            compute_score(signals(attempt_number=0), DEFAULT_CONFIG)
        broken = signals()
        del broken["check_failures"]
        with pytest.raises(RiskError):
            compute_score(broken, DEFAULT_CONFIG)
        with pytest.raises(RiskError):  # thresholds missing entirely
            compute_score(signals(), {"weights": DEFAULT_WEIGHTS})

    def test_malformed_config_fail_hard(self):
        from factory_kernel.risk import RiskError, compute_score

        with pytest.raises(RiskError):  # non-monotonic thresholds
            compute_score(signals(), {"weights": DEFAULT_WEIGHTS,
                                      "thresholds": {"low": 50, "medium": 50,
                                                     "high": 100}})
        with pytest.raises(RiskError):  # missing weight key
            compute_score(signals(), {"weights": {"guard_violation": 40},
                                      "thresholds": DEFAULT_THRESHOLDS})


# ----------------------------------------------------------------------
# Banding and gate resolution (red: risk.py slice)
# ----------------------------------------------------------------------

class TestBandsAndActions:
    def test_band_from_thresholds(self):
        from factory_kernel.risk import resolve_band

        t = DEFAULT_THRESHOLDS
        assert resolve_band(0, t) == "low"
        assert resolve_band(24, t) == "low"
        assert resolve_band(25, t) == "medium"   # thresholds are ceilings
        assert resolve_band(49, t) == "medium"
        assert resolve_band(50, t) == "high"
        assert resolve_band(100, t) == "high"
        assert resolve_band(150, t) == "high"    # over-cap input still bands high

    def test_band_from_custom_thresholds(self):
        from factory_kernel.risk import resolve_band

        assert resolve_band(4, {"low": 5, "medium": 10, "high": 50}) == "low"
        assert resolve_band(5, {"low": 5, "medium": 10, "high": 50}) == "medium"
        assert resolve_band(10, {"low": 5, "medium": 10, "high": 50}) == "high"

    def test_gate_action_mapping_is_kernel_owned(self):
        from factory_kernel.risk import RiskError, gate_action

        assert gate_action("low") == "auto_advance"
        assert gate_action("medium") == "awaiting_human"
        assert gate_action("high") == "blocked"
        with pytest.raises(RiskError):
            gate_action("extreme")

    def test_assess_returns_the_full_deterministic_verdict(self):
        from factory_kernel.risk import assess

        assert assess(signals(), DEFAULT_CONFIG) == {
            "score": 0, "band": "low", "action": "auto_advance"}
        assert assess(signals(check_failures=2), DEFAULT_CONFIG) == {
            "score": 30, "band": "medium", "action": "awaiting_human"}
        assert assess(signals(budget_status="hard_exceeded"),
                      DEFAULT_CONFIG) == {
            "score": 50, "band": "high", "action": "blocked"}
        assert assess(signals(guard_violations=1,
                              budget_status="soft_exceeded",
                              check_failures=1, attempt_number=2),
                      DEFAULT_CONFIG) == {
            "score": 85, "band": "high", "action": "blocked"}


class TestLoadRiskConfig:
    def test_absent_config_falls_back_to_documented_defaults(self):
        from factory_kernel.risk import load_risk_config

        assert load_risk_config(None) == DEFAULT_CONFIG

    def test_absent_section_in_factory_config_uses_defaults(self):
        from factory_kernel.risk import load_risk_config

        cfg = read_json(REPO_ROOT / "factory.json")
        cfg.pop("risk_scoring", None)
        assert load_risk_config(cfg.get("risk_scoring")) == DEFAULT_CONFIG

    def test_shipped_risk_section_round_trips_to_the_defaults(self):
        from factory_kernel.risk import load_risk_config

        shipped = read_json(REPO_ROOT / "factory.json")
        assert load_risk_config(shipped["risk_scoring"]) == DEFAULT_CONFIG

    def test_explicit_config_passes_through_validated(self):
        from factory_kernel.risk import load_risk_config

        doc = {"weights": {**DEFAULT_WEIGHTS, "check_failure": 5},
               "thresholds": {"low": 10, "medium": 40, "high": 80}}
        assert load_risk_config(doc) == doc

    def test_invalid_configs_fail_hard(self):
        from factory_kernel.risk import RiskError, load_risk_config

        with pytest.raises(RiskError):  # present-but-empty: no defaults rescue
            load_risk_config({})
        with pytest.raises(RiskError):  # thresholds not strictly ordered
            load_risk_config({"weights": DEFAULT_WEIGHTS,
                              "thresholds": {"low": 60, "medium": 40,
                                             "high": 100}})
        with pytest.raises(RiskError):  # gate_actions is kernel-owned
            load_risk_config({**DEFAULT_CONFIG, "gate_actions": {
                "low": "auto_advance", "medium": "awaiting_human",
                "high": "blocked"}})
        with pytest.raises(RiskError):  # strict integers, even integral floats
            load_risk_config({"weights": {**DEFAULT_WEIGHTS,
                                          "retry_attempt": 2.0},
                              "thresholds": DEFAULT_THRESHOLDS})


# ----------------------------------------------------------------------
# Engine integration — the gate consumes the computed band (red: Step 3)
# ----------------------------------------------------------------------

def _events(kernel, job_id):
    return read_jsonl(kernel._find_job_dir(job_id) / "events.jsonl")


class TestEngineRiskGate:
    def test_verify_stage_emits_risk_computed_and_decides_from_it(
            self, kernel, demo_job):
        kernel, job = demo_job
        result = kernel.job_execute(job["id"], adapter_id="echo")
        assert result["state"] == "awaiting_human"

        events = _events(kernel, job["id"])
        risk_events = [e for e in events if e["type"] == "risk.computed"]
        assert risk_events, \
            "risk_scored gates must put their score on the record"
        assert all(e["data"]["stage"] == "verify" for e in risk_events), \
            risk_events
        # Noise promise: only stages whose gate consumes risk pay the event.
        assert {e["data"]["stage"] for e in risk_events} == {"verify"}

        first = risk_events[0]
        assert first["data"]["score"] == 0  # hermetic clean run: nothing failed
        assert first["data"]["band"] == "low"
        assert first["data"]["signals"] == signals()  # the exact kernel shape

        # The gate decision followed the band, not the old hardcoded zero.
        verify_gates = [e for e in events
                        if e["type"] == "gate.evaluated"
                        and e["data"]["stage"] == "verify"
                        and e["data"]["gate"] == "risk_scored"]
        assert verify_gates and verify_gates[0]["data"]["decision"] == "auto"

    def test_config_lowered_thresholds_flip_the_gate_decision(
            self, factory_root):
        # A clean attempt still scores 0; with a `medium` ceiling of 1,
        # every score lands in the medium band and the risk gate must hold
        # the stage for a human instead of auto-advancing.
        cfg = read_json(factory_root / "factory.json")
        cfg["risk_scoring"]["thresholds"] = {"low": 0, "medium": 1, "high": 100}
        (factory_root / "factory.json").write_text(
            json.dumps(cfg, indent=2), encoding="utf-8")

        from factory_kernel.kernel import Kernel

        k = Kernel(factory_root)
        k.project_create("demo", mode="solo", domain="web")
        job = k.job_run("demo", "Build a landing page")
        result = k.job_execute(job["id"], adapter_id="echo")

        events = _events(k, job["id"])
        risk_events = [e for e in events if e["type"] == "risk.computed"]
        assert risk_events and \
            all(e["data"]["band"] == "medium" for e in risk_events)
        verify_gates = [e for e in events
                        if e["type"] == "gate.evaluated"
                        and e["data"]["stage"] == "verify"]
        assert verify_gates and verify_gates[0]["data"]["decision"] != "auto"
        assert result["state"] == "awaiting_human"  # held at the risk gate

    def test_no_risk_event_for_gates_that_do_not_consume_risk(
            self, kernel, demo_job):
        kernel, job = demo_job
        kernel.job_execute(job["id"], adapter_id="echo")

        scored_stages = {e["data"].get("stage")
                         for e in _events(kernel, job["id"])
                         if e["type"] == "risk.computed"}
        assert "understand" not in scored_stages
        assert "approve" not in scored_stages  # gate: required never scores

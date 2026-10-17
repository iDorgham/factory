"""P2.2: budgets and metering (P2 gap #4, spec §12.1, §543).

The kernel converts adapter-reported usage to cost with the price table from
``factory.json``, checks it against the stage's soft/hard limits, and records
the verdict as ``budget.json`` per attempt plus exceed events. Cost math is a
pure function: no subprocesses, no LLM, no network — the same discipline as
guards (§12.1: pure functions over their context).

Policy baked into the design (tested here so it cannot drift silently):
- An unpriced *metered* metric (``*_tokens``) or a missing price tier fails
  hard, never silently costs $0 — "no job exceeds its hard budget" requires
  every reported token to have a price.
- Unknown non-token fields (``estimated``, ``events``, ``tool_calls``) are
  visible in budget.json but carry no price.
- Stage ``budget.usd`` is the stage's hard limit for cumulative attempts;
  ``budget.soft_usd`` is the soft limit, defaulting deterministically to
  0.8 × usd (rounded to cents). Soft and hard both can be violated in one
  check: soft is the notify level, hard is the stop.
"""
from __future__ import annotations

import pytest

from factory_kernel.schemas import SchemaStore

PRICES = {
    "default": {"input_per_1m": 3.00, "output_per_1m": 15.00, "cached_per_1m": 0.30},
    "burner-1": {"input_per_1m": 1.00, "output_per_1m": 2.00, "cached_per_1m": 0.10},
}


# ----------------------------------------------------------------------
# Schemas: budget + price table
# ----------------------------------------------------------------------

class TestBudgetSchema:
    def test_shipped_profile_budgets_validate(self, schemas_dir, repo_root):
        import yaml

        for fields in ("lite.yaml", "standard.yaml"):
            doc = yaml.safe_load(
                (repo_root / "kernel" / "stages" / fields).read_text(encoding="utf-8"))
            store = SchemaStore(schemas_dir)
            for stage in doc["stages"]:
                store.validate("budget", stage["budget"])

    def test_soft_usd_optional_shape(self, schemas_dir):
        store = SchemaStore(schemas_dir)
        assert store.is_valid("budget", {
            "tokens": 100000, "usd": 5.00, "minutes": 30, "soft_usd": 3.00,
        })
        assert store.is_valid("budget", {"tokens": 100000, "usd": 5.00, "minutes": 30})

    def test_unknown_keys_and_bad_values_rejected(self, schemas_dir):
        store = SchemaStore(schemas_dir)
        assert not store.is_valid("budget", {
            "tokens": 10, "usd": 5.00, "minutes": 30, "soft_limit": 4.00,
        })  # runtime naming is not profile naming
        assert not store.is_valid("budget", {"tokens": 10, "usd": -5.0, "minutes": 1})
        assert not store.is_valid("budget", {"tokens": "many", "usd": 5.0, "minutes": 1})


class TestPriceTableSchema:
    def test_shipped_factory_table_validates(self, schemas_dir, repo_root):
        import json

        cfg = json.loads((repo_root / "factory.json").read_text(encoding="utf-8"))
        SchemaStore(schemas_dir).validate("price_table", cfg["price_table"])

    def test_tier_shape(self, schemas_dir):
        store = SchemaStore(schemas_dir)
        assert store.is_valid("price_table", PRICES)
        assert not store.is_valid("price_table", {
            "default": {"input_per_1m": 3.00, "output_per_1m": 15.00},  # cache missing
        })
        assert not store.is_valid("price_table", {
            "default": {"input_per_1m": -3.00, "output_per_1m": 15.00,
                        "cached_per_1m": 0.30},
        })
        assert not store.is_valid("price_table", {
            "default": {"input_per_1m": 3.00, "output_per_1m": 15.00,
                        "cached_per_1m": 0.30, "gpu_minutes": 9},
        })


# ----------------------------------------------------------------------
# calculate_cost — pure arithmetic over usage and the price table
# ----------------------------------------------------------------------

class TestCalculateCost:
    def test_zero_usage_costs_zero(self):
        from factory_kernel.budgets import calculate_cost

        assert calculate_cost({}, PRICES) == 0.0

    def test_metered_metrics_priced_per_million(self):
        from factory_kernel.budgets import calculate_cost

        usage = {"input_tokens": 1_000_000, "output_tokens": 1_000_000,
                 "cached_tokens": 1_000_000}
        assert abs(calculate_cost(usage, PRICES) - 18.30) < 1e-9

    def test_sub_million_tokens_partial_cost(self):
        from factory_kernel.budgets import calculate_cost

        usage = {"input_tokens": 2_000_000, "output_tokens": 500}
        # 2_000_000 x 3.00/1M + 500 x 15.00/1M
        assert abs(calculate_cost(usage, PRICES) - (6.0 + 0.0075)) < 1e-9

    def test_named_tier_overrides_default(self):
        from factory_kernel.budgets import calculate_cost

        usage = {"model": "burner-1", "input_tokens": 1_000_000}
        assert abs(calculate_cost(usage, PRICES) - 1.00) < 1e-9

    def test_unknown_model_falls_back_to_default(self):
        from factory_kernel.budgets import calculate_cost

        usage = {"model": "yeti-pro-max", "input_tokens": 1_000_000}
        assert abs(calculate_cost(usage, PRICES) - 3.00) < 1e-9

    def test_unpriced_metered_metric_fails_hard(self):
        from factory_kernel.budgets import BudgetError, calculate_cost

        usage = {"context_tokens": 1_000_000}
        with pytest.raises(BudgetError, match="unpriced"):
            calculate_cost(usage, PRICES)

    def test_non_token_fields_never_price(self):
        from factory_kernel.budgets import calculate_cost

        usage = {"input_tokens": 0, "tool_calls": 12, "events": 3,
                 "estimated": True}
        assert calculate_cost(usage, PRICES) == 0.0

    def test_negative_counts_clamp_to_zero(self):
        from factory_kernel.budgets import calculate_cost

        usage = {"input_tokens": -500, "output_tokens": 1_000_000}
        assert abs(calculate_cost(usage, PRICES) - 15.0) < 1e-9

    def test_unpriced_model_without_default_fails_hard(self):
        from factory_kernel.budgets import BudgetError, calculate_cost

        usage = {"model": "yeti-pro-max", "input_tokens": 10}
        with pytest.raises(BudgetError, match="unpriced"):
            calculate_cost(usage, {"burner-1": PRICES["burner-1"]})


# ----------------------------------------------------------------------
# check_budget + limit derivation
# ----------------------------------------------------------------------

class TestCheckBudget:
    def _ctx(self, extra_hard=5.00, extra_soft=4.00, pr=1_000_000):
        from factory_kernel.budgets import BudgetContext

        return BudgetContext(
            usage={"input_tokens": pr},
            price_table=PRICES,
            soft_limit=extra_soft,
            hard_limit=extra_hard,
        )

    def test_ok_below_soft(self):
        from factory_kernel.budgets import check_budget

        result = check_budget(self._ctx(pr=100_000))  # $0.30
        assert result.status == "ok"
        assert result.current_cost == pytest.approx(0.30)

    def test_soft_exceeded_notifies_between_limits(self):
        from factory_kernel.budgets import check_budget

        result = check_budget(self._ctx(pr=1_500_000))  # $4.50
        assert result.status == "soft_exceeded"
        assert result.limit == pytest.approx(4.00)

    def test_hard_exceeded_stops(self):
        from factory_kernel.budgets import check_budget

        result = check_budget(self._ctx(pr=6_000_000))  # $18.00
        assert result.status == "hard_exceeded"
        assert result.limit == pytest.approx(5.00)

    def test_exact_limits_match_inclusively(self):
        from factory_kernel.budgets import check_budget

        # $0.30 exactly: hard fires when hard == cost (>= is inclusive), and
        # soft fires when cost == soft < hard.
        exact = self._ctx(pr=100_000, extra_soft=0.29, extra_hard=0.30)
        assert check_budget(exact).status == "hard_exceeded"
        boundary = self._ctx(pr=100_000, extra_soft=0.30, extra_hard=0.31)
        assert check_budget(boundary).status == "soft_exceeded"

    def test_soft_default_is_deterministic_fraction(self):
        from factory_kernel.budgets import stage_limits

        soft, hard = stage_limits({"tokens": 10, "usd": 5.00, "minutes": 30})
        assert hard == pytest.approx(5.00)
        assert soft == pytest.approx(4.00)  # 0.8 x usd, rounded to cents

    def test_explicit_soft_usd_wins(self):
        from factory_kernel.budgets import stage_limits

        soft, hard = stage_limits(
            {"tokens": 10, "usd": 5.00, "minutes": 30, "soft_usd": 2.50})
        assert (soft, hard) == (pytest.approx(2.50), pytest.approx(5.00))

    def test_stage_limits_reject_missing_usd(self):
        from factory_kernel.budgets import BudgetError, stage_limits

        with pytest.raises(BudgetError):
            stage_limits({"tokens": 10, "minutes": 30})


# ----------------------------------------------------------------------
# Doctor budget configuration integrity
# ----------------------------------------------------------------------

def _set_build_budget(kernel, budget_yaml_line: str):
    """Rewrite the shipped lite build budget in the hermetic factory tree."""
    lite = kernel.stages_dir / "lite.yaml"
    text = lite.read_text(encoding="utf-8")
    text = text.replace(
        "budget: { tokens: 600000, usd: 5.00, minutes: 60 }",
        budget_yaml_line,
    )
    lite.write_text(text, encoding="utf-8")


class TestDoctorBudgetConfig:
    def test_doctor_warns_when_soft_exceeds_hard(self, kernel):
        _set_build_budget(kernel, "budget: { tokens: 600000, usd: 5.00, "
                                  "minutes: 60, soft_usd: 10.00 }")
        report = kernel.doctor()
        assert report["ok"] is True  # advisory: runtime enforcement is absolute
        assert any("Stage build soft_limit (10.0) must be less than "
                   "hard_limit (5.0)" in w for w in report["warnings"]), \
            report["warnings"]

    def test_doctor_warns_on_unpriced_usage(self, kernel, demo_job):
        from factory_kernel.atomic import atomic_write_json

        kernel, job = demo_job
        attempt = (kernel._find_job_dir(job["id"]) / "stages" / "00-understand"
                   / "attempt-1")
        attempt.mkdir(parents=True, exist_ok=True)
        atomic_write_json(attempt / "usage.json",
                          {"model": "unpriced-1", "input_tokens": 42})

        report = kernel.doctor()
        assert any("unpriced-1" in w and "price" in w
                   for w in report["warnings"]), report["warnings"]

    def test_doctor_flags_invalid_price_table(self, kernel):
        from factory_kernel.atomic import read_json

        cfg = read_json(kernel.root / "factory.json")
        cfg["price_table"]["default"]["input_per_1m"] = -3.00
        import json

        (kernel.root / "factory.json").write_text(
            json.dumps(cfg, indent=2), encoding="utf-8")
        report = kernel.doctor()
        assert any("price_table" in e or "price table" in e
                   for e in report["errors"]), report["errors"]

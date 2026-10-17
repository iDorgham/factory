"""Budget meter — pure cost arithmetic and limit checks (spec §3.9, §12.1).

Cost-awareness is a kernel principle: every attempt reports usage and budgets
are enforced at stage boundaries. This module owns the *math* only; the engine
owns verdicts and events, keeping the "kernel enforces, agents propose" split
(agents report usage; the kernel prices it and decides).

Pure functions: no subprocesses, no LLM calls, no network, no file I/O. The
same discipline as guards (§12.1: pure functions over their context).

Pricing model: the price table from ``factory.json`` is a mapping of model
tier names to per-million-token rates (`input_per_1m`, `output_per_1m`,
`cached_per_1m`), with ``default`` as the fallback tier (bundle schema:
``kernel/schemas/price_table.schema.json``). A usage key shaped ``X_tokens``
is a *metered metric* priced by the rate ``X_per_1m`` of the usage's model
tier — so canonical metrics (``input_tokens``, ``output_tokens``,
``cached_tokens``) need no special case, and an unpriced metric is exactly
what raises: unpriced usage must never silently cost $0, or "no job exceeds
its hard budget" would be unenforceable. Non-token fields (``estimated``,
``events``, ``tool_calls``) carry no price.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ``X_tokens`` → metered metric X, priced by ``X_per_1m`` of the model tier.
METERED_METRIC = re.compile(r"^(.+)_tokens$")

# A valid tier prices exactly these three components (schema-enforced too).
REQUIRED_RATES = ("input_per_1m", "output_per_1m", "cached_per_1m")

# Deterministic default soft limit when a stage declares no explicit soft_usd.
SOFT_DEFAULT_RATIO = 0.8


class BudgetError(Exception):
    """Budget configuration or pricing is invalid (fail-hard policy)."""


@dataclass
class BudgetContext:
    """Everything the meter may look at for one check (no I/O, no state)."""
    usage: dict = field(default_factory=dict)      # attempt's usage.json
    price_table: dict = field(default_factory=dict)  # factory.json price_table
    soft_limit: float = 0.0                        # notify threshold, USD
    hard_limit: float = 0.0                        # stop threshold, USD


@dataclass
class BudgetResult:
    status: str                                    # ok | soft_exceeded | hard_exceeded
    current_cost: float                            # USD
    limit: float                                   # the decisive bound


def _tier_rates(model, price_table: dict) -> tuple:
    """Rates for a usage's model tier (fallback: ``default``).

    Returns (tier_name, rates). Raises BudgetError when no tier applies or a
    tier is incomplete — a half-priced tier is the same lie as no tier.
    """
    if not isinstance(price_table, dict) or not price_table:
        raise BudgetError("unpriced usage: price table is missing or empty")
    name = str(model) if model else "default"
    tier_name = name if isinstance(price_table.get(name), dict) else "default"
    rates = price_table.get(tier_name)
    if not isinstance(rates, dict):
        raise BudgetError(
            f"unpriced usage: no price tier for model '{model}' "
            "and no 'default' fallback")
    for rate_name in REQUIRED_RATES:
        rate = rates.get(rate_name)
        if not isinstance(rate, (int, float)) or isinstance(rate, bool) or rate < 0:
            raise BudgetError(
                f"unpriced usage: price tier '{tier_name}' is missing or has "
                f"an invalid rate '{rate_name}'")
    return tier_name, rates


def calculate_cost(usage: dict, price_table: dict) -> float:
    """Sum the USD cost of a usage record against the price table.

    Every ``X_tokens`` key contributes ``x(r) = max(0, count) * R / 1_000_000``
    where R is the ``X_per_1m`` rate of the record's model tier. Missing rates
    or tiers raise ``BudgetError`` (fail-hard: nothing is priced free).
    Negative counts clamp to 0 defensively. Non-numeric counts raise too —
    malformed usage is kernel-rejected, not estimated.
    """
    if not isinstance(usage, dict):
        raise BudgetError("usage must be a mapping")
    _tier_name, rates = _tier_rates(usage.get("model"), price_table)

    total = 0.0
    for key, count in usage.items():
        match = METERED_METRIC.match(str(key))
        if match is None:
            continue  # non-metered field (estimated, events, tool_calls, ...)
        rate = rates.get(f"{match.group(1)}_per_1m")
        if rate is None:
            raise BudgetError(
                f"unpriced metered metric '{key}': no "
                f"'{match.group(1)}_per_1m' rate in tier '{_tier_name}'")
        if not isinstance(count, (int, float)) or isinstance(count, bool):
            raise BudgetError(f"metered metric '{key}' is not numeric: {count!r}")
        total += max(0.0, float(count)) * float(rate) / 1_000_000
    return round(total, 6)


def stage_limits(budget: dict) -> tuple:
    """(soft_limit, hard_limit) from a stage budget mapping.

    ``usd`` is the hard limit and is required (shipped profiles always have
    it). ``soft_usd`` overrides the soft limit; absent → deterministic
    ``0.8 x usd`` rounded to cents. Inverted limits raise: a soft limit at or
    past the hard limit would notify after stopping.
    """
    if not isinstance(budget, dict):
        raise BudgetError("stage budget must be a mapping")
    hard = budget.get("usd")
    if not isinstance(hard, (int, float)) or isinstance(hard, bool) or hard <= 0:
        raise BudgetError("stage budget requires a positive numeric 'usd'")
    soft = budget.get("soft_usd")
    if soft is None:
        soft = round(hard * SOFT_DEFAULT_RATIO, 2)
    elif (not isinstance(soft, (int, float)) or isinstance(soft, bool)
            or soft < 0):
        raise BudgetError(
            f"invalid 'soft_usd' ({soft!r}): must be a non-negative number")
    if soft >= hard:
        raise BudgetError(
            f"soft_limit ({soft}) must be less than hard_limit ({hard})")
    return float(soft), float(hard)


def check_budget(ctx: BudgetContext) -> BudgetResult:
    """Compare the usage's cost against the limits (inclusive boundaries).

    ``cost >= hard`` stops (hard_exceeded). ``cost >= soft < hard`` notifies
    (soft_exceeded). Otherwise ok with the hard limit attached, so callers
    always have the decisive bound in hand.
    """
    cost = calculate_cost(ctx.usage, ctx.price_table)
    if cost >= ctx.hard_limit:
        return BudgetResult("hard_exceeded", cost, ctx.hard_limit)
    if cost >= ctx.soft_limit:
        return BudgetResult("soft_exceeded", cost, ctx.soft_limit)
    return BudgetResult("ok", cost, ctx.hard_limit)

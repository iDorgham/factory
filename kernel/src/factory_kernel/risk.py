"""Risk scoring — pure arithmetic for the ``risk_scored`` gate (P2.4).

Spec §5 principle 5: "Deterministic gates first. Build/lint/type/test/a11y/
visual results decide. LLM review informs; it never solely approves." The
score below is a weighted sum over kernel-observed signals — no model output
is an input, no LLM opinion is a factor. And the band-to-action mapping is
kernel-owned: configuration can re-weight what raises the score, it can
never renegotiate what a band means — a config-settable
``high -> auto_advance`` would let tuning negotiate the safety floor away.

Pure module: no subprocess, no file I/O, no side effects. Config arrives
already parsed (the engine hands over ``factory.json``'s ``risk_scoring``
section), signals arrive assembled by the engine from kernel-owned records;
the same validator backs both — malformed config or signals raise
``RiskError`` instead of being "best-efforted" into a score (a safeguard
that silently degrades is worse than one that stops).

Band semantics, pinned in the tests: thresholds are band *ceilings* and the
clamp cap — ``score < low`` -> ``low``, ``< medium`` -> ``medium``, otherwise
``high``. ``thresholds["high"]`` saturates the score, so an over-cap sum
lands solidly in the highest band.
"""
from __future__ import annotations

# The documented defaults — equal to the shipped ``factory.json`` block.
DEFAULT_WEIGHTS = {
    "guard_violation": 40,
    "budget_soft_exceeded": 20,
    "budget_hard_exceeded": 50,
    "check_failure": 15,
    "retry_attempt": 10,
    "injection_flag": 100,
}
DEFAULT_THRESHOLDS = {"low": 25, "medium": 50, "high": 100}

_BAND_ACTIONS = {
    "low": "auto_advance",
    "medium": "awaiting_human",
    "high": "blocked",
}

_SIGNAL_KEYS = frozenset({
    "guard_violations", "budget_status", "check_failures", "attempt_number"})
_WEIGHT_KEYS = frozenset({
    "guard_violation", "budget_soft_exceeded", "budget_hard_exceeded",
    "check_failure", "retry_attempt", "injection_flag"})
_THRESH_KEYS = frozenset({"low", "medium", "high"})
_BUDGET_STATUSES = frozenset({"ok", "soft_exceeded", "hard_exceeded"})


class RiskError(Exception):
    """Risk configuration is invalid, or the assembled signals are malformed."""


def _strict_int(value) -> int:
    """Accept ``bool``-free true integers only (a float 2.0 is NOT an int here)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise RiskError(f"expected an integer, got {value!r}")
    return value


def _validate_thresholds(thresholds) -> dict:
    if not isinstance(thresholds, dict) or set(thresholds) != _THRESH_KEYS:
        raise RiskError(
            "'thresholds' must map exactly low/medium/high to integers")
    low = _strict_int(thresholds["low"])
    medium = _strict_int(thresholds["medium"])
    high = _strict_int(thresholds["high"])
    if low < 0 or not low < medium or medium > high or high < 1:
        raise RiskError(
            f"thresholds must satisfy 0 <= low < medium <= high, "
            f"got low={low}, medium={medium}, high={high}")
    return {"low": low, "medium": medium, "high": high}


def _validate_config(config) -> tuple[dict, dict]:
    """Validate the full risk config; unknown keys (e.g. ``gate_actions``)
    are rejected — the band-to-action mapping is kernel-owned (see docstring)."""
    if not isinstance(config, dict):
        raise RiskError("risk config must be a mapping")
    if set(config) != {"weights", "thresholds"}:
        raise RiskError(
            "risk config must hold exactly 'weights' and 'thresholds' — "
            "unknown keys (incl. 'gate_actions') are rejected: the "
            "band-to-action mapping is kernel-owned")
    weights = config["weights"]
    if not isinstance(weights, dict) or set(weights) != _WEIGHT_KEYS:
        raise RiskError(
            "'weights' must map exactly the five signal weights to integers")
    clean_weights = {}
    for key in sorted(_WEIGHT_KEYS):
        value = _strict_int(weights[key])
        if value < 0:
            raise RiskError(f"weight '{key}' must be >= 0, got {value}")
        clean_weights[key] = value
    return clean_weights, _validate_thresholds(config["thresholds"])


def compute_score(signals: dict, config: dict) -> int:
    """Weighted signal sum, clamped at the threshold cap (pure).

    The engine assembles ``signals`` from kernel-owned records; the shape is
    pinned: ``guard_violations`` (count), ``check_failures`` (count),
    ``attempt_number`` (1-based; retries = attempts - 1), and
    ``budget_status`` (``ok``/``soft_exceeded``/``hard_exceeded`` from the
    winning attempt's ``budget.json``). Anything unknown, missing, negative,
    or non-integer raises ``RiskError`` — malformed input never becomes a
    guessed score.
    """
    weights, thresholds = _validate_config(config)
    if not isinstance(signals, dict) or set(signals) != _SIGNAL_KEYS:
        raise RiskError(
            "signals must have exactly the keys "
            "guard_violations/budget_status/check_failures/attempt_number")

    guard_violations = _strict_int(signals["guard_violations"])
    check_failures = _strict_int(signals["check_failures"])
    attempt_number = _strict_int(signals["attempt_number"])
    budget_status = signals["budget_status"]
    if not isinstance(budget_status, str) or budget_status not in _BUDGET_STATUSES:
        raise RiskError(
            f"budget_status must be one of {sorted(_BUDGET_STATUSES)}, "
            f"got {budget_status!r}")
    if guard_violations < 0 or check_failures < 0 or attempt_number < 1:
        raise RiskError(
            "guard_violations/check_failures must be >= 0 and "
            f"attempt_number >= 1, got {guard_violations}/{check_failures}/"
            f"{attempt_number}")

    retries = attempt_number - 1  # struggle is evidence, not proof
    score = (
        guard_violations * weights["guard_violation"]
        + check_failures * weights["check_failure"]
        + retries * weights["retry_attempt"]
    )
    if budget_status == "soft_exceeded":
        score += weights["budget_soft_exceeded"]
    elif budget_status == "hard_exceeded":  # pragma: no cover (reached only
        # from an engine path where a hard breach did not already stop the
        # run; kept for the contract's completeness)
        score += weights["budget_hard_exceeded"]
    return min(score, thresholds["high"])


def resolve_band(score: int, thresholds: dict) -> str:
    """Ceiling semantics: ``score < low`` -> low, ``< medium`` -> medium,
    else high (pure). An over-cap score still bands high; a negative score
    is a caller bug and raises."""
    thresholds = _validate_thresholds(thresholds)
    score = _strict_int(score)
    if score < 0:
        raise RiskError(f"score must be >= 0, got {score}")
    if score < thresholds["low"]:
        return "low"
    if score < thresholds["medium"]:
        return "medium"
    return "high"


def gate_action(band: str) -> str:
    """The kernel-owned band-to-action map (NOT configurable - spec §5: the
    safety floor cannot be negotiated, even by configuration)."""
    try:
        return _BAND_ACTIONS[band]
    except (KeyError, TypeError):
        raise RiskError(
            f"unknown band {band!r}: expected one of {list(_BAND_ACTIONS)}")


def assess(signals: dict, config: dict) -> dict:
    """One deterministic verdict: ``{"score", "band", "action"}`` (pure).

    Every layer validates independently, so ``score -> band -> action`` all
    cite the same checked numbers — the gate decision is auditable against
    the recorded ``risk.computed`` event end-to-end.
    """
    score = compute_score(signals, config)
    band = resolve_band(score, config["thresholds"])
    action = gate_action(band)
    return {"score": score, "band": band, "action": action}


def load_risk_config(section) -> dict:
    """Validate and return a defensive copy of the risk config (pure).

    ``None`` (no ``risk_scoring`` key in factory.json) -> the documented
    defaults. A present-but-empty or malformed section raises ``RiskError``
    — an explicitly broken config never silently "rescues itself" back to
    the defaults; doctor (P2.4 step 4) names it as the authoritative error.
    Structural validation mirrors ``risk.schema.json`` (the schema stays the
    declarative contract; this module stays I/O-free and cannot load it).
    """
    if section is None:
        return {
            "weights": dict(DEFAULT_WEIGHTS),
            "thresholds": dict(DEFAULT_THRESHOLDS),
        }
    weights, thresholds = _validate_config(section)
    return {"weights": weights, "thresholds": thresholds}

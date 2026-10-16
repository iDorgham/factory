"""Stage profile loading and validation (spec §8.1, §8.2).

A profile lives in ``kernel/stages/<name>.yaml`` and is a list of stages. Each
stage declares requires, produces, checks, guards, effects, max_rounds, budget,
gate, and on_fail. The kernel validates profiles before using them so a typo in
a stage graph fails loudly instead of silently truncating execution.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

VALID_EFFECTS = {"local", "external"}
VALID_ON_FAIL = {"loop", "escalate", "fail"}
_GATE_RE = re.compile(r"^(none|risk_scored|required|if_risk_above:(low|medium|high))$")

REQUIRED_STAGE_FIELDS = (
    "id",
    "role",
    "requires",
    "produces",
    "checks",
    "guards",
    "effects",
    "max_rounds",
    "budget",
    "gate",
    "on_fail",
)
BUDGET_FIELDS = ("tokens", "usd", "minutes")
_LIST_FIELDS = ("requires", "produces", "checks", "guards")


class ProfileError(Exception):
    pass


def validate_stage(stage: Any, index: int) -> None:
    """Validate a single stage mapping. Raises ProfileError on any problem."""
    where = f"stages[{index}]"
    if not isinstance(stage, dict):
        raise ProfileError(f"{where}: expected a mapping, got {type(stage).__name__}")

    stage_id = stage.get("id")
    if not isinstance(stage_id, str) or not stage_id:
        raise ProfileError(f"{where}: missing or empty 'id'")
    where = f"stage '{stage_id}'"

    for field in REQUIRED_STAGE_FIELDS:
        if field not in stage:
            raise ProfileError(f"{where}: missing required field '{field}'")

    if not isinstance(stage["role"], str) or not stage["role"]:
        raise ProfileError(f"{where}: 'role' must be a non-empty string")

    for field in _LIST_FIELDS:
        value = stage[field]
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ProfileError(f"{where}: '{field}' must be a list of strings")

    if stage["effects"] not in VALID_EFFECTS:
        raise ProfileError(
            f"{where}: 'effects' must be one of {sorted(VALID_EFFECTS)}, got {stage['effects']!r}"
        )

    max_rounds = stage["max_rounds"]
    if not isinstance(max_rounds, int) or isinstance(max_rounds, bool) or max_rounds < 1:
        raise ProfileError(f"{where}: 'max_rounds' must be an integer >= 1")

    budget = stage["budget"]
    if not isinstance(budget, dict):
        raise ProfileError(f"{where}: 'budget' must be a mapping")
    for field in BUDGET_FIELDS:
        if field not in budget:
            raise ProfileError(f"{where}: 'budget' missing '{field}'")
        value = budget[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ProfileError(f"{where}: 'budget.{field}' must be a non-negative number")

    gate = stage["gate"]
    if not isinstance(gate, str) or not _GATE_RE.match(gate):
        raise ProfileError(
            f"{where}: 'gate' must be none|risk_scored|required|if_risk_above:<level>, got {gate!r}"
        )

    if stage["on_fail"] not in VALID_ON_FAIL:
        raise ProfileError(
            f"{where}: 'on_fail' must be one of {sorted(VALID_ON_FAIL)}, got {stage['on_fail']!r}"
        )


def validate_profile(profile: Any) -> None:
    """Validate a whole profile mapping."""
    if not isinstance(profile, dict):
        raise ProfileError("Profile must be a mapping")
    name = profile.get("profile")
    if not isinstance(name, str) or not name:
        raise ProfileError("Profile missing non-empty 'profile' name")
    stages = profile.get("stages")
    if not isinstance(stages, list) or not stages:
        raise ProfileError(f"Profile '{name}' must define a non-empty 'stages' list")

    seen: set[str] = set()
    for i, stage in enumerate(stages):
        validate_stage(stage, i)
        sid = stage["id"]
        if sid in seen:
            raise ProfileError(f"Profile '{name}': duplicate stage id '{sid}'")
        seen.add(sid)


def load_profile(path: Path | str) -> dict:
    """Load and validate a stage profile from a YAML file."""
    path = Path(path)
    if not path.exists():
        raise ProfileError(f"Stage profile not found: {path}")
    try:
        profile = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ProfileError(f"Invalid YAML in {path}: {e}") from e
    validate_profile(profile)
    result = dict(profile)
    result["path"] = str(path)
    return result


def stage_ids(profile: dict) -> list[str]:
    """Declared stage order (the order stages appear in the profile)."""
    return [s["id"] for s in profile["stages"]]

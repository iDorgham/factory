"""Stage profile validation tests (spec §8)."""
from __future__ import annotations

import pytest

from factory_kernel.profiles import (
    ProfileError,
    load_profile,
    stage_ids,
    validate_profile,
)


def test_lite_profile_loads(repo_root):
    p = load_profile(repo_root / "kernel" / "stages" / "lite.yaml")
    assert p["profile"] == "lite"
    assert stage_ids(p) == ["understand", "plan", "build", "verify", "approve"]


def test_standard_profile_loads(repo_root):
    p = load_profile(repo_root / "kernel" / "stages" / "standard.yaml")
    assert p["profile"] == "standard"
    assert len(p["stages"]) == 11


def test_missing_profile_raises(tmp_path):
    with pytest.raises(ProfileError):
        load_profile(tmp_path / "nope.yaml")


def _valid_stage(**overrides):
    stage = {
        "id": "build",
        "role": "builder",
        "requires": ["plan.md"],
        "produces": ["build.md"],
        "checks": ["lint"],
        "guards": [],
        "effects": "local",
        "max_rounds": 4,
        "budget": {"tokens": 1000, "usd": 1.0, "minutes": 10},
        "gate": "none",
        "on_fail": "loop",
    }
    stage.update(overrides)
    return stage


def test_valid_stage_passes():
    validate_profile({"profile": "p", "stages": [_valid_stage()]})


@pytest.mark.parametrize(
    "overrides",
    [
        {"id": ""},
        {"role": ""},
        {"requires": "plan.md"},
        {"checks": [1]},
        {"effects": "space"},
        {"max_rounds": 0},
        {"budget": {"tokens": 1}},
        {"budget": {"tokens": -1, "usd": 1, "minutes": 1}},
        {"gate": "sometimes"},
        {"on_fail": "explode"},
    ],
)
def test_invalid_stage_rejected(overrides):
    with pytest.raises(ProfileError):
        validate_profile({"profile": "p", "stages": [_valid_stage(**overrides)]})


def test_duplicate_stage_ids_rejected():
    with pytest.raises(ProfileError):
        validate_profile({"profile": "p", "stages": [_valid_stage(), _valid_stage()]})


def test_empty_stages_rejected():
    with pytest.raises(ProfileError):
        validate_profile({"profile": "p", "stages": []})


def test_risk_gate_pattern_accepted():
    validate_profile(
        {"profile": "p", "stages": [_valid_stage(gate="if_risk_above:medium")]}
    )

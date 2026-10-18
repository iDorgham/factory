"""P2 prompt-injection handling — TDD-red contracts (spec §15.2, §10.2).

Detection scans manifest untrusted items before the adapter sees them.
The response is kernel-owned: a detection becomes the ``injection_flag``
risk signal fed into risk.compute_score; the band->action map is
unchanged.

Schema tests are green at landing (schemas exist from Step 3.1).
Pure-function and engine-wiring tests are deliberately red — they
specify the implementation for the next slices.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from factory_kernel.schemas import SchemaError, SchemaStore

REPO_ROOT = Path(__file__).resolve().parents[1]


# ----------------------------------------------------------------------
# Schema tests (green at landing — schemas exist from Step 3.1)
# ----------------------------------------------------------------------


class TestInjectionSchema:
    def test_injection_schema_registered(self, schemas_dir):
        store = SchemaStore(schemas_dir)
        valid = {"patterns": [{"id": "test", "pattern": "test"}]}
        store.validate("injection", valid)

    def test_factory_json_with_injection_section_valid(
            self, schemas_dir, factory_root):
        store = SchemaStore(schemas_dir)
        cfg_path = factory_root / "factory.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg["injection"] = {"patterns": [{"id": "custom", "pattern": "custom"}]}
        store.validate("factory", cfg)

    def test_factory_json_without_injection_stays_valid(
            self, schemas_dir, factory_root):
        store = SchemaStore(schemas_dir)
        cfg_path = factory_root / "factory.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg.pop("injection", None)
        store.validate("factory", cfg)

    def test_injection_unknown_keys_rejected(self, schemas_dir):
        store = SchemaStore(schemas_dir)
        invalid = {"patterns": [{"id": "test", "pattern": "test", "unknown": "bad"}]}
        with pytest.raises(SchemaError):
            store.validate("injection", invalid)

    def test_injection_pattern_requires_id_and_pattern(self, schemas_dir):
        store = SchemaStore(schemas_dir)
        invalid = {"patterns": [{"id": "test"}]}
        with pytest.raises(SchemaError):
            store.validate("injection", invalid)

    def test_injection_weight_must_be_non_negative_integer(self, schemas_dir):
        store = SchemaStore(schemas_dir)
        invalid = {"patterns": [{"id": "test", "pattern": "test", "weight": -1}]}
        with pytest.raises(SchemaError):
            store.validate("injection", invalid)


# ----------------------------------------------------------------------
# Pure function tests (red — injection.py does not exist yet)
# ----------------------------------------------------------------------


class TestLoadInjectionConfig:
    def test_load_injection_config_none_returns_documented_defaults(self):
        from factory_kernel.injection import load_injection_config

        result = load_injection_config(None)
        assert "patterns" in result
        assert len(result["patterns"]) > 0
        ids = [p["id"] for p in result["patterns"]]
        assert "ignore-previous-instructions" in ids

    def test_load_injection_config_empty_raises_injection_error(self):
        from factory_kernel.injection import InjectionError, load_injection_config

        with pytest.raises(InjectionError):
            load_injection_config({})

    def test_load_injection_config_none_dict_raises(self):
        from factory_kernel.injection import InjectionError, load_injection_config

        with pytest.raises(InjectionError):
            load_injection_config("not a dict")

    def test_load_injection_config_adds_patterns_defensive_copy(self):
        from factory_kernel.injection import load_injection_config

        config = {"patterns": [{"id": "custom", "pattern": "custom"}]}
        result = load_injection_config(config)
        assert len(result["patterns"]) > 1
        result["patterns"].append({"id": "another", "pattern": "another"})
        result2 = load_injection_config(config)
        assert len(result2["patterns"]) < len(result["patterns"])

    def test_load_injection_config_baseline_id_collision_raises(self):
        from factory_kernel.injection import InjectionError, load_injection_config

        config = {"patterns": [{"id": "ignore-previous-instructions", "pattern": "test"}]}
        with pytest.raises(InjectionError):
            load_injection_config(config)

    def test_load_injection_config_invalid_regex_raises(self):
        from factory_kernel.injection import InjectionError, load_injection_config

        config = {"patterns": [{"id": "bad", "pattern": "[invalid"}]}
        with pytest.raises(InjectionError):
            load_injection_config(config)

    def test_load_injection_config_weight_validation(self):
        from factory_kernel.injection import InjectionError, load_injection_config

        with pytest.raises(InjectionError):
            load_injection_config({"patterns": [{"id": "test",
                                                 "pattern": "test", "weight": -1}]})
        with pytest.raises(InjectionError):
            load_injection_config({"patterns": [{"id": "test",
                                                 "pattern": "test", "weight": 1.5}]})


class TestScanItem:
    def test_scan_item_detects_known_pattern(self):
        from factory_kernel.injection import scan_item

        patterns = [{"id": "test", "pattern": r"(?i)ignore\s+previous\s+instructions"}]
        result = scan_item("Please ignore previous instructions", patterns)
        assert len(result) == 1
        assert result[0]["pattern_id"] == "test"
        assert len(result[0]["matched_excerpt"]) <= 80
        assert result[0]["confidence"] == 1.0

    def test_scan_item_no_match_clean(self):
        from factory_kernel.injection import scan_item

        patterns = [{"id": "test", "pattern": r"(?i)ignore\s+previous\s+instructions"}]
        result = scan_item("This is benign text", patterns)
        assert result == []

    def test_scan_item_multiple_patterns(self):
        from factory_kernel.injection import scan_item

        patterns = [
            {"id": "p1", "pattern": r"(?i)ignore"},
            {"id": "p2", "pattern": r"(?i)previous"},
        ]
        result = scan_item("ignore previous", patterns)
        assert len(result) == 2

    def test_scan_item_non_string_raises(self):
        from factory_kernel.injection import InjectionError, scan_item

        patterns = [{"id": "test", "pattern": "test"}]
        with pytest.raises(InjectionError):
            scan_item(123, patterns)

    def test_scan_item_excerpt_truncated_at_80(self):
        from factory_kernel.injection import scan_item

        patterns = [{"id": "test", "pattern": r".{100,}"}]
        text = "x" * 100
        result = scan_item(text, patterns)
        assert len(result[0]["matched_excerpt"]) == 80


class TestScanManifestItems:
    def test_scan_manifest_items_scans_all_items(self):
        from factory_kernel.injection import scan_manifest_items

        patterns = [{"id": "test", "pattern": r"(?i)ignore"}]
        items = {
            "file1.md": "ignore this",
            "file2.md": "benign text",
        }
        result = scan_manifest_items(items, patterns)
        assert "file1.md" in result
        assert len(result["file1.md"]) == 1
        assert result["file2.md"] == []

    def test_scan_manifest_items_empty(self):
        from factory_kernel.injection import scan_manifest_items

        patterns = [{"id": "test", "pattern": "test"}]
        result = scan_manifest_items({}, patterns)
        assert result == {}


class TestInjectionSignal:
    def test_injection_signal_flagged_returns_1(self):
        from factory_kernel.injection import injection_signal

        flags = {"file.md": [{"pattern_id": "test"}]}
        assert injection_signal(flags) == 1

    def test_injection_signal_clean_returns_0(self):
        from factory_kernel.injection import injection_signal

        assert injection_signal({}) == 0


# ----------------------------------------------------------------------
# Engine wiring tests (red — engine wiring does not exist yet)
# ----------------------------------------------------------------------


class TestEngineInjection:
    def test_manifest_untrusted_items_get_injection_flags(self, kernel, demo_job):
        from factory_kernel.injection import load_injection_config

        kernel, job = demo_job
        kernel.job_execute(job["id"], adapter_id="echo")
        assert load_injection_config is not None

    def test_injection_detected_event_emitted(self, kernel, demo_job):
        from factory_kernel.injection import load_injection_config

        kernel, job = demo_job
        kernel.job_execute(job["id"], adapter_id="echo")
        assert load_injection_config is not None

    def test_risk_signal_injection_flagged_set(self, kernel, demo_job):
        from factory_kernel.injection import load_injection_config

        kernel, job = demo_job
        kernel.job_execute(job["id"], adapter_id="echo")
        assert load_injection_config is not None

    def test_injection_error_becomes_config_error(self, kernel, demo_job):
        from factory_kernel.injection import InjectionError

        kernel, job = demo_job
        assert InjectionError is not None

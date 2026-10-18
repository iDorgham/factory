"""Prompt-injection detection — pure kernel functions (P2 injection handling).

Spec §15.2 threat model: untrusted content is wrapped and labeled as data in
the manifest; agents have no ambient authority to act on instructions inside
it. This module detects injection patterns in untrusted manifest items.

Detection is configurable (baseline + operator-added patterns); the *response*
is kernel-owned: a detection becomes the ``injection_flag`` risk signal fed
into risk.compute_score, and the existing band->action map decides what
happens next.

Pure module: no subprocesses, no file I/O, no LLM, no network.
"""
from __future__ import annotations

import re

# Kernel-owned baseline patterns. Config may ADD patterns but cannot override
# or remove baseline ids (load_injection_config enforces this).
DEFAULT_PATTERNS = [
    {
        "id": "ignore-previous-instructions",
        "pattern": r"(?i)ignore\s+previous\s+instructions",
        "weight": 0,
    },
    {
        "id": "system-prompt-leak",
        "pattern": r"(?i)(?:reveal|show)\s+(?:your|the)\s+system\s+prompt",
        "weight": 0,
    },
    {
        "id": "do-not-follow",
        "pattern": r"(?i)do\s+not\s+follow\s+(?:previous|prior)",
        "weight": 0,
    },
    {
        "id": "pretend-to-be",
        "pattern": (
            r"(?i)pretend\s+to\s+be\s+(?:a\s+)?(?:different|another)"
            r"\s+(?:assistant|ai|model)"
        ),
        "weight": 0,
    },
]

BASELINE_IDS = frozenset(p["id"] for p in DEFAULT_PATTERNS)

EXCERPT_LIMIT = 80


class InjectionError(Exception):
    """Injection configuration is invalid, or scan input is malformed."""


def load_injection_config(section) -> dict:
    """Validate and return a defensive copy of the injection config.

    ``None`` (no ``injection`` key in factory.json) -> documented defaults
    (baseline patterns). A present-but-empty section raises InjectionError —
    an explicitly broken config never silently rescues itself back to the
    defaults; doctor names it as the authoritative error.

    Config patterns are additive to baseline patterns. A config pattern id
    colliding with a baseline id raises InjectionError (kernel-owned patterns
    cannot be overridden). Invalid regex, negative weight, or float weight
    raise InjectionError.
    """
    if section is None:
        return {
            "patterns": [
                {"id": p["id"], "pattern": p["pattern"], "weight": p["weight"]}
                for p in DEFAULT_PATTERNS
            ],
        }
    if not isinstance(section, dict) or not section:
        raise InjectionError(
            "injection config must be a non-empty mapping")

    raw_patterns = section.get("patterns")
    if not isinstance(raw_patterns, list) or not raw_patterns:
        raise InjectionError(
            "'patterns' must be a non-empty list of pattern objects")

    # Baseline patterns are always present; config patterns are additive.
    patterns: list[dict] = [
        {"id": p["id"], "pattern": p["pattern"], "weight": p["weight"]}
        for p in DEFAULT_PATTERNS
    ]
    seen_ids: set[str] = set(BASELINE_IDS)
    for entry in raw_patterns:
        if not isinstance(entry, dict):
            raise InjectionError(
                f"invalid pattern entry: {entry!r}")
        pid = entry.get("id")
        pattern = entry.get("pattern")
        if not isinstance(pid, str) or not pid:
            raise InjectionError(
                "pattern entry requires a non-empty 'id' string")
        if not isinstance(pattern, str) or not pattern:
            raise InjectionError(
                "pattern entry requires a non-empty 'pattern' string")
        if pid in seen_ids:
            raise InjectionError(
                f"pattern id '{pid}' is kernel-owned and cannot be overridden")
        try:
            re.compile(pattern)
        except re.error as e:
            raise InjectionError(
                f"pattern '{pid}' has invalid regex '{pattern}': {e}")
        weight = entry.get("weight", 0)
        if isinstance(weight, bool) or not isinstance(weight, int) or weight < 0:
            raise InjectionError(
                f"pattern '{pid}' weight must be a non-negative integer, "
                f"got {weight!r}")

        seen_ids.add(pid)
        patterns.append({
            "id": pid,
            "pattern": pattern,
            "weight": weight,
        })

    return {"patterns": patterns}


def scan_item(text: str, patterns: list[dict]) -> list[dict]:
    """Scan text for injection patterns (pure).

    Returns a list of flags, each with ``pattern_id``, ``matched_excerpt``
    (truncated to 80 chars), and ``confidence`` (1.0). Returns ``[]`` when
    no pattern matches.

    Non-string text or non-list patterns raises InjectionError.
    """
    if not isinstance(text, str):
        raise InjectionError("text must be a string")
    if not isinstance(patterns, list):
        raise InjectionError("patterns must be a list")

    flags: list[dict] = []
    for entry in patterns:
        if not isinstance(entry, dict):
            continue
        pattern_str = entry.get("pattern")
        if not isinstance(pattern_str, str):
            continue
        match = re.search(pattern_str, text)
        if match is None:
            continue
        excerpt = match.group(0)
        if len(excerpt) > EXCERPT_LIMIT:
            excerpt = excerpt[:EXCERPT_LIMIT]
        flags.append({
            "pattern_id": entry.get("id", ""),
            "matched_excerpt": excerpt,
            "confidence": 1.0,
        })
    return flags


def scan_manifest_items(
        items: dict[str, str], patterns: list[dict]) -> dict[str, list[dict]]:
    """Scan a dict of {path: content} for injection patterns (pure).

    Returns {path: [flags]}. Empty items returns {}.
    """
    if not isinstance(items, dict):
        raise InjectionError("items must be a mapping")
    result: dict[str, list[dict]] = {}
    for path, content in items.items():
        result[path] = scan_item(content, patterns)
    return result


def injection_signal(flags_by_item: dict[str, list[dict]]) -> int:
    """Derive the risk signal from scan flags (pure).

    Returns 1 if any item has flags, 0 otherwise.
    """
    if not isinstance(flags_by_item, dict):
        raise InjectionError("flags_by_item must be a mapping")
    for flags in flags_by_item.values():
        if isinstance(flags, list) and len(flags) > 0:
            return 1
    return 0

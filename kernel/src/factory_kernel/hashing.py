"""Hashing utilities for event chaining and content integrity."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def event_hash(event: dict) -> str:
    """Canonical hash of an event (excluding the 'prev' field itself for chain)."""
    # We hash the whole event including prev so the chain is self-describing.
    canonical = json.dumps(event, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return sha256_hex(canonical)


def content_hash(path_or_bytes: str | bytes) -> str:
    if isinstance(path_or_bytes, str):
        with open(path_or_bytes, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    return hashlib.sha256(path_or_bytes).hexdigest()

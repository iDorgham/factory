"""Minimal ULID generator (Crockford base32, 26 chars)."""
from __future__ import annotations

import os
import time
from typing import Optional

# Crockford's Base32 alphabet (no I, L, O, U)
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode(n: int, length: int) -> str:
    chars = []
    for _ in range(length):
        n, rem = divmod(n, 32)
        chars.append(ALPHABET[rem])
    return "".join(reversed(chars))


def new_ulid(timestamp_ms: Optional[int] = None) -> str:
    """Generate a new ULID. Timestamp is milliseconds since Unix epoch."""
    if timestamp_ms is None:
        timestamp_ms = int(time.time() * 1000)
    # 48-bit timestamp
    ts_part = _encode(timestamp_ms, 10)
    # 80-bit randomness
    rand_bytes = os.urandom(10)
    rand_int = int.from_bytes(rand_bytes, "big")
    rand_part = _encode(rand_int, 16)
    return ts_part + rand_part


def is_ulid(s: str) -> bool:
    if len(s) != 26:
        return False
    return all(c in ALPHABET for c in s.upper())

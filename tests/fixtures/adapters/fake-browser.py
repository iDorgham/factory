#!/usr/bin/env python3
"""Fake headless browser for visual-capture tests (hermetic, no browser).

Mimics the argv contract of headless Chromium:

    <browser> --headless --disable-gpu --hide-scrollbars
        --user-data-dir=... --window-size=W,H --screenshot=<png>
        [--blink-settings=preferredColorScheme=<v>] <url>

Semantics (deliberately the INVERSE of the Edge build on the dev machine, so
the probe logic is exercised for real):
- preferredColorScheme=0 → white (light)
- preferredColorScheme=1 → near-black (dark)
- no flag (default)      → white (light)

If ``FACTORY_FAKE_BROWSER_LOG`` is set, each invocation appends a compact
JSON line there (url, viewport, color_scheme) for test assertions.

If the URL contains ``/missing`` and ``--screenshot-point-at`` is absent,
nothing is written (simulates a broken browser) unless ``FAILMODE`` env is
set to "crash", in which case the process exits non-zero.
"""
from __future__ import annotations

import json
import os
import struct
import sys
import zlib
from pathlib import Path


def png_bytes(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    def chunk(t: bytes, d: bytes) -> bytes:
        crc = zlib.crc32(t + d) & 0xFFFFFFFF
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBB", width, height, 8, 2)
    px = bytes(rgb)
    raw = b"".join(b"\x00" + px * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main(argv: list[str]) -> int:
    screenshot = None
    viewport = "320x200"
    scheme = None
    url = ""
    for a in argv[1:]:
        if a.startswith("--screenshot="):
            screenshot = a.split("=", 1)[1]
        elif a.startswith("--window-size="):
            viewport = a.split("=", 1)[1].replace(",", "x")
        elif a.startswith("--blink-settings=preferredColorScheme="):
            scheme = a.rsplit("=", 1)[1]
        elif not a.startswith("--"):
            url = a
    w, h = (int(v) for v in viewport.split("x"))

    if os.environ.get("FACTORY_FAKE_BROWSER_LOG"):
        Path(os.environ["FACTORY_FAKE_BROWSER_LOG"]).open("a", encoding="utf-8").write(
            json.dumps({"url": url, "viewport": viewport,
                        "color_scheme": scheme}) + "\n")

    if os.environ.get("FACTORY_FAKE_BROWSER_FAIL") == "1":
        return 3
    if "/missing" in url:
        return 2  # missing page: no screenshot

    colors = {"0": (255, 255, 255), "1": (17, 17, 17)}
    rgb = colors.get(scheme, colors["0"])
    Path(screenshot).write_bytes(png_bytes(w, h, rgb))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

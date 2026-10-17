"""Real screenshot producer for the visual contract (`ADAPTERS.md` §7).

Captures the job's page with headless Chromium (Edge or Chrome, already on
Windows) — no new Python dependencies — and writes the attempt's
`outputs/visual.json` manifest. Data recorded by this script is real browser
output, never synthesized.

Usage (typically as the project's `visual` check; the kernel exports
`FACTORY_VISUAL_OUT` — the absolute attempt `outputs/` dir — and runs the
command with `cwd` = the job worktree)::

    python "<factory-root>/adapters/visual-capture/capture.py" --url index.html

Behavior:
- `--url` is a file name/path relative to the worktree (or an absolute path /
  file:// URL). Missing file target → a `skipped` manifest, exit 0 (no page
  to capture is not a failure — the check only collects evidence when a page
  exists); server URLs are unsupported in this slice.
- `--viewport WxH` may be repeated (default: 1280x800 and 390x844).
- `--theme light|dark` may be repeated (default: both). The dark flag
  (`--blink-settings=preferredColorScheme=<v>`) varies between Chromium
  builds, so this script pixel-probes a tiny light/dark page to learn the
  mapping for the browser it actually runs — never hardcoded.
- Manifest rules: an existing *synthetic* manifest is discarded when a real
  capture lands; an existing real manifest is merged (same viewport/theme
  overwritten). The output manifest is always `synthetic: false`.
- Browser discovery order: `--browser` / `FACTORY_VISUAL_BROWSER` env →
  Edge → Chrome (standard Windows install locations).
- Any capture that fails to produce a non-empty PNG → exit 1, no manifest
  update (honest failure).
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

DEFAULT_VIEWPORTS = ["1280x800", "390x844"]
DEFAULT_THEMES = ["light", "dark"]


def browser_candidates() -> list[str]:
    pf = os.environ.get("ProgramFiles", "")
    pfx86 = os.environ.get("ProgramFiles(x86)", "")
    local = os.environ.get("LOCALAPPDATA", "")
    return [
        pfx86 + r"\Microsoft\Edge\Application\msedge.exe",
        pf + r"\Microsoft\Edge\Application\msedge.exe",
        pf + r"\Google\Chrome\Application\chrome.exe",
        local + r"\Google\Chrome\Application\chrome.exe",
    ]


def find_browser(explicit: str = "") -> str:
    """Browser resolution order: explicit arg → env → candidates.

    An explicit value short-circuits discovery entirely (exists → use it,
    else fail loudly) so tests can pin a fake browser deterministically.
    """
    if explicit:
        return explicit if Path(explicit).is_file() else ""
    env = os.environ.get("FACTORY_VISUAL_BROWSER", "")
    if env:
        return env if Path(env).is_file() else ""
    return next((c for c in browser_candidates() if c and Path(c).is_file()),
                "")


def shoot(browser: str, url: str, png: Path, viewport: str,
          color_scheme: str | None = None) -> bool:
    """One headless capture; True iff a non-empty PNG lands at ``png``."""
    png.parent.mkdir(parents=True, exist_ok=True)
    if png.exists():
        png.unlink()
    profile = tempfile.mkdtemp(prefix="factory-visual-")
    w, h = viewport.split("x", 1)
    launcher = (sys.executable, browser) if browser.lower().endswith(".py") \
        else (browser,)
    cmd = [
        *launcher,
        "--headless", "--disable-gpu", "--hide-scrollbars",
        f"--user-data-dir={profile}", f"--window-size={w},{h}",
        f"--screenshot={png}", "--virtual-time-budget=4000",
    ]
    if color_scheme is not None:
        cmd.append(f"--blink-settings=preferredColorScheme={color_scheme}")
    cmd.append(url)
    try:
        subprocess.run(cmd, capture_output=True, check=False, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return png.is_file() and png.stat().st_size > 0


def _decode(png: Path) -> tuple[int, int, int, list[bytearray]]:
    """Decode a headless screenshot into (width, height, comps, rows)."""
    data = png.read_bytes()
    pos, idat, w = 8, b"", None
    h = None
    ctype = None
    while pos < len(data):
        ln, typ = struct.unpack(">I4s", data[pos:pos + 8])
        chunk = data[pos + 8:pos + 8 + ln]
        pos += 8 + ln + 4
        if typ == b"IHDR":
            w, h, _bd, ctype = struct.unpack(">IIBB", chunk[:10])
        elif typ == b"IDAT":
            idat += chunk
        elif typ == b"IEND":
            break
    raw = zlib.decompress(idat)
    comp = {0: 1, 2: 3, 4: 2, 6: 4}[ctype]
    stride = w * comp
    prev: bytearray | None = None
    i, rows = 0, []
    while i < len(raw):
        f = raw[i]
        i += 1
        row = bytearray(raw[i:i + stride])
        i += stride
        if f == 1:
            for j in range(comp, stride):
                row[j] = (row[j] + row[j - comp]) & 0xFF
        elif f == 2:
            for j in range(stride):
                row[j] = (row[j] + (prev[j] if prev else 0)) & 0xFF
        elif f == 3:
            for j in range(stride):
                a = row[j - comp] if j >= comp else 0
                b = prev[j] if prev else 0
                row[j] = (row[j] + ((a + b) >> 1)) & 0xFF
        elif f == 4:
            for j in range(stride):
                a = row[j - comp] if j >= comp else 0
                b = prev[j] if prev else 0
                c = prev[j - comp] if (prev and j >= comp) else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                row[j] = (row[j] + pr) & 0xFF
        rows.append(row)
        prev = row
    return w, h, comp, rows


def pixel_of(png: Path, x: int = 8, y: int = 8) -> tuple[int, int, int]:
    """Decode one pixel of a headless screenshot (8-bit grayscale/RGB/RGBA)."""
    w, _h, comp, rows = _decode(png)
    off = comp * x
    return tuple(rows[y][off:off + comp])


PROBE_HTML = (
    "<!doctype html><html><head><style>html,body{margin:0;background:#fff}"
    "@media (prefers-color-scheme:dark){html,body{background:#111}}</style>"
    "</head><body></body></html>"
)


def learn_dark_value(browser: str) -> str:
    """Pixel-probe which preferredColorScheme value renders a dark page.

    The probe page is white in light mode and near-black in dark mode; the
    value whose capture comes out dark is this browser's dark mapping.
    Returns "" when inconclusive (then dark capture is skipped with a note —
    never guessed).
    """
    probe_dir = Path(tempfile.mkdtemp(prefix="factory-visual-probe-"))
    probe_html = probe_dir / "probe.html"
    probe_html.write_text(PROBE_HTML, encoding="utf-8")
    for value in ("0", "1"):
        png = probe_dir / f"v{value}.png"
        if not shoot(browser, probe_html.resolve().as_uri(), png, "320x200",
                     color_scheme=value):
            continue
        try:
            r, g, b = pixel_of(png)
        except (OSError, KeyError, zlib.error, ValueError):
            continue
        if r + g + b < 200:
            return value
    return ""


def diff_pct(png_a: Path, png_b: Path, threshold: int = 8) -> float | None:
    """Share (%) of pixels that visibly differ between two screenshots.

    A pixel counts as changed when any decoded channel differs by more than
    ``threshold`` (0–255) — noise-tolerant. Two same-size screenshots only:
    different dimensions or an unreadable PNG → None, so callers never get a
    guessed number. O(pixels) pure-Python decode; screenshots are small.
    """
    try:
        w1, h1, c1, rows1 = _decode(png_a)
        w2, h2, c2, rows2 = _decode(png_b)
    except (OSError, KeyError, zlib.error, ValueError):
        return None
    if (w1, h1) != (w2, h2):
        return None
    comp = min(c1, c2)
    total = w1 * h1
    if total == 0 or comp <= 0:
        return None
    changed = 0
    for row1, row2 in zip(rows1, rows2):
        b1 = bytes(row1[: comp * w1])
        b2 = bytes(row2[: comp * w2])
        for i in range(w1):
            px1 = b1[i * comp:(i + 1) * comp]
            px2 = b2[i * comp:(i + 1) * comp]
            if any(abs(a - b) > threshold for a, b in zip(px1, px2)):
                changed += 1
    return round(changed * 100.0 / total, 1)


def learn_light_value(browser: str, dark_value: str) -> str | None:
    """Color-scheme value to force for light captures.

    Returns the opposite of the probed dark value when the probe worked.
    Only when the probe is inconclusive (dark not available), light capture
    falls back to the browser default (None).
    """
    if dark_value in ("0", "1"):
        return "0" if dark_value == "1" else "1"
    return None


def _previous_manifest(manifest_path: Path) -> Path | None:
    """Sibling attempt dir: <job>/stages/<stage>/attempt-N → attempt-N-1."""
    import re

    attempt_dir = os.environ.get("FACTORY_ATTEMPT_DIR", "")
    if attempt_dir:
        m = re.fullmatch(r"attempt-(\d+)", Path(attempt_dir).name)
        if m and int(m.group(1)) > 1:
            prev = (Path(attempt_dir).parent
                    / f"attempt-{int(m.group(1)) - 1}" / "outputs"
                    / "visual.json")
            if prev.is_file():
                return prev
    return None


def annotate_diffs(entries: list[dict], manifest_path: Path,
                   previous: str) -> None:
    """Attach ``changed_pct`` to entries with a comparable previous capture."""
    prev_manifest = (Path(previous).absolute()
                     if previous != "auto" else _previous_manifest(manifest_path))
    if prev_manifest is None or not prev_manifest.is_file():
        return
    try:
        prev = json.loads(prev_manifest.read_text(encoding="utf-8"))
        prev_entries = prev.get("entries") or []
    except (ValueError, OSError):
        return
    prev_png = {
        (str(e.get("viewport")), str(e.get("theme"))): prev_manifest.parent / str(e.get("file"))
        for e in prev_entries if isinstance(e, dict) and e.get("file")
    }
    for e in entries:
        key = (e["viewport"], e["theme"])
        other = prev_png.get(key)
        if other is None or not other.is_file():
            continue
        mine = manifest_path.parent / e["file"]
        if not mine.is_file():
            continue
        pct = diff_pct(mine, other)
        if pct is not None:
            e["changed_pct"] = pct


def merge_manifest(path: Path, entries: list[dict], skipped: str = "") -> None:
    """Write visual.json: discard synthetic legacy, merge real entries."""
    existing: list[dict] = []
    if path.is_file():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(old, dict) and old.get("synthetic") is not True:
                kept = old.get("entries") or []
                if isinstance(kept, list):
                    existing = [e for e in kept if isinstance(e, dict)]
        except (ValueError, OSError):
            pass
    fresh = {
        f"{e['viewport']}@{e['theme']}": e
        for e in existing + entries
    }
    merged: dict = {"synthetic": False, "entries": list(fresh.values())}
    if skipped:
        merged["skipped"] = skipped
    manifest_path = path
    manifest_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Factory visual capture (§7)")
    ap.add_argument("--url", required=True,
                    help="Page to capture: file name relative to the "
                         "worktree (cwd), an absolute path, or a file:// URL")
    ap.add_argument("--viewport", action="append",
                    help="WxH; repeatable (default 1280x800, 390x844)")
    ap.add_argument("--theme", action="append",
                    help="light or dark; repeatable (default both)")
    ap.add_argument("--manifest", default=None,
                    help="visual.json path; default $FACTORY_VISUAL_OUT/"
                         "visual.json")
    ap.add_argument("--out-dir", default=None,
                    help="PNG dir; default $FACTORY_VISUAL_OUT/visual")
    ap.add_argument("--browser", default=None,
                    help="Browser executable (default: auto-discover)")
    ap.add_argument("--diff-previous", nargs="?", const="auto", default=None,
                    metavar="VISUAL_JSON",
                    help="Annotate entries with changed_pct vs. the previous "
                         "attempt's captures. Without a value, the previous "
                         "attempt dir is derived from $FACTORY_ATTEMPT_DIR "
                         "(attempt-N → attempt-(N-1)).")
    args = ap.parse_args(argv)

    visual_out = Path(
        os.environ.get("FACTORY_VISUAL_OUT")
        or (Path.cwd() / "outputs")
    ).absolute()
    out_dir = Path(args.out_dir).absolute() if args.out_dir \
        else visual_out / "visual"
    manifest_path = Path(args.manifest).absolute() if args.manifest \
        else visual_out / "visual.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    url = args.url
    if not (url.startswith("file://") or url.startswith("http://")
            or url.startswith("https://")):
        tpath = Path(url)
        if not tpath.is_absolute():
            tpath = Path.cwd() / tpath
        if not tpath.is_file():
            merge_manifest(manifest_path, [],
                           skipped=f"target not found: {args.url}")
            return 0
        url = tpath.resolve().as_uri()
    else:
        # Only file targets are capturable without a live server.
        merge_manifest(manifest_path, [],
                       skipped=f"unsupported target: {args.url}")
        return 0

    browser = find_browser(args.browser or "")
    if not browser:
        print("capture: no headless browser found "
              "(set --browser or FACTORY_VISUAL_BROWSER)", file=sys.stderr)
        return 1

    viewports = args.viewport or list(DEFAULT_VIEWPORTS)
    themes = args.theme or list(DEFAULT_THEMES)

    dark_value = ""
    if "dark" in themes:
        dark_value = learn_dark_value(browser)

    entries: list[dict] = []
    for viewport in viewports:
        for theme in themes:
            if theme == "dark" and not dark_value:
                print("capture: dark-mode flag inconclusive for this "
                      "browser; dark screenshots skipped", file=sys.stderr)
                continue
            png = out_dir / f"{viewport}-{theme}.png"
            if theme == "light":
                # Headless Chromium builds disagree on the default color
                # scheme (some render dark with no flag). If the probe
                # worked, force the *opposite* of the dark value; only a
                # fresh browser with no probe result may fall back to no
                # flag for light mode.
                probe_learner = learn_light_value(browser, dark_value)
                color_scheme = probe_learner
            else:
                color_scheme = dark_value
            ok = shoot(browser, url, png, viewport,
                       color_scheme=color_scheme)
            if not ok:
                print(f"capture failed: {viewport} {theme}",
                      file=sys.stderr)
                return 1
            entries.append({
                "viewport": viewport,
                "theme": theme,
                "file": f"visual/{viewport}-{theme}.png",
            })

    if args.diff_previous and entries:
        annotate_diffs(entries, manifest_path, args.diff_previous)

    merge_manifest(manifest_path, entries)
    return 0


if __name__ == "__main__":
    sys.exit(main())

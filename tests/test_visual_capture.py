"""Tests for the real visual capture producer (`ADAPTERS.md` §7).

The producer (`adapters/visual-capture/capture.py`) is tested hermetically
with `tests/fixtures/adapters/fake-browser.py`, a stdlib headless-browser
shim whose light/dark mapping is the *inverse* of the dev machine's Edge, so
the runtime pixel-probe logic is genuinely exercised.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from factory_kernel.checks import run_one

REPO_ROOT = Path(__file__).resolve().parents[1]
CAPTURE = REPO_ROOT / "adapters" / "visual-capture" / "capture.py"
FAKE_BROWSER = REPO_ROOT / "tests" / "fixtures" / "adapters" / "fake-browser.py"


def _load_capture():
    spec = importlib.util.spec_from_file_location("capture", CAPTURE)
    capture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(capture)
    return capture


@pytest.fixture
def browser(monkeypatch):
    monkeypatch.setenv("FACTORY_VISUAL_BROWSER", str(FAKE_BROWSER))
    return monkeypatch


def _small_page(tmp_path: Path, name: str = "index.html") -> Path:
    page = tmp_path / name
    page.write_text(
        "<!doctype html><title>t</title><h1>hello</h1>", encoding="utf-8")
    return page


def _out(tmp_path: Path):
    out = tmp_path / "outputs"
    out.mkdir()
    return out


def test_probe_learns_dark_value(browser):
    capture = _load_capture()
    # The fake browser maps 0 → light, 1 → dark (inverse of the dev's Edge):
    # the probe must discover the *actual* mapping, not assume one.
    assert capture.learn_dark_value(str(FAKE_BROWSER)) == "1"
    # Inconclusive probe: no dark mapping, light falls back to the default.
    assert capture.learn_light_value("x", "") is None
    assert capture.learn_light_value("x", "0") == "1"
    # An explicit browser short-circuits discovery (exists → the value;
    # missing → empty, no accidental machine-browser fallback).
    assert capture.find_browser(str(FAKE_BROWSER)) == str(FAKE_BROWSER)
    assert capture.find_browser("does-not-exist.exe") == ""


def test_capture_writes_real_pngs_and_manifest(browser, tmp_path):
    capture = _load_capture()
    page = _small_page(tmp_path)
    out = _out(tmp_path)
    log = tmp_path / "log.ndjson"
    browser.setenv("FACTORY_VISUAL_OUT", str(out))
    browser.setenv("FACTORY_FAKE_BROWSER_LOG", str(log))

    rc = capture.main(["--url", str(page)])
    assert rc == 0

    manifest = json.loads((out / "visual.json").read_text(encoding="utf-8"))
    assert manifest["synthetic"] is False
    assert [(e["viewport"], e["theme"]) for e in manifest["entries"]] == [
        ("1280x800", "light"), ("1280x800", "dark"),
        ("390x844", "light"), ("390x844", "dark"),
    ]
    for e in manifest["entries"]:
        png = out / e["file"]
        assert png.is_file() and png.stat().st_size > 100

    # The probe finds the dark flags; light and dark capture calls are forced
    # explicitly — both theme values appear in the browser's argv.
    calls = [json.loads(line)
             for line in log.read_text(encoding="utf-8").splitlines()]
    schemes = [c["color_scheme"] for c in calls if c["color_scheme"]]
    assert set(schemes) == {"0", "1"}


def test_capture_forces_both_themes_differently(browser, tmp_path):
    """Light and dark pixels must differ (the default render is not trusted)."""
    capture = _load_capture()
    page = _small_page(tmp_path)
    out = _out(tmp_path)
    browser.setenv("FACTORY_VISUAL_OUT", str(out))

    assert capture.main(["--url", str(page)]) == 0

    light = capture.pixel_of(out / "visual" / "1280x800-light.png")
    dark = capture.pixel_of(out / "visual" / "1280x800-dark.png")
    assert sum(light) > 600 and sum(dark) < 200
    # The mapping must be learned: light is NOT the scheme-0 default here.
    assert light == (255, 255, 255) and dark == (17, 17, 17)


def test_capture_discards_synthetic_manifest(browser, tmp_path):
    capture = _load_capture()
    page = _small_page(tmp_path)
    out = _out(tmp_path)
    out.joinpath("visual.json").write_text(json.dumps({
        "synthetic": True,
        "entries": [{"viewport": "1x1", "theme": "light", "file": "a.png"}],
    }), encoding="utf-8")
    browser.setenv("FACTORY_VISUAL_OUT", str(out))

    assert capture.main(["--url", str(page)]) == 0

    manifest = json.loads(out.joinpath("visual.json").read_text("utf-8"))
    assert manifest["synthetic"] is False
    assert [e["viewport"] for e in manifest["entries"]] == [
        "1280x800", "1280x800", "390x844", "390x844"]


def test_capture_keeps_previous_real_entries(browser, tmp_path):
    capture = _load_capture()
    page = _small_page(tmp_path)
    out = _out(tmp_path)
    (out / "visual").mkdir()
    (out / "visual" / "1920x1080-light.png").write_bytes(
        b"\x89PNG\r\n\x1a\n" + b"0" * 400)
    out.joinpath("visual.json").write_text(json.dumps({
        "synthetic": False,
        "entries": [{"viewport": "1920x1080", "theme": "light", "file":
                     "visual/1920x1080-light.png"}],
    }), encoding="utf-8")
    browser.setenv("FACTORY_VISUAL_OUT", str(out))

    assert capture.main(["--url", str(page), "--viewport", "800x600",
                         "--theme", "light"]) == 0

    manifest = json.loads(out.joinpath("visual.json").read_text("utf-8"))
    ports = [(e["viewport"], e["theme"]) for e in manifest["entries"]]
    assert ("1920x1080", "light") in ports and ("800x600", "light") in ports


def test_missing_page_is_skipped_not_failed(browser, tmp_path):
    capture = _load_capture()
    out = _out(tmp_path)
    log = tmp_path / "log.ndjson"
    browser.setenv("FACTORY_VISUAL_OUT", str(out))
    browser.setenv("FACTORY_FAKE_BROWSER_LOG", str(log))

    rc = capture.main(["--url", "index.html"])  # does not exist
    assert rc == 0
    manifest = json.loads(out.joinpath("visual.json").read_text("utf-8"))
    assert manifest["entries"] == []
    assert "not found" in manifest["skipped"]
    assert not log.exists()  # the browser was never launched


def test_broken_capture_fails_honestly(browser, tmp_path):
    capture = _load_capture()
    page = _small_page(tmp_path)
    out = _out(tmp_path)
    browser.setenv("FACTORY_VISUAL_OUT", str(out))
    browser.setenv("FACTORY_FAKE_BROWSER_FAIL", "1")

    rc = capture.main(["--url", str(page)])
    assert rc == 1  # no manifest is written pretending to be evidence
    assert not out.joinpath("visual.json").exists()


def test_server_urls_unsupported_skipped(browser, tmp_path):
    capture = _load_capture()
    out = _out(tmp_path)
    browser.setenv("FACTORY_VISUAL_OUT", str(out))

    rc = capture.main(["--url", "http://localhost:8321/"])
    assert rc == 0
    manifest = json.loads(out.joinpath("visual.json").read_text("utf-8"))
    assert manifest["entries"] == []
    assert "unsupported" in manifest["skipped"]


def test_pixel_of_decodes_png(tmp_path):
    capture = _load_capture()

    def chunk(t: bytes, d: bytes) -> bytes:
        return (struct_pack(len(d)) + t
                + d + struct_pack(crc32(t + d)))

    import struct
    import zlib

    def struct_pack(n: int) -> bytes:
        return struct.pack(">I", n)

    def crc32(b: bytes) -> int:
        return zlib.crc32(b) & 0xFFFFFFFF

    ihdr = struct.pack(">IIBB", 4, 3, 8, 2)
    px = bytes((250, 10, 5))
    raw = b"".join(b"\x00" + px * 4 for _ in range(3))
    png = tmp_path / "p.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                    + chunk(b"IDAT", zlib.compress(raw, 9))
                    + chunk(b"IEND", b""))
    assert capture.pixel_of(png, x=3, y=2) == (250, 10, 5)


def test_engine_exports_visual_env_to_checks(kernel):
    """The engine hands checks the attempt paths via FACTORY_* env vars."""
    kernel.project_create("v", mode="solo", domain="web")
    checks_path = kernel.projects_dir / "v" / "checks.json"
    log = kernel.root / "env-log.txt"
    keep = ["lint", "typecheck", "unit", "build", "a11y"]
    checks = {k: {"cmd": "echo 'placeholder'", "required": False}
              for k in keep}
    checks["visual"] = {
        "cmd": f'cmd /c "echo %FACTORY_VISUAL_OUT% > \"{log}\""',
        "required": False,
    }
    checks_path.write_text(json.dumps(checks), encoding="utf-8")
    job = kernel.job_run("v", "Env export probe")
    kernel.job_execute(job["id"])

    job_dir = kernel._find_job_dir(job["id"])
    attempt = job_dir / "stages" / "03-verify" / "attempt-1"
    logged = log.read_text(encoding="utf-8").strip()
    assert Path(logged.strip()).resolve() == \
        (attempt / "outputs").absolute().resolve()


def test_project_default_visual_check_is_the_real_producer(kernel):
    kernel.project_create("v", mode="solo", domain="web")
    checks = (kernel.projects_dir / "v" / "checks.json").read_text(
        encoding="utf-8")
    assert "visual-capture" in checks
    assert "--url index.html" in checks


def test_run_one_honours_extra_env(tmp_path):
    (tmp_path / "out.tmp").write_text("", encoding="utf-8")
    result = run_one(
        "envcheck",
        {"cmd": f'echo %FACTORY_TEST_VAR% > "{tmp_path / "out.tmp"}"',
         "required": True},
        tmp_path,
        timeout=30,
        extra_env={"FACTORY_TEST_VAR": "probe-value"},
    )
    assert result.passed
    assert "probe-value" in (tmp_path / "out.tmp").read_text(
        encoding="utf-8")


# ----------------------------------------------------------------------
# Visual diff (changed_pct vs. the previous attempt)
# ----------------------------------------------------------------------

def _solid_png(path: Path, w: int, h: int, rgb: tuple[int, int, int]) -> None:
    import struct
    import zlib

    def chunk(t: bytes, d: bytes) -> bytes:
        return (struct.pack(">I", len(d)) + t + d
                + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBB", w, h, 8, 2)
    px = bytes(rgb)
    raw = b"".join(b"\x00" + px * w for _ in range(h))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                     + chunk(b"IDAT", zlib.compress(raw, 9))
                     + chunk(b"IEND", b""))


def test_diff_pct_share_of_changed_pixels(tmp_path):
    capture = _load_capture()
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    _solid_png(a, 4, 1, (255, 255, 255))
    _solid_png(b, 4, 1, (255, 255, 255))
    assert capture.diff_pct(a, b) == 0.0
    # one channel differs by more than the noise threshold → changed pixel
    _solid_png(b, 4, 1, (250, 255, 255))  # delta 5: below threshold
    assert capture.diff_pct(a, b) == 0.0
    _solid_png(b, 4, 1, (250, 10, 5))
    assert capture.diff_pct(a, b) == 100.0


def test_diff_pct_refuses_to_guess(tmp_path):
    capture = _load_capture()
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    _solid_png(a, 4, 1, (1, 2, 3))
    _solid_png(b, 2, 1, (1, 2, 3))  # different dimensions
    assert capture.diff_pct(a, b) is None
    assert capture.diff_pct(tmp_path / "no.png", a) is None


def test_diff_previous_auto_from_attempt_dir(tmp_path, monkeypatch):
    capture = _load_capture()
    page = _small_page(tmp_path, "page.html")
    job = tmp_path / "job"
    prev_out = job / "stages" / "03-verify" / "attempt-1" / "outputs"
    out = job / "stages" / "03-verify" / "attempt-2" / "outputs"
    prev_out.mkdir(parents=True)
    (prev_out / "visual").mkdir()

    prev_png = prev_out / "visual" / "1280x800-light.png"
    _solid_png(prev_png, 1280, 800, (250, 10, 5))  # everything differs
    (prev_out / "visual.json").write_text(json.dumps({
        "synthetic": False,
        "entries": [{"viewport": "1280x800", "theme": "light",
                     "file": "visual/1280x800-light.png"}],
    }), encoding="utf-8")

    monkeypatch.setenv("FACTORY_VISUAL_BROWSER", str(FAKE_BROWSER))
    monkeypatch.setenv("FACTORY_VISUAL_OUT", str(out))
    monkeypatch.setenv("FACTORY_ATTEMPT_DIR", str(out.parent))

    assert capture.main(["--url", str(page), "--diff-previous"]) == 0

    manifest = json.loads(out.joinpath("visual.json").read_text("utf-8"))
    by_key = {(e["viewport"], e["theme"]): e for e in manifest["entries"]}
    assert by_key[("1280x800", "light")]["changed_pct"] == 100.0
    # no comparable previous capture → no invented diff number
    for key in [("1280x800", "dark"), ("390x844", "light"),
                ("390x844", "dark")]:
        assert "changed_pct" not in by_key[key]


def test_visual_evidence_passes_changed_pct_through(tmp_path):
    from factory_kernel.dashboard import _visual_evidence

    out = tmp_path / "job" / "stages" / "03-verify" / "attempt-1" / "outputs"
    out.mkdir(parents=True)
    (out / "visual").mkdir()
    _solid_png(out / "visual" / "p.png", 4, 1, (250, 10, 5))
    (out / "visual.json").write_text(json.dumps({
        "synthetic": False,
        "entries": [
            {"viewport": "1280x800", "theme": "light",
             "file": "visual/p.png", "changed_pct": 12.5},
            {"viewport": "390x844", "theme": "dark",
             "file": "visual/p.png"},
        ],
    }), encoding="utf-8")

    found = _visual_evidence(tmp_path / "job")
    assert len(found) == 1
    entries = found[0]["entries"]
    assert entries[0]["changed_pct"] == 12.5
    assert "changed_pct" not in entries[1]

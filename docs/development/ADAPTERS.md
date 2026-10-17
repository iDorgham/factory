# Adapters Guide

**Audience:** anyone adding support for a new coding agent or model provider.
**Related:** [Architecture §11](../architecture/ARCHITECTURE.md) · [Specification v3.0 §20](<../specification/Enterprise AI Software Factory — Specification v3.0.md>) · [Testing](TESTING.md)

Adapters are the **only** tool-specific code in the factory. Everything else is files and the kernel. Adding a new tool should require exactly one adapter folder and a passing conformance suite.

---

## 1. Anatomy of an adapter

```
adapters/<tool>/
├── manifest.json     # identity, capabilities, limits, roles supported
├── run.py            # entrypoint: stdin request → stdout NDJSON events
└── (helpers…)        # anything the entrypoint needs
```

Reference: [`adapters/echo/`](../../adapters/echo/) — a deterministic stand-in used by the kernel's conformance tests. [`adapters/cli-agent/`](../../adapters/cli-agent/) — the first live backend: a generic shell-out adapter (see §8).

## 2. Manifest

```json
{
  "id": "claude-code",
  "name": "Claude Code",
  "version": "1.0.0",
  "description": "…",
  "capabilities": ["stream", "resume", "cancel", "sandbox_native", "mcp", "vision"],
  "models": ["…"],
  "limits": {"max_context_tokens": 200000, "max_run_minutes": 60},
  "roles_supported": ["definer", "architect", "planner", "designer", "builder", "verifier", "reviewer", "curator"],
  "entrypoint": "run.py",
  "conformance": {"reports_usage": true, "respects_token_budget": true, "writes_only_attempt_dir": true}
}
```

| Field | Notes |
|-------|-------|
| `id`, `entrypoint` | **Required** — the loader rejects a manifest missing either (`adapters.Adapter`). |
| `capabilities` | Drives routing via `select_adapter(capabilities=…)`. A stage routes to an adapter that satisfies its requirements; missing capabilities degrade gracefully where defined. |
| `roles_supported` | If the stage declares a role and the adapter lists roles, a non-matching adapter is skipped. |
| `limits` | Declared max context tokens and max run minutes. |
| `conformance` | Declares which conformance properties hold; verified by the conformance suite. |

Adapters are discovered by scanning `adapters/*/manifest.json` (`discover_adapters`). A malformed manifest is skipped, not fatal.

## 3. Run contract

The kernel invokes the entrypoint as a subprocess, passes the **run request as JSON on stdin**, and reads an **NDJSON event stream on stdout**.

Request fields the kernel supplies (see `engine._invoke_adapter` and `echo/run.py`):

| Field | Meaning |
|-------|---------|
| `run_id` | Stable id for this run (idempotent start key) |
| `stage`, `attempt` | Current stage id and attempt number |
| `role` | Role the stage is acting as |
| `attempt_dir` | Where the adapter may write outputs (`outputs/`) |
| `worktree` | Job worktree (the only other writable location) |
| `produces` | Contract files the stage must produce |
| `manifest_path` | Path to `context.manifest.json` |
| `budget`, `env_refs`, `fence` | Budget hints, secret *references* (never values), fencing token |

### Event stream

One JSON object per line. Event types: `progress | tool_use | file_written | question | usage | heartbeat | done | error`.

```json
{"type": "progress", "message": "editing src/app.tsx"}
{"type": "file_written", "path": "…/attempts/outputs/build.md"}
{"type": "question", "id": "q1", "kind": "blocking", "text": "…"}
{"type": "usage", "model": "…", "input_tokens": 1234, "output_tokens": 567, "estimated": true}
{"type": "heartbeat"}
{"type": "done"}
{"type": "error", "class": "transient", "message": "…"}
```

## 4. Requirements (spec §20.2)

1. **Heartbeat at least every 30 s.** Missing heartbeats cause the kernel to revoke the lease and mark the attempt `interrupted`.
2. **Usage reporting is mandatory**, even if estimated — and labelled `"estimated": true` when so.
3. **Streaming:** progress events feed the dashboard so long runs show live activity.
4. **Idempotent start:** repeating a run with the same `run_id` must not start a second execution.
5. **Output discipline:** write only into the attempt directory and the job worktree; report each write; **never edit state files**.
6. **Error classification:** `transient` (retry), `capability` (reroute), `budget`, `fatal`. The kernel owns retry policy — adapters do not implement their own retries.

### Writing outputs

Contract files go in `<attempt_dir>/outputs/<name>`. Entries in `produces` that start with `git:` or end with `/` are not files (they denote commits or directories) and should be skipped — see `echo/run.py`.

## 5. Conformance suite

A new adapter is accepted **only** after passing the conformance suite (spec §20.3). Run it with:

```bash
factory adapter test <id>
```

The suite verifies:

- [ ] Starting a run and receiving a `done` event
- [ ] Cancelling a run
- [ ] Resuming from a resume token
- [ ] Heartbeat-loss handling (lease revoked, attempt `interrupted`)
- [ ] Writing a valid contract file (schema/frontmatter compliant)
- [ ] Reporting usage
- [ ] Honouring the write boundary (no writes outside the attempt dir/worktree)
- [ ] Handling an injected-instruction fixture (does not act on instructions found in untrusted input)

Passing results are recorded in the adapter's folder.

## 6. The `cli-agent` live backend

`adapters/cli-agent/` is the first real backend. Without configuration it behaves deterministically (contract files + estimated usage, hermetic). Point it at a real coding CLI to run live jobs:

```bash
# Any command works. It receives the run request as JSON on stdin, runs with
# cwd set to the job worktree, and may read FACTORY_ATTEMPT_DIR / FACTORY_BRIEF.
export FACTORY_CLI_AGENT_CMD='opencode run --format json'
# export FACTORY_CLI_AGENT_CMD='claude -p --output-format stream-json'
# export FACTORY_CLI_AGENT_CMD='"C:\Python\python.exe" "path\to\agent.py"'

factory job execute <job-id> --adapter cli-agent
```

Live-command protocol (what the command must do):

- Parse the request from stdin (`attempt_dir`, `worktree`, `produces`, `brief`, `budget`, `run_id`).
- Write every `produces` file under `<attempt_dir>/outputs/` (entries starting with `git:` or ending with `/` are not files — skip them). The job worktree is the only other writable location.
- Print an NDJSON event stream on stdout: `progress | tool_use | file_written | question | usage | heartbeat | done | error`. Non-JSON lines are forwarded as `progress`. Always emit `usage` (with `"estimated": false` when the numbers are real) and a terminal `done`.
- Exit `0` on success. A nonzero exit or a `0` exit with missing contract files is reported as `fatal` (the kernel fails the attempt — silence is never treated as success). A timeout (`budget.minutes`, overridable via `FACTORY_CLI_AGENT_TIMEOUT_S`) is reported as `transient` so the kernel retries without consuming a round.
- Idempotent start: the adapter records `run_id` per attempt dir; a repeated `run_id` replays `usage` + `done` without re-executing (declared `resume` capability, exercised by the conformance suite).

Reference command: [`tests/fixtures/adapters/cli-echo-agent.py`](../../tests/fixtures/adapters/cli-echo-agent.py) — a hermetic stand-in proven end to end (`run → execute → approve → merge → undo` on project `live` with real, non-estimated usage flowing into `usage.json`).

Conformance state: `factory adapter test cli-agent` passes (5 required cases + `resume` exercised; `cancel`/`heartbeat` skip — not declared). See [`adapters/cli-agent/conformance.json`](../../adapters/cli-agent/conformance.json).

## 7. Visual-evidence contract (`visual.json`)

A screenshot-capable adapter or command records its captures as
`<attempt_dir>/outputs/visual.json`:

```json
{
  "synthetic": false,
  "entries": [
    {"viewport": "1280x800", "theme": "light", "file": "visual/desktop-light.png"},
    {"viewport": "1280x800", "theme": "dark", "file": "visual/desktop-dark.png"},
    {"viewport": "390x844", "theme": "light", "file": "visual/mobile-light.png"}
  ]
}
```

Rules:

- `file` paths are relative to the attempt `outputs/` dir and must exist (the kernel hashes all outputs into the checkpoint SHA, so evidence is bound to the approval).
- `synthetic: true` marks test-fixture placeholders. The dashboard labels them *"synthetic fixture — not a real screenshot"* and they never count as evidence.
- No manifest → the dashboard shows no visual section (not an error). A manifest that fails to parse is ignored.
- Test fixtures can still emit synthetic manifests (`FACTORY_FIXTURE_VISUAL=1`, see `tests/fixtures/adapters/cli-echo-agent.py`) — they are labeled as such, so plumbing is exercised without posing as evidence.

### 7.1 The real capture producer (`adapters/visual-capture/capture.py`)

The factory ships a real screenshot producer — no Python dependencies; it
drives headless **Edge or Chrome** (Chromium) already installed on the machine.
New web projects get a `visual` check wired to it by default:

```json
{"visual": {"cmd": "python \"<factory-root>/adapters/visual-capture/capture.py\" --url index.html",
            "required": false}}
```

- **Env contract:** the engine exports `FACTORY_ATTEMPT_DIR` and
  `FACTORY_VISUAL_OUT` (absolute attempt outputs dir) into every check
  subprocess; the check runs with `cwd` = the job worktree, so `--url
  index.html` resolves against the worktree.
- **Browser discovery:** `--browser` → `FACTORY_VISUAL_BROWSER` → Edge →
  Chrome (Windows install locations). A `.py` browser path is launched via
  the current interpreter (used by the test fixtures).
- **Themes:** captures both light and dark by forcing
  `--blink-settings=preferredColorScheme=<v>`. Because that flag's semantics
  vary across Chromium builds *and several builds render dark by default*,
  the producer pixel-probes a tiny light/dark page at runtime to learn the
  actual mapping for this browser — the default render is never trusted. If
  the probe is inconclusive, dark captures are skipped with a stderr note,
  never guessed.
- **Viewports:** default `1280x800` + `390x844`; `--viewport WxH` repeatable.
- **Manifest semantics:** a real capture always writes `synthetic: false`;
  an existing synthetic manifest is discarded, existing real entries are
  kept (same viewport/theme overwritten). A missing page target writes a
  `skipped` note and exits 0 (nothing to capture is not a failure — the
  evidence collection only runs when a page exists); a wrong target type
  (server URL) likewise skips. Any capture that fails to produce a non-empty
  PNG exits 1 and does not touch the manifest — honest failure.
- **Tests:** hermetic via `tests/fixtures/adapters/fake-browser.py` (whose
  theme mapping is the *inverse* of the dev machine's Edge, so the probe
  logic is genuinely exercised); the test suite never requires Edge.
- **Visual diff (`changed_pct`):** with `--diff-previous` (default in the
  wired check), each captured entry is annotated with the share of visibly
  changed pixels vs. the same viewport/theme of the previous attempt (auto-
  derived from `FACTORY_ATTEMPT_DIR` = `attempt-N` → sibling
  `attempt-(N-1)`, or an explicit visual.json path). Different dimensions or
  unreadable PNGs → no number (never guessed); identical rebuilds report an
  honest `0.0`. Threshold: any channel differing by > 8/255 counts as
  changed. The dashboard renders `changed N%` per entry. Real-tree proof:
  identical rebuild → `0.0` across all four captures; a real copy edit →
  `1.1` (desktop) / `3.4` (mobile).

## 8. Testing your adapter

- Add discovery/selection tests to `tests/test_adapters.py` (live-backend behavior goes in `tests/test_cli_agent.py`, following the fixture-agent pattern).
- Keep the adapter deterministic for tests; use the echo adapter as a model.
- Test the failure paths explicitly: bad request → `fatal`; simulated timeout → `transient`; a write outside the boundary → rejected by the kernel.
- Response parsing: the loader tolerates non-JSON lines by converting them to `progress` events, but valid NDJSON is required for conformance.

## 9. Checklist for a new adapter

- [ ] `adapters/<tool>/manifest.json` with required fields and honest capabilities
- [ ] Entrypoint reads stdin JSON, emits NDJSON, never touches state
- [ ] Heartbeats, usage, and error classes implemented
- [ ] `factory adapter test <tool>` passes; results recorded
- [ ] Docs updated: [Architecture §11](../architecture/ARCHITECTURE.md) adapter table and the relevant [phase plan](../plans/ROADMAP.md)

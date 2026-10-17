# Changelog

All notable changes to the factory are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); versions follow `<spec-major>.<spec-minor>.<patch>` (see [Releasing](docs/development/RELEASING.md)).

## [Unreleased]

### Fixed
- `gitrepo.is_repo` no longer walks up to a parent checkout: only a `.git` entry directly under the path counts. Previously a repo-less project's plain worktree nested in the factory's own clone was mistaken for a worktree, so checkpoint commits landed in the outer repo and the resume `reset --hard` rewrote it — silently dropping the approve checkpoint/acceptance/gate events and failing the subsequent `job approve` (stale attempt index past `max_rounds`). Repo-less jobs now complete via content-hash checkpoints with `commit: null` and no merge event. Regression test `test_repoless_job_inside_outer_checkout_never_touches_outer_repo` (10 tests in `test_worktree.py`).
- `dashboard.build_view` empty-state `undo.reason` no longer claims merge is unimplemented (merge queue + Undo shipped in `9398dfe`).
- Reconciled P1 plan/roadmap/context docs with the implemented tree: worktrees, merge queue, Undo, and the live `cli-agent` backend marked done; remaining P1 work is visual evidence + the Solo question budget. Test count updated to 214 collected (212 passed, 2 skipped).

### Added
- Real visual capture producer (P1): `adapters/visual-capture/capture.py`
  drives headless Edge/Chrome (stdlib-only) to take actual screenshots at
  declared viewports in light+dark themes, writing genuine `visual.json`
  evidence into attempt outputs (`synthetic: false`, bound to the checkpoint
  SHA). Theme flag semantics are never hardcoded — the producer pixel-probes
  a tiny page at runtime; inconclusive probes skip dark captures with a note
  instead of guessing. The engine exports `FACTORY_ATTEMPT_DIR` /
  `FACTORY_VISUAL_OUT` to check subprocesses (`checks.run_one`/`run_checks`
  gained `extra_env`); `project_create` wires new web projects' default
  `visual` check to the real producer. Hermetic tests via
  `tests/fixtures/adapters/fake-browser.py` (theme mapping inverted vs. the
  dev Edge); 16 tests in `tests/test_visual_capture.py`; suite 242 collected
  (240 passed, 2 skipped). Proven end-to-end on the real tree: verify-stage
  captures of a genuinely built page, 4 real PNGs, approve → merge → undo.
- Visual diff and explanation helpers (P1 polish): capture entries get
  `changed_pct` vs. the previous attempt's captures (`--diff-previous`, auto-
  derived from `FACTORY_ATTEMPT_DIR`; different dimensions → no number, never
  guessed; identical rebuilds report an honest `0.0`; real-tree proof: a real
  copy edit → 1.1% desktop / 3.4% mobile). Dashboard cards gained
  "Explain this": `dispatch "explain"` returns plain-language explanations
  derived only from kernel state, the event log, and attempt artifacts (never
  agent self-report), with per-state next-step guidance. (+6 tests.)
- Solo question budget (P1): adapters may emit `question` NDJSON events; the
  engine persists each as a `job.question_asked` event with dedupe on id and
  normalized text (re-asks can't burn the budget), enforces at most 3 blocking
  questions per job (a 4th fails the job instead of interrogating forever),
  parks the job `blocked` between asks, and both sides of the exchange reach
  future attempts through `questions.md` in the context manifest. New
  `factory job answer <job> <question_id> <answer> [--adapter]`,
  `JOB.answer` dashboard action with option buttons + free-text box, fixture
  agent `tests/fixtures/adapters/cli-ask-agent.py`, and 9 tests in
  `tests/test_questions.py`.
- Visual-evidence plumbing (P1): adapters may write
  `<attempt>/outputs/visual.json` describing screenshots (`viewport`, `theme`,
  `file` relative to `outputs/`, `synthetic: true` labels fixtures); the
  dashboard collects the manifests into `preview.visual` and renders them,
  labeling synthetic ones *"not a real screenshot"*. Contract documented in
  `docs/development/ADAPTERS.md` §7; fixtures under `FACTORY_FIXTURE_VISUAL=1`
  exercise the plumbing without pretending to be evidence. Real screenshots
  still need a capture tool — the contract is ready, evidence stays honest.
- `job.answer` / `request-changes` resume with the same adapter via
  `--adapter` (dashboard actions `JOB.answer` / `JOB.change` pass it through).
- Documentation set under `docs/`, organized by category:
  - `product/` — [PRD](docs/product/PRD.md)
  - `architecture/` — [Architecture](docs/architecture/ARCHITECTURE.md)
  - `specification/` — [Specification v3.0](<docs/specification/Enterprise AI Software Factory — Specification v3.0.md>)
  - `plans/` — [Roadmap](docs/plans/ROADMAP.md) and per-phase plans P0–P5
  - `development/` — [Development](docs/development/DEVELOPMENT.md), [Contributing](docs/development/CONTRIBUTING.md), [Coding standards](docs/development/CODING-STANDARDS.md), [Testing](docs/development/TESTING.md), [Adapters](docs/development/ADAPTERS.md), [Schema versioning](docs/development/SCHEMA-VERSIONING.md), [Releasing](docs/development/RELEASING.md)
  - `operations/` — [Runbook](docs/operations/RUNBOOK.md), [Troubleshooting](docs/operations/TROUBLESHOOTING.md), [Security](docs/operations/SECURITY.md)
- `cli-agent` live backend: external-command NDJSON forwarding, honest failure classification (`fatal` on failed command / missing outputs, `transient` on timeout), run_id idempotency with declared `resume` capability, recorded `adapters/cli-agent/conformance.json`, fixture command `tests/fixtures/adapters/cli-echo-agent.py`, 8 tests in `tests/test_cli_agent.py`, wiring guide in `docs/development/ADAPTERS.md` §6.

## [0.4.0] — P0 Kernel Core

### Added
- Append-only `events.jsonl` with ULID ids and a `prev` hash chain (source of truth)
- Derived `job.json` snapshot regenerated as a fold of events
- Atomic writes: temp → fsync → `os.replace`, Windows-safe
- Lease locks with heartbeat and monotonic fencing tokens
- Job state machine with legal-transitions-only enforcement
- JSON Schemas for event, job, project, and context manifest; validation on every kernel write
- Stage profiles `lite` and `standard` with YAML validation
- `Kernel` API and CLI (`project create|list|status`, `job run|status|list|cancel`, `doctor`, `reindex`)
- `factory doctor`: schema + chain verification, snapshot repair, lease/worktree warnings
- `factory reindex`: rebuild derived `state/index.json`
- Policy presets `solo`, `team`, `enterprise`; global `factory.json` config
- Engine: stage/attempt orchestration, contract validation, gate application
- Check runner with trimmed output and failure fingerprints
- Context manifest builder with token budgets and degradation
- Adapter runtime with capability-based selection and the `echo` adapter stub
- Hermetic pytest suite (109 tests) and `flake8` config

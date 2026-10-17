# Changelog

All notable changes to the factory are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); versions follow `<spec-major>.<spec-minor>.<patch>` (see [Releasing](docs/development/RELEASING.md)).

Entries inside `[Unreleased]` are grouped newest-first within each section, and each names the
roadmap phase it belongs to so the history stays readable against [the roadmap](docs/plans/ROADMAP.md).

## [Unreleased]

> **Phase status:** P0 complete · P1 complete · **P2.1 guards landed** · **P2.2 budgets in flight**.
> Suite at `9948840`: **312 collected — 305 passed, 2 skipped, 5 failed**. The 5 failures are the
> intentionally-red TDD contracts for the P2.2 budget wiring (engine step 3, `doctor` step 4), which the
> slices below specify; each slice's cases turn green as it lands.

### Added

- **Budget and price-table schemas (P2.2, step 1)** — `kernel/schemas/budget.schema.json` validates a
  stage budget object (`tokens`, `usd` as the hard limit, `minutes`, optional `soft_usd`, unknown keys
  rejected); `kernel/schemas/price_table.schema.json` validates the per-tier table in `factory.json`
  (`input_per_1m` / `output_per_1m` / `cached_per_1m`, all `>= 0`, free-form tier names plus the
  required `default` fallback). Canonical key names stay `usd` / `soft_usd` because shipped profiles
  already use them. Migration: none — both are new optional documents; log entries in
  `kernel/schemas/CHANGELOG.md`.
- **Budget meter (P2.2, step 2)** — `kernel/src/factory_kernel/budgets.py`, a pure module with no file
  I/O, no subprocess, and no model, holding the cost arithmetic and nothing else:
  - `calculate_cost` prices any usage key shaped `X_tokens` at the rate `X_per_1m` of that usage's
    model tier, so the canonical metrics (`input_tokens`, `output_tokens`, `cached_tokens`) need no
    special case; an unknown model falls back to the `default` tier, while a missing tier or rate
    **raises** `BudgetError` — unpriced usage must never silently cost $0, or "no job exceeds its hard
    budget" would be unenforceable.
  - `stage_limits` treats `usd` as the required hard limit, honours `soft_usd` when present, and
    otherwise applies a deterministic `0.8 × usd` default rounded to cents; `soft_usd >= usd` raises
    (`doctor` reports that as an advisory warning; the runtime never relaxes a limit).
  - `check_budget` uses inclusive boundaries (cost `==` hard stops, cost `==` soft notifies) and
    carries the decisive bound on `ok` results so callers always know which limit applied.
  - Negative token counts clamp to zero; non-numeric counts raise, because malformed usage is
    kernel-rejected rather than estimated.
- **Budget TDD contracts (P2.2, step 1)** — `tests/test_budgets.py` (24 cases) and the two engine
  cases covering soft-notify and hard-stop. The engine-write-path and `doctor` cases are **red on
  purpose**: they encode the next slices (per-attempt `budget.json`, `budget.soft_exceeded` /
  `budget.hard_exceeded` events, and the `doctor` budget-configuration checks) before the
  implementation exists, which is why this release reports failures instead of 0. Each slice's cases
  turn green as it lands — a red suite here is a specification in flight, not a regression.
- **Commit provenance subsystem** — `kernel/src/factory_kernel/provenance.py` plus
  `factory provenance verify [--range --require --allow --all-before --allowlist --json]`, a
  deterministic check that commits carry their `AI-Tool` / `AI-Model` trailers. Supporting files:
  `.gitmessage` (commit template), `.githooks/commit-msg` (opt-in local hook), `.provenance-allow`
  (grandfather list for pre-convention history), and CI jobs in `.github/workflows/ci.yml` and
  `.github/workflows/provenance.yml`. 23 cases in `tests/test_provenance.py`. P2.1 is the first phase
  whose provenance is machine-verified by git rather than owner-attested — see
  [docs/context/AI-PROVENANCE.md](docs/context/AI-PROVENANCE.md).
- **Guard authorization file type (P2.1)** — `kernel/schemas/authorizations.schema.json` validates a
  kernel-owned per-job `authorizations.json` (`allowed_test_deletions`, `allowed_dep_changes` as
  exact-path arrays, optional `reason` / `authorized_by`). Authorization is structural rather than
  parsed out of `plan.md` prose, unknown keys and duplicates are rejected, and wildcards never match —
  a human authorizes a file they can name.
- **Guard events (P2.1)** — `guards.completed` and `guard.violation` added to the event-type enum.
  Violations also feed the attempt fingerprint, so a repeated identical violation trips the existing
  no-progress detection (`stalled`) instead of burning every retry round.
- **Diff extraction (P2.1)** — `gitrepo.collect_diff(worktree, base)` gathers the per-attempt scope
  for guards: committed, staged, unstaged, and untracked files; line content read from the unified
  diff text only inside `@@` hunks; binary files flagged through `numstat` and never decoded; renames
  disabled so a delete + add pair stays honest.
- **Deterministic guards (P2.1)** — `kernel/src/factory_kernel/guards.py` with the `GUARDS` registry:
  - `no_test_deletion` — deletion of test-shaped files (`tests/`, `__tests__/`, `test_*`, `*_test.*`,
    `*.spec.*`, … across languages) requires an exact-path authorization.
  - `no_lockfile_surprise` — a known manifest and its lockfile must move together; deletions are
    flagged.
  - `no_secret_in_diff` — added lines only, matched against AWS access keys, `ghp_` tokens, PEM
    private-key blocks, and credential assignments; base64 blobs and 64-hex digests are treated as
    benign by design rather than flagged as noise.
  - An unknown guard id raises `GuardError` (fail-hard, the same policy as a check missing from
    `checks.json`): a typo can never silently skip a safeguard. 40 cases in `tests/test_guards.py`.
- **Engine guard hook (P2.1)** — the attempt-base SHA is recorded at attempt start; guards run after
  checks and before the accept decision; a violation flips the attempt to `failed` even when every
  check passed; results land in `guards.json` beside `checks.json` plus one `guard.violation` event per
  (guard, kind) group with compact `paths`. Configuration problems (unknown id, invalid
  `authorizations.json`) are recorded as `guard_config` pseudo-guard violations — real events, never
  silent skips. Authorizations live at job level because attempts are disposable caches.
- **Guard surfacing in the dashboard and doctor (P2.1)** — plain-language verdicts on the timeline
  ("⚠ Guard flagged deleted tests in `tests/test_app.py`", "✓ Guards clean", raw kind id as fallback so
  a future guard never renders as an empty sentence), and `doctor` gains an advisory check that every
  guard id declared in `kernel/stages/*.yaml` exists in the registry, plus authoritative schema
  validation of each job's `authorizations.json` (an error, because a corrupt kernel-owned policy file
  must never read as "no authorization").
- **Real visual capture producer (P1)** — `adapters/visual-capture/capture.py` drives headless
  Edge/Chrome (stdlib-only) to take actual screenshots at declared viewports in light + dark themes,
  writing genuine `visual.json` evidence into attempt outputs (`synthetic: false`, bound to the
  checkpoint SHA). Theme flag semantics are never hardcoded — the producer pixel-probes a tiny page at
  runtime; inconclusive probes skip dark captures with a note instead of guessing. The engine exports
  `FACTORY_ATTEMPT_DIR` / `FACTORY_VISUAL_OUT` to check subprocesses (`checks.run_one`/`run_checks`
  gained `extra_env`); `project_create` wires new web projects' default `visual` check to the real
  producer. Hermetic tests via `tests/fixtures/adapters/fake-browser.py` (theme mapping inverted vs.
  the dev Edge); 16 cases in `tests/test_visual_capture.py`. Proven end-to-end on the real tree:
  verify-stage captures of a genuinely built page, four real PNGs, approve → merge → undo.
- **Visual diff and explanation helpers (P1 polish)** — capture entries get `changed_pct` vs. the
  previous attempt's captures (`--diff-previous`, auto-derived from `FACTORY_ATTEMPT_DIR`; different
  dimensions → no number, never guessed; identical rebuilds report an honest `0.0`; real-tree proof: a
  real copy edit → 1.1% desktop / 3.4% mobile). Dashboard cards gained "Explain this": `dispatch
  "explain"` returns plain-language explanations derived only from kernel state, the event log, and
  attempt artifacts (never agent self-report), with per-state next-step guidance.
- **Solo question budget (P1)** — adapters may emit `question` NDJSON events; the engine persists each
  as a `job.question_asked` event with dedupe on id and normalized text (re-asks can't burn the
  budget), enforces at most 3 blocking questions per job (a 4th fails the job instead of
  interrogating forever), parks the job `blocked` between asks, and both sides of the exchange reach
  future attempts through `questions.md` in the context manifest. New
  `factory job answer <job> <question_id> <answer> [--adapter]`, `JOB.answer` dashboard action with
  option buttons + free-text box, fixture agent `tests/fixtures/adapters/cli-ask-agent.py`, and 9 cases
  in `tests/test_questions.py`.
- **Visual-evidence plumbing (P1)** — adapters may write `<attempt>/outputs/visual.json` describing
  screenshots (`viewport`, `theme`, `file` relative to `outputs/`, `synthetic: true` labels fixtures);
  the dashboard collects the manifests into `preview.visual` and renders them, labeling synthetic ones
  *"not a real screenshot"*. Contract documented in `docs/development/ADAPTERS.md` §7; fixtures under
  `FACTORY_FIXTURE_VISUAL=1` exercise the plumbing without pretending to be evidence.
- `job.answer` / `request-changes` resume with the same adapter via `--adapter` (dashboard actions
  `JOB.answer` / `JOB.change` pass it through).
- Documentation set under `docs/`, organized by category:
  - `product/` — [PRD](docs/product/PRD.md)
  - `architecture/` — [Architecture](docs/architecture/ARCHITECTURE.md)
  - `specification/` — [Specification v3.0](<docs/specification/Enterprise AI Software Factory — Specification v3.0.md>)
  - `plans/` — [Roadmap](docs/plans/ROADMAP.md) and per-phase plans P0–P5
  - `development/` — [Development](docs/development/DEVELOPMENT.md), [Contributing](docs/development/CONTRIBUTING.md), [Coding standards](docs/development/CODING-STANDARDS.md), [Testing](docs/development/TESTING.md), [Adapters](docs/development/ADAPTERS.md), [Schema versioning](docs/development/SCHEMA-VERSIONING.md), [Releasing](docs/development/RELEASING.md)
  - `operations/` — [Runbook](docs/operations/RUNBOOK.md), [Troubleshooting](docs/operations/TROUBLESHOOTING.md), [Security](docs/operations/SECURITY.md)
- `cli-agent` live backend: external-command NDJSON forwarding, honest failure classification (`fatal`
  on failed command / missing outputs, `transient` on timeout), run_id idempotency with declared
  `resume` capability, recorded `adapters/cli-agent/conformance.json`, fixture command
  `tests/fixtures/adapters/cli-echo-agent.py`, 9 cases in `tests/test_cli_agent.py`, and a wiring
  guide in `docs/development/ADAPTERS.md` §6.

### Fixed

- `gitrepo.is_repo` no longer walks up to a parent checkout: only a `.git` entry directly under the
  path counts. Previously a repo-less project's plain worktree nested in the factory's own clone was
  mistaken for a worktree, so checkpoint commits landed in the outer repo and the resume
  `reset --hard` rewrote it — silently dropping the approve checkpoint/acceptance/gate events and
  failing the subsequent `job approve` (stale attempt index past `max_rounds`). Repo-less jobs now
  complete via content-hash checkpoints with `commit: null` and no merge event. Regression test
  `test_repoless_job_inside_outer_checkout_never_touches_outer_repo` (10 cases in
  `test_worktree.py`).
- `dashboard.build_view` empty-state `undo.reason` no longer claims merge is unimplemented (merge queue
  + Undo shipped in `9398dfe`).
- Reconciled the P1 plan, roadmap, and context docs with the implemented tree: worktrees, merge queue,
  Undo, and the live `cli-agent` backend marked done, with the remaining P1 work recorded honestly at
  the time (visual evidence + the Solo question budget, both of which subsequently landed in this same
  release — see the Added section above).

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
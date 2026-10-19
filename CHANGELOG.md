# Changelog

All notable changes to the factory are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); versions follow `<spec-major>.<spec-minor>.<patch>` (see [Releasing](docs/development/RELEASING.md)).

Every roadmap phase ships as one minor version, so this file doubles as the phase ledger — the table
below is the authoritative phase → version pairing. A phase's entries stay under `[Unreleased]` until
its version is bumped in `pyproject.toml` and tagged; entries are grouped newest-first within each
phase subsection (planned phases last) and each names the phase it belongs to, so the history stays
readable against [the roadmap](docs/plans/ROADMAP.md).

## Phase → version

| Phase | Version | State |
|-------|---------|-------|
| **P0 — Kernel core** | `0.4.0` | ✅ Shipped — the version `pyproject.toml` declares |
| **P1 — Solo slice** | `0.5.0` | ✅ Complete — release pending (version bump + tag not cut yet) |
| **P2 — Trust layer** | `0.6.0` | 🚧 In progress — P2.1–P2.5 landed; safety floor and import-with-baseline open |
| **P3 — Learning** | `0.7.0` | ⬜ Planned — the Step 3 slice (lessons ledger, memory hygiene, minimal eval harness) is designed, not built |

## [Unreleased]

> **Phase status:** P0 complete (`0.4.0`) · P1 complete (`0.5.0`, release pending) ·
> **P2.1 guards**, **P2.2 budgets**, **P2.3 sandbox hardening**, **P2.4 risk-scored gates**, and
> **P2.5 prompt-injection handling** landed (`0.6.0` line) · P3 planned (`0.7.0`).
> Suite (current tree, at `d933adf`): **423 collected — 421 passed, 2 skipped, 0 failed** —
> fully green (the 2 skips are capability-gated conformance cases).
>
> **Version note:** `pyproject.toml` still declares `0.4.0`; `0.5.0`–`0.7.0` are the release lines
> these phases ship as. A phase moves out of `[Unreleased]` into its own version section when its
> version is bumped and tagged ([Releasing](docs/development/RELEASING.md)).

### Added

#### P2 — Trust layer (`0.6.0`, in progress)

- **Prompt-injection handling (P2.5)** — untrusted input is now detected, labeled, recorded, and priced
  into risk instead of being trusted:
  - `kernel/schemas/injection.schema.json` (the project's tenth schema, kind `injection`; mirrored as an
    optional `injection` section in `factory.schema.json`): configurable detection `patterns` (`id`,
    `pattern`, optional non-negative integer `weight`), `additionalProperties: false` at every level.
    The shipped `factory.json` keeps no `injection` section — absence is the documented baseline
    configuration, not an unconfigured guess. Migration: none — new optional document; logged in
    `kernel/schemas/CHANGELOG.md`.
  - Kernel-owned baseline patterns (`ignore-previous-instructions`, `system-prompt-leak`,
    `do-not-follow`, `pretend-to-be`) that config can only **add to**: a config pattern reusing a
    baseline id is rejected, so an operator can widen detection but never remove or override it.
    `injection.detected` added to the event enum; `context.manifest.schema.json`'s `untrusted_content`
    items became objects carrying an `injection_flags` array; `risk.schema.json` weights gained the
    required `injection_flag` (shipped default weight 100, so one flag alone clears the high band).
  - `kernel/src/factory_kernel/injection.py`, a pure module (no subprocess, no file I/O, no LLM):
    `load_injection_config` (`None` → documented baseline defaults, additive merge, defensive copies;
    empty/malformed section, invalid regex, negative or non-integer weight, and baseline-id collision
    all raise `InjectionError`), `scan_item` (regex match, excerpt truncated at 80 chars, confidence
    1.0), `scan_manifest_items`, and `injection_signal` (1 when any item was flagged).
  - Engine wiring: untrusted items under the job's `issues/` are discovered and scanned **before** the
    adapter runs; flags are attached to the manifest entries, one `injection.detected` event is emitted
    per match, and the `injection_flagged` signal (job-wide: any detection in the job raises it for all
    downstream risk-scored stages) feeds the P2.4 weighted score under the `injection_flag` weight — so
    the existing kernel-owned band→action map decides whether to auto-advance, park for a human, or
    block. `InjectionError` becomes the deterministic `config_error` status and writes an
    `injection.json` verdict file; a broken detector can never degrade into "nothing flagged".
  - Dashboard: injection verdicts join guard and budget notes as plain-language timeline rows
    ("⚠ Injection pattern flagged in stage 'build' (`issues/BUG.md`: 'ignore previous instructions')"),
    latest attempt per stage winning, raw pattern id as the fallback so a future pattern never renders
    as an empty sentence.
  - `factory doctor` injection-integrity checks: section schema validity is authoritative; a config
    pattern id colliding with a kernel-owned baseline is an authoritative error (naming the ownership
    violation); zero-weight patterns are advisories. 30 cases in `tests/test_injection.py`.

- **Risk-scored gates (P2.4)** — `gate: risk_scored` finally has a real score behind it:
  - `kernel/schemas/risk.schema.json` (the project's ninth schema, kind `risk`; the shape is inlined
    in `factory.schema.json`) — `risk_scoring` in `factory.json` carries kernel-known `weights`
    (guard_violation, budget_soft_exceeded, budget_hard_exceeded, check_failure, retry_attempt) and
    ceiling-style `thresholds`; `gate_actions` is rejected outright (the band→action map is
    kernel-owned). The shipped config gained the explicit default block (40/20/50/15/10,
    25/50/100); P2.5 later appended `injection_flag` (100) to the same weights. Migration: none —
    new document; absent sections keep kernel defaults; logged in `kernel/schemas/CHANGELOG.md`.
  - `risk.computed` event added to the event enum: stage, score, band, action, and the exact
    signals dict — emitted verbatim before `gate.evaluated` so the decision cites stored evidence.
    Only risk-consuming gates (`risk_scored`, `if_risk_above:*`) emit it.
  - `kernel/src/factory_kernel/risk.py`, a pure module (no subprocess, no file I/O):
    `compute_score` (weighted sum over kernel-observed signals, clamped at the cap; malformed input
    raises `RiskError`, never a guessed score), `resolve_band` (strict ceilings: `< low` → low,
    `< medium` → medium, else high), `gate_action` (kernel-owned map), `assess` (one verdict dict
    whose score/band/action cite the same checked numbers), `load_risk_config` (absent → documented
    defaults; present-but-empty or malformed → `RiskError`).
  - Engine wiring: `risk_scored`/`if_risk_above:*` gates compute the verdict over **stage-scoped**
    signals ("the road to this pass" — violations and check failures of the stage's earlier rounds
    plus the winning attempt's retries and budget verdict), then resolve: `low → auto`,
    `medium → require_human` (job parked awaiting_human at the gate), `high → blocked`
    (deterministic failure). A `RiskError` fails the job deterministically — a broken config can
    never degrade into a silently loosened gate.
  - Doctor: `risk_scoring` schema-validity and `gate_actions` overrides are authoritative errors;
    zero weights and non-monotonic thresholds are advisories.

- **Sandbox hardening (P2.3)** — the adapter boundary is enforced, not just declared:
  - `kernel/schemas/factory.schema.json` — the first global-config schema, validating the whole
    `factory.json` (`additionalProperties: false`); the shipped config gained its hardening block.
    Migration: none — new document; logged in `kernel/schemas/CHANGELOG.md`.
  - `kernel/src/factory_kernel/sandbox.py`, a pure module (no subprocess, no file I/O):
    `sanitize_env` keeps exactly the allowlist intersection of the kernel env (case-insensitive exact
    / `*`-suffix rules, lone `*` as the explicit allow-all opt-out); `resolve_under` rejects lexical
    path escapes; `load_sandbox_policy` fails hard on unknown types, empty allowlists, and malformed
    keys, with documented defaults for absent ones.
  - Sandboxed adapter execution: `Adapter.run` accepts explicit `cwd`/`env`; `engine._invoke_adapter`
    runs every adapter sandboxed — sanitized env plus kernel-reserved attribution injected after the
    filter (`FACTORY_JOB_ID`, `FACTORY_STAGE`, `FACTORY_ATTEMPT`, `FACTORY_ATTEMPT_DIR`,
    `FACTORY_WORKTREE`), `strict_cwd` locking adapter cwd to the job worktree, and both sandbox paths
    proven contained before any subprocess sees them (`SandboxError` → `fatal`). Declared boundary:
    kernel-owned project checks keep their full env (operator tooling needs credentials).
  - `factory doctor` sandbox-integrity checks: whole-config schema validity is authoritative;
    `env_allowlist: ["*"]` and absent/false `strict_cwd` are honest advisories.
  - 27 cases in `tests/test_sandbox.py` plus the `env-probe` fixture adapter, whose `usage.json`
    reports its environment visibility and cwd inside the subprocess — kernel-recorded evidence.

- **Budget enforcement runtime (P2.2, steps 3–4)** — `engine._run_budget` writes the per-attempt
  verdict into `budget.json` every budgeted round (per-attempt cost stays in the file, no per-round
  noise): `budget.soft_exceeded` notifies while the attempt stands, `budget.hard_exceeded` fails the
  attempt, breaks the retry loop (`on_fail: loop` must not re-spend past an absolute stop), and
  transitions the job to `failed`; a cached hard refusal is returned on resume without re-running the
  adapter. `BudgetError` (missing/inverted limits, unpriced usage) is the deterministic
  `config_error` status, same policy as `guard_config`. Dashboard verdicts join guard notes as
  plain-language rows. `factory doctor` budget checks: price-table schema validity is authoritative,
  inverted soft/hard limits and unpriced usage are advisories naming the fix.
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
  cases covering soft-notify and hard-stop. They were **red on purpose** at landing: they encoded the
  then-unbuilt slices (per-attempt `budget.json`, `budget.soft_exceeded` / `budget.hard_exceeded`
  events, and the `doctor` budget-configuration checks) before the implementation existed — a TDD
  slice in flight, not a regression. All of them have since turned green with the engine and doctor
  slices above.
- **Commit provenance subsystem (P2.1)** — `kernel/src/factory_kernel/provenance.py` plus
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

#### P1 — Solo slice (`0.5.0`, complete — release pending)

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
- `cli-agent` live backend: external-command NDJSON forwarding, honest failure classification (`fatal`
  on failed command / missing outputs, `transient` on timeout), run_id idempotency with declared
  `resume` capability, recorded `adapters/cli-agent/conformance.json`, fixture command
  `tests/fixtures/adapters/cli-echo-agent.py`, 9 cases in `tests/test_cli_agent.py`, and a wiring
  guide in `docs/development/ADAPTERS.md` §6.
- **Factory-managed git worktrees, checkpoint commits, merge queue + Undo (P1)** — `gitrepo.py` wraps
  git with a fixed identity; each project owns `projects/<name>/repo` with its initial commit recorded
  as `base_commit`. Job execute creates a real worktree at `.work/<job-id>` on branch
  `factory/<job-id>` from `base_commit` (spec §19.8); accepted attempts record a git commit alongside
  the content-hash SHA (spec §23.7) so resume restores the worktree with `reset --hard` + `clean -fd`
  (spec §23.9). Approving runs a `--no-ff` merge of the job branch into `main` through an engine
  completion hook; a conflict moves the job to `blocked` (never `completed`), leaves the repo clean,
  and records `merge.conflict`. `factory job undo` reverts the merge (`reset --hard` when the job merge
  is HEAD, else `git revert`), records `merge.undone`, refuses a second undo and an unmerged job; the
  dashboard Undo button enables when a merge is present. 10 tests in `tests/test_worktree.py`.
- **Solo dashboard (P1)** — `dashboard.py` builds the three-element Solo view (`build_view`), renders
  HTML, exports a static snapshot (`export-dashboard`), and serves it (`serve`: stdlib HTTP server +
  SSE + `POST /api/command`); `dispatch` covers create project/sample/job, execute, approve, change,
  cancel, and undo. The approval card shows the preview link + assumptions with **Approve** /
  **Change this…**, a hidden Details drawer carries the raw event timeline, and a first-run empty-state
  sample gives a beginner something to run. CLI: `factory serve`, `factory export-dashboard`,
  `factory request-changes` (spec §21).
- **Adapter conformance suite (P1)** — `conformance.py` exercises start, contract-file, usage,
  write-boundary, and injected-instruction cases for any adapter, plus capability-gated
  cancel/resume/heartbeat (reported as a skip when the capability is absent, per §20.1 graceful
  degradation); `record_results` writes `conformance.json` into the adapter folder.
  `factory adapter test <id> [--no-record]`; the `slow` fixture exercises cancel/resume/heartbeat; the
  `echo` adapter ships a recorded pass (spec §20.3).
- **Checkpoints, SHA-bound approval, recovery (P1)** — `checkpoint.py` computes a deterministic
  content hash (clean-tree/result SHA) over accepted attempt outputs plus the worktree, writes
  `checkpoint.json` per accepted attempt, and emits `checkpoint.created` events. `job approve` binds
  to the latest checkpoint SHA: a changed result (or an explicit `--sha` mismatch) is refused and the
  job stays `awaiting_human`. An attempt started but never finished is recorded as `interrupted` on
  resume and retried without consuming a round (adapter timeouts/killed processes classify as
  transient); identical inputs that already produced an accepted result are reused, not re-run.
- **Solo build loop (P1)** — `engine.py` drives a job through its stage profile: per-stage attempt
  dirs, a schema-valid context manifest before each attempt, adapter invocation, kernel-run checks,
  gate evaluation, and the build loop with failure-fingerprint no-progress detection → `stalled`
  (spec §9.2). `checks.py` runs real commands with trimmed output, required/conditional checks, a
  `required_checks` meta-check, and stable failure fingerprints; `context.py` resolves
  brief/requires + project memory under token budgets with degradation; `adapters.py` discovers
  adapters, loads manifests, selects by capability/role, and speaks the NDJSON subprocess contract
  with error classification. CLI: `factory job execute`, `factory job approve`.
- **Solo dashboard task player (P1)** — the Solo view only showed progress when you scrolled to the
  timeline, so an operator browsing the page had no ambient signal of what the factory was doing or
  when it needed them. A sticky footer bound to the active job now carries a status glyph, the
  brief, stage progress, and Resume / Needs-you / Stop controls that stay reachable from any scroll
  position. The controls are static nodes toggled by visibility rather than rebuilt per stream tick
  — an early version recreated them on every frame and swallowed an in-flight click, which the live
  check caught. The footer offers only the actions the kernel will actually run (`Engine.execute`
  accepts `pending` / `running` / `awaiting_human`; approving is SHA-bound and separate), names the
  reason when the job needs the human instead of the active stage, renders in the read-only export
  (a click there lands on the export's "Read-only export" note, the same contract as the Undo
  button), and carries real accessibility semantics: a labelled region with a `role=progressbar`
  (value from the streamed model, as both `aria-valuenow` and a "3 of 5 stages" `valuetext`) and a
  polite live status, so a "needs you" transition is announced rather than merely drawn.
- Documentation set under `docs/`, organized by category:
  - `product/` — [PRD](docs/product/PRD.md)
  - `architecture/` — [Architecture](docs/architecture/ARCHITECTURE.md)
  - `specification/` — [Specification v3.0](<docs/specification/Enterprise AI Software Factory — Specification v3.0.md>)
  - `plans/` — [Roadmap](docs/plans/ROADMAP.md) and per-phase plans P0–P5
  - `development/` — [Development](docs/development/DEVELOPMENT.md), [Contributing](docs/development/CONTRIBUTING.md), [Coding standards](docs/development/CODING-STANDARDS.md), [Testing](docs/development/TESTING.md), [Adapters](docs/development/ADAPTERS.md), [Schema versioning](docs/development/SCHEMA-VERSIONING.md), [Releasing](docs/development/RELEASING.md)
  - `operations/` — [Runbook](docs/operations/RUNBOOK.md), [Troubleshooting](docs/operations/TROUBLESHOOTING.md), [Security](docs/operations/SECURITY.md)

#### P3 — Learning (`0.7.0`, planned — Step 3 slice: lessons ledger, memory hygiene, minimal eval harness)

- **Nothing implemented.** P3 remains planned as of `878629b`; this changelog makes no P3 capability
  claim. The [P3 plan](docs/plans/P3-learning.md) now records the designed Step 3 slice (lessons
  ledger, memory hygiene, minimal eval harness) as unchecked work, and says plainly that it starts
  only after P2 closes.
- Planned scope (tracked in the [P3 plan](docs/plans/P3-learning.md)):
  - *Eval harness* — fixture tasks (small repo + brief + expected checks), runs against any
    combination of roles, skills, models, and adapters, reproducible results under `evals/results/`
    with every version pinned; used for skill-promotion gating, adapter/model comparison, and
    regression detection on prompt changes.
  - *Skill packages* — `SKILL.md` / `evals/` / `CHANGELOG.md` / `skill.json` (version, scope, owner,
    provenance, dependencies, status), semantic versioning with jobs pinning versions at creation,
    and the lifecycle proposed → project scope → candidate → promoted (evals + measured gain + 2
    independent uses) → deprecated/rolled back; project skills override global; skills carry no
    permissions. CLI: `factory skill create|improve|promote|deprecate|pin`, `factory eval run`.
  - *Memory* — `decisions.md` (human-approved ADRs), `conventions.md`, commit-SHA-stamped
    `repo-map.json`, and a `lessons.jsonl` ledger; no secrets, humans can edit/delete, and lessons
    influence behavior only through reviewed convention/skill changes (never silent injection); the
    curator role mines lessons and keeps the repo map fresh.
- Only groundwork exists in the tree (P1 plumbing, not a learning system): every project's `memory/`
  directory is created with an empty `lessons.jsonl`, and the context manifest includes a `lessons`
  summary when that file has content.

### Fixed

#### P2 — Trust layer

- **Declared risk gates were not computing risk (P2.4).** `gate: risk_scored` evaluated a hardcoded
  `risk = 0.0` and `if_risk_above:*` kept a second hardcoded threshold table, so the declared gate was
  a no-op on every job. Both now use the computed score/band from `risk.py`; a broken or missing
  `risk_scoring` config fails the job deterministically instead of silently passing it.
- **Global config problems are surfaced before a job can spend money on them (P2.2/P2.3).** `doctor`
  now validates the whole `factory.json` against `factory.schema.json` (authoritative) and re-checks
  the price table and sandbox block from disk, and the budget runtime raises `BudgetError` on an
  unpriced tier or rate instead of pricing it at $0. Previously no schema described `factory.json` at
  all, so a malformed `price_table` could misprice every attempt and an invalid sandbox block could
  run as an unknown boundary.
- **Test-contract corrections, no production semantics changed.** The budget soft-case token knob was
  corrected to 1,597,500 input tokens (the burner's fixed 500 output tokens at $15/1M add $0.0075, so
  the attempt totals exactly $4.80 between the $4.00 soft and $5.00 hard limits); the risk config-flip
  engine test dropped the `kernel`/`demo_job` fixtures it created and never used; the doctor
  zero-weight expectation was reordered alphabetically (`check_failure` before `guard_violation`); the
  sandbox test doubles now mimic `CompletedProcess` and the `sanitize_env` expectation includes the
  configured `FACTORY_*` rule; and the guard TDD fixture's `M`-status case commits the file to base
  first (`A` is an honest addition, `M` is the case that can hide a deletion).
- **Docs reconciled with the implemented trust layer** — the P2.1/P2.2/P2.3/P2.4 sections of the
  roadmap, plans, architecture, and context pack now describe what shipped (`634ff41`, `8bcd7f3`,
  `c482e70`, and the risk docs pass), and the schema log records every schema change with its
  migration.

#### P1 — Solo slice

- `gitrepo.is_repo` no longer walks up to a parent checkout: only a `.git` entry directly under the
  path counts. Previously a repo-less project's plain worktree nested in the factory's own clone was
  mistaken for a worktree, so checkpoint commits landed in the outer repo and the resume
  `reset --hard` rewrote it — silently dropping the approve checkpoint/acceptance/gate events and
  failing the subsequent `job approve` (stale attempt index past `max_rounds`). Repo-less jobs now
  complete via content-hash checkpoints with `commit: null` and no merge event. Regression test
  `test_repoless_job_inside_outer_checkout_never_touches_outer_repo` (10 cases in
  `test_worktree.py`).
- `checks.run_checks` now forwards `extra_env` to each per-check `run_one`. The visual producer's
  `FACTORY_ATTEMPT_DIR` / `FACTORY_VISUAL_OUT` previously reached only the single-check path, so the
  multi-check path silently dropped them; caught by the env-probe test.
- `dashboard.build_view` empty-state `undo.reason` no longer claims merge is unimplemented (merge queue
  + Undo shipped in `9398dfe`).
- Reconciled the P1 plan, roadmap, and context docs with the implemented tree: worktrees, merge queue,
  Undo, and the live `cli-agent` backend marked done, with the remaining P1 work recorded honestly at
  the time (visual evidence + the Solo question budget, both of which subsequently landed in this same
  release — see the Added section above).

## [0.4.0] — P0 Kernel core

### Added

- Append-only `events.jsonl` with ULID ids and a `prev` hash chain (source of truth)
- Derived `job.json` snapshot regenerated as a fold of events
- Atomic writes: temp → fsync → `os.replace`, Windows-safe
- Lease locks with heartbeat and monotonic fencing tokens
- Job state machine with legal-transitions-only enforcement
- JSON Schemas for event, job, project, and context manifest; validation on every kernel write
- Schema change log `kernel/schemas/CHANGELOG.md` (the interim versioning record until schemas carry
  `$id` versions)
- Stage profiles `lite` and `standard` with YAML validation
- `Kernel` API and CLI (`project create|list|status`, `job run|status|list|cancel`, `doctor`, `reindex`)
- `factory doctor`: schema + chain verification, snapshot repair, lease/worktree warnings
- `factory reindex`: rebuild derived `state/index.json`
- Policy presets `solo`, `team`, `enterprise`; global `factory.json` config
- Specification v3.0 in-tree as the normative contract
- Engine: stage/attempt orchestration, contract validation, gate application
- Check runner with trimmed output and failure fingerprints
- Context manifest builder with token budgets and degradation
- Adapter runtime with capability-based selection and the `echo` adapter stub
- Lease guard file bracketing every mutation (exclusive create, stale-guard steal)
- Hermetic pytest suite (109 tests) and `flake8` config

### Fixed

- **Windows atomic writes** — the write path fsynced a directory, which does not exist as a portable
  operation on Windows; the directory fsync was dropped and overwrite goes through `os.replace`, so
  writes are crash-safe on both platforms.
- **Nullable lease in the job schema** — the event fold sets `lease: null` whenever no lease is held,
  so the strict schema rejected every freshly created job snapshot; `lease` now allows `null`, and the
  change is recorded in `kernel/schemas/CHANGELOG.md` with no migration needed for existing data.
- **Dead imports dropped** so the shipped tree lints clean under the new `.flake8` config.

# Project History

Complete development history of the Enterprise AI Software Factory, reconstructed from `git log` and the
repository contents. Snapshot date: **2026-10-19**.

- **Repository:** GitHub repo `github.com/iDorgham/factory` (public), branches `master` and
  `feat/dashboard-task-player` (PR #1), HEAD `8a390c0`, 42 commits.
- **Author of all commits:** `iDorgham` (`yasser.dorgham@gmail.com`).
- **Dates:** 8 commits on 2026-10-16 (the P0 + P1 build day), 20 on 2026-10-17 (P1 hardening, P2.1,
  P2.2), 8 on 2026-10-18 (P2.3, P2.4), 6 on 2026-10-19 (P2.5, the task player, the docs set).
- **Tooling:** the owner attests that **P0 and P1 were developed with OpenCode using the Big Pickle model**
  (not machine-verified; those commits predate the provenance convention). From P2.1 onward the tool and
  model are recorded per commit in `AI-Tool` / `AI-Model` trailers and enforced by hook + CI
  (see [AI-PROVENANCE.md](../AI-PROVENANCE.md)).

> Note on a discrepancy: the `README.md` and docs that existed before the documentation reorganization
> described the project as "P0 complete, P1 planned." The git history shows P1 work had already landed.
> The documentation was subsequently reconciled to match reality.

---

## Timeline

### 1. `d328d49` — initial import of factory P0 skeleton with project scaffolding
**Phase:** P0 · **Date:** 2026-10-16

Established the entire tree: `factory.json`, the `factory` launcher, packaging, `.gitignore`, the full
Specification v3.0 (810 lines), the four JSON Schemas, three policy presets (solo/team/enterprise), the
initial kernel modules (`atomic`, `hashing`, `kernel`, `lease`, `state`, `ulid`, `cli`), the `README`, and
the `adapters/echo` manifest.

### 2. `b96c6c5` — P0 hardening: cross-platform atomic writes, schema validation, profile parsing, doctor v2, test suite
**Phase:** P0 · **Date:** 2026-10-16

- Fixed atomic write on Windows (no directory `fsync`; `os.replace` for overwrite).
- Added `SchemaStore` and validate every event/snapshot/project **before** write.
- Added the stage-profile loader/validator (`profiles.py`), replacing a raw-text stub.
- `doctor` v2: event hash-chain verification, lease/worktree/network checks.
- Allowed `null` lease in the job schema to match the event fold.
- Added the pytest suite (81 tests), `pyproject.toml`, `.gitignore`; `git init`.

### 3. `f1ffc41` — polish: spec-conformant lease guard, transition audit, schema log, lint/repo config
**Phase:** P0 · **Date:** 2026-10-16

- Lease: bracket every mutation with an exclusive-create guard file (`O_CREAT|O_EXCL`, spec §5.2); steal a stale guard; tests.
- Tests: executable audit of the spec §7 transition matrix (109 tests total).
- `kernel/schemas/CHANGELOG.md`: migration note for the lease-nullability change.
- Added `.gitattributes` (LF), `.editorconfig`, `.flake8`; dropped dead imports.

*This effectively completed P0 — the kernel core with its safety invariants and 109 tests.*

### 4. `fd06130` — P1: stage-graph engine, adapter runtime, check runner, CLI execute/approve
**Phase:** P1 · **Date:** 2026-10-16

Added the deterministic execution layer that drives a job through its stage profile:

- `engine.py`: per-stage attempt dirs, context manifest before each attempt, adapter invocation,
  kernel-run checks, gate evaluation, and the build loop with failure-fingerprint no-progress detection → `stalled` (spec §9.2).
- `checks.py`: real command runner, trimmed output, required/conditional checks, `required_checks` meta-check, stable failure fingerprints.
- `context.py`: schema-valid `context.manifest.json` builder resolving brief/requires + project memory.
- `adapters.py`: adapter discovery, manifest loading, capability/role selection, NDJSON subprocess run contract with error classification.
- `adapters/echo/run.py`: deterministic echo adapter exercising the contract.
- CLI: `factory job execute` / `job approve`; `Kernel.job_execute` / `job_approve`.
- Tests: `test_engine`, `test_checks`, `test_context`, `test_adapters` (144 total: 142 passed, 2 skipped).

### 5. `92b0b2a` — P1: content-addressed checkpoints, SHA-bound approval, interrupted-attempt recovery
**Phase:** P1 · **Date:** 2026-10-16

Kernel-side P1 increment (P1 plan workstreams 1/2/6 groundwork):

- `checkpoint.py`: deterministic content hash (clean-tree/result SHA) over all accepted attempt outputs plus
  the worktree; `checkpoint.json` per accepted attempt; `checkpoint.created` events.
- **SHA-bound approval:** `job approve` binds to the latest checkpoint SHA; a changed result (or explicit
  `--sha` mismatch) is refused and the job stays `awaiting_human`. Added an `approval` field to `job.schema.json`.
- **Interrupted attempts:** a stage attempt started but never finished (killed process) is recorded as
  `interrupted` on resume and retried without consuming a round; adapter timeouts/killed processes classify as transient.
- **Input-hash idempotency:** identical inputs that already produced an accepted result are reused, not re-run.
- CLI: `job approve --sha <checkpoint-sha>`.
- Tests: `test_checkpoint` + engine cases (156 total: 154 passed, 2 skipped).

### 6. `a3fde93` — P1: adapter conformance suite (spec §20.3) + `factory adapter test`
**Phase:** P1 · **Date:** 2026-10-16

- `conformance.py`: `run_suite` exercises start, contract-file, usage, write-boundary, and injected-instruction
  cases for any adapter, plus capability-gated cancel/resume/heartbeat (reported skip when the capability is
  absent, per §20.1 graceful degradation). `record_results` writes `conformance.json` into the adapter folder.
- CLI: `factory adapter test <id> [--no-record]`.
- Fixtures: `tests/fixtures/adapters/slow` exercises cancel/resume/heartbeat.
- `adapters/echo/conformance.json`: recorded pass for the echo adapter.
- Tests: `test_conformance` (159 total: 159 passed, 2 skipped).

### 7. `5dfdf19` — P1: Solo dashboard (`serve` SSE + `export-dashboard`), `request-changes` rework loop
**Phase:** P1 · **Date:** 2026-10-16

- `dashboard.py`: `build_view` (three-element Solo view), `render_html`, `export_dashboard` (static snapshot), `serve` (stdlib HTTP server + SSE + `POST /api/command`), `dispatch` (create_project/create_sample/create_job/execute/approve/change/cancel/undo).
- Approval card: preview link + assumptions, actions **Approve** / **Change this…**; hidden Details drawer with raw event timeline; first-run empty-state sample.
- CLI: `factory serve`, `factory export-dashboard`, `factory request-changes`.
- Tests: `test_dashboard` (171 / 173 at the time).

### 8. `9398dfe` — P1: factory-managed git worktrees, checkpoint commits, merge queue + Undo
**Phase:** P1 · **Date:** 2026-10-16

- `gitrepo.py`: thin git wrapper with a fixed identity. Each project owns a repo at `projects/<name>/repo`;
  project create makes an initial commit and records it as the project's `base_commit`.
- Job `execute`: creates a real worktree at `.work/<job-id>` on branch `factory/<job-id>` from `base_commit`
  (spec §19.8). The worktree becomes the canonical execution workspace for the job.
- Checkpoints: record a git commit alongside the content-hash SHA (spec §23.7). The SHA still binds approval;
  the git commit restores the worktree. Resume restores the worktree to the last accepted checkpoint with
  `reset --hard` and `clean -fd` (spec §23.9).
- Merge queue (spec §19.9): approving a job runs a `--no-ff` merge of the job branch into `main` via an engine
  completion hook. If a conflict occurs, the job moves to `blocked` (never completed) and the repo is left clean.
  The state records `merge.completed` or `merge.conflict`; the fold exposes `job.merge`.
- Undo (spec §21.2): `factory job undo <job-id>` reverts the merge (`reset --hard` when the job merge is HEAD,
  else `git revert`). It records `merge.undone`. A second undo and an unmerged job are refused. The dashboard
  Undo button is enabled when a merge is present.
- `echo` adapter writes a file into the worktree so job branches are actually observable.
- Tests: `test_worktree` (9 tests covering worktree/merge/undo paths; 205 collected total: 203 passed, 2 skipped).

*With this, the core P1 Solo slice items (worktrees, merge queue, Undo) are implemented.*

---

## P2 — Trust layer

### P2.1 — Guards over the diff (2026-10-17, commits `f5815b9` … `9010e60`)

Implements [P2-trust-layer.md](../plans/P2-trust-layer.md) workstream 2 (spec §9.3). Guards are pure
kernel functions over the attempt diff — no subprocesses, no LLM — under the same discipline as
`checks.py`: declared by stage profiles, executed only by the kernel, recorded as hash-chained events.

- **Structural authorization** (`f5815b9`): new kernel-owned file type `authorizations.json`
  (per job; exact-path allowlists `allowed_test_deletions`/`allowed_dep_changes`; schema strictly
  rejects unknown keys and duplicates; wildcards never match — a human authorizes a file they can
  name). Replaces plan-prose parsing by design. Event schema gains `guards.completed` and
  `guard.violation`. Six TDD-red tests committed first.
- **Diff extraction** (`741bf84`): `gitrepo.collect_diff(worktree, base)` — per-attempt scope
  ("guards run after every round"): committed, staged, unstaged, and untracked files; line content
  from the unified diff text only inside `@@` hunks; binary files flagged via `numstat` and never
  decoded; renames disabled so `D`+`A` stay honest.
- **Guard core** (`12f231f`): `guards.py` — `no_test_deletion` (deletion of test-shaped files, exact
  authorization), `no_lockfile_surprise` (manifest↔lockfile move together; deletion flagged),
  `no_secret_in_diff` (added lines only: AWS keys, `ghp_`, PEM blocks, credential assignments;
  base64 blobs ≥100 chars and 64-hex hex are benign by design). Unknown guard id → `GuardError`
  (fail-hard, same policy as a check missing from `checks.json`).
- **Engine hook** (`42b8ae6`): attempt-base recorded at attempt start; guards run after checks,
  before the accept decision; verdict flips the attempt to `failed` even when all checks passed;
  guard ids+paths feed the failure fingerprint so repeated identical violations hit the existing
  no-progress detection (`stalled`) instead of burning rounds; `guard.violation` per (guard, kind)
  group plus compact `paths`; `guards.json` beside `checks.json`; config problems (unknown id,
  invalid authorizations) become `guard_config` pseudo-guard violations — recorded events, never
  silent skips. Authorizations live at job level (§5.2: attempts are disposable caches).
- **Dashboard** (`8f2e8de`): plain-language timeline verdict per guarded stage (latest attempt wins):
  "⚠ Guard flagged deleted tests in tests/test_app.py" / "✓ Guards clean", with a red dot; raw kind
  id is the fallback so a future guard never renders as an empty sentence.
- **Doctor** (`9010e60`): advisory check that every guard id declared in `kernel/stages/*.yaml`
  exists in the registry (warnings, sorted by stage then guard id, naming the file to fix), plus
  authoritative schema validation of each job's `authorizations.json` (errors — a corrupt
  kernel-owned policy file must never read as "no authorization").
- History nuance worth keeping: the first commit with risk of silent cheating was caught here —
  the TDD suite failed once because a fixture `M`-status case needed the file committed to base
  first (`A` is an honest addition, `M` is the case that can hide deletion).
- **First machine-verified provenance phase:** this and all subsequent commits carry
  `AI-Tool`/`AI-Model` trailers enforced by the commit-msg hook (see
  [AI-PROVENANCE.md](AI-PROVENANCE.md) §3). Suite: **286 collected — 284 passed, 2 skipped**;
  flake8 clean; `doctor` ok on the real tree (5 projects, 10 jobs, no guard warnings).

### 9. `634ff41` — docs: reconcile P2.1 guards implementation with project documentation
**Phase:** P2 · **Date:** 2026-10-17

Documentation-only commit: updated the roadmap, phase plans, architecture, runbook, and context pack so
they describe the guards that actually shipped instead of the guards that were planned.

---

## P2.2 — Budgets and metering (2026-10-17)

### `9558498` — schemas and TDD contracts (red)

Added `budget.schema.json` and `price_table.schema.json`, registered both in `SchemaStore`, and committed
the test contracts **before** the implementation: `tests/test_budgets.py` (24 cases) plus two engine cases
for soft-notify and hard-stop. The suite is intentionally red at this commit — the failing tests are the
specification for the next slice.

### `9948840` — the cost meter itself (`budgets.py`)

Pure cost arithmetic and nothing else — no file I/O, no subprocess, no model:

- `calculate_cost`: any usage key shaped `X_tokens` is priced at `X_per_1m` for that usage's model tier,
  so `input_tokens` / `output_tokens` / `cached_tokens` need no special case; an unknown model falls back to
  `default`; a missing tier or rate **raises** `BudgetError`, because unpriced usage that silently costs
  $0 would make the hard budget unenforceable. Negative counts clamp to 0, non-numeric counts raise.
- `stage_limits`: `usd` is the required hard limit; `soft_usd` overrides the soft limit, else a
  deterministic `0.8 × usd` rounded to cents; `soft_usd >= usd` raises rather than silently reordering.
- `check_budget`: inclusive boundaries (`==` hard stops, `==` soft notifies) and `ok` results carry the
  decisive bound so callers always know which limit applied.

**Still open (the 5 red tests):** the engine write path — `budget.json` per attempt,
`budget.soft_exceeded` / `budget.hard_exceeded` events — and the `doctor` checks that warn when soft ≥ hard
and reject an invalid price table.

**Current suite at `9948840`:** **312 collected — 305 passed, 2 skipped, 5 failed**.

### `08980ed` — the engine write path (budget enforcement live)

`_run_budget` runs after checks and guards, before the accept decision, pricing each attempt's reported
usage against the stage limits with factory config's price table:

- Verdict into `budget.json` (`{"status", "current_cost", "limit"}`) every budgeted round; the breach
  events (`budget.soft_exceeded` / `budget.hard_exceeded`) fire **only** on breach — per-attempt cost
  stays in the file, no per-round timeline noise.
- A hard breach fails the attempt (budgets are ground truth over reported usage, like guards) and
  `_run_stage` reads the verdict file to break the retry loop: `on_fail: loop` must not re-spend past an
  absolute stop. The job transitions to `failed`; raising the budget and re-executing is the operator's
  way forward.
- A soft breach notifies and the attempt still stands — the work completed within the hard ceiling.
- `BudgetError` (inverted limits, missing `usd`, unpriced usage) becomes the deterministic
  `config_error` status — same policy as `guard_config`, recorded, never a silent $0 cost.
- Cached refusal: an attempt whose `budget.json` already says `hard_exceeded` returns the cached failure
  without re-running the adapter on resume; a human redo (`reset=True`) re-opens it.

Dashboard: budget verdicts join guard notes as plain-language timeline rows
(`⚠ Hard budget exceeded in stage 'build' ($6.01 ≥ $5.00)` as a red row; soft notes say
"keeping going" with the stage still active).

One declared test fix: the soft-case env knob was corrected to 1,597,500 input tokens — the burner's
fixed 500 output tokens at $15/1M add $0.0075, so the attempt totals exactly $4.80 between the $4.00
soft and $5.00 hard limits. No assertion semantics changed.

### `1895f14` — doctor budget-integrity checks

`doctor` verifies the budget system's invariants at boot, before any spend happens:

- The `price_table` must validate against `price_table.schema.json` — **authoritative** (`ok=False`,
  nothing can be priced with a corrupt table). Doctor re-reads `factory.json` from disk at check time:
  it inspects the tree as it is, not the config snapshot taken at kernel init.
- Every stage budget must pass `stage_limits()` — advisory warning echoing the runtime `BudgetError`
  wording exactly, with the fix location appended (doctor and runtime speak the same words).
- Usage pricing coverage, aggregated per job (attempts repeat the same usage shape; per-file findings
  would flood the report): a model absent from the table is priced at the `default` tier when it exists
  (advisory — estimates may be off, pin a dedicated tier) and fails deterministically when it does not;
  a `*_tokens` metric whose rate the tier lacks fails at runtime, so doctor names it before the spend.

Read-only and order-stable: jobs by path, then model names, then metric names.

**Deviations recorded during P2.2** (documented here so HISTORY matches the tree):

1. **Per-million price table kept** — the shipped `X_per_1m` rate structure (tier names + `default`
   fallback) stayed instead of the initial per-token sketch (`llm_input_token: 0.000001`), matching
   `factory.json` as shipped and `price_table.schema.json`.
2. **Doctor wording uses the runtime vocabulary** — `soft_limit`/`hard_limit` (pinned tests +
   `stage_limits()`'s error message), not the initial `soft_usd`/`usd` sketch.
3. **Hard stop semantics** — a `hard_exceeded` budget transitions the job to `failed` (absolute stop,
   spec §543, acceptance-gate invariant) rather than advancing to the next stage; the input `source of
   truth` also pinned this via the committed `test_hard_budget_exceeded_fails_attempt_and_stops`.
4. **Dashboard extension** — budget verdicts render as plain-language `_timeline` rows alongside guard
   notes (soft: "keeping going", hard: red warning row); not in the original task list, declared for
   the manual verification requirement.

**Closing suite at `1895f14`:** **312 collected — 310 passed, 2 skipped** — fully green; flake8 clean;
`factory doctor` reports ok on the real tree, no budget-config warnings (only honest advisories: the
recorded fixture/demo jobs' models are priced at the `default` tier).

---

## P2.3 — Sandbox hardening (2026-10-17)

### `8348af8` — the schema and TDD contracts (red)

Registered the `factory` kind in `SchemaStore` and committed the project's first global-config schema,
`factory.schema.json`, validating the whole `factory.json` (`additionalProperties: false`; sandbox
`type` enum is `["process"]` until containers land). The shipped `factory.json` gained its hardening
block (`env_allowlist` + `strict_cwd: true`). `tests/test_sandbox.py` pinned the contracts red:
schema validation, `sanitize_env`, `resolve_under`, policy parsing, the `Adapter.run`
cwd/env subprocess contract, and one end-to-end engine case. Plus `tests/fixtures/adapters/env-probe/`,
an instrument whose `usage.json` records what environment it could *see* and its cwd inside the
subprocess — the kernel records those claims verbatim in its own job dirs, so probe results are
kernel-observed evidence, not adapter self-attestation.

### `408c538` — pure `sandbox.py` and the sandboxed engine wiring

`sandbox.py` is pure — no subprocess, no file I/O:

- `sanitize_env` keeps exactly the allowlist intersection of the env. Matching is case-insensitive on
  both sides (Windows env is case-insensitive; determinism beats platform drift); a rule without `*`
  is an exact name (`PATH` never keeps `PATH_TOKEN`), a `*`-suffix rule is a prefix, and the lone
  `"*"` is the explicit allow-all opt-out, documented as the foot-gun it is. Output preserves input
  order and values verbatim.
- `resolve_under` is lexical path containment: relative paths root at the base, absolute paths must
  already sit inside it, and any `..` escape raises `SandboxError` — computed by pure string math
  (`normpath` + platform `normcase`), with no filesystem access. Symlink resolution is deliberately
  not performed and documented as a limitation.
- `load_sandbox_policy` / `SandboxPolicy.from_config` fail hard: unknown type, empty allowlist, or
  malformed keys raise instead of guessing. Missing keys fall to documented defaults — a built-in
  allowlist of process essentials (`PATH`, Windows `SYSTEMROOT`/`SYSTEMDRIVE`, home, temp, and the
  kernel-reserved `FACTORY_*`) and `strict_cwd: false` for legacy back-compat.

Wiring: `Adapter.run` gained explicit `cwd`/`env` (defaults preserve the pre-sandbox behavior the
operator-side conformance harness uses — a trusted tool run by the operator). `engine._invoke_adapter`
now runs **every** adapter sandboxed: the env is the sanitized `os.environ` with kernel-reserved
attribution injected **after** the filter (`FACTORY_JOB_ID`, `FACTORY_STAGE`, `FACTORY_ATTEMPT`,
`FACTORY_ATTEMPT_DIR`, `FACTORY_WORKTREE` — the kernel owns that namespace and overrides any operator
value under it), `strict_cwd` locks the adapter process into the job worktree, and both paths handed
to the subprocess are proven contained in the factory root (`resolve_under`) before anything can see
them; a `SandboxError` fails the adapter run as `fatal`, the same deterministic policy as
`AdapterError`/`BudgetError`/`GuardError`.

**Deviations recorded during P2.3** (my own Step 2 test bugs, fixed and declared — no assertion
semantics changed): the `sanitize_env` expectation now keeps the kernel-reserved `FACTORY_JOB_ID`
alongside `PATH` (the test forgot the `FACTORY_*` rule it had itself configured); the
`AdapterSubprocess` test doubles mimic `CompletedProcess` (they returned `RunResult`, which has no
`stdout` for the NDJSON parser); the env-probe fixture also probes `FACTORY_JOB_ID` and
`FACTORY_ATTEMPT_DIR`, matching the manual verification checklist.

**Declared boundary:** project checks (`checks.run_one`) keep their full env — kernel-owned commands
run by the operator's own tooling are a separate concern from the agent sandbox, and their tools
(often `git`, node toolchains, pytest) need credentials to function; revisiting that is a later slice.

### `b3696c6` — doctor sandbox-integrity checks

Doctor verifies the sandbox system's invariants at boot, before any adapter runs under it (re-reading
`factory.json` from disk at check time, matching the budget convention):

- The whole config must validate against `factory.schema.json` — **authoritative** (`ok=False`): a
  corrupt config means the kernel cannot know which sandbox policy it is enforcing.
- `env_allowlist` containing `"*"` — advisory: a valid explicit opt-out, but it disables the primary
  security benefit of the sandbox (secret stripping), so doctor names it plainly.
- `strict_cwd` absent or false — advisory: legacy behavior is valid, but adapter processes then start
  outside the job worktree, which weakens isolation; the two states are worded distinctly.

Read-only and order-stable.

**Closing suite at `b3696c6`:** **343 collected — 341 passed, 2 skipped** — fully green; flake8 clean;
`factory doctor` reports ok on the real tree with no sandbox warnings; the manual env-probe run
confirmed the three sandbox facts end-to-end (secrets invisible, `FACTORY_*` attribution visible,
adapter cwd = the job worktree).

---

## P2.4 — Risk-scored gates (2026-10-18)

### `8c422fc` — the config contract and TDD contracts (red)

The `verify` stage declared `gate: risk_scored`, yet the engine evaluated every gate against a
hardcoded `risk = 0.0` (and kept a second hardcoded threshold table for `standard.yaml`'s
`if_risk_above:*` gates). This slice committed the contract the score must satisfy:

- `kernel/schemas/risk.schema.json` (kind `risk`; shape inlined in `factory.schema.json` — the
  project's ninth schema): `weights` for the five signals (guard_violation, budget_soft_exceeded,
  budget_hard_exceeded, check_failure, retry_attempt — non-negative integers, unknown keys rejected)
  and `thresholds`. The shipped `factory.json` gained the explicit block (40/20/50/15/10,
  thresholds 25/50/100) — configuration visible, not implicit.
- `risk.computed` added to the event-type enum: data carries stage, score, band, action, and the
  exact signals dict, so the gate's decision cites stored evidence, not recollection. Emission
  scope recorded up front: only gates that consume risk pay the event.
- `tests/test_risk.py` (32 cases): schema/contract cases green at landing; 21 pure-function cases
  and 2 engine-wiring cases deliberately red — the specification for the next slices. Suite at this
  commit: **375 collected — 350 passed, 2 skipped, 23 failed**, the failures exactly the named reds.

**Contract deviations recorded during P2.4** (the pinned tests are the spec; the task sketch
yielded — declared, not silently bent):

1. **Kernel-owned `gate_actions`.** The band→action map (`low → auto_advance`,
   `medium → awaiting_human`, `high → blocked`) is NOT operator-configurable. A config that could
   set `high: "auto_advance"` would let tuning negotiate the safety floor away — the same reason
   guards and budgets are kernel code. The schema rejects `gate_actions`, and the doctor names
   any attempt as the kernel-ownership violation it is.
2. **Thresholds are ceilings, not floors.** `score < low → low`, `< medium → medium`, else high;
   `thresholds["high"]` doubles as the clamp cap. Floor semantics ("score ≥ 100 is high") would
   make the top band nearly unreachable with sane weights. The loader adds what JSON Schema
   cannot express: cross-key monotonic ordering and strict-integer values (a float `2.0` weight
   is invalid here).
3. **`compute_score` takes the full config dict** (cap derives from `thresholds`), and the signal
   vocabulary is the pinned 4-key kernel shape (`guard_violations`, `budget_status`,
   `check_failures`, `attempt_number`) rather than the sketch's weight-key booleans — the verb
   keys would collide with weight names and lose the status-vs-count distinction.
4. **`assess` returns a plain verdict dict.** The pinned contracts compare dict equality; the
   sketch's `RiskVerdict` dataclass would have needed equals-gymnastics for zero kernel benefit —
   the kernel's existing style passes plain dicts (budget verdicts, check results).

### `0f76850` — pure `risk.py` and the gate wiring

`risk.py` is pure — no subprocess, no file I/O: `compute_score` (weighted sum clamped at the cap;
unknown, missing, negative, or non-integer input raises `RiskError` rather than becoming a guessed
score), `resolve_band` (strict ceilings), `gate_action` (kernel-owned map), `assess` (one verdict
dict whose score/band/action all cite the same checked numbers), `load_risk_config` (`None` →
documented defaults; present-but-empty or malformed → `RiskError`; defensive copy).

Wiring (`engine._apply_gate` / `_risk_gate` / `_stage_signals`), and the slice's key design
decision — **stage-scoped signals**: the gate only ever evaluates a *passed* attempt, so failures
of the winning attempt are impossible by definition; what is real is the road that got here. Guard
violations and check failures are summed across the stage's recorded rounds (they made the stage
retry), the winning attempt number carries the retries, and the winning attempt's `budget.json`
carries the possible soft breach. Without this, `retry_attempt` and `check_failure` weights could
never score non-zero. The verdict lands in `risk.computed` verbatim before `gate.evaluated`;
`auto_advance` → decision `auto`, `awaiting_human` → decision `require_human` (job parked at
awaiting_human at the risk gate), `blocked` → decision `blocked` (deterministic job failure citing
score/band — the counterpiece of the P2.2 hard stop). A `RiskError` at gate time fails the job
deterministically, the same policy as unpriced usage: a broken risk config must never degrade into
a silently loosened gate. `if_risk_above:L` now compares the computed band's severity to the level
(the old hardcoded table is gone). Noise promise kept: `gate: none`/`required` stages never emit.

One declared Step 2 test fix (no semantics change): the config-flip engine test's signature dropped
the `kernel`/`demo_job` fixtures it created and never used (a fresh `Kernel` over the edited
factory.json was already the point).

Manual verification on the real engine path with the default shipped config: a crafted
*recovering* check (fails attempt 1, passes attempt 2 of verify) scores a genuine
`1×15 + 1×10 = 25 → medium → require_human`, parking the job at the risk gate; a clean sibling
tree runs `0 → low → auto` through the same gate, with the approve stage still demanding its human.

### `7778f06` — doctor risk-integrity checks

Doctor verifies the risk system's invariants at boot (the section re-read from disk, matching the
convention): `risk_scoring` schema-validity is authoritative (`ok=False` — the kernel cannot
compute scores from a corrupt config); `gate_actions` is authoritative too, naming the
kernel-ownership violation explicitly instead of burying it in a generic additional-properties
message; zero (or negative) weights and non-monotonic thresholds are advisories — runtime refuses
the latter, doctor surfaces it earlier so no job has to die of it first. Read-only, order-stable
(weight warnings sorted by signal name).

Declared while verifying: the zero-weights expectation originally listed the two signals in the
wrong order (alphabetically `check_failure` sorts before `guard_violation`).

**Closing suite at `7778f06`:** **380 collected — 378 passed, 2 skipped** — fully green; flake8
clean; `factory doctor` reports ok on the real tree with no risk warnings. Risk-scored gates are
the last enforcement slice of the trust layer's kernel-computed signals: guards say what changed,
budgets say what it cost, sandbox says what the agent could see, and risk now says how worried the
kernel is about the road to acceptance.

---

## P2.5 — Prompt-injection handling (2026-10-19)

### `344c81f` — the schema contract (green)

`kernel/schemas/injection.schema.json` (the project's tenth schema, kind `injection`; the shape
inlined as an optional section in `factory.schema.json`): configurable detection `patterns`
(`id`, `pattern`, optional non-negative integer `weight`), `additionalProperties: false` at every
level. The shipped `factory.json` keeps **no** `injection` section — absence is the documented
baseline configuration, not an unconfigured guess. The same commit registered the
`injection.detected` event type and added the `injection_flag` risk weight (shipped default 100, so
a single flag alone clears the high band).

### `ae7fc58` — TDD-red contracts (red)

`tests/test_injection.py` (30 cases): the schema cases green at landing; the detector, engine, and
doctor cases deliberately red — the written contract for the next commits.

### `851987f` — pure `injection.py`

The detector is pure: no subprocess, no file I/O, no LLM. `load_injection_config` (absent → the
documented kernel baseline patterns; present-but-empty, malformed, an invalid regex, a negative or
non-integer weight, or a config id colliding with a kernel-owned baseline id → `InjectionError`;
defensive copies), `scan_item` (regex match, excerpt truncated at 80 chars, confidence 1.0),
`scan_manifest_items`, and `injection_signal` (1 when any item was flagged).

**Design decisions recorded during the slice** (declared, not silently bent):

1. **The response is kernel-owned; only detection is configurable.** The kernel ships four baseline
   patterns (`ignore-previous-instructions`, `system-prompt-leak`, `do-not-follow`,
   `pretend-to-be`). A config may **add** patterns; reusing a baseline id is rejected outright,
   because a tunable detection set that could *remove* the baseline would let configuration
   negotiate the safety floor away — the same reasoning that keeps the risk band→action map out of
   config.
2. **No new enforcement path.** A detection becomes the `injection_flagged` signal (weighted by `injection_flag`) and the
   **existing** band→action map decides (low → auto-advance, medium → park for a human, high →
   blocked). The kernel gained no new way to stop a job; it gained a new *observation*.
3. **Detection runs on manifest untrusted items, before the adapter sees them** — not on adapter
   output, which is the guards' job. The manifest entry is labeled with `injection_flags` so the
   agent *sees* that the kernel flagged something, and the same pass emits the events. Labeling
   without the signal, or the signal without the label, would each be half a control.

### `ed55c31` — engine wiring

Untrusted items under the job's `issues/` are discovered and scanned before the adapter runs; flags
are attached to the manifest entries, one `injection.detected` event is emitted per match (stage,
attempt, item path, pattern id, ≤80-char excerpt, confidence 1.0), and the job-wide
`injection_flagged` signal feeds the P2.4 weighted score. An `InjectionError` becomes the
deterministic `config_error` status and writes an `injection.json` verdict file — a broken
detector can never degrade into "nothing flagged".

### `878629b` — doctor injection-integrity checks

Section schema validity is authoritative; a config pattern id colliding with a kernel-owned baseline
is an authoritative error naming the ownership violation; zero-weight patterns are advisories
(sorted by pattern id). Read-only, order-stable, re-reading `factory.json` from disk.

## P1.1 — Solo dashboard task player (2026-10-19)

Commits on `feat/dashboard-task-player` (PR #1), all in the Solo dashboard:

- `a8697f1` — a sticky task-player footer bound to the active job (status glyph, brief, stage
  progress, and Resume / Needs-you / Stop controls that stay reachable from any scroll position).
  The controls are static nodes toggled by visibility rather than rebuilt per stream tick — an
  early version recreated them on every frame and swallowed an in-flight click, which the live
  check caught.
- `c45d8a7` — the footer offered Resume for blocked/stalled/failed/paused jobs, but
  `Engine.execute` accepts only pending/running/awaiting_human, so every such click failed with
  "Job is 'blocked'; cannot execute". The footer now offers only the actions the kernel will
  actually run, and the ambient status line names the reason (the state phrase) instead of the
  active-stage phrase — the footer no longer contradicts the card above it.
- `7b94aeb` — the read-only export hid the sticky footer because the render path gated it on LIVE,
  so a colleague opening the snapshot lost the ambient "what is the factory doing" signal. The
  export now renders the footer too; in read-only mode the controls still render and a click lands
  on the export's "Read-only export" note, the same contract as the top-level Undo button.
- `d933adf` — the footer was invisible to assistive tech: a decorative arrow glyph, a progress strip
  with no role, and a stage line that changed silently. It is now a labelled region containing a
  real `role=progressbar` (value from the streamed model, as both `aria-valuenow` and a "3 of 5
  stages" `valuetext`) and a polite live status, so a "needs you" transition is announced instead
  of merely drawn.
- `77f32e9` — the review round, and the one that found a real defect: **Stop did not stop the
  work.** `job_cancel` changed the saved state while the adapter process kept running, so the
  agent went on editing files and spending money after the operator was told the job had stopped.
  - `kernel/src/factory_kernel/cancel.py` — process-tree termination (a POSIX process group, a
    Windows `taskkill /T`) and a cancellable run loop with a deadline and a cancel predicate.
  - `adapters.py` / `checks.py` — the adapter and the check runner run under that loop; a
    cancelled run reports the new `cancelled` error class instead of a verdict.
  - `engine.py` — the engine polls the job's own state and the lease fence, so a cancel kills the
    work in flight, skips the checks, and writes nothing after the operator's own state change.
  - `dashboard.py` — the footer tracks *unfinished* work (a freshly finished job no longer hides a
    pending one), a pending job plays the play glyph instead of the pause glyph, a paused job
    names the pause instead of the stage it was in, and the footer stacks on narrow screens so the
    Stop control stays reachable.

**Closing suite at `77f32e9`:** **437 collected — 435 passed, 2 skipped** — fully green; flake8
clean.

---

## Post-HEAD work (landed as `634ff41` and earlier)

Performed by the documentation session (see [AI-PROVENANCE.md](AI-PROVENANCE.md)):

- Created the categorized `docs/` tree: `product/`, `architecture/`, `specification/`, `plans/`,
  `development/`, `operations/`, plus `docs/context/` (this folder).
- Added root `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`.
- Moved the Specification v3.0 into `docs/specification/`.
- Added the provenance tool, `.gitmessage`, `.githooks/commit-msg`, `.provenance-allow`, and the CI
  workflows (`lint-and-test` plus a `provenance` job).
- Reconciled plan status with reality (P1 is implemented, not merely planned).

---

## Hardening sessions (2026-10-16, landed)

Three working sessions extended `9398dfe` before P2 began. Test counts below are from the suite **at the
time of each session**; they are a record of growth, not current state.

### Session A — recovery, live backend, doc reconciliation
- Fixed the `gitrepo.is_repo` parent-walk-up bug: a repo-less project nested in
  the factory's own checkout had checkpoint commits land in the outer repo and
  its resume `reset --hard` dropped approve-time events. Outer history was
  reset to `9398dfe` (working tree kept); regression tests added
  (`test_worktree.py`, 10 tests).
- Hardened `adapters/cli-agent/run.py` into the first live backend: external
  command NDJSON forwarding, honest failure classes (`fatal`/`transient`),
  `resume` exercised, conformance recorded; 8 tests in `test_cli_agent.py`.
- Proved the full P1 loop twice on fresh projects (`slice`, then `live` with
  real non-estimated usage).
- Reconciled all plan/doc files with the implemented tree.

### Session B — question budget + visual-evidence plumbing (P1 completion)
- Schema migration: `event.schema.json` enum + `job.question_asked`;
  `job.schema.json` + optional `questions` ledger (folded; `human.answer`
  marks entries answered). Logged in `kernel/schemas/CHANGELOG.md`.
- Engine: adapter `question` events persisted durably, deduped by id/normalized
  text, ≤ 3 blocking per job (`MAX_BLOCKING_QUESTIONS`); a new blocking
  question parks the job `blocked` before any accept, past-budget fails the
  job. Questions + answers reach future attempts via `questions.md` in the
  context manifest.
- Answer side: `factory job answer` / `JOB.answer` with option buttons + free
  text; `change`/`answer` resume with the same adapter (`--adapter`).
- Visual contract: `<attempt>/outputs/visual.json` manifest convention
  (`ADAPTERS.md` §7), dashboard collection (`preview.visual`) + rendering with
  synthetic-fixture labeling; fixtures emit labeled manifests under
  `FACTORY_FIXTURE_VISUAL=1`. No real screenshot producer exists yet — the
  contract is open, evidence stays honest.
- Tests +10: `test_questions.py` (9) and one in `test_cli_agent.py`.
- E2E on the real tree (project `ask`): `blocked` → answer → completed →
  approve → `merge.completed` → undo; visual manifests collected from all 6
  attempts, labeled synthetic. Suite: **224 collected — 222 passed, 2 skipped**;
  flake8 clean; `doctor` ok.

---

### Session C — real visual capture (P1 visual evidence closes)
- Built `adapters/visual-capture/capture.py`, a stdlib-only producer driving
  headless Edge/Chrome. Chromium's `--blink-settings=preferredColorScheme`
  semantics vary per build (this machine's Edge renders dark with **no**
  flag), so the producer pixel-probes a tiny light/dark page at runtime to
  learn the mapping — never hardcoded; inconclusive → dark capture skipped
  with a note.
- Kernel wiring: `checks.run_one`/`run_checks` accept `extra_env`; the engine
  exports `FACTORY_ATTEMPT_DIR` + `FACTORY_VISUAL_OUT` into every check
  subprocess (a real bug was caught here: `run_checks` initially didn't
  forward `extra_env` to per-check `run_one` — caught by the env-probe test).
- `project_create` now wires the default `visual` check to the real
  producer; missing page → `skipped` manifest (exit 0), failed capture →
  exit 1 with the manifest untouched.
- Hermetic tests use `tests/fixtures/adapters/fake-browser.py` with a theme
  mapping inverted vs. the dev Edge, so the probe logic is genuinely
  exercised; `cli-echo-agent.py` gained `FACTORY_FIXTURE_HTML=1` to build a
  real page.
- E2E on the real tree (project `vis-e2e`, job `01M53NJ23…`): four genuine
  Edge captures (light/dark × 1280x800/390x844, pixel-verified white vs
  #111) bound to the checkpoint SHA via attempt outputs; approve →
  `merge.completed` → undo; dashboard shows them with `synthetic: false`.

### Session C2 — "Explain this" + visual diff (P1 polish)
- `"explain"` dashboard command + card button: plain-language explanations
  derived only from kernel state/events/artifacts (approval quotes the
  checkpoint SHA and separates real vs. labeled-synthetic captures; blocked
  shows the open question and budget usage; stalled names the no-progress
  rule).
- `capture.py --diff-previous` annotates entries with `changed_pct` (pixel
  share differing by > 8/255; auto previous attempt from `FACTORY_ATTEMPT_DIR`);
  dashboard renders `changed N%`. Different dimensions → no number.
- Real-tree proof on genuine captures: identical rebuild → `0.0`
  everywhere; a real copy edit → `1.1%` desktop / `3.4%` mobile.
- Tests +6 (2 × explain, 4 × diff), plus the growing hermetic coverage in
  `tests/test_visual_capture.py`. Suite after the session:
  **242 collected — 240 passed, 2 skipped**; flake8 clean; `doctor` ok.

---

## Test-count growth (a proxy for progress)

| Commit | Tests (passed / total) |
|--------|------------------------|
| `d328d49` (P0 skeleton) | — |
| `b96c6c5` (P0 hardening) | 81 |
| `f1ffc41` (P0 polish) | 109 |
| `fd06130` (P1 engine) | 142 / 144 |
| `92b0b2a` (P1 checkpoints) | 154 / 156 |
| `a3fde93` (P1 conformance) | 159 / 159 |
| `5dfdf19` (P1 dashboard) | **171 / 173** (2 skipped) |
| `9398dfe` (P1 worktrees/merge/undo) | **203 / 205** (2 skipped) |
| session A (recovery + live backend) | 212 / 214 (2 skipped) |
| session B (question budget + visual plumbing) | 222 / 224 (2 skipped) |
| session C (real visual capture) | 234 / 236 (2 skipped) |
| session C2 (explain + diff polish) | **240 / 242** (2 skipped) |
| `9010e60` (P2.1 guards complete) | **284 / 286** (2 skipped) |
| `634ff41` (docs reconciliation) | 284 / 286 (2 skipped) |
| `9558498` (P2.2 schemas + red contracts) | 284 / 290 (6 red — TDD) |
| `9948840` (P2.2 cost meter, **current HEAD**) | **305 / 312** (2 skipped, 5 red — the P2.2 wiring contracts) |

---

## What this history suggests

1. **Ordering discipline:** P0 invariants (atomicity, fencing, transitions, schemas) were finished and
   tested *before* any execution engine was added — exactly as the roadmap demands.
2. **Test-first evidence:** each commit adds its own test module; the suite grew monotonically with features.
   The one place the count dips is deliberate: P2.2 committed its failing contracts *before* the
   implementation, so the tests specify the slice instead of describing it afterwards.
3. **Spec-driven:** every commit message cites the specification section it implements (§5.2, §7, §9.2, §20.3, §21).
4. **Schema changes are logged:** the `kernel/schemas/CHANGELOG.md` documents each change and its migration.
5. **Two focused build days, one author:** 2026-10-16 delivered P0 and P1; 2026-10-17 delivered the P1
   hardening, P2.1, and the start of P2.2. Authorship is a single human (`iDorgham`) throughout.
6. **Dogfooding the provenance convention:** from P2.1 the project's own claim about how each change was
   produced is machine-checkable rather than remembered — which is the whole thesis applied to itself.

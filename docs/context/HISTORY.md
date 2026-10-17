# Project History

Complete development history of the Enterprise AI Software Factory, reconstructed from `git log` and the
repository contents. Snapshot date: **2026-10-16**.

- **Repository:** local git repo, branch `master`, HEAD `9398dfe` (was `5dfdf19` after the new commit).
- **Author of all commits:** `iDorgham` (`yasser.dorgham@gmail.com`).
- **All 8 commits are dated 2026-10-16** (a single intensive build day).
- **Tooling:** the owner attests that **P0 and P1 were developed with OpenCode using the Big Pickle model**
  (not machine-verified; see [AI-PROVENANCE.md](AI-PROVENANCE.md)).

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
**Phase:** P1 · **Date:** 2026-10-16 · **Current HEAD**

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

---

## Post-HEAD work (not yet committed)

Performed by the documentation session (see [AI-PROVENANCE.md](AI-PROVENANCE.md)):

- Created the categorized `docs/` tree: `product/`, `architecture/`, `specification/`, `plans/`,
  `development/`, `operations/`, plus `docs/context/` (this folder).
- Added root `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`.
- Moved the Specification v3.0 into `docs/specification/`.
- Reconciled plan status with reality (P1 is largely implemented, not merely planned).

These changes are uncommitted in the working tree at the time of writing.

---

## Post-HEAD hardening sessions (2026-10-16, uncommitted)

Three working sessions extended the pinned HEAD `9398dfe`. All changes remain
uncommitted in the working tree; test counts below are from the current suite.

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
- Tests +6: suite **242 collected — 240 passed, 2 skipped**; flake8 clean;
  `doctor` ok.
- Tests +12 (`tests/test_visual_capture.py`): suite **236 collected — 234
  passed, 2 skipped**; flake8 clean; `doctor` ok.

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
| `9398dfe` (P1 worktrees/merge/undo, HEAD) | **203 / 205** (2 skipped) |
| uncommitted (recovery + live backend, session A) | 212 / 214 (2 skipped) |
| uncommitted (question budget + visual plumbing, session B) | 222 / 224 (2 skipped) |
| uncommitted (real visual capture, session C) | 234 / 236 (2 skipped) |
| uncommitted (explain + diff polish, session C2) | **240 / 242** (2 skipped) |
| `9010e60` (P2.1 guards complete) | **284 / 286** (2 skipped) |

---

## What this history suggests

1. **Ordering discipline:** P0 invariants (atomicity, fencing, transitions, schemas) were finished and
   tested *before* any execution engine was added — exactly as the roadmap demands.
2. **Test-first evidence:** each commit adds its own test module; the suite grew monotonically with features.
3. **Spec-driven:** every commit message cites the specification section it implements (§5.2, §7, §9.2, §20.3, §21).
4. **Schema changes are logged:** the `kernel/schemas/CHANGELOG.md` documents each change and its migration.
5. **Single author, single day:** consistent authorship and timestamps suggest one focused build session per phase.

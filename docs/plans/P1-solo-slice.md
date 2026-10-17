# P1 — Solo Slice Plan

**Phase:** P1
**Status:** ✅ Complete — question budget and visual evidence landed (see "Hardening landed 2026-10-16 (PM)" and "(evening)"): the Solo question budget, `visual.json` contract, dashboard rendering, and a **real capture producer** (headless Edge/Chrome with runtime theme probe) are all proven end-to-end on the live `cli-agent` backend.
**Goal:** Make the Solo promise real: *a beginner types one sentence and gets a previewable, checked result, with at most two clicks of approval and no configuration.*

> Reconciled 2026-10-16 against the repository: worktree isolation, merge queue, and Undo are implemented (`gitrepo.py`, `kernel._merge_on_complete`, `kernel.job_undo`, `test_worktree.py` — 9 tests). Earlier "NOT STARTED" notes below are superseded.

## Scope

Per the [roadmap](ROADMAP.md): `lite` profile end-to-end execution, one real adapter, a build loop with no-progress detection, `factory serve` with the three-element dashboard, SHA-bound approval card, and undo.

## Workstreams

### 1. Real worktree isolation — ✅ DONE (was "NOT STARTED"; implemented in `9398dfe`)
- [x] `git worktree add .work/<job-id> -b factory/<job-id> <base-sha>` on job creation (`gitrepo.add_worktree`, `kernel.job_execute`)
- [x] Per-job worktree directory at `.work/<job-id>` on branch `factory/<job-id>` (port-range allocation still open — not needed for Solo)
- [x] Checkpoint at every stage attempt end: content-addressed result SHA in the attempt record (`checkpoint.py`)
- [x] Recovery: resume restores the last accepted attempt state via `git reset --hard` + `clean -fd` — never treats a killed run as success
- [x] `doctor` upgraded: real worktree/branch checks, orphan detection, stale-base detection (`kernel.doctor`)
- [x] Tests: kill mid-attempt → `interrupted`, never success; resume restores worktree (`test_worktree.py`, 9 tests)

### 2. Build loop with no-progress detection (kernel construct) — ✅ DONE
- [x] Round structure `build → checks → review(advisory) → fix` executed by the Engine, bounded by `max_rounds`
- [x] Round context built from the manifest (plan + requires), never full transcripts
- [x] Failure fingerprint per round (failing check IDs + normalized error signatures) (`checks.fingerprint`)
- [x] `stalled` on: same fingerprint in two consecutive rounds, or empty diff (spec §9.2)
- [x] Escalation handled via stage `on_fail` (`loop | escalate | fail`)
- [x] Attempt statuses incl. `interrupted`; input-hash idempotency for accepted attempts

### 3. One real adapter (via the run contract) — ✅ DONE (live `cli-agent` backend + recorded conformance)
- [x] Run contract, streaming events, heartbeat, usage, idempotent start, cancel/resume, write boundary, error classes, conformance suite (`adapters.py`, `conformance.py`, `factory adapter test`)
- [x] Generic `adapters/cli-agent/` shell-out backend hardened into the first live adapter: external-command NDJSON forwarding (`progress|tool_use|file_written|question|usage|heartbeat|done|error`), real (non-estimated) usage preserved, honest failure (nonzero exit or exit-0-with-missing-outputs → `fatal`; timeout → `transient` so the kernel retries), run_id idempotency, no placeholder backfill
- [x] `resume` capability declared and exercised (was skipped); `factory adapter test cli-agent` passes, recorded in `adapters/cli-agent/conformance.json`
- [x] Proven end to end against a live command (`tests/fixtures/adapters/cli-echo-agent.py` via `FACTORY_CLI_AGENT_CMD`): `run → execute → approve → merge → undo` on project `live` with real usage in `usage.json`; a misconfigured command fails honestly (`fatal` + `stalled` on no-progress, with stderr in the event)
- [x] Wiring guide: `docs/development/ADAPTERS.md` §6 (any CLI works: `opencode run`, `claude -p`, a script)

### 4. `lite` profile execution end to end — ✅ DONE (incl. real visual capture, 2026-10-16 evening)
- [x] Understand → normalize request into `brief.md`; blocking questions → `blocked`
- [x] Plan → `plan.md` with ordered tasks, acceptance criteria, risks, expected file set (planning stays mandatory)
- [x] Build loop (workstream 2) driven through the stage graph
- [x] Verify → checks run (`checks.py`), including the real `visual` capture check on web projects (`adapters/visual-capture/capture.py` — genuine headless-Edge/Chrome screenshots into attempt outputs)
- [x] Approve and merge → approval gate parks at `awaiting_human`; approving runs `--no-ff` merge into `main` via `_merge_on_complete` (conflict → `blocked`); `job undo` reverts it

### 5. Solo UX: `factory serve` + dashboard — 🟨 MOSTLY DONE
- [x] Local HTTP server streaming events from the log to the browser (`serve`, SSE); `export-dashboard` static snapshot
- [x] Three elements only: prompt box with cost/time estimate · plain-language timeline · single "Needs you" card
- [x] Approval card: preview link + assumptions, actions **Approve** / **Change this…**
- [x] Hidden "Details" drawer showing the raw event timeline; first-run empty-state sample (`_create_sample`)
- [x] Every dashboard action is dispatched as a kernel command (`POST /api/command` → `dispatch`)
- [x] Blocking questions: a `question` NDJSON event is persisted durably
  (`job.question_asked`), the job parks `blocked`, and the "Needs you" card
  renders the question with option buttons + a free-text answer box
  (`JOB.answer` dispatch); the answer (and later answers) reach future attempts
  via `questions.md` in the context manifest (see workstream 6)
- [x] Screenshots at declared viewports, light+dark: `visual.json` captures
  land in attempt outputs via the real producer
  (`adapters/visual-capture/capture.py`, headless Edge/Chrome with runtime
  theme probe), wired as the default `visual` check, bound to the checkpoint
  SHA, and rendered in the dashboard with `synthetic: false`
- [ ] Visual-diff % and live-server preview capture (P2/P4 territory:
  baselines are spec'd for P4; the contract already carries viewport/theme
  naming so diffs can be added without format churn)
- [ ] "Explain this" / "What should I do next?" helpers

### 6. SHA-bound approval and undo — ✅ DONE
- [x] Approval bound to a checkpoint SHA; a changed result invalidates it and the job stays `awaiting_human`
- [x] Record approver identity, SHA, and feedback in the event log (`human.approval`)
- [x] `factory job undo <job-id>`: reverts the merge as a new audited event chain (`merge.undone`; double-undo and unmerged refused)
- [x] Solo question limit: ≤ 3 blocking questions per job (4th fails the job, nothing hidden from the ledger), multiple-choice phrasing per `roles/analyst.md`, re-asks deduped by id/normalized text so a stuck agent can't burn the budget (workstream 5 + this: landed 2026-10-16 PM)
- [x] Assumptions ledger surfaced; `request-changes` reopens the last accepted stage for rework (resume keeps the same adapter via `--adapter`)

## Remaining P1 work (the real blockers)

1. ~~**Solo question budget**~~ — **DONE (2026-10-16 PM)**: `job.question_asked` event
   (schema enum widened), engine counting with dedupe, `factory job answer`,
   dashboard question card. See "Hardening 2026-10-16 (PM)" below.
2. ~~**Visual evidence**~~ — **DONE (2026-10-16 evening)**: the contract, the
   dashboard collection/rendering, **and a real capture producer**
   (`adapters/visual-capture/capture.py`, headless Edge/Chrome with
   runtime theme probe) are all landed; proven end-to-end on the real tree —
   see "Hardening 2026-10-16 (evening)" below.

## Hardening landed 2026-10-16 (uncommitted)

- `gitrepo.is_repo` walk-up bug fixed (repo-less worktree nested in the factory clone was treated as a worktree; checkpoint commits polluted the outer repo and resume `reset --hard` dropped approve events → approve failed). Outer history restored to `9398dfe`; regression test added.
- Verified end to end on project `slice`: `run → execute (awaiting_human, 5 checkpoints) → approve (completed + merge.completed) → undo (merge.undone)`, `doctor` clean, outer repo untouched. The legacy repo-less `demo` job `01M530145TVZAR4VKZ2DBF14FE` remains `failed` as evidence of the bug (its approve-time events were dropped before the fix); repo-less jobs created after the fix complete without a merge event.

## Hardening landed 2026-10-16 (PM) — question budget + visual plumbing

- **Schema migration** (`kernel/schemas/`, logged in `kernel/schemas/CHANGELOG.md`):
  `event.schema.json` enum + `job.question_asked`; `job.schema.json` + optional
  `questions` ledger folded from events (`human.answer` marks entries answered).
- **Engine**: `_record_questions` persists adapter `question` events with dedupe
  (fixed id or normalized text ⇒ not re-counted) and
  `_blocking_question_count` enforces ≤ 3 (`MAX_BLOCKING_QUESTIONS`); a new
  blocking question parks the job `blocked` before any accept, and once the
  budget is exhausted the job **fails** honestly instead of interrogating
  forever. Questions (asked+answered) flow to future attempts through
  `questions.md` in the context manifest (`context.collect_stage_context`).
- **Answer side**: `kernel.job_answer` (`factory job answer`, `JOB.answer`),
  records `human.answer`, appends `### A: <qid>` to `questions.md`, resumes with
  the same adapter (`--adapter`), then executes. Validation: not-blocked /
  unknown question / empty answer / already-answered all refused.
- **Dashboard**: the `blocked` needs-you card carries `questions` with option
  buttons (one click answers) + a free-text box; `change` passes `adapter` too.
- **Visual contract** (`ADAPTERS.md` §7): adapters record screenshot manifests as
  `<attempt>/outputs/visual.json` (entries: viewport/theme/file, `synthetic`
  labels fixtures); `dashboard._preview` collects them (`preview.visual`) and
  the page renders entries, marking synthetic ones "not a real screenshot".
- **Fixtures**: `cli-ask-agent.py` (ask modes `once|always|unique|info`) for
  budget tests + E2E; both fixtures emit synthetic visual manifests under
  `FACTORY_FIXTURE_VISUAL=1`.
- **Tests**: 9 new in `tests/test_questions.py` (schema, park, answer→resume,
  dedupe, exhaustion→`failed`, info-questions never block, answer validation,
  visual collection), +1 in `test_cli_agent.py` (synthetic manifest through the
  live adapter). Suite: 224 collected, 222 passed, 2 skipped (historic); flake8
  clean.
- **E2E on the real tree** (project `ask`, jobs
  `01M53EZ41EJ…` / `01M53K5HF5E33MVCRK4DBP3807`): `run → execute (blocked,
  question q-hero with options) → answer Split (ask again for un-burned
  repeat → deduped; re-run unchanged) → completed; approve → merge.completed →
  undo → merge.undone`. Live usage recorded in `results.json`; visual manifests
  collected from all 6 attempts, all labeled synthetic. `doctor` ok (one
  expected expired-lease warning on the cancelled stalled job).

## Hardening landed 2026-10-16 (evening) — real visual capture

- **Real producer** `adapters/visual-capture/capture.py` (stdlib-only): drives
  headless Edge/Chrome (no new Python dependencies); browser discovery
  (`--browser` → `FACTORY_VISUAL_BROWSER` → Edge → Chrome), per-launch temp
  profiles, declared viewports (default 1280x800 + 390x844), and light+dark
  themes forced via `--blink-settings=preferredColorScheme=<v>`.
- **Theme mapping is probed, never hardcoded**: headless Chromium builds
  disagree about `preferredColorScheme` (the dev machine's Edge renders dark
  even with no flag) — the producer pixel-decodes a tiny probe page at
  runtime to learn the actual dark value; inconclusive → dark captures are
  skipped with a stderr note, not guessed.
- **Kernel wiring**: `checks.run_one/run_checks` accept `extra_env`; the
  engine exports `FACTORY_ATTEMPT_DIR` + `FACTORY_VISUAL_OUT` (absolute
  attempt outputs dir) into every check subprocess; `project_create` wires
  the default `visual` check to the real producer (`--url index.html`).
- **Manifest semantics**: real capture writes `synthetic: false`; existing
  synthetic manifests are discarded, existing real entries merge (same
  viewport/theme overwritten). Missing page → `skipped` manifest, exit 0.
  Failed capture → exit 1, manifest untouched (honest failure).
- **Fixtures**: `tests/fixtures/adapters/fake-browser.py` is a stdlib
  headless-browser shim with a theme mapping *inverted* relative to the dev
  Edge, so the probe path is genuinely exercised hermetically.
  `cli-echo-agent.py` gained `FACTORY_FIXTURE_HTML=1` (writes a light/dark
  aware `index.html` into the worktree).
- **E2E on the real tree** (project `vis-e2e`, job
  `01M53NJ23EGX6BJXYS50ND59Y6`): the agent built a real page in the
  worktree; the verify stage's `visual` check captured 4 genuine headless-Edge
  screenshots (300 × 200; light/dark × 1280x800/390x844; pixel-verified
  white vs #111), bound to the checkpoint SHA via attempt outputs;
  `completed; approve → merge.completed → undo → merge.undone`; the
  dashboard shows the entries with `synthetic: false`.
- **Tests**: 12 new in `tests/test_visual_capture.py`; suite now
  **236 collected — 234 passed, 2 skipped** (historic skips); flake8 clean;
  `doctor` ok (the one expected expired-lease warning on the cancelled
  stalled job).

## Hardening landed 2026-10-16 (late evening) — "Explain this" + visual diff

- **"Explain this"** on every needs-you card (approve / question / stalled):
  `dispatch "explain"` returns a plain-language explanation derived **only**
  from kernel-visible state, the event log, and attempt artifacts — never
  from agent self-report. Approval lines quote the checkpoint SHA and the
  evidence counts (real vs. labeled-synthetic captures separately); blocked
  lines show the open question and the blocking-budget usage; stalled lines
  name the honest no-progress rule. Rendered in a collapsible box on the
  card; static export shows a read-only notice.
- **Visual diff `changed_pct`**: `adapters/visual-capture/capture.py
  --diff-previous` annotates each captured entry with the share of visibly
  changed pixels (channel delta > 8/255, noise-tolerant) vs. the same
  viewport/theme in the previous attempt (`auto`: derived from
  `FACTORY_ATTEMPT_DIR`; or an explicit manifest path). Different
  dimensions/unreadable PNGs → no number, never guessed. The engine's check
  env carries the attempt dir, and the default wired check includes the
  flag; the dashboard renders `changed N%` per entry.
- Real-tree proof: same-input rebuild → `0.0` on all four genuine captures;
  a real copy edit → `1.1%` desktop / `3.4%` mobile.
- Tests +6 (2 × explain, 4 × diff): suite now **242 collected — 240 passed,
  2 skipped**; flake8 clean; `doctor` ok.

## Explicitly out of scope for P1

Budgets/metering enforcement, anti-cheating guards, hardened sandbox, risk-scored gates, import, skills/evals, epics, visual baselines, RBAC, audit chain — those are P2+.

## Exit criteria (maps to spec success criteria)

1. A beginner types one sentence → previewable result, ≤ 2 approval clicks, zero configuration.
2. Killing the process at any point and resuming never corrupts state (checkpoint recovery + `interrupted` attempts).
3. Passing checks — not agent statements — allow the job to complete.
4. `factory doctor` clean on a real tree after every recovery scenario.
5. Full test suite green; hermetic tests cover loop, fingerprint, recovery, and adapter contract paths.

## Risks and mitigations

| Risk | Mitigation |
|------|-----------|
| Real adapter flakiness breaks hermetic tests | Tests use the echo adapter + fixtures; the real adapter is exercised by the conformance suite |
| Dashboard scope creep | Three-element rule is a hard constraint; anything else goes in the Details drawer |
| Approval invalidation edge cases | Approval is bound to SHA by construction; no SHA → no approval |

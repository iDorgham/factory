# P3 — Learning Plan

**Phase:** P3
**Status:** ⬜ Planned — nothing implemented. The Step 3 slice below is the designed scope; it does
not start until P2.6 (safety-floor hardening) lands. P2.7 (import with baseline) is deferred by
decision and does not block P3 — see [P2 §7](P2-trust-layer.md) for the reasoning.
**Goal:** Make the factory learn incrementally: capture structured lessons after each job, keep
project memory fresh (conventions + repo map), and establish a minimal eval harness so future
changes don't silently regress behavior.

**Depends on:** [P2](P2-trust-layer.md) 🚧 in progress — P2.1–P2.5 landed; P2.6 (safety floor) is the
last blocker, P2.7 (import with baseline) is deferred and not a blocker.

## Workstreams

### 1. Lessons ledger (structured, append-only)
- [ ] Schema: `kernel/schemas/lessons.schema.json`
- [ ] Writer: `kernel/lessons.py` (atomic, dedup by `job_id` + `outcome`)
- [ ] Terminal hook writes lessons on `completed` / `failed` / `cancelled`
- [ ] Separate stall hook: `stalled` is **recoverable** (the job can resume from
      it), so it is not a terminal state — a lesson is written when the stall is
      *resolved* (the job leaves `stalled` for `running`/`failed`/`cancelled`),
      recorded as `outcome: stalled` with the resolving transition, so a
      half-finished job is never recorded as terminal

### 2. Memory: conventions + repo map hygiene
- [ ] Schema: `kernel/schemas/repo-map.schema.json`
- [ ] Repo map: `kernel/memory.py` with staleness detection and `files_hash`
- [ ] Conventions proposals (non-blocking, no auto-merge)
- [ ] Doctor memory checks

### 3. Minimal eval harness
- [ ] Fixtures in `evals/fixtures/`, suites in `evals/suites/`
- [ ] Runner: `kernel/eval.py` with temp trees
- [ ] CLI: `factory eval run`
- [ ] Results in `evals/results/` with version pins

### 4. Integration & safety
- [ ] Terminal hook in the engine; schemas registered; atomic writes; no silent injection;
      hermetic eval

## Exit criteria
- Lessons written on terminal states with full structured fields
- Repo map tracks `commit_sha` / `files_hash` and detects staleness
- `factory eval run` works with hermetic fixtures and writes versioned results
- `factory doctor` passes with the memory checks
- Full suite remains green
- No auto-merge of conventions; lessons are not injected into agent context
- **Measurable improvement** (the roadmap's P3 definition of done): on the eval
      fixtures, later jobs pass more checks in fewer rounds than earlier ones.
      The eval harness in §3 is the instrument that proves it — the lessons
      ledger and memory are the mechanism, the measurement is the exit
      criterion. Skill packages and promotion ride on the same harness and are
      listed under §3b, not as a separate phase.

### 3b. Skill packages and promotion (rides on the eval harness)
- [ ] Skill package schema + registry (`kernel/skills/`)
- [ ] Promotion rule: a skill is promoted only when it wins on the eval
      fixtures — promotion is measured, never asserted
- [ ] Skills are injected into agent context only after promotion

## Commands
```bash
# Once P3 lands (the modules below do not exist yet):
# python -m pytest tests/test_lessons.py tests/test_repo_map.py tests/test_eval_harness.py -v
python -m pytest -v
python -m flake8 kernel/src tests
./factory doctor
# ./factory eval run --suite minimal
```

## Deferred to follow-up (Step 3b)
- Full skill package lifecycle and promotion with a measured gain over a no-skill baseline
- Cross-project/global skills; curator automatic behavior changes (only proposals in this slice)

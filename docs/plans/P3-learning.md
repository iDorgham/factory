# P3 — Learning Plan

**Phase:** P3
**Status:** ⬜ Planned — nothing implemented. The Step 3 slice below is the designed scope; it does
not start until P2 closes (import-with-baseline and the safety-floor rows are still open).
**Goal:** Make the factory learn incrementally: capture structured lessons after each job, keep
project memory fresh (conventions + repo map), and establish a minimal eval harness so future
changes don't silently regress behavior.

**Depends on:** [P2](P2-trust-layer.md) 🚧 in progress.

## Workstreams

### 1. Lessons ledger (structured, append-only)
- [ ] Schema: `kernel/schemas/lessons.schema.json`
- [ ] Writer: `kernel/lessons.py` (atomic, dedup by `job_id` + `outcome`)
- [ ] Terminal hook writes lessons on `completed` / `failed` / `cancelled` / `stalled`

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

## Commands
```bash
python -m pytest tests/test_lessons.py tests/test_repo_map.py tests/test_eval_harness.py -v
python -m pytest -v
python -m flake8 kernel/src tests
./factory doctor
./factory eval run --suite minimal
```

## Deferred to follow-up (Step 3b)
- Full skill package lifecycle and promotion with a measured gain over a no-skill baseline
- Cross-project/global skills; curator automatic behavior changes (only proposals in this slice)

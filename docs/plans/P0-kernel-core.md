# P0 — Kernel Core Plan

**Phase:** P0
**Status:** ✅ Implemented
**Tests:** 109 hermetic pytest cases, lint-clean (`flake8`)

> Everything else depends on safe state. This phase delivers the invariants that the rest of the factory is built on.

## Objective

A deterministic kernel — not an LLM — is the only writer of state. Events are the truth; snapshots are disposable; stale writers are rejected; illegal transitions never happen; an invalid file never reaches disk.

## Delivered

### State and events
- [x] Append-only `events.jsonl` per job: ULID `id`, ISO-8601 `ts`, `job`, `type`, `actor`, `fence`, `data`, `prev` hash chain
- [x] `job.json` regenerated as a pure fold of events after every transition
- [x] `prev` hash chain verification end to end (`state.verify_chain`, used by `doctor`)
- [x] Derived, rebuildable `state/index.json` + `factory reindex`

### Safety primitives
- [x] Atomic writes: temp file → fsync → `os.replace`, Windows-safe (`atomic.py`)
- [x] Lease locks with heartbeat and monotonic fencing tokens; stale writers rejected (`lease.py`)
- [x] Cross-platform exclusive-create guard file (`O_CREAT|O_EXCL`); stale-guard stealing
- [x] Job state machine: 11 states, legal-transitions-only enforcement
- [x] Network-filesystem detection warning in `doctor`

### Validation
- [x] JSON Schemas (Draft 2020-12) for job, event, project, context manifest (`kernel/schemas/`)
- [x] Schema validation on **every** kernel write (`schemas.py`)
- [x] Stage-profile YAML loader + validation (`profiles.py`, `lite.yaml`, `standard.yaml`)

### Kernel surface
- [x] `Kernel` class: `project_create/list/get`, `job_run/status/list/cancel`, `job_transition`
- [x] CLI (`factory`): `project create|list|status`, `job run|status|list|cancel`, `doctor`, `reindex`
- [x] `factory doctor`: schema + chain verification, snapshot repair, expired-lease and worktree checks
- [x] Policy presets `solo.json`, `team.json`, `enterprise.json`
- [x] Global config `factory.json` with price table, sandbox config, budget defaults

### Engine groundwork
- [x] `engine.py` — profile execution: stages → attempts → adapter invocation → contract validation → gate application
- [x] `checks.py` — check runner over `checks.json` with trimmed output and failure fingerprints
- [x] `context.py` — `context.manifest.json` builder with token estimation and include modes
- [x] `adapters.py` — adapter discovery, manifest loading, capability-based selection
- [x] Echo adapter stub (`adapters/echo/`) proving the run contract end to end
- [x] Role contracts: 5 starter roles (`analyst`, `planner`, `builder`, `verifier`, `integrator`)

### Testing
- [x] Hermetic suite: each test builds a throwaway factory tree from the real schemas/presets/stages
- [x] Coverage: atomic, ulid, hashing, lease, state, transitions, profiles, schemas, kernel, doctor, engine, checks, context, adapters
- [x] `flake8` clean with `.flake8` config

## Known gaps / carried into P1

- Worktree isolation is a placeholder (`.work/<job-id>/` exists but no real git worktree/branch yet)
- Only the echo adapter; no real coding-agent adapter
- No `factory serve` dashboard
- No build loop with no-progress detection wired into a real agent run
- No SHA-bound approval or undo
- No sandboxing beyond config placeholders

## Verification

```bash
pip install -e ".[dev]"
python -m pytest          # 109 tests
python -m flake8 kernel/src tests
./factory doctor          # chain + schema verification, snapshot repair
./factory reindex
```

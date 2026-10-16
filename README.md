# Enterprise AI Software Factory — Architecture (Built from Scratch)

**Version:** 3.0 (P0 Kernel Core)  
**Status:** Runnable reference implementation of the specification

> Files are the protocol. Events are the truth. A small kernel enforces. Agents only propose.

## What was built

This directory is a complete, working skeleton of the factory architecture described in the v3.0 specification. It implements the **P0 Kernel Core** from the roadmap:

| Component | Status | Location |
|-----------|--------|----------|
| Global config & policy presets | ✅ | `factory.json`, `kernel/presets/` |
| JSON Schemas (job, event, project, context) | ✅ | `kernel/schemas/` |
| Stage profiles (lite + standard) | ✅ | `kernel/stages/` |
| Atomic writes + JSONL event log | ✅ | `kernel/src/factory_kernel/atomic.py` |
| ULID generation | ✅ | `kernel/src/factory_kernel/ulid.py` |
| Lease locks + fencing tokens | ✅ | `kernel/src/factory_kernel/lease.py` |
| Job state machine + event fold | ✅ | `kernel/src/factory_kernel/state.py` |
| Kernel (project/job lifecycle) | ✅ | `kernel/src/factory_kernel/kernel.py` |
| CLI (`factory` command) | ✅ | `factory` launcher + `cli.py` |
| Stage profile loader + validation (lite/standard) | ✅ | `kernel/src/factory_kernel/profiles.py` |
| JSON Schema validation on every kernel write | ✅ | `kernel/src/factory_kernel/schemas.py` |
| Cross-platform atomic writes (Windows-safe) | ✅ | `kernel/src/factory_kernel/atomic.py` |
| Test suite (109 pytest cases) | ✅ | `tests/` |
| Role definitions (8 → 5 starter) | ✅ | `roles/` |
| Echo adapter stub | ✅ | `adapters/echo/` |
| `factory doctor` (chain check, leases, repair) + `reindex` | ✅ | Implemented |
| Worktree isolation (placeholder) | ✅ | `.work/<job-id>/` |
| Derived state index | ✅ | `state/index.json` |

## Directory layout (as specified)

```
factory/
├── factory.json                 # global config
├── factory                      # CLI entry point
├── pyproject.toml               # packaging + pytest config
├── .gitignore
├── kernel/
│   ├── schemas/                 # JSON Schemas
│   ├── presets/                 # solo / team / enterprise
│   ├── stages/                  # lite.yaml, standard.yaml
│   └── src/factory_kernel/      # Python reference kernel
├── tests/                       # pytest suite (hermetic)
├── projects/<name>/
│   ├── project.json
│   ├── checks.json
│   ├── memory/
│   └── jobs/<job-id>/
│       ├── job.json             # derived snapshot
│       ├── events.jsonl         # SOURCE OF TRUTH
│       ├── brief.md
│       ├── assumptions.md
│       ├── questions.md
│       └── artifacts/
├── roles/                       # markdown role contracts
├── adapters/                    # tool-specific translators
├── skills/                      # versioned skill packages (future)
├── audit/                       # hash-chained audit (Team+)
├── state/index.json             # derived, rebuildable
└── .work/<job-id>/              # isolated worktrees
```

## Quick start

```bash
cd factory

# Create a Solo project
./factory project create demo --mode solo --domain web

# Start a job
./factory job run demo "Build a landing page with hero and contact form"

# Inspect
./factory job list
./factory job status <job-id>
./factory doctor
./factory reindex
```

## Core invariants enforced by the kernel

1. **Agents never write state** — only the kernel appends to `events.jsonl` and regenerates `job.json`.
2. **Events are the truth** — `job.json` is a pure fold; if they disagree, the fold wins and `doctor` repairs.
3. **Lease + fencing** — every state write carries a monotonic fencing token; stale writers are rejected.
4. **Atomic writes** — temp file → fsync → rename for every snapshot.
5. **Legal transitions only** — the state machine rejects illegal moves.
6. **Derived state is disposable** — `factory reindex` rebuilds `state/index.json` from the event logs.

## Architecture layers

```
Clients (CLI / future dashboard)
        │ validated commands
        ▼
     KERNEL  (deterministic, not an LLM)
        │                │
        │ run requests   │ atomic R/W
        ▼                ▼
    Adapters          Files (protocol)
        │
        ▼
  Coding Agents (sandboxed, propose only)
```

## Next phases (from the specification roadmap)

- **P1 Solo slice** — full lite profile execution, one real adapter, build loop with no-progress detection, `factory serve` dashboard, SHA-bound approval.
- **P2 Trust layer** — budgets/metering, guards, sandbox hardening, risk-scored gates, import with baseline.
- **P3 Team** — concurrent jobs, merge queue, RBAC, audit chain.
- **P4 Enterprise** — brands, design-system checks, compliance export, change windows.

## Design decisions captured

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Language of reference kernel | Python 3 | Readable, fast to iterate, good stdlib for files |
| ID generation | ULID | Time-sortable, 26-char, no external dep |
| Event chaining | prev = hash of previous event | Detects tampering / missing events |
| Locking | Exclusive file + fencing token | Works without advisory flock; portable |
| Lock mutual exclusion | Exclusive-create guard file (`O_CREAT\|O_EXCL`) | Portable create-exclusive semantics (spec §5.2); a stale guard is stolen |
| Stage definitions | YAML | Human-readable, easy to compose profiles |
| Adapters | Folder + manifest.json | Tool-agnostic core; new tools = new folder |
| Atomic writes | temp → fsync → `os.replace` | Cross-platform (POSIX fsyncs the dir; Windows cannot, so it is skipped) |
| Schema validation | `jsonschema`, on every kernel write | An invalid event/snapshot never reaches disk |

## Running the tests of the architecture

Install the dev dependencies and run the suite:

```bash
pip install -e ".[dev]"     # or: pip install pytest pyyaml jsonschema flake8
python -m pytest            # 109 tests: atomic, ulid, hashing, lease, state,
                            #   transitions, profiles, schemas, kernel, doctor
python -m flake8 kernel/src tests   # lint (config in .flake8)
```

The suite is hermetic: each test builds a throwaway factory tree in a temp
directory from the real `kernel/schemas`, `kernel/presets`, and `kernel/stages`.

Health checks against a real tree:

```bash
./factory doctor          # schema + event-chain verification, lease/worktree checks, snapshot repair
./factory project list
./factory job list
./factory reindex
```

`doctor` verifies the `prev` hash chain end to end, validates every event and
snapshot against its schema, repairs `job.json` when it diverges from the event
fold, and warns on expired leases, missing/orphan worktrees, and network roots.

The kernel is deliberately small. Everything that can be expressed as files and events is expressed that way. Adding a new coding tool requires only an adapter that speaks the same contract.

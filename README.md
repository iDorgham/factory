# Enterprise AI Software Factory — Architecture (Built from Scratch)

**Version:** 3.0 (P1 Solo slice — in progress)  
**Status:** Runnable reference implementation of the specification

> Files are the protocol. Events are the truth. A small kernel enforces. Agents only propose.

## Documentation

- [docs/](docs/README.md) — index of all documentation
- [PRD](docs/product/PRD.md) — product requirements, personas, features per mode
- [Architecture](docs/architecture/ARCHITECTURE.md) — design & architecture of the implemented system
- [Roadmap](docs/plans/ROADMAP.md) — phases P0–P5 with status and per-phase plans
- [Specification v3.0](docs/specification/Enterprise%20AI%20Software%20Factory%20—%20Specification%20v3.0.md) — canonical specification
- [Development](docs/development/DEVELOPMENT.md) · [Contributing](docs/development/CONTRIBUTING.md) · [Testing](docs/development/TESTING.md) · [Runbook](docs/operations/RUNBOOK.md)
- [Context pack](docs/context/PROJECT-CONTEXT.md) — full portable briefing for other AI tools (Qwen, Grok, …), plus [history](docs/context/HISTORY.md) and [AI provenance](docs/context/AI-PROVENANCE.md)

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
| Stage-graph engine + build loop (no-progress → `stalled`) | ✅ | `kernel/src/factory_kernel/engine.py` |
| Check runner + failure fingerprints | ✅ | `kernel/src/factory_kernel/checks.py` |
| Context-manifest builder | ✅ | `kernel/src/factory_kernel/context.py` |
| Adapter runtime (discover / select / run) | ✅ | `kernel/src/factory_kernel/adapters.py` |
| Adapter conformance suite (§20.3) | ✅ | `kernel/src/factory_kernel/conformance.py` |
| Content-addressed checkpoints + SHA-bound approval | ✅ | `kernel/src/factory_kernel/checkpoint.py` |
| Git worktrees + merge queue + Undo (§6, §199, §21.2) | ✅ | `kernel/src/factory_kernel/gitrepo.py` |
| Dashboard: `serve` (live SSE) + `export-dashboard` (static) | ✅ | `kernel/src/factory_kernel/dashboard.py` |
| CLI (`factory` command) | ✅ | `factory` launcher + `cli.py` |
| Stage profile loader + validation (lite/standard) | ✅ | `kernel/src/factory_kernel/profiles.py` |
| JSON Schema validation on every kernel write | ✅ | `kernel/src/factory_kernel/schemas.py` |
| Cross-platform atomic writes (Windows-safe) | ✅ | `kernel/src/factory_kernel/atomic.py` |
| Test suite (180 pytest cases) | ✅ | `tests/` |
| Role definitions (8 → 5 starter) | ✅ | `roles/` |
| Echo adapter stub | ✅ | `adapters/echo/` |
| `factory doctor` (chain check, leases, repair) + `reindex` | ✅ | Implemented |
| Git worktree isolation (branch `factory/<job-id>`) | ✅ | `projects/<name>/repo` + `.work/<job-id>/` |
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
│   ├── project.json             # includes base_commit
│   ├── checks.json
│   ├── repo/                    # factory-managed git repo (main branch)
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
└── .work/<job-id>/              # git worktree on branch factory/<job-id>
```

## Quick start

```bash
cd factory

# Create a Solo project
./factory project create demo --mode solo --domain web

# Start a job
./factory job run demo "Build a landing page with hero and contact form"

# Execute it through the lite stage graph (understand → plan → build → verify → approve)
./factory job execute <job-id>

# The 'approve' gate parks the job at awaiting_human; approve (bound to the
# latest checkpoint SHA) to finish. A changed result invalidates the approval.
# Approval merges the job branch into the project's main branch (§199).
./factory job approve <job-id> [--sha <checkpoint-sha>]

# Revert a merge (spec §21.2 Undo)
./factory job undo <job-id>

# Run the adapter conformance suite (§20.3) and record the result
./factory adapter test echo

# Open the Solo dashboard (local server; live via server-sent events)
./factory serve

# ...or write a static, read-only snapshot to share
./factory export-dashboard --out dashboard.html

# Send feedback from the approval card ("Change this…") — re-does the last stage
./factory request-changes <job-id> "make the hero bigger"

# Inspect
./factory job list
./factory job status <job-id>
./factory doctor
./factory reindex
```

The dashboard is a client: every browser action is a kernel command, never a direct file edit. `serve` streams the view over server-sent events; `export-dashboard` writes a static, read-only snapshot.

Each project owns a factory-managed git repository at `projects/<name>/repo` (created with the project; its initial commit is the project's `base_commit`). Creating a job adds a **worktree** at `.work/<job-id>/` on branch `factory/<job-id>`, branched from `base_commit` (§198). Every accepted stage attempt ends in a checkpoint that commits the worktree (§237), and resuming restores the worktree to the last accepted checkpoint rather than rerunning on a dirty tree (§239). Approving merges the job branch into `main` (§199) — `factory job undo` reverts that merge.

## Core invariants enforced by the kernel

1. **Agents never write state** — only the kernel appends to `events.jsonl` and regenerates `job.json`.
2. **Events are the truth** — `job.json` is a pure fold; if they disagree, the fold wins and `doctor` repairs.
3. **Lease + fencing** — every state write carries a monotonic fencing token; stale writers are rejected.
4. **Atomic writes** — temp file → fsync → rename for every snapshot.
5. **Legal transitions only** — the state machine rejects illegal moves.
6. **Derived state is disposable** — `factory reindex` rebuilds `state/index.json` from the event logs.

## Architecture layers

```
Clients (CLI / dashboard)
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

- **P1 Solo slice** (in progress) — lite-profile execution through the stage-graph engine ✅, adapter runtime + echo adapter ✅, adapter conformance suite (§20.3) ✅, build loop with no-progress detection ✅, content-addressed checkpoints + SHA-bound approval ✅, `interrupted` attempt recovery + input-hash idempotency ✅, Solo dashboard (`factory serve` live + `export-dashboard` static, with Approve / Change this… from the card) ✅, factory-managed git worktrees + checkpoint commits + merge queue + Undo ✅; still to come: a real coding-agent adapter.
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
| Dashboard delivery | stdlib `http.server` + SSE; static export fallback | No runtime deps; the dashboard stays a thin client of the kernel |
| Repository source | Factory-managed repo per project (`projects/<name>/repo`) | Self-contained and hermetic; no external repo needed (spec §18 `project import` can link a real one later) |
| Checkpoint identity | Content-hash `sha` (approval) **and** git `commit` (recovery) | Approval binds to the produced bytes; resume restores the exact tree (`git reset --hard` + `clean -fd`) |
| Merge integration | Serialized `--no-ff` merge on approval; conflict → `blocked` | One job at a time in Solo (spec §6); a conflict never leaves the repo mid-merge |

## Running the tests of the architecture

Install the dev dependencies and run the suite:

```bash
pip install -e ".[dev]"     # or: pip install pytest pyyaml jsonschema flake8
python -m pytest            # 180 tests: atomic, ulid, hashing, lease, state,
                            #   transitions, profiles, schemas, kernel, doctor,
                            #   engine, checks, context, adapters, checkpoint,
                            #   conformance, dashboard, gitrepo/worktree/merge
python -m flake8 kernel/src tests adapters   # lint (config in .flake8)
```

The suite is hermetic: each test builds a throwaway factory tree in a temp
directory from the real `kernel/schemas`, `kernel/presets`, and `kernel/stages`.
Git-backed tests (worktrees, merge, undo) create real repositories in that temp
tree and skip themselves when no `git` executable is available.

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

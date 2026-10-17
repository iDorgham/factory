# Enterprise AI Software Factory — Full Project Context

> A portable briefing for any AI tool or model. Snapshot date: **2026-10-17** (reconciled against working tree: 286 tests collected, P2.1 guards machine-verified in code and commit history).
> Everything below is grounded in the repository. Where something is unknown, it is labeled as unknown.

---

## 1. TL;DR (what this project is)

The **Enterprise AI Software Factory** is a **deterministic kernel plus file protocol** that turns an
idea, an issue, or an existing repository into *verified, reviewable, mergeable* software by orchestrating
coding agents. The coding agents do the writing; a small non-LLM **kernel** owns all state, validation,
checks, budgets, and audit. Agents only **propose** — the kernel **enforces**.

Its core promise is **maximum *verified* automation, not maximum automation**. The value is the reliability
with which it can say "this is actually done," not the number of agents it runs.

The system is a **runnable reference implementation** of a canonical specification (v3.0). The specification
is the source of truth for intended behavior; the code implements P0 (kernel core) fully and most of P1
(Solo slice).

**Status right now:** P0 complete; **P1 Solo slice complete** (stage-graph engine, build loop, live `cli-agent` adapter, checkpoints, SHA-bound approval, worktrees + merge queue + Undo, question budget, and real visual capture via headless Edge/Chrome) — all proven end-to-end on the real tree.

---

## 2. The core idea in one paragraph

Everything important is expressed as **files and events**, so the whole system is portable and auditable.
One file per job (`events.jsonl`) is the immutable **source of truth**; every other view (`job.json`,
indexes, dashboards) is a **derived cache** that can be deleted and rebuilt. A deterministic kernel is the
only thing allowed to append events or change state; it validates every write against a JSON schema,
enforces a legal state machine, and rejects stale writers using lease locks with fencing tokens. Coding
agents run through **adapters** (the only tool-specific code) in a sandbox, write only into their attempt
directory and worktree, and their claims are never evidence — only real checks are.

---

## 3. Principles (the non-negotiables)

1. **Tool-agnostic core.** All state/contracts/history are markdown, JSON, JSONL. Adapters are the only tool-specific code.
2. **Kernel enforces, agents propose.** Agents write output files; only the kernel validates and commits state.
3. **Events are the truth.** Current state is a fold over the event log; everything else is a rebuildable cache.
4. **Isolation by default.** One worktree and branch per job.
5. **Deterministic gates first.** Build/lint/type/test/a11y/visual results decide. LLM review informs; it never solely approves.
6. **Safety floor.** Some controls cannot be configured away.
7. **Progressive complexity.** One engine, three presets (Solo/Team/Enterprise); Solo users never see what they don't need.
8. **Resumable and idempotent.** Recovery restores checkpoints; external effects are never repeated.
9. **Cost-aware.** Every attempt reports usage; budgets enforced at stage boundaries.
10. **Compounding.** Lessons, memory, and evaluated skills make later jobs better than earlier ones.

---

## 4. Glossary

| Term | Meaning |
|------|---------|
| **Kernel** | The small deterministic program (not an LLM) that owns scheduling, locks, state machine, validation, checks, policy, budget, audit. |
| **Job** | One unit of work ("build a landing page"). Lives under `projects/<p>/jobs/<job-id>/`. |
| **Event** | One line in `events.jsonl`: `{id (ULID), ts, job, type, actor, fence, data, prev}`. Append-only, hash-chained. |
| **Snapshot** | `job.json` — a pure fold of the events, regenerated after every transition. Disposable. |
| **Fence (fencing token)** | A monotonic number incremented on every lease grant. Every state write carries the current fence; stale writers are rejected. |
| **Lease** | A per-job lock `{owner, token, expires}` renewed by heartbeat. |
| **Checkpoint** | A content-addressed hash of an accepted attempt's outputs + worktree, recorded per attempt. Used for recovery and SHA-bound approval. |
| **Stage** | A step in a profile (`understand`, `plan`, `build`, `verify`, `approve`, …) declaring role, requires, produces, checks, guards, effects, budget, gate, on_fail. |
| **Profile** | A composition of stages: `lite` (Solo, 5 steps) or `standard` (Team/Enterprise). |
| **Attempt** | One try at a stage, in `stages/<nn>-<stage>/attempt-<k>/`. |
| **Guard** | A deterministic anti-cheating check over the diff (e.g., `no_test_deletion`). |
| **Adapter** | A folder translating the kernel's run request to a specific coding agent. The only tool-specific code. |
| **Conformance suite** | Tests any adapter must pass before acceptance (spec §20.3). |
| **Gate** | A human/policy checkpoint: `none`, `risk_scored`, or `required`. |
| **Lens** | A review perspective (security, performance, accessibility, maintainability) — not a separate agent. |
| **Role** | A markdown contract (`analyst`, `planner`, `builder`, `verifier`, `reviewer`, `designer`, `architect`, `curator`). |

---

## 5. Architecture

### 5.1 Layers

```
        ┌───────────────────────────────────────────┐
        │   Dashboard / CLI / Command palette        │  clients — never touch state
        └──────────────┬────────────────────────────┘
                       │ validated commands
        ┌──────────────▼────────────────────────────┐
        │                 KERNEL                     │  deterministic — NOT an LLM
        │  Scheduler · Locks · State machine ·       │
        │  Schema validation · Check runner ·        │
        │  Policy engine · Budget meter · Audit      │
        └───────┬──────────────────────┬────────────┘
                │ run requests         │ atomic reads/writes
        ┌───────▼───────┐      ┌───────▼─────────────┐
        │   Adapters    │      │  Files (the truth)   │
        └───────┬───────┘      └──────────────────────┘
                │
        ┌───────▼───────┐
        │ Coding agents │   sandboxed — propose only
        └───────────────┘
```

**Layer rules:** agents read only their context manifest and write only into their attempt dir and worktree;
adapters translate but never decide; the dashboard is a client (every browser action is a kernel command,
never a direct file edit); derived files are rebuildable by `factory reindex`.

### 5.2 State model

- **Source of truth:** `projects/<p>/jobs/<id>/events.jsonl` (append-only, hash-chained by `prev`).
- **Derived/disposable:** `job.json`, `state/index.json`, board/dashboard views.
- If a snapshot disagrees with the event fold, **the fold wins** and `factory doctor` repairs the snapshot.

### 5.3 Invariants the kernel enforces

1. Agents never write state; only the kernel appends events and regenerates `job.json`.
2. Events are the truth; derived state is disposable.
3. Lease + fencing: stale writers are rejected.
4. Atomic writes: temp → fsync → `os.replace` (Windows-safe: directory fsync skipped).
5. Legal transitions only; illegal moves raise.
6. Derived state is rebuildable by `factory reindex`.

### 5.4 Job state machine

States: `pending, running, awaiting_human, blocked, stalled, paused, failed, completed, cancelled, superseded, archived`.

```
pending → running → completed → archived
            │ ▲ │
            │ │ ├→ awaiting_human → running | blocked | cancelled
            │ │ ├→ blocked → running | cancelled
            │ │ ├→ stalled → running (new strategy) | failed | cancelled
            │ │ ├→ paused → running | cancelled
            │ │ └→ failed → running (operator retry) | cancelled
            └─┴──┘
cancelled | superseded → archived
```

### 5.5 Kernel modules (reference implementation)

| Module | Responsibility |
|--------|----------------|
| `kernel.py` | `Kernel` — project/job lifecycle, `job_execute`, `job_approve`, `job_request_changes`, `doctor`, `reindex`. The only public entry point to state. |
| `state.py` | `JobState` — event load/append/fold, chain verification, transitions, snapshot writing. |
| `lease.py` | `LeaseManager` — acquire/renew/release with fencing tokens; exclusive-create guard file. |
| `atomic.py` | `atomic_write`, `atomic_write_json`, `append_jsonl`, `read_json(l)` — all durable I/O. |
| `ulid.py` | ULID generation (time-sortable, 26-char, no deps). |
| `hashing.py` | `sha256_hex`, `event_hash`, `content_hash`. |
| `schemas.py` | `SchemaStore` — Draft 2020-12 validation of every kernel write. |
| `profiles.py` | Stage-profile loader + YAML validation (`lite`, `standard`). |
| `engine.py` | `Engine` — drives a job through its stage profile: attempt dirs, context manifest, adapter invocation, kernel-run checks, gate evaluation, and the build loop with failure-fingerprint no-progress detection → `stalled` (spec §9.2). |
| `checks.py` | Real command runner with trimmed output, required/conditional checks, `required_checks` meta-check, stable failure fingerprints. |
| `context.py` | `context.manifest.json` builder (schema-valid), resolving brief/requires + project memory, with token budgeting/degradation. |
| `adapters.py` | Adapter discovery, manifest loading, capability/role selection, NDJSON subprocess run contract with error classification. |
| `checkpoint.py` | Deterministic content hashes (`tree_hash`, `result_hash`), `checkpoint.json` per accepted attempt, `checkpoint.created` events. |
| `conformance.py` | Adapter conformance suite (§20.3): start, contract-file, usage, write-boundary, injected-instruction, plus capability-gated cancel/resume/heartbeat. Records `conformance.json`. |
| `dashboard.py` | `build_view` (three-element Solo view), `render_html`, `export_dashboard` (static snapshot), `serve` (stdlib HTTP server + SSE + `POST /api/command`), `dispatch`. |
| `gitrepo.py` | Factory-managed git: per-project repo + `base_commit`, per-job worktree/branch, checkpoint commits, `--no-ff` merge queue (conflict → `blocked`), revert/reset Undo. |
| `provenance.py` | Commit provenance trailer conventions (per `CONTRIBUTING.md` §3.1). |
| `guards.py` | Pure deterministic diff guards (`no_test_deletion`, `no_lockfile_surprise`, `no_secret_in_diff`) + registry, `GUARDS`; hard-fail on unknown id, exact-path structural `authorized()`. |
| `cli.py` | The `factory` command (see §9). |

---

## 6. Repository map

```
factory/
├── factory.json                 # global config: price table, sandbox, budget defaults
├── factory                      # CLI launcher script
├── pyproject.toml               # packaging (factory-kernel 0.4.0) + pytest + flake8
├── kernel/
│   ├── schemas/                 # event, job, project, context.manifest, authorizations + CHANGELOG
│   ├── presets/                 # solo.json, team.json, enterprise.json
│   ├── stages/                  # lite.yaml, standard.yaml
│   └── src/factory_kernel/      # the Python reference kernel (20 modules)
├── tests/                       # hermetic pytest suite (286 collected: 284 passed, 2 skipped)
│   └── fixtures/adapters/slow/  # adapter fixture exercising cancel/resume/heartbeat
├── roles/                       # markdown role contracts (5 starter: analyst, planner, builder, verifier, integrator)
├── adapters/echo/               # deterministic echo adapter (manifest.json, run.py, conformance.json)
├── adapters/cli-agent/          # generic CLI-agent shell-out adapter (FACTORY_CLI_AGENT_CMD; deterministic no-op by default)
├── projects/<name>/             # runtime state: project.json, checks.json, memory/, jobs/
├── state/index.json             # derived, rebuildable
├── .work/<job-id>/              # isolated git worktrees on branch factory/<job-id>
└── docs/                        # product / architecture / specification / plans / development / operations / context
```

---

## 7. Behavior by mode (Solo / Team / Enterprise)

Mode is a named policy preset stored in `project.json` (`"mode"`). All modes run the same kernel and job engine.

| | **Solo** (default) | **Team** | **Enterprise** |
|---|---|---|---|
| Target | Beginners, indie builders | Small teams, agencies | Multi-product orgs, regulated |
| Profile | `lite` (5 steps) | `standard` | `standard` + compliance |
| Concurrency | 1 job (queued) | Up to N, worktree-isolated | Configurable per project/brand |
| Gates | Visual approval on UI + floor | Risk-scored + reviewer assignment | Risk-scored + approvers + change windows |
| Budgets | Soft/hard cap per job | Per job and project | Per job/project/brand/month |
| Identity | Single local user | Named users, simple roles | Full RBAC, SSO |
| Audit | Event log | Event log + export | Hash-chained audit, retention, compliance export |
| Design system | Off | Optional | Brand-level, lint-enforced |
| Dashboard | Three-element view | Queues, cost, PRs | Policy, audit, budgets, brands |

**Solo promise:** a beginner types one sentence, gets a previewable result, with at most two approval
clicks and no configuration. The dashboard shows exactly three things: a prompt box with cost/time
estimate, a plain-language timeline, and a single "Needs you" card (a question or the approval card).

---

## 8. Stage profiles (the actual YAML)

### `lite` (Solo, 5 steps) — `kernel/stages/lite.yaml`
`understand` → `plan` → `build` → `verify` → `approve`

- `understand` (analyst): produces `brief.md, assumptions.md, questions.md`; gate none; on_fail escalate.
- `plan` (planner): requires `brief.md`, produces `plan.md`; planning is always mandatory.
- `build` (builder): requires `plan.md`, produces `build.md, git:commits`; checks `[lint, typecheck, unit, build]`; guards `[no_test_deletion, no_lockfile_surprise, no_secret_in_diff]`; max_rounds 6; on_fail loop.
- `verify` (verifier): checks `[lint, typecheck, unit, build, a11y, visual]`; gate risk_scored.
- `approve` (integrator): produces `decision.md`; gate **required** (parks at `awaiting_human`); max_rounds 1.

### `standard` (Team/Enterprise) — `kernel/stages/standard.yaml`
`understand` → `define` (adaptive) → `plan` → `design` (UI domains) → `scaffold` (adaptive, new projects) → `build` → `verify` → `review` (lenses: security, performance, accessibility, maintainability) → `polish` → `approve` → `merge`.

Each stage declares `role, requires, produces, checks, guards, effects, max_rounds, budget, gate, on_fail`
and optionally `adaptive`, `domain`, `lenses`.

---

## 9. CLI reference (current)

```
factory project create <name> [--mode solo|team|enterprise] [--domain web|mobile|desktop|game|generic] [--brand b]
factory project list
factory project status <name>

factory job run <project> "<description>" [--epic id] [--profile lite|standard]
factory job execute <job-id> [--adapter id] [--check-timeout n]   # run/resume through the stage graph
factory job approve <job-id> [--adapter id] [--sha <checkpoint-sha>]
factory job status <job-id>
factory job list [--project p]
factory job cancel <job-id> [--reason r]

factory request-changes <job-id> "<feedback>"                     # "Change this…" from the approval card
factory adapter test <adapter-id> [--no-record]                   # run conformance suite (§20.3)
factory serve [--host --port --no-open]                           # live dashboard (SSE)
factory export-dashboard [--out f.html] [--project p]             # static read-only snapshot
factory doctor                                                     # verify + repair
factory reindex                                                     # rebuild derived state
```

Root/actor overrides: `--root`, `--actor`.

### A full Solo round trip
```bash
./factory project create demo --mode solo --domain web
./factory job run demo "Build a landing page with hero and contact form"
./factory job execute <job-id>          # drives understand→plan→build→verify→approve
./factory job status <job-id>           # parked at awaiting_human (approve gate)
./factory job approve <job-id>          # bound to the latest checkpoint SHA
./factory serve                          # or: ./factory export-dashboard --out dashboard.html
```

---

## 10. Roadmap and current status

| Phase | Deliver | Status |
|-------|---------|--------|
| **P0 Kernel core** | events/snapshot, atomic writes, leases+fencing, schema validation, check runner, `doctor`, `reindex` | ✅ Complete |
| **P1 Solo slice** | lite execution, adapter runtime, build loop, checkpoints + SHA-bound approval, conformance suite, dashboard | 🚧 **In progress — mostly implemented** |
| **P2 Trust layer** | budgets/metering, guards, sandbox hardening, risk-scored gates, import with baseline | 🚧 **In progress — P2.1 guards landed** (diff collection, three deterministic guards, engine hook, plain-language dashboard verdicts, doctor integrity checks) |
| **P3 Learning** | eval harness, skill packages + promotion, lessons ledger, memory | ⬜ Planned |
| **P4 Team** | more adapters via conformance, epics + dependencies, visual baselines, named users | ⬜ Planned |
| **P5 Enterprise** | control plane, RBAC, hash-chained audit + anchors, brand design systems, compliance export | ⬜ Planned |

### P1 — done vs. remaining
**Done (verified in code):** stage-graph engine + build loop; adapter runtime + echo + live cli-agent backend (NDJSON forwarding, honest failure classes, `resume`, recorded conformance); content-addressed
checkpoints (+ git commit per checkpoint); SHA-bound approval (refuses changed results); `interrupted` attempt recovery + input-hash
idempotency; adapter conformance suite (§20.3) + `factory adapter test`; Solo dashboard (`serve` live SSE
+ `export-dashboard` static, with Approve / Change this… / Undo on the card); `request-changes` rework loop;
factory-managed git worktrees + merge queue (conflict → `blocked`) + Undo (`merge.undone`).

**Remaining (P1):** nothing in code. The `visual.json` contract plus a real capture producer
(`adapters/visual-capture/capture.py`, headless Edge/Chrome, runtime theme probe) are landed; see
`docs/plans/P1-solo-slice.md` — "Hardening 2026-10-16 (PM)" and "(evening)".

---

## 11. Development, testing, and metrics

- **Language:** Python ≥ 3.11. Runtime deps: `PyYAML`, `jsonschema`. Lint: `flake8` (max line 100).
- **Packaging:** `factory-kernel` v0.4.0; console script `factory`.
- **Run tests:** `pip install -e ".[dev]"` then `python -m pytest` and `python -m flake8 kernel/src tests`.
- **Hermetic tests:** each test builds a throwaway factory tree in `tmp_path` from the real schemas/presets/stages.
- **Source metrics:** 20 kernel modules (includes checkpoint, conformance, dashboard, gitrepo, provenance, guards); commit history carries `AI-Tool`/`AI-Model` provenance trailers per-commit since P2.1 (machine-verified by the commit-msg hook).
- **Test count (verified 2026-10-17, working tree):** `286 collected — 284 passed, 2 skipped`. Test files: atomic, ulid, hashing, lease, state, transitions, profiles, schemas, kernel, doctor, engine, checks, context, adapters, cli-agent, checkpoint, conformance, dashboard, worktree (git/merge/undo/isolation), questions (Solo question budget), visual_capture (real capture producer + diffs), explain dispatched from dashboard, provenance, guards (P2.1: guard units, diff collection, engine hook, doctor authorizations).

---

## 12. Known gaps / open questions (good discussion material)

1. **Worktree lifecycle (done, verify edge cases)** — `.work/<job-id>/` is now a real git worktree (`gitrepo.add_worktree`, branch `factory/<job-id>`). Open: port-range allocation, orphan/stale-base handling under concurrent jobs (P4).
2. **Question budget open** — `echo`/`cli-agent` can emit `question` events but the engine never counts them; no ≤ 3 cap, no `blocked` on exhaustion, no dashboard surfacing (needs the schema migration noted in the P1 plan).
3. **Guards not executed** — *closed 2026-10-17 (P2.1)*: `no_test_deletion`, `no_lockfile_surprise`, `no_secret_in_diff` run per attempt over the diff from the attempt-base commit; violations fail the attempt, feed the fingerprint (repeat → stalled), land as hash-chained events, and are authorized structurally by per-job `authorizations.json` (exact paths, schema-validated). `scope_guard` and plan-file-set authorization remain future. **Budgets/metering (gap #4) is now the head of the P2 queue.**
4. **Budgets declared but not enforced** — every stage has a `budget` in YAML, but there is no metering/stop yet (P2; next up).
5. **Sandbox is config-only** — `factory.json` declares a sandbox, but no process/container isolation is implemented (P2).
6. **No risk scoring** — `verify` declares `gate: risk_scored`, but the score computation is absent (P2).
7. Undo/merge — done (`gitrepo.merge_branch`/`revert_merge`, `kernel._merge_on_complete`/`job_undo`, conflict → `blocked`, `merge.undone`; dashboard Undo enabled when a merge is present).
8. **Schema versioning is interim** — schemas have no `$id` version yet; `kernel/schemas/CHANGELOG.md` is the interim record.
9. **Roles incomplete** — spec defines 8 roles; only 5 exist (analyst, planner, builder, verifier, integrator); reviewer/designer/architect/curator are missing.
10. **Dashboard scope** — currently Solo three-element; Team/Enterprise panels are future.

---

## 13. Suggested prompts for another AI

Use these to get high-value reasoning from another model:

- "Here is the architecture (§5). Which invariants are most fragile, and what tests would harden them?"
- "Visual capture uses headless Chromium with a runtime theme probe. Where exactly should visual-diff thresholds gate the `verify` stage, and what baseline-management flow keeps them deterministic?"
- "The profiles declare guards and budgets that aren't enforced yet (§12). Sketch the enforcement design for P2."
- "Review the build loop's no-progress detection (failure fingerprint → stalled). What failure modes would evade it?"
- "The conformance suite runs cancel/resume/heartbeat only when the adapter declares the capability. Is graceful degradation the right call, or should these be mandatory?"
- "Where does the implementation diverge from the specification's promises? List concrete gaps."
- "Propose a risk-score computation (signals → score bands → gate actions) that is deterministic and hard to game."

---

## 14. Provenance

**Tool and model:** P0 and P1 were developed with **OpenCode** using the **Big Pickle** model (provider
`opencode`). This is owner-attested; the git history itself carries no tool/model trailers, so it is
recorded as attestation rather than machine-verified proof. The documentation set was also authored with
OpenCode + Big Pickle. See **[AI-PROVENANCE.md](AI-PROVENANCE.md)** for the per-phase table and how to
capture provenance going forward.

---

## 15. Where to look next (in this repository)

- Spec: `docs/specification/Enterprise AI Software Factory — Specification v3.0.md`
- Architecture: `docs/architecture/ARCHITECTURE.md`
- Roadmap & phase plans: `docs/plans/`
- Contributing/standards/testing/adapters: `docs/development/`
- Operations/security: `docs/operations/`
- History: `docs/context/HISTORY.md`

**If this document conflicts with the code, the code and the spec win.** Update this file, not the code, to match.

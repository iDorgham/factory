# Design & Architecture — Enterprise AI Software Factory

**Version:** 3.0
**Status:** Matches the reference implementation at `d933adf` — P0 and P1 complete, P2.1 guards landed, P2.2 budgets landed, P2.3 sandbox hardening landed, P2.4 risk-scored gates landed, P2.5 prompt-injection handling landed. Claims below that describe *target* behavior are marked as such.
**Related:** [Specification v3.0](<../specification/Enterprise AI Software Factory — Specification v3.0.md>) · [PRD](../product/PRD.md) · [Roadmap](../plans/ROADMAP.md)

> Files are the protocol. Events are the truth. A small kernel enforces. Agents only propose.

---

## 1. Layered architecture

```
        ┌───────────────────────────────────────────┐
        │   Dashboard / CLI / Command palette        │   clients — never touch state
        └──────────────┬────────────────────────────┘
                       │ validated commands
        ┌──────────────▼────────────────────────────┐
        │                 KERNEL                     │   deterministic — NOT an LLM
        │  Scheduler · Locks · State machine ·       │
        │  Schema validation · Check runner ·        │
        │  Policy engine · Budget meter · Audit      │
        └───────┬──────────────────────┬────────────┘
                │ run requests         │ atomic reads/writes
        ┌───────▼───────┐      ┌───────▼─────────────┐
        │   Adapters    │      │  Files (the truth)   │
        │  (per tool)   │      │  job.json, events,   │
        └───────┬───────┘      │  worktrees, skills,  │
                │              │  memory, audit       │
        ┌───────▼───────┐      └──────────────────────┘
        │ Coding agents │     sandboxed — propose only
        └───────────────┘
```

**Layer rules**

- Agents read only their context manifest and write only into their attempt directory and the job worktree.
- Adapters translate; they do not decide. They cannot change policy, budgets, or state.
- The dashboard is a client. Every action is a kernel command, never a direct file edit.
- Derived files (`state/index.json`, board views) can be deleted and rebuilt by `factory reindex`.

## 2. State model

### 2.1 Source of truth vs derived state

| File | Role |
|------|------|
| `projects/<p>/jobs/<id>/events.jsonl` | **Source of truth.** Append-only. One JSON object per line. |
| `projects/<p>/jobs/<id>/job.json` | Derived snapshot — a pure fold of the events, regenerated after every transition. |
| `state/index.json` | Derived index — rebuildable by `factory reindex`. |
| Locks / leases | Ephemeral coordination files, fenced by monotonic tokens. |

If `job.json` and the event fold disagree, **the fold wins** and `factory doctor` repairs the snapshot.

### 2.2 Event format

Every event carries: `id` (ULID), `ts` (ISO-8601 UTC), `job`, `type`, `actor`, `fence` (fencing token), `data`, and `prev` (hash of the previous event for that job). The `prev` chain makes tampering and gaps detectable — `state.verify_chain()` walks it end to end.

### 2.3 Write rules

1. **Atomic writes everywhere:** temp file in the same directory → `fsync` → `os.replace`. Windows-safe: directory fsync is skipped where unsupported (`atomic.py`).
2. **Only the kernel appends events** and only after validating against `kernel/schemas/event.schema.json`.
3. **Lease + fencing:** a job lock holds `{owner, token, expires}`. Every grant increments a monotonic fencing token; every state write must carry the current token. A late write from a crashed/zombie agent has a stale token and is rejected (`lease.py`).
4. **Cross-platform locking:** exclusive-create guard file (`O_CREAT|O_EXCL`), not advisory `flock`; a stale guard is stolen. Network filesystems are unsupported for concurrent mode and `doctor` warns.
5. **Legal transitions only:** the state machine rejects anything not in the transition table (spec §7).

## 3. Job state machine

```
pending ──▶ running ──▶ completed ──▶ archived
   │          │  ▲  │
   │          │  │  ├─▶ awaiting_human ─▶ running | blocked | cancelled
   │          │  │  ├─▶ blocked ────────▶ running | cancelled
   │          │  │  ├─▶ stalled ────────▶ running (new strategy) | failed | cancelled
   │          │  │  ├─▶ paused ─────────▶ running | cancelled
   │          │  │  └─▶ failed ─────────▶ running (operator retry) | cancelled
   │          │  └────┘
   └──────────┴──────▶ cancelled | superseded ──▶ archived
```

Implemented in `kernel/src/factory_kernel/state.py` (`JobState.transition`) and enforced by `Kernel.job_transition`.

## 4. Kernel module map (reference implementation)

| Module | Responsibility |
|--------|----------------|
| `kernel.py` | `Kernel` — project/job lifecycle, `doctor`, `reindex`, the only public entry point to state |
| `state.py` | `JobState` — event load/append/fold, chain verification, transitions, snapshot writing |
| `lease.py` | `LeaseManager` — acquire/renew/release with fencing tokens, guard-file mutual exclusion |
| `atomic.py` | `atomic_write`, `atomic_write_json`, `append_jsonl`, `read_json(l)` — all disk I/O |
| `ulid.py` | ULID generation (time-sortable, 26-char, no external deps) |
| `hashing.py` | `sha256_hex`, `event_hash`, `content_hash` — event chain + artifact hashing |
| `schemas.py` | `SchemaStore` — Draft 2020-12 validation of every kernel write |
| `profiles.py` | Stage-profile loader + YAML validation (`lite`, `standard`) |
| `engine.py` | `Engine.execute` — runs a profile end to end: stages → attempts → adapter → checks → gates |
| `checks.py` | Check runner — executes `checks.json` commands, trims output, computes failure fingerprints |
| `context.py` | `context.manifest.json` builder — token estimation, include modes, budget degradation |
| `adapters.py` | Adapter discovery, manifest loading, capability-based selection, NDJSON subprocess run contract with error classification |
| `checkpoint.py` | Content-addressed checkpoints: `tree_hash`, `result_hash`, `checkpoint.json` per accepted attempt, `checkpoint.created` events |
| `gitrepo.py` | Factory-managed git: per-project repo + `base_commit`, per-job worktree/branch, checkpoint commits, `--no-ff` merge queue (conflict → `blocked`), revert/reset Undo, and `collect_diff` for the per-attempt guard scope |
| `guards.py` | Pure deterministic anti-cheating guards over the attempt diff (`no_test_deletion`, `no_lockfile_surprise`, `no_secret_in_diff`) + the `GUARDS` registry; hard-fails on an unknown guard id; exact-path structural authorization via the job's `authorizations.json` |
| `budgets.py` | Pure cost arithmetic: `calculate_cost` (price table × reported usage), `stage_limits` (soft/hard resolution), `check_budget` (verdict). No I/O — the engine owns verdicts and events |
| `provenance.py` | Commit provenance trailers: build them and verify them (`factory provenance verify`) |
| `conformance.py` | Adapter conformance suite (§20.3): start, contract-file, usage, write-boundary, injected-instruction, plus capability-gated cancel/resume/heartbeat; records `conformance.json` |
| `dashboard.py` | Solo dashboard: `build_view`, `render_html`, `export_dashboard`, `serve` (stdlib HTTP + SSE + `POST /api/command`), `dispatch` (incl. `explain` and `JOB.answer`) |
| `cli.py` | `factory` command: `project create\|list\|status`, `job run\|execute\|approve\|undo\|answer\|status\|list\|cancel`, `request-changes`, `adapter test`, `provenance verify`, `serve`, `export-dashboard`, `doctor`, `reindex`; global `--root` / `--actor` |

## 5. Isolation and concurrency

- **Worktree per job:** `.work/<job-id>/` on branch `factory/<job-id>` from the project's base commit.
- **Merge queue:** integration serialized per repository; the Integrator rebases, re-runs checks, merges only if green. A conflict returns the job to Build with the conflict as input.
- **Stale base detection:** if the base moved and changed files intersect the plan's file set, the kernel requires a re-plan.
- **Resource isolation:** per-job dev-server port ranges, temp dirs, and fixture namespaces.
- **File-set conflict hints:** planning declares an expected file set; the scheduler delays overlapping jobs as an optimization only — the merge queue is the correctness mechanism.

## 6. Stage graph and contracts

Stages are YAML in `kernel/stages/` composed into profiles. A stage declares `role`, `requires`, `produces`, `checks`, `guards`, `effects` (`local | external`), `max_rounds`, `budget`, `gate`, and `on_fail`.

**Profiles:** `lite` (Solo, 5 steps: Understand → Plan → Build loop → Verify → Approve/merge) and `standard` (research/spec/architecture as adaptive steps, Plan, Design, Scaffold, Build loop, Verify, Review lenses, Polish, Package, Approve, Merge/Deploy).

**Artifact contracts** (schema-validated markdown frontmatter): `brief.md`, `plan.md`, `build.md`, `handoff.md` (≤ 400 words), `reviews/<lens>.md`, `decision.md`.

## 7. The build loop

Each round is **build → checks → guards → accept or fingerprint**, bounded by `max_rounds` and by the
stage's `budget` (tokens/minutes today; USD enforcement is P2.2, see §14).

- Each round receives the plan, the previous handoff, trimmed failing check output, and unresolved findings — never the full transcript of earlier rounds.
- **No-progress detection:** the kernel fingerprints each round (failing check IDs + normalized error signatures). Same fingerprint twice, or an empty diff → `stalled`. Escalation ladder: change strategy → switch model/adapter → reduce scope + re-plan → escalate to human. Each rung is an event.
- **Guards (anti-cheating), deterministic over the diff (P2.1):** implemented today — `no_test_deletion`, `no_lockfile_surprise`, `no_secret_in_diff`. Spec'd but **not yet implemented** — `no_check_tampering`, `scope_guard` (out-of-plan files allowed but raising the risk score).

### 7.1 The guard pipeline

```
attempt start ──▶ record attempt-base SHA
                      │
        adapter runs ──┴──▶ writes into the attempt dir + worktree only
                      │
              collect_diff(base → now)      # committed + staged + unstaged + untracked
                      │
        load + validate authorizations.json # kernel-owned, exact paths, wildcards never match
                      │
        run declared guards (pure functions)
                      │
        ├── violations ──▶ guard.violation events (per guard, per kind)
        │                   guards.json beside checks.json
        │                   verdict flips the attempt to failed, even with green checks
        │                   guard ids + paths join the attempt fingerprint → repeats stall
        └── clean ────────▶ guards.completed event → accept decision
```

Two deliberate properties: an **unknown guard id or a malformed `authorizations.json` becomes a
recorded `guard_config` violation** (so a typo can never silently disable a safeguard), and guards
are fed into the same fingerprint as checks, so an agent that repeats the same violation stalls
instead of consuming its rounds.

## 8. Roles and context

Five markdown role contracts in `roles/`: analyst, planner, builder, verifier, integrator. Review types are **lenses**, not agents (the `standard` profile's `review` stage declares lenses, not roles). The Integrator is not an agent — merging is a kernel function. The spec's wider set (designer, architect, reviewer, curator) is P3/P4 work.

Before every attempt the kernel writes `context.manifest.json` with a token budget and include modes (`full`, `summary`, `failures_only`, `relevant_slice`, `pointer`). Over budget, degradation is a fixed order: drop pointers → summarize old handoffs → slice repo map → fail loudly. Untrusted inputs (issues, READMEs) are wrapped and labeled as data.

**Uncertainty protocol:** agents write `questions.md` — `blocking` (job → `blocked`, human asked) or `assumable` (logged in `assumptions.md` with reversal cost, job continues). Assumptions are visible at approval.

## 9. Checks and quality

`checks.json` declares real commands (`lint`, `typecheck`, `unit`, `build`, `a11y`, `visual`). The kernel runs them itself in the sandbox and stores exit codes and trimmed output. An agent's claim that tests pass is never evidence. Every completed job gets a quality **record** (check outcomes, diff stats, rounds/stalls, review findings, human outcome, cost) — data, not one magic number.

## 10. Security

**Safety floor (spec target; enforced today to the degree marked below):** human gate for irreversible
external effects ✅ (the `approve` stage is `gate: required`; note every `lite` stage is currently
`effects: local`, so the external-effect path is unexercised) · no secrets in agent env/context/files
⚠️ (diff secret scanning is implemented by `no_secret_in_diff`, and the agent env is sanitized to the
`factory.json` allowlist with kernel-injected `FACTORY_*` attribution since P2.3; artifact scrubbing
is P2 work) ·
destructive ops outside the worktree blocked ❌ (P2) · hard budget caps ✅ (implemented and enforced
since P2.2: verdict per attempt, breach events, absolute hard stop) · audit events always written ✅ for the event types
that exist · agents cannot edit policy/budget/role/kernel files ✅ by construction (the write path is
closed to agents).

**Threat model mitigations** — current state, honestly marked: prompt injection → untrusted wrapping +
kernel-evaluated gates ✅ (the gate side is real as of P2.4 — kernel-evaluated, score-driven gates
decide by computed band, never agent judgment; P2.5 adds detection: kernel-owned baseline patterns
flag untrusted manifest items, the manifest entry is labeled, and the `injection_flagged` signal feeds
the same band→action map — the conformance suite's `injected_instruction` case runs and passes;
wrapping *every* untrusted source — web pages, imported repos — is still open) ·
secret exfiltration → no secrets in env ⚠️ + `no_secret_in_diff` ✅ + egress allowlist ❌ ·
dependency attacks → `no_lockfile_surprise` ✅, risk scoring ✅ as of P2.4 (install scripts /
allowlists still spec'd) · test tampering → `no_test_deletion` ✅, `no_check_tampering` ❌ ·
runaway cost → `budgets.py` ✅ as of P2.2 and feeding the risk score as of P2.4 · skill privilege
escalation → skills carry no permissions (P3, no skills yet) ·
audit tampering → event hash chain ✅, external anchors ❌ (P5).

> The point of the marks is that this table can be trusted. A security document that lists planned
> controls next to shipped ones without saying which is which is worse than a short one.

## 10.1 Adapters in the tree

| Folder | Kind | What it is |
|--------|------|------------|
| `adapters/echo/` | Adapter | Deterministic implementation of the run contract — exercises every code path without a model |
| `adapters/cli-agent/` | Adapter | Live backend that forwards the NDJSON contract to any external command (`FACTORY_CLI_AGENT_CMD`) |
| `adapters/visual-capture/` | **Not an adapter** | Stdlib-only headless Edge/Chrome capture producer, wired as the default `visual` **check**. It has no `manifest.json`, so adapter discovery correctly skips it |

## 11. Adapters

`adapters/<tool>/` with a `manifest.json` (id, version, capabilities, models, limits, roles supported). Run contract: `run(request) → stream of events` (`progress | tool_use | file_written | question | usage | heartbeat | done | error`), plus `cancel` and `resume`. Requirements: heartbeat ≤ 30 s (lease revoked on silence), mandatory usage reporting, idempotent start by `run_id`, write-boundary discipline, error classes `transient | capability | budget | fatal`. The kernel owns retries. New adapters pass a **conformance suite** before acceptance.

## 12. Scalability boundary

Files plus a single-host kernel comfortably handle hundreds of active jobs per project. Beyond one host or a few thousand events/second, the file layer is replaced by a database-backed store **behind the same kernel interface**; the file format remains the export/interchange format. This boundary is explicit — files are the protocol, not promised to be the only storage engine at scale.

## 13. Implementation rules

- Keep the kernel small, deterministic, and tested; it is the only component whose bugs can corrupt state.
- Every capability is expressible as files, a role or check, and optionally an adapter.
- Prefer configuration (`project.json`, `checks.json`, policy presets) over hard-coded behavior.
- Every file format has a JSON Schema in `kernel/schemas/`; schema changes are versioned with a migration.
- Never store secrets in the factory tree.
- Solo mode must stay simple: any feature appearing in Solo needs a zero-decision default.
- When spec and kernel disagree, the kernel's conformance tests are authoritative and the spec is corrected.
- Fail hard on anything a safeguard depends on. An unknown guard id, a malformed `authorizations.json`, or an unpriced usage key must raise rather than degrade — a safeguard that silently no-ops is worse than an absent one, because it looks present.

---

## Appendix — implemented vs. target at `77f32e9`

The suite is **436 collected — 434 passed, 2 skipped, 0 failed** — fully green after the task
player's review round (the 2 skips are capability-gated conformance cases).

| Capability | State |
|------------|-------|
| Events, fold, snapshots, leases + fencing, atomic writes, schema validation, legal transitions | ✅ implemented, tested |
| Stage-graph engine, build loop, no-progress detection, checkpoints, SHA-bound approval | ✅ implemented, tested |
| Dashboard (`serve` SSE + static export), Approve / Change this… / Undo / Explain this | ✅ implemented, tested |
| Git worktrees, checkpoint commits, merge queue, Undo | ✅ implemented, tested |
| Adapters (`echo`, live `cli-agent`) + conformance suite | ✅ implemented, tested |
| Solo question budget, real visual capture, visual diff `changed_pct` | ✅ implemented, tested |
| Guards: `no_test_deletion`, `no_lockfile_surprise`, `no_secret_in_diff` | ✅ implemented (40 cases) |
| Guards: `no_check_tampering`, `scope_guard` | ❌ not implemented (P2) |
| Budget cost meter + schemas | ✅ implemented (24 cases): pricing, limits, engine enforcement (verdict file, breach events, hard stop), doctor checks |
| Sandbox: env sanitization, lexical path containment, worktree-locked adapter cwd, doctor integrity | ✅ implemented (27 cases); container isolation and network/resource-limit enforcement are not yet |
| Risk-scored gates | ✅ implemented (37 cases): `risk_scoring` config schema + defaults, pure weighted-signal scoring with ceiling bands, kernel-owned band→action map, stage-scoped "road to this pass" signals, `risk.computed` verdict on the record, doctor integrity checks; per-preset band profiles and the spec's wider aspirational signal set (diff size, sensitive paths, scope drift, …) are not yet |
| Prompt-injection handling | ✅ implemented (30 cases): `injection` config schema, kernel-owned baseline patterns (config may only add), pure `injection.py` detector, manifest `injection_flags` labeling, `injection.detected` events, `injection_flagged` signal (weighted by `injection_flag`), dashboard verdict rows, doctor integrity checks; the conformance suite's `injected_instruction` case runs and passes, but the spec's wrapping of *all* untrusted sources (web pages, imported repos) is not yet |
| Operator cancellation of work in flight | ✅ implemented (8 cases): process-tree termination, cancellable adapter and check runs, a cancelled job ending `cancelled` with the pipeline writing nothing after the operator's own state change |
| Skill packages, evals, lessons, memory compounding | ❌ P3 |
| RBAC, hash-chained audit + anchors, brands, compliance export | ❌ P5 |

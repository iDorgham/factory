# Enterprise AI Software Factory — Full Project Context

> A portable briefing for any AI tool or model. Snapshot date: **2026-10-19**, commit `d933adf`
> (reconciled against the working tree: **423 tests collected — 421 passed, 2 skipped, 0 failed** —
> fully green at the close of P2.5).
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
is the source of truth for intended behavior; the code implements P0 (kernel core) and P1 (Solo slice)
fully, plus P2.1 (guards), P2.2 (budgets), P2.3 (sandbox), P2.4 (risk gates), and P2.5 (injection
handling) within the trust layer.

**Status right now:** P0 complete; **P1 Solo slice complete** (stage-graph engine, build loop, live `cli-agent` adapter, checkpoints, SHA-bound approval, worktrees + merge queue + Undo, question budget, and real visual capture via headless Edge/Chrome) — all proven end-to-end on the real tree; **P2.1 guards landed** (three deterministic diff guards, structural authorization, engine hook, dashboard verdicts, doctor integrity checks); **P2.2 budgets landed** (budget + price-table schemas, pure cost meter, engine enforcement — verdict file, breach events, hard stop, cached-refusal idempotency, dashboard verdict rows — and doctor integrity checks); **P2.3 sandbox landed** (`factory.json` schema-globally validated, pure env sanitization with an allowlist, kernel-reserved `FACTORY_*` attribution injection, lexical path containment, `strict_cwd` worktree lock, and doctor integrity checks); **P2.4 risk-scored gates landed** (`risk_scoring` config schema, pure weighted-signal scoring with ceiling bands, kernel-owned band→action map — untunable by configuration, `risk.computed` on the record, stage-scoped "road to this pass" signals driving the verify gate, and doctor integrity checks); **P2.5 prompt-injection handling landed** (`injection` config schema with kernel-owned baseline patterns that config may only add, a pure `injection.py` detector, untrusted manifest items scanned before the adapter runs, `injection_flags` labeling on the manifest entries, hash-chained `injection.detected` events, the `injection_flagged` signal (weighted by `injection_flag`) feeding the same band→action map, plain-language dashboard rows, and doctor integrity checks). Next head of the P2 queue: **safety-floor hardening** and **import with baseline verification** (§12).

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
| `engine.py` | `Engine` — drives a job through its stage profile: attempt dirs, context manifest, sandboxed adapter invocation (P2.3: sanitized env with kernel-reserved `FACTORY_*` attribution, `strict_cwd` locks adapter cwd to the job worktree, sandbox paths proven contained), kernel-run checks, gate evaluation (P2.4: `risk_scored`/`if_risk_above:*` gates decide from the computed band over stage-scoped signals, `risk.computed` on the record), and the build loop with failure-fingerprint no-progress detection → `stalled` (spec §9.2). |
| `checks.py` | Real command runner with trimmed output, required/conditional checks, `required_checks` meta-check, stable failure fingerprints. |
| `context.py` | `context.manifest.json` builder (schema-valid), resolving brief/requires + project memory, with token budgeting/degradation. |
| `adapters.py` | Adapter discovery, manifest loading, capability/role selection, NDJSON subprocess run contract with error classification. |
| `checkpoint.py` | Deterministic content hashes (`tree_hash`, `result_hash`), `checkpoint.json` per accepted attempt, `checkpoint.created` events. |
| `conformance.py` | Adapter conformance suite (§20.3): start, contract-file, usage, write-boundary, injected-instruction, plus capability-gated cancel/resume/heartbeat. Records `conformance.json`. |
| `dashboard.py` | `build_view` (three-element Solo view), `render_html`, `export_dashboard` (static snapshot), `serve` (stdlib HTTP server + SSE + `POST /api/command`), `dispatch`. |
| `gitrepo.py` | Factory-managed git: per-project repo + `base_commit`, per-job worktree/branch, checkpoint commits, `--no-ff` merge queue (conflict → `blocked`), revert/reset Undo. |
| `provenance.py` | Commit provenance trailer conventions, build + verify (`factory provenance verify`), enforced per-commit since P2.1 by the commit-msg hook and CI. |
| `guards.py` | Pure deterministic diff guards (`no_test_deletion`, `no_lockfile_surprise`, `no_secret_in_diff`) + registry `GUARDS`; hard-fail on unknown id, exact-path structural `authorized()`. |
| `budgets.py` | Pure deterministic cost calculation, limit checking, and fail-hard unpriced-usage enforcement: `calculate_cost` (price table × reported usage, any unpriced metered metric raises `BudgetError` — unpriced usage never silently costs $0), `stage_limits` (soft/hard resolution, `0.8 × usd` default soft, inverted limits raise), `check_budget` (inclusive boundaries). No I/O — the engine owns verdicts and events. |
| `sandbox.py` | Pure deterministic environment sanitization, lexical path containment, and fail-hard sandbox policy enforcement: `sanitize_env` (allowlist intersection of the kernel env — case-insensitive exact or `*`-suffix rules, lone `*` as explicit opt-out; output preserves order/values), `resolve_under` (relative paths root at base, absolute must sit inside, escapes raise `SandboxError`; pure string math after `normpath`+`normcase`, symlinks deliberately not resolved), `load_sandbox_policy` / `SandboxPolicy.from_config` (missing keys → documented defaults; unknown type, empty allowlist, malformed keys raise). No I/O — the engine owns subprocess wiring and doctor owns config integrity. |
| `risk.py` | Pure deterministic risk scoring, band resolution, and kernel-owned gate action mapping: `compute_score` (weighted sum over kernel-observed signals — guard violations, check failures, retries, budget verdict — clamped at the threshold cap; malformed input raises `RiskError`, never a guessed score), `resolve_band` (strict ceiling bands: `< low` → low, `< medium` → medium, else high; `high` saturates), `gate_action` (the band→action map lives in the kernel, NOT in config — tuning may re-weight the score, never renegotiate what a band does), `assess` (one verdict dict whose score/band/action all cite the same checked numbers), `load_risk_config` (absent → documented defaults; present-but-empty or malformed → `RiskError`; defensive copy). No I/O — the engine owns signal sourcing and event emission, doctor owns config integrity. |
| `injection.py` | Pure deterministic prompt-injection detection: `load_injection_config` (absent → documented kernel baseline patterns; present-but-empty, malformed, invalid regex, or a config id colliding with a kernel-owned baseline id → `InjectionError`; config may only *add* patterns, never remove or weaken a baseline), `scan_item` (regex match over text, excerpt truncated at 80 chars, confidence 1.0), `scan_manifest_items`, `injection_signal`. No I/O — the engine owns scanning, labeling, and events; doctor owns config integrity. |
| `cli.py` | The `factory` command (see §9). |

---

## 6. Repository map

```
factory/
├── factory.json                 # global config: price table, sandbox, budget defaults
├── factory                      # CLI launcher script
├── pyproject.toml               # packaging (factory-kernel 0.4.0) + pytest + flake8
├── .githooks/ .gitmessage .provenance-allow   # provenance enforcement + grandfather list
├── .github/workflows/           # CI: lint + test, and a provenance gate
├── CHANGELOG.md CONTRIBUTING.md SECURITY.md   # repository-level entry points
├── kernel/
│   ├── schemas/                 # event, job, project, context.manifest, authorizations,
│   │                            #   budget, price_table, factory, risk, injection (10) + CHANGELOG (schema migration log)
│   ├── presets/                 # solo.json, team.json, enterprise.json
│   ├── stages/                  # lite.yaml, standard.yaml
│   └── src/factory_kernel/      # the Python reference kernel (24 .py files: 23 modules + package __init__)
├── tests/                       # hermetic pytest suite (423 collected: 421 passed,
│   │                            #   2 skipped — fully green after P2.5)
│   └── fixtures/adapters/       # slow, fake-browser, cli-echo-agent, cli-ask-agent, budget-burner
├── roles/                       # markdown role contracts (5 starter: analyst, planner, builder, verifier, integrator)
├── adapters/echo/               # deterministic echo adapter (manifest.json, run.py, conformance.json)
├── adapters/cli-agent/          # generic CLI-agent shell-out adapter (FACTORY_CLI_AGENT_CMD; deterministic no-op by default)
├── adapters/visual-capture/     # NOT an adapter: stdlib headless Edge/Chrome capture producer (a check command)
├── projects/<name>/             # runtime state: project.json, checks.json, repo/, memory/, jobs/
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
factory job undo <job-id>                                        # revert a completed merge (§21.2)
factory job answer <job-id> <question-id> "<answer>" [--adapter id]  # answer a blocking question

factory request-changes <job-id> "<feedback>" [--adapter id]     # "Change this…" from the approval card
factory adapter test <adapter-id> [--no-record]                   # run conformance suite (§20.3)
factory serve [--host --port --no-open]                           # live dashboard (SSE)
factory export-dashboard [--out f.html] [--project p]             # static read-only snapshot
factory provenance verify [--range r] [--require k] [--allow sha]  # check AI-Tool/AI-Model trailers
                          [--all-before sha] [--allowlist f] [--json]
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
| **P1 Solo slice** | lite execution, adapter runtime, build loop, checkpoints + SHA-bound approval, conformance suite, dashboard, worktrees + merge/undo, question budget, real visual capture | ✅ Complete |
| **P2 Trust layer** | budgets/metering, guards, sandbox hardening, injection handling, risk-scored gates, import with baseline | 🚧 **In progress** — P2.1 guards landed (diff collection, three deterministic guards, engine hook, fingerprint feed, plain-language dashboard verdicts, doctor integrity checks); P2.2 budgets landed (schemas, pure cost meter, engine enforcement, doctor checks); P2.3 sandbox landed (`factory.json` schema, pure env sanitization + path containment, sandboxed adapter invocation, doctor checks); P2.4 risk gates landed (`risk_scoring` config schema, pure weighted scoring with ceiling bands, kernel-owned action map, `risk.computed` on the record, stage-scoped signals, doctor checks); P2.5 injection handling landed (`injection` config schema, pure detector, manifest labeling, `injection.detected` events, `injection_flagged` signal (weighted by `injection_flag`), dashboard rows, doctor checks); remaining: safety-floor hardening, import with baseline |
| **P3 Learning** | eval harness, skill packages + promotion, lessons ledger, memory | ⬜ Planned |
| **P4 Team** | more adapters via conformance, epics + dependencies, visual baselines, named users | ⬜ Planned |
| **P5 Enterprise** | control plane, RBAC, hash-chained audit + anchors, brand design systems, compliance export | ⬜ Planned |

### P1 — done vs. remaining
**Done (verified in code):** stage-graph engine + build loop; adapter runtime + echo + live cli-agent backend (NDJSON forwarding, honest failure classes, `resume`, recorded conformance); content-addressed
checkpoints (+ git commit per checkpoint); SHA-bound approval (refuses changed results); `interrupted` attempt recovery + input-hash
idempotency; adapter conformance suite (§20.3) + `factory adapter test`; Solo dashboard (`serve` live SSE
+ `export-dashboard` static, with Approve / Change this… / Undo / Explain this on the card); `request-changes` rework loop;
factory-managed git worktrees + merge queue (conflict → `blocked`) + Undo (`merge.undone`).

**Remaining (P1):** nothing blocking. One open nicety: live-server preview capture (the contract and the
real producer are landed; capturing a served URL rather than a file is not implemented).

---

## 11. Development, testing, and metrics

- **Language:** Python ≥ 3.11. Runtime deps: `PyYAML`, `jsonschema`. Lint: `flake8` (max line 100).
- **Packaging:** `factory-kernel` v0.4.0; console script `factory`.
- **Run tests:** `pip install -e ".[dev]"` then `python -m pytest` and `python -m flake8 kernel/src tests`.
- **Hermetic tests:** each test builds a throwaway factory tree in `tmp_path` from the real schemas/presets/stages.
- **Source metrics:** 24 kernel modules (25 `.py` files — the 25th is the package `__init__`; the set incl. checkpoint, conformance, dashboard, gitrepo, provenance, guards, budgets, sandbox, risk, injection, cancel); 10 schemas; commit history carries `AI-Tool`/`AI-Model` provenance trailers per-commit since P2.1 (machine-verified by the commit-msg hook and CI).
- **Test count (verified 2026-10-19):** `437 collected — 435 passed, 2 skipped` — fully green, zero failures. Test files: atomic, ulid, hashing, lease, state, transitions, profiles, schemas, kernel, doctor, engine, checks, context, adapters, cli-agent, checkpoint, conformance, dashboard, worktree (git/merge/undo/isolation), questions (Solo question budget), visual_capture (real capture producer + diffs), explain (dispatched from the dashboard), provenance, guards (P2.1: guard units, diff collection, engine hook, doctor authorizations), budgets (P2.2: cost math, limits, schemas, engine hook, doctor budget checks), sandbox (P2.3: schema validation, env sanitization, path containment, policy parsing, subprocess cwd/env contract, sandboxed engine run, doctor sandbox checks), risk (P2.4: risk_scoring schema/config contracts, signal scoring, ceiling bands, kernel-owned actions, config loading, engine gate wiring with `risk.computed`, doctor risk checks), injection (P2.5: injection schema contracts, kernel-owned baseline patterns, config loading, item scanning, manifest labeling, `injection.detected` events, the `injection_flagged` signal (weighted by `injection_flag`), doctor injection checks), cancel (operator cancellation: the adapter/check process tree is killed, the job ends `cancelled` and the pipeline writes nothing after it).

---

## 12. Known gaps / open questions (good discussion material)

1. **Worktree lifecycle (done, verify edge cases)** — `.work/<job-id>/` is a real git worktree (`gitrepo.add_worktree`, branch `factory/<job-id>`). Open: port-range allocation, orphan/stale-base handling under concurrent jobs (P4).
2. ~~**Question budget open**~~ — *closed 2026-10-16 (P1)*: `echo`/`cli-agent` `question` events are persisted as `job.question_asked`, deduped by id/normalized text, capped at 3 blocking questions per job, park the job `blocked`, fail the job honestly when exhausted, and surface on the dashboard card with option buttons and a free-text box. Both sides reach future attempts through `questions.md` in the context manifest.
3. **Guards not executed** — *closed 2026-10-17 (P2.1)*: `no_test_deletion`, `no_lockfile_surprise`, `no_secret_in_diff` run per attempt over the diff from the attempt-base commit; violations fail the attempt, feed the fingerprint (repeat → stalled), land as hash-chained events, and are authorized structurally by per-job `authorizations.json` (exact paths, schema-validated). `scope_guard` and plan-file-set authorization remain future.
4. ~~**Budgets not enforced**~~ — *closed 2026-10-17 (P2.2)*: `budgets.py` (pure cost meter: `calculate_cost` prices every `X_tokens` metric at the tier's `X_per_1m` rate; unpriced usage raises `BudgetError` — nothing silently costs $0), `engine._run_budget` (verdict into `budget.json` each budgeted round; `budget.soft_exceeded` notifies while the work stands, `budget.hard_exceeded` fails the attempt and stops the retry loop; job → `failed` as an absolute stop per §543; a cached hard refusal is returned on resume without re-spending), and doctor (price-table schema validity is authoritative; inverted soft/hard limits and unpriced usage are advisories naming the fix). Per-attempt cost stays in `budget.json`; no per-attempt timeline noise. Remaining budget scope (future): budgets at job/project scope, pre-job cost estimates, cost reports, mid-run cut-off.
5. ~~**Sandbox is config-only**~~ — *closed 2026-10-17 (P2.3)*: `factory.schema.json` validates the whole `factory.json` (first-ever global-config schema; sandbox `type` enum is `["process"]` until containers land), `sandbox.py` is the pure contract (`sanitize_env` strips the kernel env to the configured allowlist — case-insensitive exact or `*`-suffix rules, lone `*` as explicit opt-out; `resolve_under` rejects lexical path escapes; `load_sandbox_policy` fails hard on unknown types and empty allowlists), `engine._invoke_adapter` always runs adapters sandboxed (sanitized env plus kernel-reserved `FACTORY_*` attribution injected after the filter, `strict_cwd` locking adapter cwd to the job worktree), and doctor (config schema-validity is authoritative; `"*"` allowlist and absent/static-off `strict_cwd` are advisories naming the trade). Still open in sandbox scope: container isolation, network-egress and resource-limit enforcement (declared, not enforced), secrets scrubbing from logs/artifacts.
6. ~~**No risk scoring**~~ — *closed 2026-10-18 (P2.4)*: `risk_scoring` config (schema-validated in `risk.schema.json` + inlined in `factory.schema.json`; absent → documented defaults; fail-hard loader), `risk.py` (pure weighted-signal arithmetic: guard violations, check failures, retries, budget verdict — clamped at the cap; strict-ceiling bands), `engine._risk_gate` (stage-scoped "road to this pass" signals from kernel-owned records, `risk.computed` emitted verbatim before the decision so score→band→action cite the same stored numbers; low → auto-advance, medium → job parked `awaiting_human` at the risk gate, high → deterministically `failed` pending operator rerun), and doctor (section schema-validity is authoritative, `gate_actions` overrides are named as the kernel-ownership violation they are; zero weights and non-monotonic thresholds are advisories). The band→action map is deliberately NOT operator-configurable — tuning may re-weight the score, never renegotiate what a band does. Remaining risk scope (future): RiskConfig in per-project/preset profiles with tighten-only auditing (Team+), plain-language risk rows on the dashboard timeline.
7. ~~**Prompt injection is unhandled**~~ — *closed 2026-10-19 (P2.5)*: the `injection` config section (schema-validated, inlined in `factory.schema.json`) carries detection patterns that config may only **add to** — the kernel's baseline ids (`ignore-previous-instructions`, `system-prompt-leak`, `do-not-follow`, `pretend-to-be`) cannot be overridden or removed, and a colliding id is a hard error. `injection.py` is pure (`load_injection_config`, `scan_item`, `scan_manifest_items`, `injection_signal`); the engine scans the job's untrusted items **before** the adapter runs, labels each flagged manifest entry with `injection_flags`, emits one hash-chained `injection.detected` event per match, and raises the `injection_flagged` signal (weighted by `injection_flag`) so the **existing** kernel-owned band→action map decides (low → auto, medium → park for a human, high → blocked). A broken detector raises `InjectionError` → deterministic `config_error` + `injection.json` verdict; it can never degrade into "nothing flagged". Doctor audits the section (schema validity authoritative; baseline-id collision an error; zero-weight patterns an advisory). Still open in this scope: wrapping *all* untrusted sources (web pages, imported repos) and the spec's injection fixture in the conformance suite.
8. Undo/merge — done (`gitrepo.merge_branch`/`revert_merge`, `kernel._merge_on_complete`/`job_undo`, conflict → `blocked`, `merge.undone`; dashboard Undo enabled when a merge is present).
9. **Schema versioning is interim** — schemas have no `$id` version yet; `kernel/schemas/CHANGELOG.md` is the interim record.
10. **Roles incomplete** — the spec defines 8 roles; only 5 exist (analyst, planner, builder, verifier, integrator); reviewer/designer/architect/curator are missing (P3/P4).
11. **Dashboard scope** — currently Solo three-element; Team/Enterprise panels are future.
12. **No LICENSE file** and no upstream git remote — worth resolving before distributing or hosting the repository.

---

## 13. Suggested prompts for another AI

Use these to get high-value reasoning from another model:

- "Here is the architecture (§5). Which invariants are most fragile, and what tests would harden them?"
- "Guards (§12 gap #3) and cost math (§12 gap #4) are implemented as pure kernel functions while their runtime wiring is not. What is the safest order to close the gap, and where could a partial integration create a false sense of enforcement?"
- "Visual capture uses headless Chromium with a runtime theme probe, and `changed_pct` diffs against the previous attempt. Where exactly should visual-diff thresholds gate the `verify` stage, and what baseline-management flow keeps them deterministic across machines?"
- "Review the build loop's no-progress detection (failure fingerprint → stalled), which now also absorbs guard violations. What failure modes would still evade it?"
- "The conformance suite runs cancel/resume/heartbeat only when the adapter declares the capability. Is graceful degradation the right call, or should these be mandatory?"
- "Where does the implementation diverge from the specification's promises? List concrete gaps."
- "Propose a risk-score computation (signals → score bands → gate actions) that is deterministic and hard to game."

---

## 14. Provenance

**Tool and model:** P0 and P1 were developed with **OpenCode** using the **Big Pickle** model (provider
`opencode`) — that part is **owner-attested**, because those commits predate the provenance convention.
Since P2.1 (`f5815b9`) every commit carries `AI-Tool` / `AI-Model` trailers, so the tool/model claim for
P2 is **machine-verified** by git: the `commit-msg` hook and the CI provenance job both refuse a commit
without them, and `factory provenance verify` audits the history. See
**[AI-PROVENANCE.md](AI-PROVENANCE.md)** for the per-phase table and the convention itself.

---

## 15. Where to look next (in this repository)

- Spec: `docs/specification/Enterprise AI Software Factory — Specification v3.0.md`
- Architecture: `docs/architecture/ARCHITECTURE.md`
- Roadmap & phase plans: `docs/plans/`
- Contributing/standards/testing/adapters: `docs/development/`
- Operations/security: `docs/operations/`
- History: `docs/context/HISTORY.md`

**If this document conflicts with the code, the code and the spec win.** Update this file, not the code, to match.

# 🏭 Enterprise AI Software Factory

> **A deterministic kernel that turns one sentence into verified, reviewable, mergeable software — by orchestrating coding agents it does not trust.**

[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![License](https://img.shields.io/badge/license-NOT%20YET%20DECLARED-lightgrey?style=flat-square)](#-license)
[![Version](https://img.shields.io/badge/kernel-0.4.0-blueviolet?style=flat-square)](pyproject.toml)
[![Spec](https://img.shields.io/badge/specification-v3.0-6F42C1?style=flat-square)](docs/specification/Enterprise%20AI%20Software%20Factory%20%E2%80%94%20Specification%20v3.0.md)
[![Language](https://img.shields.io/badge/stack-Python%20%C2%B7%20YAML%20%C2%B7%20JSON%20%C2%B7%20Markdown-3572A5?style=flat-square)](kernel/)
[![Phase](https://img.shields.io/badge/phase-P2%20trust%20layer-in%20progress-orange?style=flat-square)](docs/plans/ROADMAP.md)
[![Tests](https://img.shields.io/badge/tests-423%20collected%20%C2%B7%20421%20passed-007ec6?style=flat-square)](docs/development/TESTING.md)
[![Lint](https://img.shields.io/badge/lint-flake8%20clean-brightgreen?style=flat-square)](.flake8)
[![CI](https://img.shields.io/badge/CI-flake8%20%2B%20pytest%20%2B%20provenance-lightgrey?style=flat-square)](.github/workflows/ci.yml)

<p align="center">
  <b>Files are the protocol. Events are the truth. A small kernel enforces. Agents only propose.</b>
</p>

---

> [!NOTE]
> **Status:** P0 ✅ · P1 ✅ · P2 🚧 (P2.1 guards → P2.2 budgets → P2.3 sandbox → P2.4 risk gates →
> P2.5 injection handling landed) · P3 planned
> — verified 2026-10-19 at commit `d933adf` with **423 tests collected, 421 passed, 2 skipped,
> 0 failed**. This is a **runnable reference implementation** of a written specification, not a
> hosted product.
>
> The **CI** badge describes what the workflows run rather than showing a pass/fail. A live status
> badge needs an `<owner>/<repo>` slug: swap it for
> `https://github.com/<owner>/<repo>/actions/workflows/ci.yml/badge.svg`.

> [!WARNING]
> **This project is not sandboxed at the OS level.** Agent subprocesses get a sanitized environment and
> a confined working directory (P2.3), but there is no container, no network egress enforcement, and no
> resource limiting. Run it as you would run any untrusted local script.
> See [Security → Threat model](docs/operations/SECURITY.md).

---

## 📑 Table of Contents

- [✨ Features](#-features)
- [🚀 Quick Start](#-quick-start)
- [🛠️ Usage & Examples](#-usage--examples)
- [🧠 AI Provenance & Methodology](#-ai-provenance--methodology)
- [🏗️ Architecture](#️-architecture--how-it-works)
- [📜 History & Evolution](#-history--evolution)
- [🤝 Contributing](#-contributing)
- [📄 License](#-license)

---

## ✨ Features

The system exists to answer questions you *cannot* get a trustworthy answer to when you simply prompt an
agent and trust the transcript:

> *"Did the tests actually pass, or did the agent decide they passed? Did it delete the failing tests?
> Is the page I'm looking at the page that passed the checks? What state is my repository in now?
> Who wrote this change — and can that claim be verified a year from now?"*

The factory takes the opposite position: **the agent is untrusted input, not a trusted collaborator.**

### 🧱 Core capabilities

| Capability | What it actually does |
|-----------|-----------------------|
| 🧾 **Events are the truth** | Every state change is an appended, `prev`-hash-chained line in `events.jsonl`. `job.json` is a pure fold and can always be rebuilt or repaired. |
| 🔒 **Kernel enforces, agents propose** | Only the deterministic kernel writes state. Agents write output files into their own attempt directory and git worktree — there is no code path giving them the log. |
| 🧪 **Checks, not claims** | The kernel *executes* `lint` / `typecheck` / `unit` / `build` / `a11y` / `visual` itself. An agent's statement that tests pass is never evidence. |
| 🛡️ **Anti-cheating guards** | Three deterministic guards read the **actual git diff** and fail an attempt for deleted tests, dependency-lockfile drift, or secrets in added lines. |
| 💰 **Budgets & metering** | Reported usage is priced against a per-tier table in `factory.json`. Soft breach notifies; hard breach fails the attempt and stops the retry loop. |
| 🧊 **Sandbox boundary** | Adapter subprocesses see only an allowlisted environment (plus kernel-reserved `FACTORY_*` attribution) and start inside the job worktree. |
| 📊 **Deterministic risk scoring** | A weighted sum over kernel-observed signals (guard violations, check failures, budget status, retries, injection flags) resolves a gate to `auto_advance` / `awaiting_human` / `blocked`. No model opinion is an input. |
| 🧯 **Injection detection** | Untrusted manifest items are scanned with kernel-owned baseline patterns. A match labels the manifest entry, records a hash-chained `injection.detected` event, and raises the `injection_flag` risk signal — the kernel-owned band→action map decides what happens next. |
| 🖼️ **Real visual evidence** | Stdlib-only headless Edge/Chrome capture at declared viewports in light + dark themes, bound to the checkpoint SHA, with honest `changed_pct` diffs. |
| 🔀 **Isolated, mergeable work** | Per-job git worktree on `factory/<job-id>`, content-addressed checkpoints, a serialized `--no-ff` merge queue, and one-command **Undo**. |
| 🧑 **Solo question budget** | At most 3 blocking questions per job, persisted as events, answerable in one click, with both sides reaching future attempts. |
| 🔌 **Bring your own agent** | Adapters are the *only* tool-specific code. `cli-agent` forwards the contract to any external command. |
| 📋 **Conformance suite** | New adapters must pass `factory adapter test` before acceptance — capability-gated cases skip honestly. |
| 🩺 **`factory doctor`** | Verifies the hash chain end to end, repairs snapshots, validates kernel-owned policy, and audits guard/budget/sandbox/risk/injection config integrity. |
| 🔍 **Machine-verified provenance** | Every commit records the AI tool and model that wrote it; `factory provenance verify` (also run in CI) proves it. |

### 🎯 Ten non-negotiable principles

<details>
<summary><b>Click to expand the project's core principles</b></summary>

1. **Tool-agnostic core.** All state, contracts, and history are markdown, JSON, and JSONL. Adapters are the only tool-specific code.
2. **Kernel enforces, agents propose.** Agents write output files; only the kernel validates and commits state.
3. **Events are the truth.** Current state is a fold over the event log; everything else is a rebuildable cache.
4. **Isolation by default.** One worktree and one branch per job.
5. **Deterministic gates first.** Build/lint/type/test/a11y/visual results decide. LLM review informs; it never solely approves.
6. **Safety floor.** Some controls cannot be configured away — band-to-action gate mapping is kernel-owned, not tunable.
7. **Progressive complexity.** One engine, three presets (Solo / Team / Enterprise); Solo users never see what they don't need.
8. **Resumable and idempotent.** Recovery restores checkpoints; external effects and cached refusals are never repeated.
9. **Cost-aware.** Every attempt reports usage; budgets are enforced at stage boundaries.
10. **Compounding.** Lessons, memory, and evaluated skills make later jobs better than earlier ones.

</details>

### 📊 Repository at a glance

| Metric | Value |
|--------|-------|
| 🧠 Kernel modules | 23 pure-ish Python modules in `kernel/src/factory_kernel/` |
| 📐 JSON Schemas | 10 — every file format is validated on write |
| 🎛️ Stage profiles | `lite` (Solo, 5 steps) · `standard` (Team/Enterprise, 11 steps) |
| 🧪 Test suite | **423 collected — 421 passed, 2 skipped, 0 failed** across 27 modules |
| 🔌 Adapters | `echo` (deterministic) · `cli-agent` (live) · `visual-capture` (check producer) |
| 🎭 Role contracts | 5 starter roles in `roles/` |
| ⏱️ Runtime dependencies | **2** — `PyYAML` and `jsonschema` |

> [!TIP]
> The 2 skipped tests are two edges of the executable spec §7 transition matrix
> (`superseded` is unreachable from `pending`). They are documented unreachable
> transitions, not skipped coverage.

---

## 🚀 Quick Start

> [!NOTE]
> **Requirements:** Python **≥ 3.11** and `git` on `PATH`. That is the whole dependency list.
> On Windows PowerShell, substitute `python .\factory` for `./factory`.

### 1️⃣ Install

```bash
git clone <repo-url> factory
cd factory

python -m venv .venv
# Windows (PowerShell): .\.venv\Scripts\Activate.ps1
# POSIX:               source .venv/bin/activate

pip install -e ".[dev]"
```

That installs the kernel, `pytest`, and `flake8`, and maps the `factory` console script. Prefer
no-install? The `./factory` launcher adds `kernel/src` to the path itself, so `./factory doctor` works
on a bare clone.

### 2️⃣ Verify the install

```bash
python -m pytest          # 423 tests, ~3.5 min
python -m flake8 kernel/src tests
./factory doctor          # ok: no jobs
```

### 3️⃣ Create a project and run a job

```bash
# Create a Solo project — mode and domain pick the profile and default checks
./factory project create demo --mode solo --domain web

# One sentence is the entire input
./factory job run demo "Build a landing page with hero and contact form"

# Drive it through the lite stage graph:
# understand -> plan -> build -> verify -> approve
./factory job execute <job-id>
```

### 4️⃣ Approve, merge, and undo

```bash
# The approve gate parks the job at awaiting_human. Approving binds to the
# exact bytes that were checked, then merges the job branch into main.
./factory job approve <job-id>

# Changed your mind? Revert the merge (spec §21.2 Undo)
./factory job undo <job-id>
```

### 5️⃣ Watch it work

```bash
./factory serve                                  # live dashboard at 127.0.0.1:8787
./factory export-dashboard --out dashboard.html  # or a static, shareable snapshot
```

---

## 🛠️ Usage & Examples

### 📋 Command reference

```bash
# Projects
factory project create <name> [--mode solo|team|enterprise] [--domain web|mobile|desktop|game|generic] [--brand b]
factory project list
factory project status <name>

# Jobs
factory job run <project> "<description>" [--epic id] [--profile lite|standard]
factory job execute <job-id> [--adapter id] [--check-timeout n]
factory job approve <job-id> [--adapter id] [--sha <checkpoint-sha>]
factory job undo <job-id>                     # revert a completed merge
factory job answer <job-id> <question-id> "<answer>" [--adapter id]
factory job status <job-id>
factory job list [--project p]
factory job cancel <job-id> [--reason r]

# Feedback loop
factory request-changes <job-id> "<feedback>" [--adapter id]

# Adapters & provenance
factory adapter test <adapter-id> [--no-record]
factory provenance verify [--range r] [--require k] [--allow sha] [--all-before sha] [--json]

# Dashboard, health, maintenance
factory serve [--host h] [--port n] [--no-open]
factory export-dashboard [--out f.html] [--project p]
factory doctor
factory reindex

# Global flags
--root <path>    # operate on a different factory tree (essential for tests)
--actor <name>   # identity recorded on every event (default: local)
```

### 🔄 A full Solo round trip, end to end

```bash
./factory project create demo --mode solo --domain web
./factory job run demo "Build a landing page with hero and contact form"
./factory job execute <job-id>       # worktree, manifest, agent, checks, guards, budget, checkpoint
./factory job status <job-id>        # parked at awaiting_human (approve gate)
./factory job approve <job-id>       # bound to the latest checkpoint SHA -> merge.completed
./factory job undo <job-id>          # merge.undone
./factory doctor                     # chain verified, snapshot consistent
```

### 🤔 Handling a blocking question

The Solo question budget is 3. When an agent genuinely needs input, the job parks `blocked` rather than
guessing, and the dashboard renders the question with one-click options:

```bash
./factory job status <job-id>
#   state: blocked
#   q-hero: Should the hero fill the viewport or sit above the fold?
#     [1] Full-bleed   [2] Above the fold   [3] Centered

./factory job answer <job-id> q-hero "Full-bleed" --adapter cli-agent
./factory job execute <job-id>    # resumes; both Q&A reach future attempts via questions.md
```

### 🪙 Wiring a real coding agent

`cli-agent` forwards the NDJSON run contract to **any** external command:

```bash
# Windows PowerShell
$env:FACTORY_CLI_AGENT_CMD = "opencode run --print-logs {prompt}"
./factory job execute <job-id> --adapter cli-agent

# POSIX
export FACTORY_CLI_AGENT_CMD="claude -p"
./factory job execute <job-id> --adapter cli-agent
```

The adapter must classify its own failures honestly: a nonzero exit or exit-0-with-missing-outputs is
`fatal`; a timeout is `transient` so the kernel may retry. Verify any adapter before trusting it:

```bash
./factory adapter test cli-agent      # conformance suite (spec §20.3)
```

### 🩺 Auditing a tree

```bash
./factory doctor
```

Doctor verifies the `prev` hash chain end to end, folds events and repairs diverging snapshots
(**the fold wins**), validates every job's `authorizations.json`, warns on unknown guard ids, verifies
budget price-table integrity, audits sandbox configuration, and checks the risk and injection
config sections — the last three as honesty advisories rather than silent passes.

<details>
<summary><b>🛠️ Troubleshooting: common symptoms → cause → fix</b></summary>

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Attempt failed but **every check passed** | A **guard** tripped over the diff | Read `guards.json` in the attempt dir; fix the change or authorize the exact path |
| Job `stalled` right after a guard violation | Expected — violations feed the no-progress fingerprint | Don't retry. Change the plan or authorize the path |
| `guard_config` / `unknown_guard` violation | The profile names a guard that doesn't exist, so it **never ran** | Fix the id in `kernel/stages/*.yaml`; confirm with `./factory doctor` |
| `job.json` disagrees with events | Snapshot drift | `./factory doctor` — the fold wins |
| "stale writer rejected" | A zombie process held an old fencing token | Expected. Confirm the process is gone |
| `BudgetError` on unpriced usage | A `X_tokens` usage key has no `X_per_1m` rate | Add the metric to the tier. Raising beats silently costing $0 |
| Visual capture says "not a real screenshot" | The manifest came from a fixture | Only real Edge/Chrome captures carry `synthetic: false` |

</details>

---

## 🧠 AI Provenance & Methodology

A project whose thesis is *auditable, verified claims* should itself be auditable. So every commit
records which AI tool and model produced it — and the repository can **prove** it rather than assert it.

### 📜 The convention

Every commit ends with provenance trailers:

```text
feat(budgets): implement deterministic cost calculation and limit checking

- calculate_cost: every X_tokens key priced at X_per_1m of the model tier
- stage_limits: usd is the hard limit; soft defaults to 0.8 x usd

AI-Tool: opencode
AI-Model: glm-5.3-flash-free
AI-Provider: opencode
```

| Trailer | Required | Notes |
|---------|----------|-------|
| `AI-Tool` | ✅ yes | The tool/agent used. Use `human` if no AI was involved. |
| `AI-Model` | ✅ yes | The model id. Use `human` if none. |
| `AI-Provider` | optional | e.g. `opencode` |
| `AI-Session` | optional | The tool's session id, for traceability |
| `Co-authored-by` | optional | A human who materially edited or reviewed the change |

### 🔍 Verification is mechanical

```bash
git config commit.template .gitmessage    # pre-filled trailers
git config core.hooksPath .githooks       # optional local enforcement

./factory provenance verify                        # audit the whole history
./factory provenance verify --range HEAD~3..HEAD   # just recent commits
./factory provenance verify --json                 # machine-readable report
```

`factory provenance verify` is the **same deterministic check CI runs**. Pre-convention history is
grandfathered through [`.provenance-allow`](.provenance-allow) rather than rewritten — rewriting
history to make a metadata claim look better would contradict the project's own append-only rule.

> [!IMPORTANT]
> **Attested ≠ verified.** P0 and P1 predate the convention, so their tool/model mapping is
> **owner-attested** (the project owner stated it; git cannot check it). Every commit from P2.1
> (`f5815b9`) onward is **machine-verified** by the `commit-msg` hook and CI. Both are labelled as such
> in the table below — never conflate them.

### 📋 Per-phase lineage

| Phase | Delivered | Tool | Model | Confidence |
|-------|-----------|------|-------|-----------|
| **P0** Kernel core | Events, atomic writes, leases + fencing, schemas, `doctor`, 109 tests | OpenCode | Big Pickle | Owner-attested |
| **P1** Solo slice | Stage-graph engine, build loop, adapters, conformance, dashboard, worktrees + merge/undo, question budget, visual capture | OpenCode | Big Pickle | Owner-attested |
| **P2.1** Guards | `authorizations.json`, `collect_diff`, three guards, engine hook, doctor checks | OpenCode | GLM-5.3-Flash Free | **Machine-verified** |
| **P2.2** Budgets | `budget`/`price_table` schemas, cost meter, engine enforcement, doctor checks | OpenCode | GLM-5.3-Flash Free | **Machine-verified** |
| **P2.3** Sandbox | `factory.schema.json`, `sandbox.py`, sandboxed adapter invocation, doctor checks | OpenCode | GLM-5.3-Flash Free | **Machine-verified** |
| **P2.4** Risk gates | `risk.schema.json`, `risk.py`, `risk.computed`, engine gate resolution | OpenCode | GLM-5.3-Flash Free | **Machine-verified** |
| **P2.5** Injection handling | `injection.schema.json`, `injection.py`, `injection.detected`, engine + dashboard + doctor wiring | OpenCode | GLM-5.3-Flash Free | **Machine-verified** |
| **P1.1** Solo dashboard task player | Sticky task-player footer, honest action states, read-only export, ARIA semantics | OpenCode | Big Pickle | Owner-attested |

### 🧬 Methodology: TDD-red slices

The project commits **failing tests before the implementation** on purpose. The failing tests are the
written contract for the *next* slice, which prevents the failure mode where tests are written to match
whatever the code happened to do.

The rules that keep this honest:

1. The failing tests must be **named in the commit body** and linked to a plan item.
2. They are committed **with** the slice they specify, never left to drift.
3. `doctor` and `flake8` stay clean; only the named tests are red.
4. The phase does not close until they are green.

P2.2 (budgets), P2.3 (sandbox), P2.4 (risk), and P2.5 (injection) each went through this state and
closed green — the suite is at **0 failures** today.

> [!TIP]
> Chasing an open question? The [`docs/context/` pack](docs/context/README.md) is a self-contained
> briefing designed to be pasted into another AI tool (Qwen, Grok, ChatGPT, Claude, local models) —
> it carries the architecture, the roadmap, the open gaps, and discussion prompts.

Full detail: **[docs/context/AI-PROVENANCE.md](docs/context/AI-PROVENANCE.md)**

---

## 🏗️ Architecture & How It Works

Read the diagram as a **permission statement**, not a call graph:

```text
        ┌─────────────────────────────────────────────────────────┐
        │  CLIENTS — factory CLI · local dashboard                 │
        └───────────────────────────┬─────────────────────────────┘
                                    │ validated commands only
        ┌───────────────────────────▼─────────────────────────────┐
        │  KERNEL — deterministic Python. No LLM inside.         │
        │  state machine · leases & fencing · schema validation   │
        │  check runner · guards · budget meter · sandbox          │
        │  risk scoring · checkpoints · merge queue                │
        └────────────┬──────────────────────────┬───────────────┘
                     │ run requests             │ atomic read/write
        ┌────────────▼────────────┐   ┌─────────▼───────────────┐
        │  ADAPTERS               │   │  FILES — the protocol    │
        │  echo · cli-agent       │   │  events.jsonl (truth)    │
        │  (the only tool code)   │   │  job.json · worktrees    │
        └────────────┬────────────┘   │  memory · manifests      │
                     │                └──────────────────────────┘
        ┌────────────▼────────────┐
        │  CODING AGENTS          │  own worktree · propose only
        │  (untrusted)            │  sanitized env · never touch state
        └─────────────────────────┘
```

### 🔁 What happens when you run a job

1. **One sentence in.** `job run` creates a job directory and records a `job.created` event.
2. **Worktree first.** A real git worktree at `.work/<job-id>/` on branch `factory/<job-id>`, branched
   from the project's `base_commit`. The agent cannot touch your working tree — it has its own.
3. **Context manifest.** `context.manifest.json` carries the plan, required artifacts, project memory,
   and trimmed failing-check output, under a token budget with an *ordered* degradation policy.
4. **Sandboxed invocation.** The adapter runs with an allowlisted environment plus kernel-reserved
   `FACTORY_*` attribution, cwd pinned to the worktree, streaming NDJSON events.
5. **Kernel runs the checks.** Never the agent. For web projects the `visual` check drives headless
   Edge/Chrome for genuine light/dark screenshots at declared viewports.
6. **Guards read the diff.** Three deterministic guards inspect what the round actually changed.
7. **Budgets price the usage.** Reported tokens × the `factory.json` price table, checked against the
   stage's soft/hard limits.
8. **The kernel decides.** Green checks *and* clean guards *and* an intact budget → accept. Otherwise
   the failure is fingerprinted; a repeated fingerprint or an empty diff means `stalled`, not a retry.
9. **Checkpoint.** A content hash over outputs + worktree, a git commit, and a `checkpoint.created`
   event — so a killed process resumes from the last accepted state, never a dirty tree.
10. **Human gate.** `verify` resolves a risk score; `approve` is `gate: required`, parking the job at
    `awaiting_human`.
11. **SHA-bound approval.** Approving binds to the exact bytes checked; change the result and the
    approval is invalid. Approval runs a `--no-ff` merge; a conflict returns the job to `blocked`
    rather than leaving the repo mid-merge.
12. **Replayable.** `factory doctor` re-verifies the chain and repairs snapshots. `factory reindex`
    rebuilds derived state. Derived state is disposable by design.

### 🧬 The verdict pipeline — one deterministic chain

Every safety mechanism in the kernel is a **pure function over kernel-owned records**, never a model's
opinion. This is what makes the decisions auditable end to end:

```text
agent run
   │
   ├─▶ checks.json    exit codes + trimmed output  ──┐
   ├─▶ collect_diff   committed/staged/untracked    ──┼─▶ fingerprint ──▶ accept │ stalled
   ├─▶ guards.json    deletions · lockfiles · keys ─┤                          │
   └─▶ usage.json     tokens × price_table         ──┘                          │
                                                                                ▼
   risk.computed ──▶ score ──▶ band ──▶ gate action (auto_advance │ awaiting_human │ blocked)
        │
        └── pure arithmetic; the band→action map is kernel-owned and NOT configurable,
            because a tunable `high → auto_advance` would let configuration renegotiate
            the safety floor away.
```

### 🧠 Job state machine

```text
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

Transitions are **data, not convention** — an illegal move raises.

<details>
<summary><b>🔒 Core invariants enforced by the kernel</b></summary>

1. **Agents never write state** — only the kernel appends to `events.jsonl`.
2. **Events are the truth** — `job.json` is a pure fold; on disagreement the fold wins.
3. **Lease + fencing** — every state write carries a monotonic token; stale writers are rejected.
4. **Atomic writes** — temp file → `fsync` → `os.replace`, cross-platform.
5. **Legal transitions only** — the state machine rejects moves outside the table.
6. **Schema validation before disk** — an invalid document never reaches the filesystem.
7. **Derived state is disposable** — `factory reindex` rebuilds it from the logs.
8. **Checks are the gate** — a green result comes from an exit code, not a sentence in a transcript.
9. **Guards are the gate too** — a violation fails the attempt even when every check passed.
10. **Budgets are the gate too** — a hard breach fails the attempt *and* breaks the retry loop.
11. **Approval binds to content** — approving a stale SHA is refused.
12. **Crash is never success** — an interrupted attempt is retried without consuming a round.
13. **No progress is detected** — repeated fingerprints or an empty diff stall the job.
14. **Work is isolated** — per-job worktree; merges are serialized; conflicts block, never corrupt.
15. **Every claim is traceable** — `factory provenance verify` proves who wrote each commit.

</details>

<details>
<summary><b>🗂️ Kernel module map (23 modules)</b></summary>

| Module | Responsibility |
|--------|----------------|
| `kernel.py` | `Kernel` — project/job lifecycle; the only public entry point to state; `doctor`, `reindex` |
| `state.py` | `JobState` — event load/append/fold, chain verification, legal transitions, snapshots |
| `lease.py` | `LeaseManager` — acquire/renew/release with monotonic fencing tokens |
| `atomic.py` | Every durable write: `atomic_write`, `append_jsonl`, `read_json(l)` |
| `ulid.py` · `hashing.py` | ULID generation · event-chain and content hashing |
| `schemas.py` | `SchemaStore` — Draft 2020-12 validation on every kernel write |
| `profiles.py` | Stage-profile loader + YAML validation |
| `engine.py` | The stage-graph driver: attempts, manifests, adapter calls, checks, guards, budgets, risk, gates, fingerprints |
| `checks.py` | Check runner — real commands, trimmed output, stable failure fingerprints |
| `context.py` | `context.manifest.json` builder — token budgeting and ordered degradation |
| `adapters.py` · `conformance.py` | Discovery, selection, NDJSON run contract · the §20.3 conformance suite |
| `checkpoint.py` · `gitrepo.py` | Content-addressed checkpoints · worktrees, merge queue, Undo, `collect_diff` |
| `guards.py` · `budgets.py` · `risk.py` · `sandbox.py` · `injection.py` | The pure verdict modules (P2 trust layer) |
| `dashboard.py` | Solo dashboard — `build_view`, `serve` (SSE + `POST /api/command`), `export_dashboard` |
| `provenance.py` · `cli.py` | Commit-trailer build/verify · the `factory` command |

</details>

> [!NOTE]
> Need the design rationale rather than the mechanics? See
> **[Architecture & Design](docs/architecture/ARCHITECTURE.md)**, which maps every layer, module, and
> invariant, and ends with an explicit *implemented vs. target* table.

---

## 📜 History & Evolution

The project is built in **ordered phases**, each depending only on what is already solid. It took
**four build days, one author, 40 commits**.

| Phase | Deliverable | Status |
|-------|-------------|--------|
| **P0** Kernel core | `events.jsonl` + `job.json`, atomic writes, leases & fencing, schema validation, check runner, `doctor`, `reindex` | ✅ Complete |
| **P1** Solo slice | `lite` execution, adapters + build loop, checkpoints + SHA-bound approval, conformance suite, dashboard, git worktrees + merge queue + Undo, live `cli-agent`, question budget, real visual capture | ✅ Complete |
| **P2** Trust layer | Guards → budgets → sandbox → risk-scored gates → prompt-injection handling; then safety-floor hardening and import with baseline | 🚧 In progress (5 of 7 workstreams) |
| **P3** Learning | Eval harness, skill packages & promotion, lessons ledger, repo map & memory | ⬜ Planned |
| **P4** Team | More adapters via conformance, epics, visual baselines, named users | ⬜ Planned |
| **P5** Enterprise | Control plane, RBAC, hash-chained audit, brand design systems, compliance export | ⬜ Planned |

### 🗺️ The arc

- **Day 1 — the invariants first (P0).** State, atomicity, fencing, transitions, and schemas were
  finished and tested *before* any execution engine existed. Exactly as the roadmap demands.
- **Day 1 — the Solo loop (P1).** Stage-graph engine, build loop, checkpoints, approval, the
  dashboard, worktrees and merge. Then a hardening pass proved the loop twice on real trees and fixed a
  worktree-identification bug that had been silently dropping approve-time events.
- **Day 2 — the trust layer (P2).** Five slices in sequence, each following the same shape: schema +
  failing contract tests → a pure verdict module → engine wiring → `doctor` integrity checks.
  1. **P2.1 Guards** — caught the cheapest form of cheating: deleting the evidence.
  2. **P2.2 Budgets** — made "no job exceeds its hard budget" actually enforceable, refusing unpriced
     usage instead of pricing it at zero.
  3. **P2.3 Sandbox** — turned a declared boundary into an enforced one for adapter subprocesses.
  4. **P2.4 Risk gates** — gave `gate: risk_scored` a real, deterministic score behind it.
  5. **P2.5 Injection handling** — made untrusted input *detectable*: kernel-owned patterns flag it,
     the manifest is labeled, and the existing band→action map decides what happens.
- **Day 3 — dogfooding.** The provenance convention became enforced by CI, so the project's claim about
  its own development stopped being a matter of memory.

<details>
<summary><b>📈 Full milestone timeline & test-count growth</b></summary>

**Test-count growth as a progress proxy** — note the deliberate dip where P2.2 committed its failing
contracts *before* the implementation:

| Milestone | Passed / total |
|-----------|----------------|
| P0 skeleton | — |
| P0 hardening | 81 |
| P0 polish (transition audit) | 109 |
| P1 engine | 142 / 144 |
| P1 checkpoints + SHA approval | 154 / 156 |
| P1 conformance suite | 159 / 159 |
| P1 dashboard | 171 / 173 |
| P1 worktrees + merge + Undo | 203 / 205 |
| P1 hardening (recovery, live backend) | 212 / 214 |
| P1 question budget + visual plumbing | 222 / 224 |
| P1 real visual capture | 234 / 236 |
| P1 "Explain this" + visual diff | 240 / 242 |
| P2.1 guards complete | 284 / 286 |
| P2.2 schemas + red contracts | 284 / 290 *(6 red — TDD)* |
| P2.2 cost meter | 305 / 312 *(5 red — TDD)* |
| P2.2 budget enforcement complete | 341 / 343 |
| P2.3 sandbox complete | 341 / 343 |
| P2.4 risk gates | 378 / 380 |
| P2.5 injection handling | 421 / 423 |
| **Solo dashboard task player (HEAD `d933adf`)** | **421 / 423** |

**Commit timeline highlights:** `d328d49` P0 skeleton → `fd06130` engine → `9398dfe` worktrees &
merge → `3e1b55b` P1 complete → `f5815b9` P2.1 contracts → `9948840` budget meter → `08980ed`
budget enforcement → `8348af8` sandbox contracts → `408c538` sandbox enforcement → `8c422fc` risk
contracts → `0f76850` risk scoring → `344c81f` injection contracts → `851987f` injection detection
→ `878629b` injection doctor checks → `a8697f1` dashboard task player.

**What the history suggests:** ordering discipline (invariants before engine), test-first evidence
(every commit brings its own test module), spec-driven work (commit messages cite the § they
implement), and a self-applied audit trail.

</details>

Full narrative: **[docs/context/HISTORY.md](docs/context/HISTORY.md)** ·
Changelog: **[CHANGELOG.md](CHANGELOG.md)**

---

## 🤝 Contributing

Contributions are very welcome — and the bar is deliberately high in one place: **anything that
touches state, leases, transitions, or schema validation on write.** Those are the components whose
bugs corrupt history, so weakening them requires changing the specification first.

### 🧰 Setup

```bash
pip install -e ".[dev]"
python -m pytest
python -m flake8 kernel/src tests    # the same command CI runs
```

### ✅ The definition of a good change

- [ ] Suite green (`python -m pytest`) — or, for a deliberate TDD-red slice, the failing tests named in
      the commit body and linked to a plan item
- [ ] `flake8` clean
- [ ] `./factory doctor` clean against a scratch tree, if you touched state, events, or leases
- [ ] Schemas updated **and** an entry in `kernel/schemas/CHANGELOG.md`
- [ ] Docs updated (PRD / Architecture / plan / CHANGELOG) — and **no doc claims a control is enforced
      when it is not**
- [ ] Provenance trailers present (`AI-Tool`, `AI-Model`); `./factory provenance verify` passes
- [ ] No secrets in code, tests, fixtures, or logs

### ✍️ Editing rules that bite

1. All durable writes go through `atomic.py` — never `open(..., "w")` on a state file.
2. Only `state.py` appends events. A new event type means a schema edit **and** an emit from
   `JobState`, not from a caller.
3. `guards.py`, `budgets.py`, `risk.py`, and `sandbox.py` are **pure** — no file I/O, no subprocess,
   no network, no clock. They return data; the engine owns events and files.
4. **Fail hard on anything a safeguard depends on.** An unknown guard id, an invalid
   `authorizations.json`, or unpriced usage must raise. A safeguard that silently degrades into a no-op
   is worse than one that is absent, because it looks present.
5. Authorization is structural — exact paths in the kernel-owned `authorizations.json`. Never parse
   permissions out of `plan.md` prose; never introduce glob matching.
6. New behavior in Solo mode needs a zero-decision default.

### 🧾 Commit provenance

```bash
git config commit.template .gitmessage   # pre-filled trailers
git config core.hooksPath .githooks      # optional local enforcement
```

CI enforces the same rule on every push, so a missing trailer fails the build rather than being caught
in review. Use `AI-Tool: human` / `AI-Model: human` when no AI was involved.

### 📚 Where to go deeper

| I want to… | Read |
|------------|------|
| Understand the process, review standards, and PR checklist | [Contributing guide](docs/development/CONTRIBUTING.md) |
| Set up an environment and debug | [Development guide](docs/development/DEVELOPMENT.md) |
| Match the house style | [Coding standards](docs/development/CODING-STANDARDS.md) |
| Add a test | [Testing](docs/development/TESTING.md) |
| Write a new coding-tool adapter | [Adapters guide](docs/development/ADAPTERS.md) |
| Change a file format | [Schema versioning](docs/development/SCHEMA-VERSIONING.md) |

### 🔐 Security

> [!CAUTION]
> **Do not open a public issue for a vulnerability.** Report privately with a description, reproduction
> steps, the affected component (kernel / adapter / dashboard / schema), and potential impact.
> → **[SECURITY.md](SECURITY.md)**

---

## 📄 License

> [!WARNING]
> **No license has been declared yet.** There is no `LICENSE` file in this repository, which means the
> default copyright rules apply: **no one may legally copy, modify, or distribute this work** without
> permission. That is almost certainly not the intent, and it blocks legitimate reuse.
>
> **Recommendation:** add a `LICENSE` file before distributing. For an enterprise-internal reference
> implementation, Apache-2.0 or MPL-2.0 both work — MPL-2.0 requires file-level changes to be published,
> which suits a project whose value is in shared kernel internals. Note that
> [`docs/specification/`](docs/specification/) contains a full written specification that you may want
> to license separately or alongside the code.

Until then:

| Asset | Status |
|-------|--------|
| Source code (`kernel/`, `adapters/`, `tests/`) | Undeclared — all rights reserved by default |
| Documentation (`docs/`, `README.md`, `CHANGELOG.md`) | Undeclared — all rights reserved by default |
| Specification v3.0 (`docs/specification/`) | Undeclared — all rights reserved by default |

---

<p align="center">
  <b>Files are the protocol. Events are the truth. A small kernel enforces. Agents only propose.</b><br>
  <sub>Enterprise AI Software Factory — specification v3.0 · kernel package <code>factory-kernel</code> 0.4.0 · Python ≥ 3.11</sub>
</p>
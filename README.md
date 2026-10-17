# 🏭 Enterprise AI Software Factory

**A deterministic kernel that turns one sentence into verified, reviewable, mergeable software — by
orchestrating coding agents it does not trust.**

[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![Specification](https://img.shields.io/badge/specification-v3.0-6F42C1)](docs/specification/Enterprise%20AI%20Software%20Factory%20%E2%80%94%20Specification%20v3.0.md)
[![Phase](https://img.shields.io/badge/phase-P2%20trust%20layer-in%20progress-orange)](docs/plans/ROADMAP.md)
[![Tests](https://img.shields.io/badge/tests-343%20collected-007ec6)](docs/development/TESTING.md)
[![Kernel modules](https://img.shields.io/badge/kernel-21%20modules-007ec6)](docs/architecture/ARCHITECTURE.md)
[![Runtime deps](https://img.shields.io/badge/runtime%20dependencies-2-blueviolet)](pyproject.toml)

**Files are the protocol. Events are the truth. A small kernel enforces. Agents only propose.**

---

## 📖 Table of contents

- [What this is](#-what-this-is)
- [Why it exists](#-why-it-exists-the-problem-with-trusting-an-agent)
- [The one idea](#-the-one-idea-kernel-enforces-agents-propose)
- [What actually happens when you run a job](#-what-actually-happens-when-you-run-a-job)
- [Architecture](#-architecture)
- [What is in the box](#-what-is-in-the-box)
- [Repository layout](#-repository-layout)
- [Quick start](#-quick-start)
- [The job lifecycle](#-the-job-lifecycle)
- [Core invariants](#-core-invariants-enforced-by-the-kernel)
- [Anti-cheating guards](#-anti-cheating-guards-p2)
- [Budgets and metering](#-budgets-and-metering-p2)
- [Provenance](#-provenance-dogfooding)
- [Design decisions](#-design-decisions-captured)
- [Roadmap](#-roadmap)
- [Development](#-development)
- [Documentation](#-documentation)
- [Project status and honest gaps](#-project-status-and-honest-gaps)
- [Contributing and security](#-contributing-and-security)

---

## 💡 What this is

This repository is a **runnable reference implementation** of the Enterprise AI Software Factory
specification (v3.0): a small, deterministic kernel plus a file protocol that drives coding agents
through a fixed, auditable engineering process — understand, plan, build, verify, approve — and
records everything they do as a hash-chained event log.

The purpose is not to run more agents. It is to be able to say, with evidence, **"this is actually
done."** Every claim the system makes is backed by something the kernel itself observed: a check
command that exited zero, a screenshot the kernel captured, a content hash the kernel computed, a
guard that read the diff. An agent's confidence is never evidence. An agent's summary of its own work
is never accepted as a result.

The current build ships **P0 (kernel core)** and **P1 (Solo slice)** complete and proven end to end,
**P2.1 (anti-cheating guards)** landed, and **P2.2 (budgets and metering)** in flight. The test suite
collects **312 cases**. See [Project status](#-project-status-and-honest-gaps) for the exact numbers,
including which tests are red *by design*.

> **Not a hosted product, not a SaaS, not a multi-agent framework.** It is a single-host kernel, a
> folder of files, and two runtime dependencies (`PyYAML`, `jsonschema`). Everything else is protocol.

---

## 🎯 Why it exists: the problem with trusting an agent

Ask a coding agent to build a landing page and you get files. What you *cannot* get, reliably, is an
answer to any of these questions:

- Did the tests actually pass, or did the agent decide they passed?
- Did it quietly delete the three tests that were failing?
- Did it add a dependency nobody planned for, without touching the lockfile?
- Is the page I am looking at the page that passed the checks?
- If it half-finished, what state is my repository in now?
- Can two of these run at once without corrupting each other?
- Who — or what tool — actually wrote this change, and can that claim be verified later?

Every mainstream answer today resolves those questions with *trust*: you trust the agent's report,
you review the diff yourself, or you re-run everything by hand. That works, and it does not scale past
a handful of small changes per day. It also cannot be audited after the fact, which is the specific
problem an enterprise has and an individual does not.

The factory takes the opposite position. **The agent is untrusted input, not a trusted collaborator.**
It gets a narrow, machine-checked contract: read your context manifest, write inside your attempt
directory and your job's git worktree, report what you did as structured events. It cannot write
state. It cannot approve its own work. It cannot mark a check as passed. It cannot convince the kernel
that nothing changed by describing nothing changed — the kernel reads the actual diff.

The result is a system where **the happy path is fast and the dishonest path is mechanically
impossible to hide**, and where every fact you might later want to audit is already sitting in a
file with a hash chain behind it.

---

## 🧠 The one idea: kernel enforces, agents propose

Everything in this repository follows from a single separation of powers:

```
        ┌─────────────────────────────────────────────────────────┐
        │  CLIENTS — factory CLI · local dashboard · later: RBAC  │
        └───────────────────────────┬─────────────────────────────┘
                                    │ validated commands only
        ┌───────────────────────────▼─────────────────────────────┐
        │  KERNEL — deterministic Python. No LLM inside.        │
        │  state machine · leases & fencing · schema validation  │
        │  check runner · guards · budget meter · checkpoints     │
        │  merge queue · audit chain                             │
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
        │  (untrusted)            │  never touch state
        └─────────────────────────┘
```

Read that diagram as a *permission* statement, not a call graph:

- **The kernel is the only writer of state.** Not "the preferred writer" — the only one. Agents propose
  output files; the kernel validates and commits. There is no code path where an agent writes to
  `events.jsonl`.
- **The kernel is deterministic and not a model.** It contains no LLM calls, no network requests, no
  hidden clocks, no randomness outside ULID timestamps. That is what makes it auditable: given the
  same inputs it produces the same decision, every time, and you can read exactly why.
- **Adapters translate; they never decide.** An adapter converts the kernel's run request into
  whatever protocol a specific tool speaks (NDJSON over a subprocess for `cli-agent`). Adding support
  for a new coding tool means writing one folder and passing a conformance suite — it never means
  touching the kernel's trust model.
- **The dashboard is a client.** Every button in the browser becomes a kernel command over HTTP. There
  is no path where a page writes a file.

One caveat stated up front rather than buried: the worktree boundary is real, but **process-level
sandboxing is not implemented**. An agent runs with the privileges of whoever started the kernel. The
[security document](docs/operations/SECURITY.md) marks every control ✅ / ⚠️ / ❌ for exactly this reason.

The practical consequence: the factory can be *unattended* precisely because it does not trust
anything it did not verify.

---

## 🔬 What actually happens when you run a job

This is the concrete lifecycle behind the abstractions, using the Solo `lite` profile. Every step is
real, shipped, and covered by tests.

**1. You type one sentence.** `factory job run demo "Build a landing page with hero and contact form"`
creates a job directory, records a `job.created` event, and hands you a job id. Nothing has run yet.

**2. You execute.** `factory job execute <job-id>` acquires a lease on the job, then walks the stage
graph declared in `kernel/stages/lite.yaml`. For each stage, for each attempt:

- **A git worktree is created** at `.work/<job-id>/` on branch `factory/<job-id>`, branched from the
  project's `base_commit`. The agent cannot touch your working tree — it has its own.
- **A context manifest is built** (`context.manifest.json`): the plan, required artifacts, project
  memory, unresolved findings, trimmed failing-check output. It has a token budget and an ordered
  degradation policy, so over-budget context is visibly reduced rather than silently truncated.
- **The adapter is invoked** with an NDJSON contract. It may stream `progress`, `tool_use`,
  `file_written`, `question`, `usage`, `heartbeat`, `done`, or `error`. Silence past the heartbeat
  deadline revokes the lease.
- **The kernel runs the checks itself.** `lint`, `typecheck`, `unit`, `build`, `a11y`, and — for web
  projects — `visual`, which drives headless Edge/Chrome to take real screenshots at declared
  viewports in light and dark themes. The kernel executes these commands; it does not ask the agent
  whether they passed.
- **Guards read the diff.** Three deterministic guards (`no_test_deletion`, `no_lockfile_surprise`,
  `no_secret_in_diff`) inspect what the round actually changed, from the attempt's base commit to now.

**3. The kernel decides.** An attempt is accepted only if the checks are green *and* the guards are
clean. If it fails, the kernel fingerprints the failure (failing check IDs + normalized error
signatures). Same fingerprint twice in a row, or an empty diff, means *no progress* → the job goes
`stalled` instead of burning its remaining rounds. Guard violations feed the same fingerprint, so an
agent that repeatedly deletes tests stalls rather than retrying.

**4. Accepted attempts are checkpointed.** The kernel computes a content hash over the attempt's
outputs and the worktree, commits the worktree, and records `checkpoint.json` + a
`checkpoint.created` event. Now the work can be resumed exactly: killing the process mid-attempt
leaves an `interrupted` record (never a success), and resuming restores the worktree to the last
accepted checkpoint with `git reset --hard && git clean -fd`.

**5. The job parks at a human gate.** After `verify`, the `approve` stage has `gate: required`, so
the job stops at `awaiting_human` and the dashboard shows one "Needs you" card.

**6. Approval is bound to content.** `factory job approve <job-id>` approves *the exact bytes that
were checked* — the approval carries the checkpoint SHA. Change the result and the approval is
invalid; the job stays parked. Approving runs a `--no-ff` merge of the job branch into `main`. A
conflict returns the job to `blocked` and leaves the repository clean — never mid-merge.

**7. Undo is a first-class operation.** `factory job undo <job-id>` reverts that merge as a new
audited event chain. It refuses a second undo and refuses an unmerged job.

**8. Everything is replayable.** `factory doctor` re-verifies the `prev` hash chain end to end, folds
the events, repairs `job.json` when it diverges from the fold, validates every job's guard
authorizations, and warns about stale leases or orphan worktrees. `factory reindex` rebuilds
`state/index.json` from the logs. Derived state is disposable by design.

---

## 🧱 What is in the box

Twenty kernel modules, seven JSON Schemas, two stage profiles, three policy presets, two adapters plus
a real capture producer, five role contracts, and a 312-case hermetic test suite.

### Kernel modules — `kernel/src/factory_kernel/`

| Module | Responsibility |
|--------|----------------|
| `kernel.py` | `Kernel` — project/job lifecycle, the only public entry point to state; `doctor`, `reindex` |
| `state.py` | `JobState` — event load/append/fold, chain verification, legal transitions, snapshot writing |
| `lease.py` | `LeaseManager` — acquire/renew/release with monotonic fencing tokens, guard-file mutual exclusion |
| `atomic.py` | `atomic_write`, `atomic_write_json`, `append_jsonl`, `read_json(l)` — every durable write |
| `ulid.py` | ULID generation (time-sortable, 26 chars, no external dependency) |
| `hashing.py` | `sha256_hex`, `event_hash`, `content_hash` — event chain and content addressing |
| `schemas.py` | `SchemaStore` — Draft 2020-12 validation on every kernel write |
| `profiles.py` | Stage-profile loader + YAML validation (`lite`, `standard`) |
| `engine.py` | `Engine.execute` — the stage-graph driver: attempts, manifests, adapter calls, checks, gates, guards, no-progress detection |
| `checks.py` | Check runner — real commands, trimmed output, stable failure fingerprints |
| `context.py` | `context.manifest.json` builder — token estimation, include modes, ordered degradation |
| `adapters.py` | Adapter discovery, capability/role-based selection, NDJSON subprocess contract, error classification |
| `conformance.py` | Adapter conformance suite (§20.3) — start, contract, usage, write-boundary, injected-instruction, cancel/resume/heartbeat |
| `checkpoint.py` | Content-addressed checkpoints — `tree_hash`, `result_hash`, `checkpoint.json`, `checkpoint.created` events |
| `gitrepo.py` | Factory-managed git — per-project repo, worktrees, checkpoint commits, `--no-ff` merge queue, revert/reset Undo, `collect_diff` |
| `guards.py` | Pure deterministic anti-cheating guards over the attempt diff + the `GUARDS` registry |
| `budgets.py` | Pure cost arithmetic — price the reported usage, resolve soft/hard limits, classify `ok` / `soft_exceeded` / `hard_exceeded` |
| `dashboard.py` | Solo dashboard — `build_view`, `render_html`, `serve` (stdlib HTTP + SSE + `POST /api/command`), `export_dashboard`, `dispatch` |
| `provenance.py` | Commit provenance trailers — build and verify the `AI-Tool` / `AI-Model` convention |
| `cli.py` | The `factory` command |

### Schemas, profiles, adapters, roles

| Asset | Contents |
|-------|----------|
| `kernel/schemas/` | 7 schemas: `event`, `job`, `project`, `context.manifest`, `authorizations`, `budget`, `price_table` |
| `kernel/stages/` | `lite.yaml` (Solo: understand → plan → build → verify → approve), `standard.yaml` (Team/Enterprise, 11 steps) |
| `kernel/presets/` | `solo.json`, `team.json`, `enterprise.json` — policy presets |
| `adapters/echo/` | Deterministic adapter that exercises the whole run contract without a model |
| `adapters/cli-agent/` | **Live** backend that shells out to any external command (`opencode run`, `claude -p`, a script) |
| `adapters/visual-capture/` | Stdlib-only headless Edge/Chrome capture producer, wired as the default `visual` check. Deliberately **not** an adapter (no `manifest.json`) — it is a check command |
| `roles/` | 5 starter role contracts: `analyst`, `planner`, `builder`, `verifier`, `integrator` |
| `tests/` | 24 hermetic test modules, 312 cases — every test builds a throwaway factory tree in `tmp_path` |

---

## 📂 Repository layout

```
factory/
├── factory.json                     # global config: price table, sandbox block, budget defaults
├── factory                          # CLI launcher (a Python script; no install needed)
├── pyproject.toml                   # packaging (factory-kernel 0.4.0) + pytest + flake8 config
├── .githooks/commit-msg             # opt-in local provenance enforcement
├── .gitmessage                      # commit template with the provenance trailers
├── .provenance-allow                # grandfathered pre-convention commits
├── .github/workflows/               # CI: lint + test, and a provenance gate
├── CHANGELOG.md                     # Keep a Changelog; spec-aligned versions
├── CONTRIBUTING.md · SECURITY.md    # entry points → docs/
├── docs/                            # the documentation set (indexed in docs/README.md)
│   ├── product/                     # PRD
│   ├── architecture/                # ARCHITECTURE.md
│   ├── specification/               # the canonical v3.0 specification
│   ├── plans/                       # ROADMAP + per-phase plans P0–P5
│   ├── development/                 # contributing, standards, testing, adapters, schemas, releasing
│   ├── operations/                  # runbook, troubleshooting, security
│   └── context/                     # portable briefing for other AI tools + history + provenance
├── kernel/
│   ├── schemas/                     # 7 JSON Schemas + their change log
│   ├── presets/                     # solo / team / enterprise
│   ├── stages/                      # lite.yaml, standard.yaml
│   └── src/factory_kernel/          # 20 modules — the Python reference kernel
├── tests/                           # 24 hermetic test modules + adapter fixtures
│   └── fixtures/adapters/           # fake-browser, cli-echo-agent, cli-ask-agent, budget-burner, slow
├── roles/                           # markdown role contracts
├── adapters/                        # echo, cli-agent, visual-capture
├── projects/<name>/                 # runtime state, one directory per project
│   ├── project.json                 # mode, domain, profile, base_commit
│   ├── checks.json                  # real check commands (the gate)
│   ├── repo/                        # factory-managed git repo (main branch)
│   ├── memory/                      # conventions.md, decisions.md
│   └── jobs/<job-id>/
│       ├── job.json                 # DERIVED snapshot (pure fold of events)
│       ├── events.jsonl             # SOURCE OF TRUTH (append-only, hash-chained)
│       ├── brief.md, assumptions.md, questions.md
│       └── stages/<nn>-<stage>/attempt-<k>/
│           ├── context.manifest.json · usage.json · guards.json
│           ├── checks.json · checkpoint.json · outputs/
│           └── artifacts/
├── .work/<job-id>/                  # git worktree on branch factory/<job-id>
└── state/index.json                 # derived, rebuildable with `factory reindex`
```

---

## 🚀 Quick start

> **Requirements:** Python ≥ 3.11. `git` on `PATH` for worktree isolation. Two runtime dependencies,
> installed with the dev extras.

```bash
pip install -e ".[dev]"       # kernel + pytest + flake8, editable
# or use the launcher directly, with no install at all:
./factory doctor              # Windows PowerShell: python .\factory doctor
```

### Create a project and run a job

```bash
# 1. Create a Solo project (mode + domain pick the profile and default checks)
./factory project create demo --mode solo --domain web

# 2. Start a job — one sentence is the whole input
./factory job run demo "Build a landing page with hero and contact form"

# 3. Drive it through the lite stage graph: understand → plan → build → verify → approve
./factory job execute <job-id>

# 4. The approve gate parks the job at awaiting_human. Approve the exact bytes that were checked.
#    Approving also merges the job branch into main.
./factory job approve <job-id>                      # optionally: --sha <checkpoint-sha>

# 5. Changed your mind? Revert the merge (spec §21.2 Undo)
./factory job undo <job-id>

# 6. Feedback loop: "Change this…" reopens the last accepted stage for rework
./factory request-changes <job-id> "make the hero bigger"

# 7. If the agent asked a blocking question (≤ 3 per job), answer it and the job resumes
./factory job answer <job-id> <question-id> "Split hero into two" --adapter cli-agent
```

### Look at it

```bash
./factory serve                                  # live dashboard at 127.0.0.1:8787 (SSE)
./factory export-dashboard --out dashboard.html  # or: a static, read-only snapshot to share
```

### Inspect and maintain

```bash
./factory job list
./factory job status <job-id>
./factory project list
./factory project status <name>
./factory job cancel <job-id> --reason "superseded"
./factory doctor                                 # verify + repair
./factory reindex                                # rebuild derived state
```

### Adapters and provenance

```bash
./factory adapter test echo                      # run the conformance suite (spec §20.3)
./factory adapter test cli-agent                # the live backend; records conformance.json
./factory provenance verify                      # check every commit carries its AI trailers
./factory provenance verify --range HEAD~3..HEAD --json
```

### Global flags

| Flag | Meaning |
|------|---------|
| `--root <path>` | Operate on a different factory tree (essential for tests and scratch trees) |
| `--actor <name>` | Identity recorded on every event; defaults to `local` |

---

## 🔄 The job lifecycle

### States

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

The transition table is data, not convention: an illegal move raises. Every transition is an event
with an actor and a fencing token, so `job.json` can always be recomputed from the log.

### What each state means in practice

| State | What a human sees | What the kernel is doing |
|-------|-------------------|--------------------------|
| `running` | Timeline advancing | Adapter invocation, checks, guards |
| `awaiting_human` | One "Needs you" card | Parked at a required gate; approval is bound to a checkpoint SHA |
| `blocked` | A question with option buttons | Waiting on a human answer, a dependency, or an exhausted question budget |
| `stalled` | "No progress detected" | Fingerprint repeated or empty diff; the escalation ladder starts here |
| `failed` | Red badge with the reason | Checks failed, a guard tripped, or the process was killed mid-attempt |
| `completed` | Green, merged | The job branch is merged into `main`; `factory job undo` can revert it |

### Artifacts of a run

| Path | Role |
|------|------|
| `events.jsonl` | **Source of truth.** Append-only, `prev`-hash-chained, one JSON object per line. |
| `job.json` | Derived snapshot — a pure fold of the events. Disposable; `doctor` rewrites it. |
| `context.manifest.json` | Exactly what the agent was allowed to read, with the token budget it was given. |
| `usage.json` | Tokens/cost reported by the adapter for that attempt — real numbers, never backfilled estimates. |
| `checks.json` | Every check the kernel ran: exit code, trimmed output, fingerprint. |
| `guards.json` | Every guard that ran over the diff and what it found. |
| `checkpoint.json` | `sha` (content hash, binds approval) and `commit` (git commit, restores the tree). |
| `outputs/visual.json` | Screenshot manifest: viewport, theme, file, `synthetic` flag, `changed_pct`. |
| `state/index.json` | Derived index across jobs. `factory reindex` rebuilds it. |

---

## 🔒 Core invariants enforced by the kernel

These are the rules the code refuses to break. Each one has tests, and each one is a reason a
half-broken run cannot be mistaken for a good one.

1. **Agents never write state.** Only the kernel appends to `events.jsonl` and regenerates `job.json`.
2. **Events are the truth.** `job.json` is a pure fold; if they disagree, the fold wins and `doctor`
   repairs the snapshot.
3. **Lease + fencing.** Every state write carries a monotonic fencing token. A late write from a
   crashed agent holds a stale token and is rejected — a zombie writer cannot corrupt state.
4. **Atomic writes.** Temp file → `fsync` → `os.replace` for every snapshot, cross-platform.
5. **Legal transitions only.** The state machine rejects moves outside the table.
6. **Schema validation before disk.** Every event, snapshot, project, manifest, authorization, and
   price table is validated against Draft 2020-12 before it is persisted. An invalid document never
   reaches the filesystem.
7. **Derived state is disposable.** `factory reindex` rebuilds `state/index.json` from the logs.
8. **Checks are the gate.** The kernel runs the commands. A green result comes from an exit code, not
   from a sentence in a chat transcript.
9. **Guards are the gate too.** A guard violation fails the attempt even when every check passed.
10. **Approval binds to content.** Approving a SHA that no longer describes the result is refused.
11. **Crash is never success.** An attempt interrupted mid-flight is recorded `interrupted` and retried
    without consuming a round.
12. **No progress is detected, not retried forever.** Repeated identical failure fingerprints or an
    empty diff stall the job.
13. **Work is isolated.** Each job gets its own worktree and branch; merging is serialized; a conflict
    blocks instead of corrupting.
14. **Every claim is traceable.** Since P2.1 every commit records the AI tool and model that produced it,
    and `factory provenance verify` (also run by CI) proves it for the whole history. Pre-convention
    commits are grandfathered, not rewritten.

---

## 🛡️ Anti-cheating guards (P2.1)

This is the part of the system that exists because the cheapest way to make a build "pass" is to
remove the evidence that it did not. Guards are **pure kernel functions over the attempt diff** — no
subprocess, no model, no network, no opinion.

| Guard | What it catches | How |
|-------|-----------------|-----|
| `no_test_deletion` | Deleting a test file to turn red green | Test-shaped paths (`tests/`, `__tests__/`, `test_*`, `*.spec.*`, …) are recognized across languages; deletion needs an explicit, exact-path authorization. *Deleting only — skipping or weakening a test is a documented follow-up* |
| `no_lockfile_surprise` | Dependency drift: a manifest changed while its lockfile did not (or vice versa) | Known manifest/lockfile pairs must move together; deletions are flagged |
| `no_secret_in_diff` | Credentials pasted into code | Added lines only, matched against AWS keys, `ghp_` tokens, PEM private-key blocks, and credential assignments; base64 blobs and 64-hex digests are treated as benign by design |

Three design choices are worth calling out, because they are what keep this honest rather than
theatrical:

- **Authorization is structural, not prose.** A guard stays silent only for a path named in the job's
  kernel-owned `authorizations.json` — exact paths, schema-validated, wildcards never match. The
  kernel cannot be persuaded by an agent writing "I deleted tests because the plan said to" into
  `plan.md`.
- **The diff is ground truth.** Guards compare the attempt against the SHA recorded at attempt start,
  including untracked files. Line content is read only inside diff hunks; binary files are flagged via
  `numstat` and never decoded.
- **Failures are events, not silences.** An unknown guard id or a malformed `authorizations.json`
  becomes a recorded `guard_config` violation that fails the attempt. A safeguard can never be
  skipped quietly by a typo — the same fail-hard policy as a missing check.

Guard results are also fed into the attempt fingerprint, so an agent that tries the same trick twice
stalls instead of burning its rounds. The dashboard renders a plain-language verdict
("⚠ Guard flagged deleted tests in `tests/test_app.py`"), and `factory doctor` verifies that every
guard id declared in `kernel/stages/*.yaml` actually exists in the registry.

Not yet implemented: `no_check_tampering` and `scope_guard` (planned in
[P2 workstream 2](docs/plans/P2-trust-layer.md)).

---

## 💰 Budgets and metering (P2.2)

Cost-awareness is a kernel principle: *every attempt reports usage; budgets are enforced at stage
boundaries*. Enforcement is deliberately split so the arithmetic can be trusted independently of the
plumbing.

**Shipped:** `budgets.py` is a pure module — no file I/O, no subprocess, no model. It prices an
attempt's reported usage against the `factory.json` price table, resolves each stage's soft and hard
limits, and returns a verdict:

- Any usage key shaped `X_tokens` is priced at `X_per_1m` for that usage's model tier, so the
  canonical metrics (`input_tokens`, `output_tokens`, `cached_tokens`) need no special case.
- An unpriced metric **raises** rather than defaulting to zero — unpriced usage must never silently
  cost nothing, or "no job exceeds its hard budget" would be unenforceable.
- `usd` is the hard limit; `soft_usd` is the soft limit, defaulting deterministically to `0.8 × usd`.
  Boundaries are inclusive, and a `soft ≥ hard` configuration is a configuration error.
- Negative counts clamp to zero; non-numeric counts raise, because malformed usage is rejected, not
  estimated.

**In flight:** the engine write path (`budget.json` per attempt, `budget.soft_exceeded` /
`budget.hard_exceeded` events, a cached hard breach refused on resume rather than re-spent) and the
`doctor` budget-configuration checks. These were specified by committed tests that are **red on
purpose** while the slices land one at a time — see
[Honest gaps](#-project-status-and-honest-gaps).

---

## 🧾 Provenance (dogfooding)

A project whose thesis is *auditable claims* should itself be auditable. So every commit records the
AI tool and model that produced it, and the repository can prove it.

```
feat(budgets): implement deterministic cost calculation and limit checking

- calculate_cost: every X_tokens key priced at X_per_1m of the model tier
- stage_limits: usd is the hard limit; soft defaults to 0.8 x usd
- check_budget: inclusive boundaries, ok results carry the decisive bound

AI-Tool: opencode
AI-Model: glm-5.3-flash-free
AI-Provider: opencode
```

```bash
git config commit.template .gitmessage    # pre-filled trailers
git config core.hooksPath .githooks       # optional: local enforcement

./factory provenance verify                        # audit the history
./factory provenance verify --range HEAD~3..HEAD   # just recent commits
./factory provenance verify --json                 # machine-readable report
```

`factory provenance verify` is the same check CI runs (`.github/workflows/`). Pre-convention history
is grandfathered through `.provenance-allow` rather than rewritten. P2.1 is the first phase whose
provenance is **machine-verified** by git rather than attested from memory — see
[AI provenance](docs/context/AI-PROVENANCE.md).

---

## 🧠 Design decisions captured

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Language of the reference kernel | Python 3 | Readable, fast to iterate, strong stdlib for files |
| ID generation | ULID | Time-sortable, 26 chars, no external dependency |
| Event chaining | `prev` = hash of the previous event | Detects tampering, gaps, and reordering end to end |
| Locking | Exclusive file + fencing token | Works without advisory `flock`; portable across platforms |
| Lock mutual exclusion | Exclusive-create guard file (`O_CREAT\|O_EXCL`) | Portable create-exclusive semantics (spec §5.2); a stale guard is stolen |
| Stage definitions | YAML | Human-readable, composable into profiles |
| Adapters | Folder + `manifest.json` | Tool-agnostic core; a new tool is a new folder |
| Atomic writes | temp → `fsync` → `os.replace` | Cross-platform (POSIX fsyncs the directory; Windows cannot, so it is skipped) |
| Schema validation | `jsonschema`, on every kernel write | An invalid event or snapshot never reaches disk |
| Dashboard delivery | stdlib `http.server` + SSE, with a static export | No runtime dependencies; the dashboard stays a thin client of the kernel |
| Repository source | Factory-managed repo per project (`projects/<name>/repo`) | Self-contained and hermetic; `project import` can link a real one later (P2) |
| Checkpoint identity | Content-hash `sha` (binds approval) **and** git `commit` (restores the tree) | Approval binds to the produced bytes; resume restores the exact tree |
| Merge integration | Serialized `--no-ff` merge on approval; conflict → `blocked` | One job at a time in Solo (§6); a conflict never leaves the repo mid-merge |
| Guard authorization | Per-job `authorizations.json`, exact paths only | Structural, kernel-validated authorization instead of parsing plan prose |
| Guard input | The diff from the attempt-base SHA, including untracked files | Ground truth, not agent self-report |
| Budget pricing | Per-tier rates in `factory.json`; unpriced usage raises | A metered cost that silently costs $0 makes budgets unenforceable |
| Visual theme semantics | Probed at runtime, never hardcoded | Headless Chromium builds disagree about `preferredColorScheme`; an inconclusive probe skips with a note instead of guessing |
| Commit provenance | Trailers + a deterministic verifier + CI gate | The project argues for verified claims; it should verify its own |

---

## 🗺️ Roadmap

One engine, three presets (Solo / Team / Enterprise). Phases are ordered so each depends only on what
is already solid.

| Phase | Deliver | Status |
|-------|---------|--------|
| **P0 Kernel core** | `events.jsonl` + `job.json`, atomic writes, leases and fencing, schema validation, check runner, `doctor`, `reindex` | ✅ Implemented |
| **P1 Solo slice** | `lite` execution, adapter runtime + build loop, checkpoints + SHA-bound approval, conformance suite, dashboard, git worktrees + merge queue + Undo, live `cli-agent` backend, question budget, real visual capture | ✅ Complete, proven end to end |
| **P2 Trust layer** | Budgets and metering, guards, sandbox hardening, risk-scored gates, import with baseline | 🚧 In progress — guards landed; budget math landed, engine/doctor wiring in flight |
| **P3 Learning** | Eval harness, skill packages and promotion, lessons ledger, repo map and memory | ⬜ Planned |
| **P4 Team** | More adapters via conformance, epics and dependencies, visual baselines, named users | ⬜ Planned |
| **P5 Enterprise** | Control plane, RBAC, hash-chained audit, brand design systems, compliance export | ⬜ Planned |

**P1 delivered, concretely:** the stage-graph engine and build loop with no-progress detection; the
adapter runtime with `echo` and the live `cli-agent` backend; the adapter conformance suite and
`factory adapter test`; content-addressed checkpoints bound to git commits; SHA-bound approval;
interrupted-attempt recovery with input-hash idempotency; the Solo dashboard (live SSE + static
export) with Approve / Change this… / Undo / Explain this; factory-managed worktrees, checkpoint
commits, merge queue, and Undo; the Solo question budget (≤ 3 blocking questions, durable
`job.question_asked` events, one-click answers); and real visual capture bound to the checkpoint SHA.

---

## 🛠️ Development

```bash
pip install -e ".[dev]"            # or: pip install pytest pyyaml jsonschema flake8
python -m pytest                   # whole suite
python -m pytest tests/test_engine.py -k guard
python -m flake8 kernel/src tests  # lint (config in .flake8; CI runs exactly this)
```

The suite is **hermetic by construction**: every test builds a throwaway factory tree in a temp
directory from the *real* `kernel/schemas`, `kernel/presets`, and `kernel/stages`, so schema and
profile regressions surface immediately. Git-backed tests (worktrees, merge, undo, guards over a
real diff) create real repositories inside that temp tree and skip themselves when no `git` executable
is available.

Coverage by area: atomic writes · ULIDs · hashing · leases and fencing · state and fold · transitions
· profiles · schemas · kernel lifecycle · doctor · engine orchestration · checks · context manifests
· adapters · the live `cli-agent` backend · checkpoints and SHA-bound approval · the conformance
suite · the dashboard · git worktrees, merge and undo · the Solo question budget · visual capture and
visual diffs · **guards (40 cases)** · **budgets (24 cases)** · provenance.

### Editing rules that bite

1. All disk writes go through `atomic.py` — never `open(..., "w")` on a state file.
2. Only `state.py` appends events. A new event type means a schema edit **and** an emit from
   `JobState`, not from a caller.
3. Every new file type gets a JSON Schema and is validated on write.
4. Transitions are declared, not implied. Illegal moves must raise.
5. `guards.py` and `budgets.py` are pure: no file I/O, no subprocess, no network, no clock. Verdicts
   and events belong to the engine.
6. Unknown guard ids and unpriced usage fail hard. A safeguard that degrades into a no-op is worse
   than one that is absent, because it looks present.
7. The kernel stays deterministic: no network, no hidden clocks, no randomness outside ULIDs.
8. Every commit ends with provenance trailers. `factory provenance verify` and CI enforce it.

Full contributor guidance: [Contributing](docs/development/CONTRIBUTING.md) ·
[Coding standards](docs/development/CODING-STANDARDS.md) · [Testing](docs/development/TESTING.md) ·
[Adapters](docs/development/ADAPTERS.md) · [Schema versioning](docs/development/SCHEMA-VERSIONING.md) ·
[Releasing](docs/development/RELEASING.md).

---

## 📚 Documentation

| Document | What it answers |
|----------|-----------------|
| [docs/](docs/README.md) | Index of the entire documentation set |
| [Specification v3.0](docs/specification/Enterprise%20AI%20Software%20Factory%20%E2%80%94%20Specification%20v3.0.md) | What the system is *supposed* to do — the canonical source |
| [PRD](docs/product/PRD.md) | Who it is for, what each mode promises, success criteria |
| [Architecture](docs/architecture/ARCHITECTURE.md) | How the implementation is put together, module by module |
| [Roadmap](docs/plans/ROADMAP.md) | Phases P0–P5, their status, and per-phase plans |
| [Runbook](docs/operations/RUNBOOK.md) | `doctor`, recovery, stuck jobs, leases and worktrees |
| [Troubleshooting](docs/operations/TROUBLESHOOTING.md) | Symptom → likely cause → fix |
| [Security](docs/operations/SECURITY.md) | Safety floor, threat model, secret handling |
| [Testing](docs/development/TESTING.md) | Hermetic strategy, coverage map, adding tests |
| [Adapters](docs/development/ADAPTERS.md) | Writing an adapter: manifest, run contract, conformance, visual evidence |
| [Context pack](docs/context/PROJECT-CONTEXT.md) | A portable briefing for another AI tool or a new teammate |

---

## 📊 Project status and honest gaps

**Verified 2026-10-17 at `9948840`** (branch `master`, 19 commits, 2 build days):

| Metric | Value |
|--------|-------|
| Test suite | **312 collected — 305 passed, 2 skipped, 5 failed** |
| The 5 failures | Intentional TDD-red for P2.2, which was sliced in four steps. At `9948840` they are: 2 engine cases (budget verdicts must fail the attempt / stop the retry loop) and 3 `doctor` cases (`TestDoctorBudgetConfig`) |
| Lint | `flake8 kernel/src tests` clean |
| Kernel | 20 modules · 7 schemas · 2 stage profiles · 3 presets · 3 guard ids · 24 test modules |

> **Red is a technique here, not a regression.** P2.2 committed its failing tests *before* the
> implementation, so the tests specify the slice instead of describing it afterwards. The slices are
> landing one at a time — as the engine wiring lands, its two cases turn green and the remaining red
> tests are the ones for the next step. Always read the failing test names before assuming something
> broke; see [Testing §4](docs/development/TESTING.md#4-tdd-red-slices-are-a-technique-not-an-accident).

Known gaps, stated plainly:

- **P2.2 budget enforcement is incomplete.** The cost arithmetic is implemented and tested; the runtime
  that acts on a verdict (engine write path, then `doctor` checks) is being wired in steps. That is
  exactly why those tests are red.
- **No sandbox enforcement yet.** `factory.json` declares a sandbox block, but there is no
  process or container isolation. Treat agents as running with your privileges.
- **No risk scoring.** Stages declare `gate: risk_scored`, but the score computation does not exist.
- **3 of 5 guards.** `no_check_tampering` and `scope_guard` are not implemented.
- **5 of 8 role contracts.** `reviewer`, `designer`, `architect`, and `curator` are not written.
- **No `LICENSE` file.** The repository has not declared a license yet — add one before distributing
  it, and note that the specification and all documentation are part of the same tree.
- **No upstream remote.** This is a local repository on branch `master`; CI workflows exist but have
  no remote to run against yet.

---

## 🤝 Contributing and security

Contributions are welcome, and the bar is high in one specific place: **anything that touches state,
leases, transitions, or schema validation on write.** Those are the components whose bugs corrupt
history, so weakening them requires changing the specification first.

```bash
git config commit.template .gitmessage   # provenance trailers, pre-filled
git config core.hooksPath .githooks      # optional: enforce them locally
```

- Process, branching, review standards: [docs/development/CONTRIBUTING.md](docs/development/CONTRIBUTING.md)
- Security policy: [SECURITY.md](SECURITY.md) → [docs/operations/SECURITY.md](docs/operations/SECURITY.md).
  **Do not open a public issue for a vulnerability.**
- Changes are logged in [CHANGELOG.md](CHANGELOG.md) under [Keep a Changelog](https://keepachangelog.com/).

---

**Files are the protocol. Events are the truth. A small kernel enforces. Agents only propose.**

*Enterprise AI Software Factory — specification v3.0 · kernel package `factory-kernel` 0.4.0*
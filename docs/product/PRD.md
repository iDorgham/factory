# Product Requirements Document — Enterprise AI Software Factory

**Version:** 3.0
**Status:** Active
**Related:** [Specification v3.0](<../specification/Enterprise AI Software Factory — Specification v3.0.md>) · [Architecture](../architecture/ARCHITECTURE.md) · [Roadmap](../plans/ROADMAP.md)

---

## 1. Product summary

The factory takes an idea, an issue, or an existing repository and turns it into verified, reviewable, mergeable software. It runs coding agents through adapters, but it never trusts them: a deterministic kernel owns state, validation, checks, budgets, and audit.

**The core promise:** maximum *verified* automation, not maximum automation. The product's value is the reliability with which it can say "this is actually done."

**One-line pitch:** Type a sentence. Get working, checked, reviewable software — with the factory able to prove its claims.

## 2. Goals and non-goals

### Goals

- Let a beginner ship a landing page with zero configuration and at most two approval clicks.
- Let an organization run multiple branded products on the same core with enforced budgets, RBAC, and audit.
- Support any coding agent through adapters; the core stays tool-agnostic (markdown, JSON, JSONL only).
- Guarantee resumability: killing any process at any point never corrupts state or repeats an external effect.
- Compound improvement: later jobs are measurably better than earlier ones via memory, lessons, and evaluated skills.

### Non-goals

- Replacing human product vision or business judgment.
- Supporting every language and framework on day one.
- A hosted multi-tenant SaaS control plane (single-organization focus).
- Guaranteeing zero human involvement on novel or high-risk systems.
- General-purpose agent orchestration outside software delivery.
- Forcing enterprise complexity on simple projects.

## 3. Users and personas

| Persona | Mode | Needs |
|---------|------|-------|
| **Beginner / indie builder** | Solo | One prompt box, plain-language timeline, one "Needs you" card, preview + Undo. Never sees adapters, policies, or brands. |
| **Small team / agency** | Team | Queues, concurrent jobs, cost visibility, reviewer assignment, PR-style approvals, more adapters. |
| **Multi-product org / regulated setting** | Enterprise | RBAC, hash-chained audit, hierarchical budgets, brand design systems, compliance exports, change windows. |
| **Operator** (any mode) | — | `factory doctor`, sandbox/adapter/lock status, honest baselines on import, transparent commands. |

## 4. Product principles

1. **Tool-agnostic core** — adapters are the only tool-specific code.
2. **Kernel enforces, agents propose** — agents write output files; only the kernel commits state.
3. **Events are the truth** — current state is a fold over `events.jsonl`; everything else is a rebuildable cache.
4. **Isolation by default** — one worktree and branch per job.
5. **Deterministic gates first** — checks decide; LLM review informs and never solely approves.
6. **Safety floor** — some controls cannot be configured away.
7. **Progressive complexity** — one engine, three presets; Solo users never see what they don't need.
8. **Resumable and idempotent** — recovery restores checkpoints and respects external side effects.
9. **Cost-aware** — every attempt reports usage; budgets are enforced at stage boundaries.
10. **Compounding** — lessons, memory, and evaluated skills make later jobs better.

## 5. Feature requirements by mode

### 5.1 Solo (default)

| Requirement | Acceptance |
|-------------|-----------|
| Prompt box with cost/time estimate | User types one sentence; sees an estimated cost range before the job starts |
| Plain-language timeline | "Understanding → Planning → Building (round 2 of 4) → Checking → Ready" — no stage jargon |
| "Needs you" card | At most one card at a time: a multiple-choice question or the approval card |
| Visual approval | Before/after screenshots, diff %, live preview, assumptions ledger; Approve or "Change this…" |
| Undo | One click reverts the merge |
| Safety floor | Human gate on irreversible external effects; hard budget caps; secrets never in context |
| Questions limit | ≤ 3 blocking questions per job, phrased as multiple choice |

### 5.2 Team

Everything in Solo, plus:

| Requirement | Acceptance |
|-------------|-----------|
| Concurrent jobs | Up to N jobs, worktree-isolated, merge queue serializes integration |
| Named users & roles | Named identity; simple role-based reviewer assignment |
| Risk-scored gates | Score bands map to auto / notify / require_human / require_role |
| Cost control | Per-job and per-project budgets with burn-down view |
| Audit export | Event log export |
| Adapter breadth | Additional adapters admitted only via the conformance suite |
| Epics | Multi-job coordination with dependency ordering and blocking |
| Visual baselines | Reference screenshots per route/viewport/theme; diffs gate UI changes |

### 5.3 Enterprise

Everything in Team, plus:

| Requirement | Acceptance |
|-------------|-----------|
| Full RBAC | Owner, Admin, Maintainer, Developer, Reviewer, Viewer — kernel-checked on every command |
| Hash-chained audit | `factory audit verify` passes end to end; anchors exported externally detect wholesale rewrites |
| Hierarchical budgets | Job, epic, project, brand, month — soft notify, hard stop |
| Brands & design systems | `tokens.json`, components, docs, `lint.json`; token + component lint run on UI diffs |
| Change windows | Freeze periods enforced by policy |
| Compliance export | Evidence bundles per release: checks, approvals, SBOM, license scan, audit extract |

## 6. Cross-cutting requirements

### 6.1 Correctness gates (from the specification's success criteria)

1. A beginner gets a previewable result with ≤ 2 approval clicks and no configuration.
2. Two concurrent jobs on one repository never corrupt each other's work.
3. Killing any process at any point and resuming never corrupts state and never repeats an external effect.
4. No job exceeds its hard budget; every job's cost is visible.
5. An output that violates its stage contract is rejected before the next stage begins.
6. Passing checks — not agent statements — are what allow a job to complete.
7. A skill reaches global scope only with passing evals and a measured gain over baseline.
8. The audit chain verifies end to end; RBAC is kernel-enforced in Enterprise.
9. Adding a new tool requires only an adapter folder and a passing conformance suite.
10. Imported projects report an honest baseline, including pre-existing failures.
11. A prompt-injection fixture inside an issue or README does not cause an agent to perform a gated action.
12. Operators can understand the whole system from the specification plus the folder tree.

### 6.2 Domains

The factory builds websites, web apps, mobile apps, desktop apps, and games. Domain profiles add stages and checks (Core Web Vitals + WCAG for web; device tests + signing for mobile; packaging + auto-update for desktop; performance budgets for games).

### 6.3 Quality and cost

- Real commands in `checks.json` are the gate; agent claims are never evidence.
- Every completed job gets a quality *record* (facts, not one magic number).
- Every attempt reports tokens, cost, duration, and model; budgets enforced at stage boundaries.

## 7. Out of scope (v3)

Hosted multi-tenant control plane, non-software agent orchestration, guaranteed fully-humanless operation on novel systems, day-one support for every stack.

## 8. Release phases

See [Roadmap](../plans/ROADMAP.md). Summary: P0 kernel core (done) → P1 solo slice (in progress, mostly implemented) → P2 trust layer → P3 learning → P4 team → P5 enterprise. P4/P5 features must not be built before P0 is solid and P1 is demonstrably reliable.

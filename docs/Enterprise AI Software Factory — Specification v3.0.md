# Enterprise AI Software Factory — Specification v3.0

**Version:** 3.0\
**Status:** Canonical specification (supersedes 2.1)\
**Audience:** implementers of the kernel, adapters, dashboard, and role/skill libraries

> **Files are the protocol. Events are the truth. A small kernel enforces. Agents only propose.**

---

## 0. What changed from 2.1

| Area | 2.1 | 3.0 |
| --- | --- | --- |
| State | `board/*.json` and `meta.json` both hold job state | One source of truth per job: `job.json` + append-only `events.jsonl`. Everything else is derived and rebuildable |
| Enforcement | Agents were trusted to follow contracts | A deterministic **kernel** owns locks, transitions, validation, checks, budgets, and audit. Agents never mutate state |
| Concurrency | Unspecified | One git worktree and branch per job, lease locks with fencing tokens, a merge queue |
| Quality gate | LLM reviewers | Deterministic checks are the gate. LLM review is advisory |
| Pipeline | Fixed 16 stages | Composable **stage graph** per domain profile; stages declare requires, produces, checks, guards, effects |
| Agents | About 30 named agents | 8 roles; review types are lenses, not agents |
| Context | "Context Builder" named only | Kernel-built `context.manifest.json` with token budgets, summaries, and a repo map |
| Skills | Promote after one reuse | Skills are versioned packages with evals; promotion requires a measured improvement |
| Gates | Binary on/off | Risk-scored gates over a non-disableable safety floor |
| Security | Secrets only | Threat model: prompt injection, sandboxing, secret isolation, test tampering guards |
| Dashboard | Static file polling state files | `factory serve` local server; static export as fallback |
| Enterprise | RBAC and audit as file conventions | Kernel-enforced RBAC, hash-chained audit, enforced budgets |
| Modes | Three different feature sets | Three **policy presets** over one engine |

---

## 1. Vision and scope

The factory takes an idea, an issue, or an existing repository and turns it into verified, reviewable, mergeable software. It serves a beginner shipping a landing page and an organization running multiple branded products on the same core.

It can build websites, web apps, mobile apps, desktop apps, and games, using any coding agent through adapters. It manages projects, jobs, epics, skills, memory, design systems, and approvals, and it records everything.

The goal is **maximum verified automation**, not maximum automation. The factory's value is the reliability with which it can say "this is actually done", not the number of agents it runs.

### 1.1 Non-goals

- Replacing human product vision or business judgment.
- Supporting every language and framework on day one.
- A hosted multi-tenant SaaS control plane (single-organization focus).
- Guaranteeing zero human involvement on novel or high-risk systems.
- General-purpose agent orchestration outside software delivery.
- Forcing enterprise complexity on simple projects.

---

## 2. Principles

1. **Tool-agnostic core.** All state, contracts, decisions, and history are markdown, JSON, and JSONL. Adapters are the only tool-specific code.
2. **Kernel enforces, agents propose.** Agents write output files. Only the kernel validates them and commits state transitions.
3. **Events are the truth.** Current state is a fold over the event log. Indexes, boards, and dashboards are caches.
4. **Isolation by default.** Every job gets its own worktree and branch.
5. **Deterministic gates first.** Build, lint, type, test, accessibility, and visual-diff results decide pass or fail. LLM review informs; it never solely approves.
6. **Safety floor.** Some controls cannot be configured away (section 15).
7. **Progressive complexity.** One engine, three presets. Solo users never see what they don't need.
8. **Resumable and idempotent.** Recovery restores a git checkpoint and respects external side effects.
9. **Cost-aware.** Every attempt reports usage. Budgets are enforced at stage boundaries.
10. **Compounding.** Lessons, memory, and evaluated skills make later jobs better than earlier ones.

---

## 3. Operating modes (policy presets)

Mode is a named policy preset stored in `project.json` (`"mode": "solo"`). All modes run the same kernel and the same job engine. A mode sets defaults for gates, budgets, visibility, and which dashboard panels are shown. Upgrading a project changes policy, never data format.

|  | **Solo** | **Team** | **Enterprise** |
| --- | --- | --- | --- |
| Target | Beginners, indie builders | Small teams, agencies | Multi-product orgs, regulated settings |
| Stage profile | `lite` (5 steps) | `standard` | `standard` + compliance stages |
| Concurrency | 1 job at a time (queued) | Up to N, worktree-isolated | Configurable per project and brand |
| Gates | Visual approval on UI changes; floor gates | Risk-scored gates; reviewer assignment | Risk-scored + required approvers + change windows |
| Budgets | Soft cap shown, hard cap default per job | Per job and per project | Per job, project, brand, and month |
| Identity and RBAC | Single local user | Named users, simple roles | Full RBAC, SSO via control plane |
| Audit | Event log | Event log + export | Hash-chained audit, retention, compliance export |
| Design system | Off | Optional | Brand-level, lint-enforced |
| Dashboard | 3-element view | Queues, cost, PRs | Policy, audit, budgets, brands |

Solo is the default. The system must never require a user to understand brands, adapters, or policies to complete a Solo job.

---

## 4. Architecture

```
            ┌───────────────────────────────────────────┐
            │   Dashboard / CLI / Command palette        │
            └──────────────┬────────────────────────────┘
                           │ commands (validated)
            ┌──────────────▼────────────────────────────┐
            │                KERNEL                      │
            │  Scheduler · Locks · State machine ·       │
            │  Schema validation · Check runner ·        │
            │  Policy engine · Budget meter · Audit      │
            └───────┬──────────────────────┬────────────┘
                    │ run requests         │ reads/writes
            ┌───────▼───────┐      ┌───────▼─────────────┐
            │   Adapters    │      │  Files (the truth)   │
            │ (per tool)    │      │  job.json, events,   │
            └───────┬───────┘      │  worktrees, skills,  │
                    │              │  memory, audit       │
            ┌───────▼───────┐      └──────────────────────┘
            │ Coding agents │
            │ in a sandbox  │
            └───────────────┘
```

### 4.1 The kernel

The kernel is a small deterministic program (a CLI in Solo; a CLI plus a local daemon from Team up). It is not an LLM. Its responsibilities:

- **Scheduling:** picks runnable jobs and stages, respecting concurrency limits, dependencies, and budgets.
- **Locking:** per-job lease with heartbeat and fencing token (section 5.2); per-repo merge queue.
- **State machine:** the only writer of `events.jsonl` and `job.json`.
- **Validation:** checks every agent output against its stage contract and JSON schema before accepting it.
- **Check execution:** runs the project's real build, lint, type, test, accessibility, and visual commands in the sandbox, and records raw results.
- **Policy:** evaluates gates, risk scores, budgets, and RBAC before any transition.
- **Audit:** appends to the audit chain.

The kernel is implementation-language-agnostic. Its contract is the file formats and CLI in this document. A reference implementation is recommended but not required, and any conformant kernel can operate on the same tree.

### 4.2 Layer rules

- Agents read only their context manifest and write only into their attempt directory and the job worktree.
- Adapters translate; they do not decide. They cannot change policy, budgets, or state.
- The dashboard is a client. Every action is a command to the kernel, never a direct file edit.
- Derived files (`state/index.json`, board views) can be deleted and rebuilt by `factory reindex`.

---

## 5. State model

### 5.1 File layout

```
factory/
├── factory.json                # global config, default policy preset
├── kernel/
│   ├── schemas/                # JSON Schemas for every file type
│   └── presets/                # solo.json, team.json, enterprise.json
├── state/                      # DERIVED, rebuildable
│   └── index.json
├── projects/<project>/
│   ├── project.json            # mode, domain, stage profile, policy overrides
│   ├── checks.json             # build/lint/type/test/a11y/visual commands
│   ├── memory/
│   │   ├── decisions.md        # architecture decision records
│   │   ├── conventions.md      # code and design conventions
│   │   ├── repo-map.json       # symbols, entry points, ownership
│   │   └── lessons.jsonl       # learned from attempts
│   ├── epics/<epic-id>/epic.json
│   ├── issues/
│   └── jobs/<job-id>/
│       ├── job.json            # current snapshot (derived from events)
│       ├── events.jsonl        # SOURCE OF TRUTH, append-only
│       ├── brief.md            # the request, normalized
│       ├── assumptions.md      # ledger of assumed answers
│       ├── questions.md        # open questions to the human
│       ├── stages/<nn>-<stage>/attempt-<k>/
│       │   ├── context.manifest.json
│       │   ├── outputs/        # contract files
│       │   ├── handoff.md      # short summary for the next stage
│       │   ├── checks.json     # raw check results
│       │   └── usage.json      # tokens, cost, duration, model
│       └── artifacts/          # screenshots, video, visual diffs, logs
├── baselines/<project>/        # visual and behavioral regression baselines
├── brands/<brand>/             # Enterprise
│   ├── brand.json
│   └── design-system/{tokens.json, components/, docs.md, lint.json}
├── skills/<name>/              # versioned skill packages (section 12)
│   ├── SKILL.md
│   ├── evals/
│   └── CHANGELOG.md
├── roles/                      # 8 markdown role definitions
├── adapters/<tool>/{manifest.json, ...}
├── audit/audit.chain           # hash-chained (Team+: enabled, Enterprise: required)
└── .work/<job-id>/             # git worktrees (outside version control)
```

### 5.2 Write rules

- All writes are atomic: write to a temp file in the same directory, `fsync`, then rename.
- `events.jsonl` is append-only. One JSON object per line. Each event has: `id` (ULID), `ts` (ISO-8601 UTC), `job`, `type`, `actor`, `fence`, `data`, and `prev` (hash of the previous event in that job).
- `job.json` is a snapshot the kernel regenerates from events after every transition. If `job.json` and the event fold disagree, the fold wins, and `factory doctor` repairs the snapshot.
- **Lease:** a job lock file holds `{owner, token, expires}`. The owner renews the lease with a heartbeat. The kernel increments a monotonic **fencing token** each time the lease is granted. Every state write must carry the current token. A late write from a crashed or zombie agent carries a stale token and is rejected.
- **Cross-platform:** the lock uses create-exclusive file semantics and does not rely on advisory `flock` alone. Network filesystems are unsupported for concurrent mode, and `factory doctor` warns.

### 5.3 Scalability

Files plus a single-host kernel comfortably handle hundreds of active jobs per project. Beyond roughly one host, or beyond a few thousand events per second, the file layer is replaced by a database-backed store behind the same kernel interface. The file format remains the **export and interchange format**, so tool-agnosticism is preserved. This boundary is explicit: files are the protocol, and they are not promised to be the only storage engine at scale.

---

## 6. Isolation and concurrency

- **Worktree per job.** Creating a job creates `.work/<job-id>/` as a git worktree on branch `factory/<job-id>` from the project's base commit.
- **Merge queue.** Integration is serialized per repository. The Integrator role rebases the job branch on the latest base, re-runs required checks, and merges only if still green. A conflict returns the job to Build with the conflict as input.
- **Stale base detection.** If the base has moved significantly since planning, the kernel flags the plan as possibly stale and requires a re-plan if the changed files intersect the plan's file list.
- **Resource isolation.** Each job gets its own dev-server port range, temp directories, and (where configured) its own database or fixture namespace. `checks.json` declares required resources.
- **File-set conflict hints.** Planning declares an expected file set. The scheduler delays jobs whose declared sets overlap, as an optimization, not a correctness mechanism. The merge queue is the correctness mechanism.

---

## 7. Job state machine

| State | Meaning |
| --- | --- |
| `pending` | Created, queued |
| `running` | A stage attempt is executing |
| `awaiting_human` | Blocked on a gate or approval |
| `blocked` | Waiting on a blocking question, an epic dependency, or a resource |
| `stalled` | No-progress detected (section 9.2); needs strategy change or escalation |
| `paused` | Manually paused |
| `failed` | Retries and escalations exhausted; recoverable by an operator |
| `completed` | All required stages passed; merged if applicable |
| `cancelled` | Explicitly cancelled |
| `superseded` | Replaced by a newer job for the same intent |
| `archived` | Terminal history |

**Transitions**

- `pending → running | cancelled`
- `running → awaiting_human | blocked | stalled | paused | failed | completed | cancelled`
- `awaiting_human → running | cancelled | blocked`
- `blocked → running | cancelled`
- `stalled → running (new strategy) | awaiting_human | failed | cancelled`
- `paused → running | cancelled`
- `failed → running (operator retry from checkpoint) | cancelled`
- `completed | cancelled | superseded → archived`

Every transition is a kernel-written event carrying actor, reason, and fencing token. Illegal transitions are rejected.

### 7.1 Checkpoints and recovery

Every stage attempt ends with a **git checkpoint**: a commit (or recorded clean-tree SHA) saved in the attempt record. Recovery rules:

1. Resume restores the worktree to the last accepted checkpoint SHA. It does not merely rerun a stage on a possibly dirty tree.
2. A stage with `effects: local` is safe to rerun.
3. A stage with `effects: external` (deploy, migration, publish, message send) records an **effect journal** entry before and after each external call. Recovery reads the journal: completed effects are not repeated. Incomplete effects run the stage's declared `compensate` action or require a human gate.
4. Stage inputs are hashed. If an accepted attempt exists with the same input hash and its checkpoint is intact, the kernel may reuse it. This is the idempotency mechanism.
5. A crash mid-attempt leaves an attempt marked `interrupted`. It is never treated as success.

---

## 8. Stage graph, profiles, and contracts

### 8.1 Stage definition

Stages are defined once in `kernel/stages/` and composed into **profiles**. A stage declares:

```yaml
stage: build
role: builder
requires: [plan.md]
produces: [build.md, git:commits]
checks: [lint, typecheck, unit, build]
guards: [no_test_deletion, no_lockfile_surprise, no_secret_in_diff]
effects: local            # local | external
max_rounds: 4
budget: { tokens: 400000, usd: 3.00, minutes: 45 }
gate: risk_scored         # none | risk_scored | required
on_fail: loop             # loop | escalate | fail
```

The kernel validates the YAML, the produced files (against JSON Schemas or markdown frontmatter schemas), and the declared checks before marking a stage accepted.

### 8.2 Profiles

**`lite` (Solo default, 5 steps)**

1. **Understand:** normalize the request into `brief.md`; build or refresh context; surface blocking questions.
2. **Plan:** `plan.md` with ordered tasks, acceptance criteria, risks, and expected file set. Planning stays mandatory.
3. **Build loop:** build, run checks, review, fix, bounded by `max_rounds` (section 9).
4. **Verify:** full check suite, visual capture if UI changed, regression comparison.
5. **Approve and merge:** gate evaluation, human approval if triggered, merge queue.

**`standard` (Team and Enterprise)**

Define (research, spec, architecture as an adaptive step; each sub-artifact is produced only if the job's size or risk warrants it), Plan, Design (UI jobs only), Scaffold (new projects only), Build loop, Verify, Review (lenses), Polish, Package (if releasing), Approve, Merge/Deploy.

**Domain profiles** add stages and checks:

- **Web:** Core Web Vitals budget, accessibility (WCAG), SEO checks, deploy target.
- **Mobile:** platform builds, device or emulator tests, signing, store assets.
- **Desktop:** packaging, auto-update, signing, sandbox permissions.
- **Game:** performance budget, asset pipeline, input tests, platform builds.

A project selects `stage_profile` and `domain`. Individual stages can be marked `skip` with a reason, which is recorded in the event log and audited in Enterprise.

### 8.3 Artifact contracts

| File | Required content |
| --- | --- |
| `brief.md` | Goal, constraints, non-goals, source (human, issue, epic) |
| `plan.md` | Ordered tasks, each with acceptance criteria and risks; expected file set; required skills; rollback note |
| `build.md` | What changed, what was deferred, known gaps |
| `handoff.md` | At most 400 words: state, decisions, open items for the next stage |
| `reviews/<lens>.md` | Frontmatter: `verdict: pass\|changes`, `findings: [...]` each with severity, file, line, and evidence; `confidence` is optional and never gating |
| `decision.md` | Frontmatter `decision: approve\|request_changes\|escalate`, plus rationale and the evidence links used |

All timestamps are ISO-8601 UTC. Frontmatter is YAML and schema-validated. A review without evidence-linked findings is rejected as non-compliant.

---

## 9. The build loop

Building is iterative. The loop is a first-class kernel construct, not a convention.

### 9.1 Round structure

Each round is: **build → checks → review (advisory) → fix**. A round is one attempt of the `build` stage. The kernel runs the declared checks after every round and records raw results. The loop ends when all required checks pass and no blocking review findings remain, or when `max_rounds` or a budget is reached.

Each round receives, through its context manifest: the plan, the previous round's handoff, the failing check output (trimmed to the relevant failures), and unresolved review findings. It does not receive the full transcript of earlier rounds.

### 9.2 No-progress detection

The kernel computes a **failure fingerprint** for each round: the set of failing check IDs plus normalized error signatures. If the same fingerprint appears in two consecutive rounds, or the diff between rounds is empty, the job moves to `stalled`. The escalation ladder is:

1. Retry with a changed strategy (the Builder is told which approach failed).
2. Switch model tier or adapter, if the policy allows.
3. Reduce scope: split the plan task, and ask the Architect to re-plan the failing task.
4. Escalate to a human with a concise failure report.

Each rung is recorded as an event. A rung is skipped if the budget forbids it.

### 9.3 Guards (anti-cheating)

Guards are deterministic checks over the diff. They run after every round. Defaults:

- **no\_test\_deletion:** tests may not be deleted, skipped, or have assertions weakened without an explicit plan task that authorizes it.
- **no\_check\_tampering:** the check configuration, CI files, and lint rules are read-only to the Builder unless the plan authorizes a change.
- **no\_lockfile\_surprise:** dependency and lockfile changes must match the plan's declared dependency changes.
- **no\_secret\_in\_diff:** secret scanning on every diff.
- **scope\_guard:** changes outside the plan's expected file set are flagged. They are allowed but raise the risk score (section 14).

---

## 10. Roles, context, and communication

### 10.1 The eight roles

Roles are markdown definitions in `roles/`. Adapters translate them into each tool's native form. Review types are **lenses** applied by the Reviewer role, not separate agents.

| Role | Responsibility |
| --- | --- |
| **Definer** | Normalizes requests into briefs and specs; produces research and requirements when warranted; raises questions |
| **Architect** | Structure, boundaries, technology choices, decision records; re-planning when a task stalls |
| **Planner** | Ordered tasks, acceptance criteria, risks, expected file set, required skills (may be combined with Architect on small jobs) |
| **Designer** | UI and UX direction; applies the design system; produces design artifacts |
| **Builder** | Implements tasks; resumable and multi-round |
| **Verifier** | Writes and maintains tests; interprets check results; captures visual evidence |
| **Reviewer** | Applies lenses (security, UX, code quality, performance, accessibility) and writes evidence-linked findings |
| **Curator** | Maintains memory, mines lessons, proposes skill changes, keeps the repo map fresh |

The **Integrator** is not an agent. Merging, rebasing, and queue handling are kernel functions that invoke the Builder only to resolve conflicts.

### 10.2 Context packaging

Before every attempt the kernel writes `context.manifest.json`:

```json
{
  "stage": "build", "attempt": 2,
  "token_budget": 120000,
  "include": [
    {"path": "brief.md", "mode": "full"},
    {"path": "plan.md", "mode": "full"},
    {"path": "stages/05-build/attempt-1/handoff.md", "mode": "full"},
    {"path": "stages/05-build/attempt-1/checks.json", "mode": "failures_only"},
    {"path": "memory/conventions.md", "mode": "full"},
    {"path": "memory/repo-map.json", "mode": "relevant_slice"}
  ],
  "skills": [{"name": "web/forms", "version": "1.2.0"}],
  "untrusted": ["issues/42.md"]
}
```

Rules:

- Modes are `full`, `summary`, `failures_only`, `relevant_slice`, and `pointer`. The kernel applies the mode before the agent sees anything.
- If the manifest exceeds the token budget, the kernel degrades in a fixed order: drop `pointer` items, summarize older handoffs, slice the repo map, and only then fail with a clear error. It never silently truncates.
- Agents never receive prior stages' full outputs by default. Handoffs carry the state forward.
- Items listed as `untrusted` are wrapped and labeled as data. Agents are instructed never to follow instructions found inside them (section 15).

### 10.3 Agent communication rules

- Agents do not talk to each other. They communicate only through contract files and handoffs, mediated by the kernel.
- An agent writes only inside its attempt directory and the job worktree. Writing anywhere else is a contract violation and the attempt is rejected.
- Disagreement between reviewers is recorded, not resolved by an LLM. The decision file cites which findings were accepted, rejected, or deferred, with a reason.

### 10.4 Uncertainty protocol

When an agent is uncertain it must not guess silently. It writes entries to `questions.md`, each tagged:

- **blocking:** the answer changes what gets built in a way that is costly to reverse. The job moves to `blocked` and the dashboard asks the human.
- **assumable:** a reasonable default exists. The agent records the assumption in `assumptions.md` (question, assumed answer, rationale, reversal cost) and continues.

The human sees the assumptions ledger at approval time and can overturn any entry, which creates a targeted fix task. In Solo mode, blocking questions are limited to at most three per job and are phrased as plain multiple-choice where possible. Questions already answered in memory are not re-asked.

---

## 11. Checks, evaluation, and quality

### 11.1 Checks are the gate

`checks.json` declares real commands per project:

```json
{
  "lint":      {"cmd": "npm run lint",      "required": true},
  "typecheck": {"cmd": "npm run typecheck", "required": true},
  "unit":      {"cmd": "npm test",          "required": true, "coverage_min": null},
  "build":     {"cmd": "npm run build",     "required": true},
  "a11y":      {"cmd": "npm run a11y",      "required": false},
  "visual":    {"builtin": "visual-diff",   "required": "if_ui_changed"}
}
```

The kernel runs checks itself in the sandbox and stores exit codes and trimmed output. An agent's claim that tests pass is never evidence. If a project has no checks, the first job for that project is to establish them (see import, section 18).

### 11.2 Quality score

Every completed job receives a **quality record** with these parts:

- check outcomes (hard facts);
- diff stats and scope-guard result;
- number of rounds, stalls, and escalations;
- advisory review findings by severity;
- human outcome: approved as is, approved after changes, rejected;
- cost and duration.

The record is data, not a single magic number. A composite score may be shown in the dashboard, but gates use the underlying facts.

### 11.3 Evaluating the factory itself

The factory ships an **eval harness**: a set of fixture tasks (small repos plus a brief plus expected checks) that can be run against any combination of roles, skills, models, and adapters. It is used to:

- gate skill promotion (section 12);
- compare adapters and models for cost and success rate;
- detect regressions when roles or kernel prompts change.

Eval results are stored in `evals/results/` with the versions of everything involved, so runs are reproducible. Model and adapter versions are pinned per project and recorded in every `usage.json`.

---

## 12. Skills

A skill is a **package**, not a single file.

```
skills/<scope>/<name>/
├── SKILL.md        # when to use, steps, output contract, acceptance criteria
├── evals/          # fixture tasks with expected checks
├── CHANGELOG.md
└── skill.json      # version, scope, owner, provenance, dependencies, status
```

**Versioning.** Semantic versions. Jobs **pin** skill versions in their manifest at creation, so a skill change never alters a running job.

**Lifecycle**

1. **Proposed:** created by a human, or by the Curator when the Planner flags a missing capability or lessons show a repeated failure pattern.
2. **Project scope (0.x):** usable only in its project. Must ship at least two eval fixtures.
3. **Candidate:** the Curator proposes promotion. The kernel runs the eval harness with and without the skill.
4. **Promoted (global 1.0):** requires passing all fixtures, beating the no-skill baseline on at least a policy-defined share of fixtures with no regressions, and at least two independent successful uses. Team and Enterprise add human approval.
5. **Deprecated or rolled back:** a skill whose later usage correlates with failed checks or human rejections is flagged. The operator can pin an earlier version or deprecate it.

Project skills override global skills of the same name. Every skill records provenance (who or what created it, from which lessons) and cannot grant itself new permissions or tool access.

---

## 13. Memory and learning

Memory is plain files under `projects/<p>/memory/`, owned by the Curator and read through the manifest.

- **decisions.md:** architecture decision records. Written by the Architect and approved or edited by humans.
- **conventions.md:** code style, patterns, naming, and design rules learned or declared.
- **repo-map.json:** a compact map of modules, entry points, symbols, and ownership. It stores the commit SHA it was built from. The kernel marks it **stale** if the base moved and relevant files changed, and refreshes it before planning.
- **lessons.jsonl:** structured entries produced after each job: what failed, why, what fixed it, and whether a skill or convention should change. Entries carry job references and a confidence note.

Rules: memory never contains secrets. Humans can edit or delete any entry. A lesson influences behavior only through reviewed changes to conventions or skills, never by being silently injected as authority. Curator output goes through the same contract validation as any other role.

---

## 14. Human gates and policy

### 14.1 Risk-scored gates

Gates are evaluated by the kernel on a **risk score** computed from deterministic signals:

| Signal | Raises risk when |
| --- | --- |
| Diff size | Large relative to the plan |
| Sensitive paths | Auth, payments, permissions, migrations, infrastructure, CI |
| Dependencies | New or upgraded packages, especially with install scripts |
| Scope drift | Files outside the planned set |
| External effects | Deploys, publishes, outbound messages, data writes |
| History | Prior stalls, repeated check failures, reverted similar changes |
| Skill maturity | Unproven or recently changed skills in use |

The policy maps score bands to actions: `auto`, `notify`, `require_human`, or `require_role`. Presets define bands. Projects can tighten them. Loosening below the preset requires an Owner or Admin in Team and Enterprise, and is audited.

### 14.2 Configuration shape

```json
"gates": {
  "visual_approval": "if_ui_changed",
  "plan_approval": "if_risk_above:medium",
  "skill_promotion": "always_human",
  "architecture_change": "if_risk_above:low",
  "auto_merge": {
    "enabled": false,
    "requires": ["required_checks_pass", "no_blocking_findings", "risk_at_most:low", "visual_approved_if_ui"]
  }
}
```

`gates.enabled: false` no longer exists. Turning off a gate turns off that specific gate. The safety floor (section 15) always remains.

### 14.3 Visual approval

Visual approval is bound to a **commit SHA**. Any new push invalidates it. It is required only when the diff touches user-visible UI. The approval card shows:

- before and after screenshots at declared viewports, in light and dark themes;
- the visual-diff percentage and highlighted regions;
- the live preview link where one exists;
- the assumptions ledger and plan acceptance criteria, each with its check status;
- actions: **Approve**, **Change this…** (free text or region comment, which becomes a fix task), **Reject**.

Approver identity, SHA, and artifact hashes are recorded in the event log.

---

## 15. Safety floor and security

### 15.1 Safety floor (cannot be disabled by any configuration)

1. Production deploys, publishing, and other `effects: external` stages with irreversible results require a human gate.
2. Secrets are never placed in an agent's environment, context, or job files.
3. Destructive operations outside the job worktree (deleting directories, force-pushing protected branches, dropping databases) are blocked.
4. Hard budget caps stop execution at the next stage boundary or sooner if the adapter supports mid-run cut-off.
5. The audit event for every approval, policy override, and external effect is always written.
6. Agents cannot edit policy, budget, role, or kernel files.

### 15.2 Threat model

| Threat | Mitigation |
| --- | --- |
| **Prompt injection** via issues, READMEs, web pages, dependencies, or imported repos | Untrusted content is wrapped and labeled as data in the manifest; agents have no ambient authority to act on instructions inside it; sensitive actions need kernel-evaluated gates, not agent judgment |
| **Secret exfiltration** | No secrets in agent env; secret scanning on diffs and artifacts; network egress allowlist in the sandbox |
| **Malicious or typosquatted dependencies** | Dependency changes must match the plan; install scripts disabled by default in the sandbox; new packages raise risk score |
| **Test and check tampering** | Guards (section 9.3); the check configuration is read-only to agents |
| **Runaway cost** | Per-attempt, per-job, and per-period budgets enforced by the kernel |
| **Privilege escalation through skills** | Skills carry no permissions of their own; tool access is granted by stage and policy only |
| **Audit tampering** | Hash-chained audit (section 22); anchors can be exported externally |

### 15.3 Sandbox

Agents and checks run in a sandbox that provides: a filesystem limited to the job worktree and temp directories, a network allowlist, resource limits, and no inherited environment variables other than an explicit list. Solo mode uses the lightest sandbox the host supports (container if available, otherwise a restricted process with command allowlist) and states plainly which protections are active. The dashboard shows sandbox status.

### 15.4 Secrets

Secrets live in the host's secret store or environment, referenced by name in `checks.json` and adapter manifests. The kernel injects them only into whitelisted check or deploy commands, and scrubs known secret values from logs and artifacts before storing them.

---

## 16. Cost and token awareness

- **Metering:** adapters must report usage per run (input tokens, output tokens, cached tokens where applicable, tool calls, wall time, model). The kernel converts to cost using a price table in `factory.json`.
- **Estimation:** before a job starts, the kernel shows an estimated cost range from similar past jobs and the plan size. In Solo mode this is a single friendly line ("typically about $1–$3").
- **Budgets:** `budget` applies at attempt, stage, job, project, brand, and period. Soft limits notify. Hard limits stop the run at the next safe point.
- **Model routing:** policy may map stages to model tiers (for example, cheap models for context building and summaries, stronger models for architecture and fixes). Routing decisions are logged and evaluated through the eval harness.
- **Reports:** per-job cost breakdown by stage and round; per-project trends; cost per approved change.

---

## 17. Regression and visual testing

- **Behavioral baselines:** the Verifier maintains tests for key user flows. A job that changes behavior must update the relevant tests as part of its plan, and the change must be visible in the diff for review.
- **Visual baselines:** `baselines/<project>/` stores reference screenshots per route or component, viewport, and theme. The `visual` check captures current screenshots from the job's preview, compares them with a tolerance, and writes diff images into `artifacts/`.
- **Baseline updates:** a baseline changes only when a human approves the visual card. The new baseline is committed with the merge, keyed to the approving SHA.
- **Flake handling:** non-deterministic regions can be masked in config. A check that flips without code change is retried once, then reported as flaky in the quality record instead of silently passing.

---

## 18. Importing existing codebases

`factory project import <path-or-url>` runs a staged, verifying import:

1. **Clone or link** with full history. Detect the default branch and protected branches.
2. **Detect** language, framework, package manager, and domain.
3. **Establish a baseline:** install and run build, lint, type, and test commands. Record the outcomes as the **baseline status**, including pre-existing failures. The factory never treats pre-existing failures as its own regressions, and never claims a green project that is not green.
4. **Infer `checks.json`** from scripts and CI configuration, and ask for confirmation of anything ambiguous.
5. **Build memory:** `repo-map.json`, a first `conventions.md` from lint and format configs and observed patterns, and a draft `decisions.md` marked as inferred.
6. **Import issues and open PRs** if requested, as untrusted input.
7. **Report:** a short import report with detected stack, baseline status, risky areas (no tests, large untested modules), and suggested first jobs, such as "add a smoke test".

Design-system requirements apply only in Enterprise mode or when a brand is specified.

---

## 19. Epics and multi-job coordination

An **epic** groups jobs that serve one goal.

```json
{
  "epic": "checkout-redesign",
  "goal": "...",
  "jobs": [
    {"id": "j1", "title": "Design tokens for checkout", "depends_on": []},
    {"id": "j2", "title": "Cart page", "depends_on": ["j1"]},
    {"id": "j3", "title": "Payment form", "depends_on": ["j1"]}
  ],
  "integration_job": {"title": "End-to-end checkout flow", "depends_on": ["j2", "j3"]}
}
```

- The kernel schedules jobs by dependency order and concurrency limits; unmet dependencies place a job in `blocked`.
- Dependent jobs branch from the dependency's merged result, or from its branch if the policy allows stacked branches.
- An epic has its own budget and progress view. Cancelling an epic cancels its non-terminal jobs.
- The Definer may propose an epic breakdown from a large brief. A human confirms it in Team and Enterprise.

---

## 20. Adapters

Adapters are the only tool-specific code. Each lives in `adapters/<tool>/`.

### 20.1 Manifest

```json
{
  "id": "claude-code", "version": "1.0.0",
  "capabilities": ["stream", "resume", "cancel", "sandbox_native", "mcp", "vision"],
  "models": ["..."],
  "limits": {"max_context_tokens": 200000, "max_run_minutes": 60},
  "roles_supported": ["definer", "architect", "planner", "designer", "builder", "verifier", "reviewer", "curator"]
}
```

The kernel routes a stage to an adapter whose capabilities satisfy the stage's requirements. Missing capabilities degrade gracefully where defined (for example, no `resume` means the kernel re-runs from a checkpoint).

### 20.2 Run contract

```
run(request) -> stream of events
request: { run_id, stage, role, manifest_path, worktree, budget, env_refs, fence }
events:  progress | tool_use | file_written | question | usage | heartbeat | done | error
cancel(run_id)
resume(resume_token)
```

Requirements:

- **Heartbeat** at least every 30 seconds. Missing heartbeats cause the kernel to revoke the lease and mark the attempt `interrupted`.
- **Usage reporting** is mandatory, even if estimated, and flagged as estimated.
- **Streaming:** progress events feed the dashboard so long runs show live activity.
- **Idempotent start:** repeating `run` with the same `run_id` must not start a second execution.
- **Output discipline:** the adapter writes outputs only to the attempt directory and worktree, reports each write, and never edits state files.
- **Errors** are classified as `transient` (retry), `capability` (reroute), `budget`, or `fatal`.
- Adapters do not implement retries on their own; the kernel owns retry policy.

### 20.3 Conformance suite

A new adapter is accepted only after passing the **conformance suite**: starting and cancelling a run, resuming, heartbeat loss handling, writing a valid contract file, reporting usage, honoring the write boundary, and handling an injected-instruction fixture. Passing results are recorded in the adapter's folder.

---

## 21. Dashboard and operator experience

### 21.1 Delivery

`factory serve` runs a local server (the kernel's HTTP interface) and opens the dashboard. It streams events from the log to the browser. `factory export-dashboard` generates a static read-only snapshot for sharing. Opening an HTML file directly from disk is not a supported mode, because browsers block local file reads.

### 21.2 Solo experience

Three elements only:

1. **A prompt box.** Describe what you want. The factory shows an estimated cost and time.
2. **A plain-language timeline.** "Understanding your request → Planning → Building (round 2 of 4) → Checking → Ready for you". No stage jargon.
3. **A single "Needs you" card** when a decision is required: a question with options, or the approval card with preview. Primary actions are **Approve** and **Change this…**.

Also present: a live preview link, an **Undo** that reverts the merge, and a hidden "Details" drawer for the curious. First run shows an empty-state guide that creates a sample project in one click. "Explain this" and "What should I do next?" helpers are available on every card.

### 21.3 Team and Enterprise views

- **Queue and board:** jobs by stage and state, filterable by project, epic, owner.
- **Needs Human:** gates and questions, assignable by role.
- **Job detail:** brief, plan, assumptions ledger, attempts with checks, review findings, artifacts, cost, event timeline.
- **PRs:** visual approval panel, diff, check status, risk score with its contributing signals.
- **Cost:** per job, project, brand, and period; budget burn-down.
- **Skills and memory:** versions, eval results, promotion candidates, lessons.
- **Policy and audit (Enterprise):** current policy, overrides with reasons, audit browser with chain verification status.
- **System health:** sandbox status, adapter status, lock and lease view, `factory doctor` results.

Global: command palette with natural language, search, keyboard shortcuts, light and dark parity, and every action expressed as a kernel command shown on hover for transparency.

---

## 22. Enterprise capabilities

- **RBAC:** roles Owner, Admin, Maintainer, Developer, Reviewer, Viewer. Permissions are checked by the kernel on every command. Identity comes from the local user in Solo, from named users in Team, and from the organization's identity provider through a control-plane component in Enterprise. Disk-level access to the factory tree is outside this model, so Enterprise deployments restrict it at the host level, and the spec states this limit plainly.
- **Audit:** each audit entry includes the hash of the previous entry. `factory audit verify` checks the chain. Periodic anchors (a hash exported to an external system) detect wholesale rewrites. Retention and export are policy-controlled.
- **Budgets:** hierarchical (job, epic, project, brand, month) with owner notifications and hard stops.
- **Brands and design systems:** a brand owns a design system (`tokens.json`, components, docs, `lint.json`). Design-system conformance is a **check**: token lint and component usage lint run on UI diffs. Product jobs may declare `design_system_required_before_products` as a dependency epic. The design-system pipeline stages are Brand Audit, Definition, Tokens, Core Components, Documentation and Preview, Accessibility and Theming (dark mode, contrast, RTL, reduced motion), Packaging and Versioning, and Adoption.
- **Multi-brand isolation:** projects, skills, memory, and budgets are scoped to a brand. Cross-brand sharing is explicit.
- **Compliance:** exportable evidence bundles per release (checks, approvals, SBOM, license scan, audit extract). Change windows and freeze periods can be enforced by policy. Data residency and model-provider restrictions are policy fields enforced at adapter selection.

---

## 23. Commands

```
# Projects
factory project create <name> [--mode solo|team|enterprise] [--domain web|mobile|desktop|game] [--brand <b>]
factory project import <path-or-url> [--mode ...]
factory project upgrade <name> --mode team|enterprise
factory project status|pause|resume|archive <name>

# Jobs
factory job run <project> "<description>" [--epic <id>] [--profile lite|standard]
factory job status|retry|cancel|pause|resume <job-id>
factory job answer <job-id> <question-id> "<answer>"
factory job undo <job-id>

# Epics and issues
factory epic create|status|cancel <id>
factory issue create|triage <project> ...

# Approvals
factory approve <job-id> [--sha <sha>]
factory request-changes <job-id> "<feedback>"

# Skills and evals
factory skill create|improve|promote|deprecate|pin <name>
factory eval run [--suite <name>] [--adapter <id>]

# Operations
factory serve
factory doctor            # verify state, repair snapshots, check locks and sandbox
factory reindex           # rebuild derived state
factory audit verify
factory export-dashboard
factory adapter test <id> # run conformance suite
```

Natural language is accepted in the dashboard command palette and translated into these commands, which are shown before execution when they change state.

---

## 24. Success criteria

The system is correct when all of the following hold:

1. A beginner types one sentence and gets a previewable result, with at most two clicks of approval and no configuration.
2. Two concurrent jobs on one repository never corrupt each other's work (worktrees and merge queue).
3. Killing any process at any point and resuming never corrupts state and never repeats an external effect.
4. No job exceeds its hard budget, and the cost of every job is visible.
5. An output that violates its stage contract is rejected before the next stage begins.
6. Passing checks, not agent statements, are what allow a job to complete.
7. A skill reaches global scope only with passing evals and a measured gain over baseline.
8. The audit chain verifies end to end, and RBAC is enforced by the kernel in Enterprise.
9. Adding a new tool requires only an adapter folder and a passing conformance suite.
10. Imported projects report an honest baseline, including pre-existing failures.
11. A prompt-injection fixture inside an issue or README does not cause an agent to perform a gated action.
12. Operators can understand the whole system from this document plus the folder tree.

---

## 25. Implementation roadmap

| Phase | Deliver | Why this order |
| --- | --- | --- |
| **P0 Kernel core** | `job.json` + `events.jsonl`, atomic writes, leases and fencing, worktree isolation, schema validation, check runner, `factory doctor` | Everything else depends on safe state |
| **P1 Solo slice** | `lite` profile, one adapter, build loop with no-progress detection, `factory serve` with the three-element dashboard, SHA-bound approval card, undo | Makes the Solo promise real |
| **P2 Trust layer** | Budgets and metering, guards, sandbox, injection handling, risk-scored gates, import with baseline verification | Makes it safe to leave running |
| **P3 Learning** | Eval harness, skill packages and promotion, lessons ledger, repo map and memory | Compounding improvement, measured |
| **P4 Team** | More adapters through the conformance suite, epics and dependencies, visual baselines, named users and reviewer assignment | Scales to multiple people and tools |
| **P5 Enterprise** | Control plane, RBAC, hash-chained audit and anchors, brand design systems with lint, compliance exports | Needs a stable core first |

Do not build P4 or P5 features before P0 is solid and P1 is demonstrably reliable.

---

## 26. Migrating from 2.1

1. Convert each job's `meta.json` into an initial `events.jsonl` (a synthetic `imported` event, plus recorded stage events where available). Delete `board/` and run `factory reindex`.
2. Map the old state `awaiting_human` and others directly; add `blocked`, `stalled`, and `superseded` as new states.
3. Replace `human_gates.enabled` with specific gates; apply the matching mode preset.
4. Convert project skills into skill packages (add `skill.json`, and at least two eval fixtures before any promotion).
5. Replace agent definitions with the eight roles; keep old definitions as reference lenses for the Reviewer.
6. Add `checks.json`, run the import baseline, and record pre-existing failures.
7. Replace `dashboard.html` usage with `factory serve`.

---

## 27. Implementation rules

- Keep the kernel small, deterministic, and tested; it is the only component whose bugs can corrupt state.
- Every capability is expressible as files, a role or check, and optionally an adapter.
- Prefer configuration in `project.json`, `checks.json`, and policy presets over hard-coded behavior.
- Every file format has a JSON Schema in `kernel/schemas/`, and every schema change is versioned with a migration.
- Never store secrets or credentials in the factory tree.
- Solo mode must remain simple. Any new feature that appears in Solo needs a default that requires no decision from the user.
- When the spec and the kernel disagree, the kernel's conformance tests are authoritative, and the spec is corrected.

This is the complete Version 3.0 specification.

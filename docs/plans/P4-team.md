# P4 — Team Plan

**Phase:** P4
**Status:** ⬜ Planned
**Goal:** Scale to multiple people and tools: several adapters and several people operate concurrently without corrupting each other's work.

**Depends on:** [P3](P3-learning.md). Do not start before P0 is solid and P1 is demonstrably reliable.

## Workstreams

### 1. Adapter breadth via the conformance suite
- [ ] Formalize the conformance suite (spec §20.3): start/cancel, resume, heartbeat loss, valid contract file, usage reporting, write boundary, injected-instruction fixture
- [ ] Admit additional adapters only with passing results recorded in the adapter folder
- [ ] `factory adapter test <id>`
- [ ] Capability-based routing with graceful degradation (e.g., no `resume` → rerun from checkpoint)

### 2. Epics and multi-job coordination
- [ ] `epic.json`: goal, jobs with `depends_on`, integration job
- [ ] Kernel schedules by dependency order + concurrency limits; unmet dependencies → `blocked`
- [ ] Dependent jobs branch from the merged dependency result (stacked branches only if policy allows)
- [ ] Epic budget and progress view; cancelling an epic cancels non-terminal jobs
- [ ] Definer proposes epic breakdown from large briefs; human confirms

### 3. Merge queue and concurrency correctness
- [ ] Serialized integration per repository: rebase on latest base → re-run required checks → merge only if green
- [ ] Conflict → job back to Build with the conflict as input
- [ ] Stale-base detection: base moved + changed files intersect plan's file set → require re-plan
- [ ] File-set conflict hints: delay overlapping jobs (optimization; merge queue remains the correctness mechanism)

### 4. Visual baselines
- [ ] `baselines/<project>/` reference screenshots per route/component, viewport, theme
- [ ] `visual` check: capture from preview → compare with tolerance → diff images in `artifacts/`
- [ ] Baseline changes only via approved visual card; committed with the merge, keyed to approving SHA
- [ ] Flake handling: maskable non-deterministic regions; a check that flips without code change retried once then reported flaky — never silently passing

### 5. Team identity and review workflow
- [ ] Named users; reviewer assignment
- [ ] Dashboard: queue/board by stage and state; Needs Human (assignable by role); job detail (brief, plan, assumptions, attempts, findings, artifacts, cost, timeline); PR view with diff + risk score signals; cost views; skills/memory views
- [ ] Disagreement between reviewers recorded, not LLM-resolved; decision file cites accepted/rejected/deferred findings with reasons

### 6. Standard profile completion
- [ ] Adaptive early stages (research/spec/architecture only when size/risk warrants), Design (UI jobs), Scaffold (new projects), Review lenses, Polish, Package, Approve, Merge/Deploy
- [ ] Domain profiles: web (Core Web Vitals, WCAG, SEO, deploy target), mobile, desktop, game

## Exit criteria

- Two concurrent jobs on one repository never corrupt each other's work (spec success criterion #2).
- Adding a new tool requires only an adapter folder and a passing conformance suite (criterion #9).
- Visual baselines gate UI changes; flaky checks are reported, not silently passed.

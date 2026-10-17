# P3 — Learning Plan

**Phase:** P3
**Status:** ⬜ Planned
**Goal:** Compounding improvement, measured: later jobs pass more checks with fewer rounds than earlier ones on the same fixtures.

**Depends on:** [P2](P2-trust-layer.md).

## Workstreams

### 1. Eval harness
- [ ] Fixture tasks: small repo + brief + expected checks
- [ ] Run against any combination of roles, skills, models, adapters
- [ ] Results in `evals/results/` with pinned versions of everything involved (reproducible)
- [ ] Used for: skill promotion gating, adapter/model comparison (cost + success rate), regression detection on role/kernel prompt changes

### 2. Skill packages
- [ ] Package format: `SKILL.md`, `evals/`, `CHANGELOG.md`, `skill.json` (version, scope, owner, provenance, dependencies, status)
- [ ] Semantic versioning; jobs **pin** versions at creation — a skill change never alters a running job
- [ ] Lifecycle: proposed → project scope (0.x, ≥ 2 eval fixtures) → candidate → promoted (global 1.0: passing evals + measured gain over no-skill baseline + 2 independent uses; Team+ needs human approval) → deprecated/rolled back
- [ ] Project skills override global of the same name; skills carry no permissions
- [ ] CLI: `factory skill create|improve|promote|deprecate|pin`, `factory eval run`

### 3. Memory and learning
- [ ] `decisions.md` (ADRs, human-approved), `conventions.md`, `repo-map.json` (commit-SHA-stamped, stale-marked, refreshed before planning), `lessons.jsonl` (post-job structured entries with job references + confidence)
- [ ] Rules enforced: no secrets; humans can edit/delete; lessons influence behavior only through reviewed convention/skill changes, never silent injection
- [ ] Curator role active: mines lessons, proposes skill changes, keeps repo map fresh; output validated like any other contract

## Exit criteria

- Skill promotion requires passing evals and a measured gain over baseline (spec success criterion #7).
- A/B runs (with/without skill) are reproducible from stored versions.
- Memory never contains secrets; every lesson traces to a job.

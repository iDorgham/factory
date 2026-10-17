# P2 — Trust Layer Plan

**Phase:** P2
**Status:** ⬜ Planned
**Goal:** Make it safe to leave running: budgets enforced, anti-cheating guards active, sandbox hardened, risk-scored gates in place, and honest baselines on import.

**Depends on:** [P1](P1-solo-slice.md) demonstrably reliable.

## Workstreams

### 1. Budgets and metering
- [ ] Usage from adapters → cost via the `factory.json` price table; stored per attempt in `usage.json`
- [ ] Budgets at attempt, stage, job, and project scopes; soft → notify, hard → stop at next safe point
- [ ] Pre-job cost estimate from similar past jobs (Solo: one friendly line)
- [ ] Cost reports: per-job breakdown by stage/round; per-project trends; cost per approved change
- [ ] Mid-run cut-off for adapters that support it

### 2. Guards (anti-cheating), deterministic over the diff
- [ ] `no_test_deletion` — tests may not be deleted/skipped/weakened without an explicit plan task
- [ ] `no_check_tampering` — check config, CI files, lint rules read-only unless plan-authorized
- [ ] `no_lockfile_surprise` — dependency changes must match the plan
- [ ] `no_secret_in_diff` — secret scanning on every diff
- [ ] `scope_guard` — out-of-plan files allowed but raise the risk score
- [ ] Guards run after every round; violations recorded as events

### 3. Sandbox hardening
- [ ] Filesystem limited to job worktree + temp; network egress allowlist; resource limits; no inherited env beyond an explicit list
- [ ] Container if available; otherwise restricted process with command allowlist — and the dashboard states plainly which protections are active
- [ ] Secrets in host store/env only; injected only into whitelisted commands; scrubbed from logs and artifacts

### 4. Risk-scored gates
- [ ] Risk score from deterministic signals: diff size, sensitive paths, new dependencies, scope drift, external effects, history, skill maturity
- [ ] Score bands → `auto | notify | require_human | require_role` per preset; projects may tighten, not loosen (loosening audited, Team+)
- [ ] Gate config shape (spec §14.2); safety floor remains non-disableable

### 5. Prompt-injection handling
- [ ] Untrusted inputs (issues, READMEs, web pages, imported repos) wrapped and labeled as data in the manifest
- [ ] Sensitive actions gated by the kernel, never by agent judgment
- [ ] Injection fixture in the conformance suite; spec success criterion #11 as a test

### 6. Safety floor hardening
- [ ] Human gate on irreversible `effects: external` stages
- [ ] Destructive operations outside the worktree blocked
- [ ] Agents cannot edit policy, budget, role, or kernel files
- [ ] Audit events always written for approvals, policy overrides, external effects

### 7. Import with baseline verification
- [ ] `factory project import <path-or-url>`: clone/link, detect stack, run build/lint/type/test as **baseline** (pre-existing failures recorded, never claimed green)
- [ ] Infer `checks.json` from scripts + CI; confirm ambiguity
- [ ] Build initial memory: `repo-map.json`, first `conventions.md`, draft `decisions.md` (marked inferred)
- [ ] Optional issue/PR import as untrusted input
- [ ] Import report: stack, baseline status, risky areas, suggested first jobs

## Exit criteria

- No job exceeds its hard budget; every job's cost is visible (spec success criterion #4).
- Guards catch test deletion, check tampering, and lockfile surprises in tests.
- An injected-instruction fixture does not cause a gated action.
- Imported projects report an honest baseline including pre-existing failures.

# P2 — Trust Layer Plan

**Phase:** P2
**Status:** 🚧 In progress (P2.1 guards landed 2026-10-17; **P2.2 budgets landed 2026-10-17** — schemas, cost meter, engine enforcement, doctor checks, suite fully green; **P2.3 sandbox hardening landed 2026-10-17** — global-config schema, pure sanitization/containment, sandboxed adapter invocation, doctor checks; **P2.4 risk-scored gates landed 2026-10-18** — `risk_scoring` config schema, pure weighted scoring with ceiling bands, kernel-owned band→action map, `risk.computed` on the record, stage-scoped signals, doctor checks; **P2.5 prompt-injection handling landed 2026-10-19** — `injection` config schema with kernel-owned baseline patterns, pure detector, manifest labeling, `injection.detected` events, the `injection_flag` risk signal, dashboard rows, doctor checks. Next: safety-floor hardening, import with baseline)
**Goal:** Make it safe to leave running: budgets enforced, anti-cheating guards active, sandbox hardened, risk-scored gates in place, and honest baselines on import.

**Depends on:** [P1](P1-solo-slice.md) demonstrably reliable.

## Workstreams

### 1. Budgets and metering
*Status: enforcement landed (P2.2, 2026-10-17). Remaining rows below are reporting/estimation scope.*

- [x] Usage from adapters → cost via the `factory.json` price table; stored per attempt in `usage.json`
      *(P2.2: `budgets.calculate_cost` prices every `X_tokens` metric at the tier's `X_per_1m` rate;
      the engine writes the verdict into the attempt's `budget.json` each budgeted round. Unpriced
      usage raises `BudgetError` — nothing silently costs $0.)*
- [x] Budgets at attempt, stage, job, and project scopes; soft → notify, hard → stop at next safe point
      *(P2.2 landed the attempt/stage scope: `budgets.stage_limits` + `check_budget` decide ok / notify /
      stop with inclusive boundaries and a deterministic `0.8 × usd` default soft limit;
      `engine._run_budget` emits `budget.soft_exceeded` (attempt still stands) / `budget.hard_exceeded`
      (attempt fails, retry loop broken, job → `failed` as an absolute stop per §543) and refuses to
      re-spend a cached hard breach on resume. Job/project scopes are future.)*
- [ ] Pre-job cost estimate from similar past jobs (Solo: one friendly line)
- [ ] Cost reports: per-job breakdown by stage/round; per-project trends; cost per approved change
- [ ] Mid-run cut-off for adapters that support it

*(The 5 TDD-red cases from mid-phase are resolved — the suite is fully green at `1895f14`:
312 collected — 310 passed, 2 skipped.)*

### 2. Guards (anti-cheating), deterministic over the diff
- [x] `no_test_deletion` — tests may not be deleted without an explicit authorization *(P2.1: exact-path authorization; skip/weakening detection is a follow-up)*
- [ ] `no_check_tampering` — check config, CI files, lint rules read-only unless plan-authorized
- [x] `no_lockfile_surprise` — dependency changes must match the plan *(P2.1: manifest↔lockfile must move together; plan-declared file-set pairing is a follow-up)*
- [x] `no_secret_in_diff` — secret scanning on every diff *(P2.1: added lines only; base64 hashes/data blobs excluded as benign)*
- [ ] `scope_guard` — out-of-plan files allowed but raise the risk score
- [x] Guards run after every round; violations recorded as events *(P2.1: per attempt, from the attempt-base SHA; fingerprint-fed so repeats stall)*

**Shipped with P2.1 (recorded here so the plan matches the tree):** the kernel-owned per-job
`authorizations.json` (`allowed_test_deletions`, `allowed_dep_changes` — exact paths, schema-validated,
wildcards never match), `gitrepo.collect_diff` for the per-attempt scope including untracked files,
`guards.json` written beside `checks.json`, the `guard_config` pseudo-guard that turns a typo or a
malformed authorization file into a recorded violation instead of a silent skip, dashboard verdicts,
and `doctor` checks for guard-id integrity plus authorization validity.

### 3. Sandbox hardening
*Status: env/paths enforcement landed (P2.3, 2026-10-17). Remaining rows below are container/network/resource scope.*
- [x] No inherited env beyond an explicit list; adapter cwd confined to the job worktree *(P2.3: `sanitize_env` strips the kernel env to the `factory.json` allowlist — case-insensitive exact or `*`-suffix rules, lone `*` explicit opt-out — plus kernel-reserved `FACTORY_*` attribution injected after the filter; `strict_cwd` locks the adapter process into the job worktree; `resolve_under` proves sandbox paths lexically contained and `load_sandbox_policy` fails hard on bad config; doctor verifies schema validity as authoritative and names the `"*"`/loose-`strict_cwd` trade-offs. Filesystem limits beyond the worktree stay kernel-owned paths; network egress and resource limits remain config-declared, not enforced.)*
- [ ] Container if available; otherwise restricted process with command allowlist — and the dashboard states plainly which protections are active
- [ ] Secrets in host store/env only; injected only into whitelisted commands; scrubbed from logs and artifacts *(P2.3 covers the env half: secrets never reach the adapter subprocess at all unless allowlisted; out of scope: host store injection, log/artifact scrubbing)*

*(The sandbox TDD-red cases from `8348af8` are resolved — the suite is fully green at `b3696c6`:
343 collected — 341 passed, 2 skipped. The risk TDD-red cases from `8c422fc` are resolved the same
way — fully green at `7778f06`: 380 collected — 378 passed, 2 skipped. The injection TDD-red cases
from `ae7fc58` likewise — fully green at `878629b`: 409 collected — 407 passed, 2 skipped, and
421 passed / 2 skipped at `d933adf` after the dashboard task-player work.)*

### 4. Risk-scored gates
- [x] Risk score from deterministic signals *(P2.4, as scoped for P2: the kernel-owned set — guard violations, check failures, retries, and the budget verdict, aggregated stage-scoped over "the road to this pass" — drives the score; the spec's wider aspirational list (diff size, sensitive paths, new dependencies, scope drift, external effects, history, skill maturity) stays future scope, with `scope_guard` raising signals once it exists)*
      *(profiles already declare `gate: risk_scored` on `verify`; the computation now exists — `risk.computed` records score, band, action, and the exact signals)*
- [x] Score bands → `auto | notify | require_human | require_role` per preset; projects may tighten, not loosen (loosening audited, Team+) *(P2.4 partially: ceiling bands land kernel-global with `low → auto_advance`, `medium → awaiting_human`, `high → blocked`; per-preset band profiles and the Team+ tighten-only/loosening-audit machinery remain open — deliberately, so no project config can loosen the Solo safety floor)*
- [x] Gate config shape (spec §14.2); safety floor remains non-disableable *(P2.4: `risk_scoring` weights + thresholds schema-shaped and doctor-checked; the band→action map is kernel-owned and rejected outright in config — the floor cannot be negotiated away)*

### 5. Prompt-injection handling
- [x] Untrusted inputs (issues, READMEs, web pages, imported repos) wrapped and labeled as data in the manifest
- [x] Sensitive actions gated by the kernel, never by agent judgment
- [x] Injection fixture in the conformance suite; spec success criterion #11 as a test
      *(P2.5 landed the detection half: the kernel's own baseline patterns flag untrusted manifest
      items before the adapter sees them, the manifest entry is labeled, an `injection.detected`
      event is recorded, and the `injection_flag` signal feeds the existing band→action map — the
      kernel gained an observation, not a new enforcement path. Still open: wrapping *all* untrusted
      sources (web pages, imported repos) and the spec's injection fixture in the conformance suite.)*

### 6. Safety floor hardening
- [ ] Human gate on irreversible `effects: external` stages *(every stage in `lite.yaml` is currently `effects: local`)*
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

- No job exceeds its hard budget; every job's cost is visible (spec success criterion #4). — *met: enforced since P2.2 (`budget.json` verdict per attempt, breach events, hard stop breaks the retry loop, job → `failed` as an absolute stop)*
- Guards catch test deletion, check tampering, and lockfile surprises in tests. — *partially met: deletion and lockfile pairing have tests; `no_check_tampering` does not exist*
- An injected-instruction fixture does not cause a gated action.
- Imported projects report an honest baseline including pre-existing failures.

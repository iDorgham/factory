# Security

**Related:** [Specification v3.0 §15](<../specification/Enterprise AI Software Factory — Specification v3.0.md>) · [Architecture §10](../architecture/ARCHITECTURE.md) · [Contributing](../development/CONTRIBUTING.md) · [Runbook](RUNBOOK.md)

---

## 1. Reporting a vulnerability

**Do not open a public issue for security problems.**

Report privately to the maintainers with: a description, reproduction steps, affected component (kernel / adapter / dashboard / schema), and potential impact. Include the minimal input or fixture that triggers it. If the issue involves prompt injection, include the fixture content verbatim.

Until a fix ships, please keep the report confidential.

## 2. Safety floor

These controls are part of the spec's non-configurable floor. Each is marked with what the kernel
**actually enforces today** — a security document that lists planned controls beside shipped ones without
saying which is which is worse than a short one.

| # | Control | Enforced today |
|---|---------|----------------|
| 1 | **External effects are gated.** Production deploys, publishing, and other `effects: external` stages with irreversible results require a human gate | ⚠️ The gate machinery is real (`approve` is `gate: required`, `gate: risk_scored` is evaluated), but every stage in `lite.yaml` is currently `effects: local`, so no external-effect path has been exercised |
| 2 | **Secrets stay out of agents.** Secrets are never placed in an agent's environment, context, or job files | ❌ Spec'd, not implemented. Secrets must not be placed in agent context **by operator discipline** today |
| 3 | **Destructive operations are blocked** outside the job worktree | ❌ Spec'd, not implemented |
| 4 | **Hard budget caps stop execution** at the next stage boundary | ⚠️ Cost arithmetic is implemented and tested (`budgets.py`); the runtime that stops a run is the in-flight P2.2 slice. Budgets are **not** enforced yet |
| 5 | **Audit events are always written** for every approval, policy override, and external effect | ✅ For every event type that exists — approvals, rework requests, merges, guard violations, answers, checkpoints |
| 6 | **Agents cannot edit** policy, budget, role, or kernel files | ✅ By construction: agents have no write path to state at all |

`gates.enabled: false` does not exist. Turning off a gate turns off *that specific gate* only; the safety
floor always remains.

## 3. Threat model and mitigations

| Threat | Mitigation | State |
|--------|-----------|-------|
| **Prompt injection** via issues, READMEs, web pages, dependencies, or imported repos | Untrusted content is wrapped and labeled as data in the context manifest; sensitive actions require kernel-evaluated gates, not agent judgment | ⚠️ The conformance suite carries an injected-instruction case and the kernel gate is real; systematic wrapping is P2 |
| **Secret exfiltration** | `no_secret_in_diff` scans added lines on every attempt; env/artifact scrubbing and an egress allowlist are specified | ⚠️ Diff scanning ✅ · agent-env allowlist ✅ (P2.3: only the sanitized env reaches adapter subprocesses) · artifact scrubbing ❌ · egress allowlist ❌ |
| **Malicious / typosquatted dependencies** | `no_lockfile_surprise` forces a manifest and its lockfile to move together; new packages are meant to raise the risk score | ⚠️ Guard ✅ · install-script disabling ❌ · risk scoring ❌ |
| **Test tampering** | `no_test_deletion` fails the attempt on deletion of test-shaped files unless authorized by exact path | ✅ for deletion · ❌ for skipping/weakening tests and for check-config tampering (`no_check_tampering` is not implemented) |
| **Runaway cost** | Per-attempt usage reporting with per-tier pricing and stage soft/hard budgets | ⚠️ Metering ✅ · enforcement ✅ (verdict per attempt, absolute hard stop, since P2.2) · job/project scope ✗ |
| **Privilege escalation through skills** | Skills are meant to carry no permissions of their own | ❌ P3 — no skill packages exist yet |
| **Audit tampering** | The event log is hash-chained (`prev`) and `doctor` verifies the chain end to end; external anchors are specified | ✅ chain + verification · ❌ external anchors (P5) |

The two guards that exist today (`no_test_deletion`, `no_lockfile_surprise`, plus
`no_secret_in_diff`) are enforced by the **kernel reading the diff**, not by an agent reporting on
itself. That distinction is the point: an agent cannot talk its way past them.

## 4. Secret handling

- Secrets live in the host's secret store or environment, **referenced by name** in `checks.json` and adapter manifests (`env_refs`).
- The kernel injects secrets only into whitelisted check or deploy commands, and scrubs known secret values from logs and artifacts before storing them.
- Never store secrets or credentials in the factory tree — including tests, fixtures, role definitions, and example files.

## 5. Sandbox expectations

> **Current state: process sandbox enforced for adapter subprocesses (P2.3).** `factory.json` declares
> the `sandbox` block, the kernel validates it against `factory.schema.json` (schema-invalid config is
> a hard error), and **every adapter subprocess runs with a sanitized environment** (only the
> `env_allowlist` intersection of the kernel env survives — provider tokens, SSH agents, proxies are
> dropped unless explicitly allowlisted) plus kernel-reserved `FACTORY_*` attribution it cannot spoof.
> With `strict_cwd: true` the adapter process is started inside the job worktree, and the sandbox paths
> are proven contained before any subprocess sees them; a detected path escape fails the attempt as
> `fatal`. `factory doctor` verifies this at boot: whole-config schema validity is authoritative, and the
> `"*"` allowlist / loose `strict_cwd` trade-offs are named as advisories.
>
> **Still declared-but-not-enforced:** the `network_allowlist` and `resource_limits` keys, filesystem
> isolation beyond the kernel-owned paths, container isolation, and secrets scrubbing from logs and
> artifacts. A sandboxed adapter process still runs with the OS privileges of the user who started
> the kernel — a shell inside the worktree is confined by policy, not by an OS sandbox. Treat those
> residual surfaces as intent, not as protection, until this section says otherwise.

The target behaviour (P2, workstream 3) is: agents and checks run with a filesystem limited to the job
worktree and temp directories, a network allowlist, resource limits, and no inherited environment
variables beyond an explicit list — the env half landed in P2.3 (declared boundary: kernel-owned
project checks keep the full host env, because operator tooling such as git/pytest often needs
credentials).

- Solo mode should use the lightest sandbox the host supports: a container if available, otherwise a restricted process with a command allowlist.
- The active protections must be **stated plainly** and shown in the dashboard's sandbox status — no implied protection that isn't active. The rule exists so that operators are never misled about what is running.

## 6. Operator responsibilities

- Restrict disk-level access to the factory tree at the host level. RBAC and RBAC-like controls govern commands through the kernel; raw file access is outside that model and must be constrained by the host (this limit is stated plainly in the spec).
- Keep `factory doctor` clean; a broken chain or unrepaired snapshot is a security-relevant condition.
- **Read the `doctor` guard checks.** An unknown guard id means a safeguard did not run; a malformed `authorizations.json` is an error, not a warning.
- Review the assumptions ledger at approval — an assumption contains real decisions made on your behalf.
- Keep the adapter list honest: only conformance-passing adapters should be enabled.
- Audit the commit history with `./factory provenance verify` before a release or an external audit.

## 7. Test suites that encode security guarantees

The following are verified by tests and must not regress:

- Stale fencing tokens are rejected (no zombie-writer corruption).
- Illegal state transitions raise.
- Invalid documents are rejected before reaching disk — including `authorizations.json`, `budget.schema.json`, and `price_table.schema.json`.
- The event chain detects tampering and gaps.
- Adapters cannot write outside the attempt directory and worktree.
- An injected-instruction fixture does not cause a gated action.
- **Guards (40 cases, `tests/test_guards.py`)** — each guard's violation, its authorized-silence path, exact-path-only authorization, and the fail-hard behaviour on an unknown guard id.
- **Budgets (24 cases, `tests/test_budgets.py`)** — unpriced usage raises instead of costing $0, malformed usage is rejected rather than estimated, and soft/hard boundaries are inclusive.
- **Provenance (23 cases, `tests/test_provenance.py`)** — a commit without its trailers is detected.

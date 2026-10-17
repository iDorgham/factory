# Security

**Related:** [Specification v3.0 §15](<../specification/Enterprise AI Software Factory — Specification v3.0.md>) · [Architecture §10](../architecture/ARCHITECTURE.md) · [Contributing](../development/CONTRIBUTING.md) · [Runbook](RUNBOOK.md)

---

## 1. Reporting a vulnerability

**Do not open a public issue for security problems.**

Report privately to the maintainers with: a description, reproduction steps, affected component (kernel / adapter / dashboard / schema), and potential impact. Include the minimal input or fixture that triggers it. If the issue involves prompt injection, include the fixture content verbatim.

Until a fix ships, please keep the report confidential.

## 2. Safety floor (cannot be disabled by any configuration)

These controls are non-negotiable and enforced regardless of mode or policy:

1. **External effects are gated.** Production deploys, publishing, and other `effects: external` stages with irreversible results require a human gate.
2. **Secrets stay out of agents.** Secrets are never placed in an agent's environment, context, or job files.
3. **Destructive operations are blocked** outside the job worktree (deleting directories, force-pushing protected branches, dropping databases).
4. **Hard budget caps stop execution** at the next stage boundary, or sooner if the adapter supports mid-run cut-off.
5. **Audit events are always written** for every approval, policy override, and external effect.
6. **Agents cannot edit** policy, budget, role, or kernel files.

`gates.enabled: false` does not exist. Turning off a gate turns off *that specific gate* only; the safety floor always remains.

## 3. Threat model and mitigations

| Threat | Mitigation |
|--------|-----------|
| **Prompt injection** via issues, READMEs, web pages, dependencies, or imported repos | Untrusted content is wrapped and labeled as data in the context manifest; agents have no ambient authority to act on instructions inside it; sensitive actions require kernel-evaluated gates, not agent judgment |
| **Secret exfiltration** | No secrets in agent env; secret scanning on diffs and artifacts; network egress allowlist in the sandbox |
| **Malicious / typosquatted dependencies** | Dependency changes must match the plan; install scripts disabled by default in the sandbox; new packages raise the risk score |
| **Test and check tampering** | Guards (`no_test_deletion`, `no_check_tampering`); the check configuration is read-only to agents |
| **Runaway cost** | Per-attempt, per-job, and per-period budgets enforced by the kernel |
| **Privilege escalation through skills** | Skills carry no permissions of their own; tool access is granted by stage and policy only |
| **Audit tampering** | Hash-chained audit; anchors can be exported externally |

## 4. Secret handling

- Secrets live in the host's secret store or environment, **referenced by name** in `checks.json` and adapter manifests (`env_refs`).
- The kernel injects secrets only into whitelisted check or deploy commands, and scrubs known secret values from logs and artifacts before storing them.
- Never store secrets or credentials in the factory tree — including tests, fixtures, role definitions, and example files.

## 5. Sandbox expectations

Agents and checks run with a filesystem limited to the job worktree and temp directories, a network allowlist, resource limits, and no inherited environment variables beyond an explicit list.

- Solo mode uses the lightest sandbox the host supports: a container if available, otherwise a restricted process with a command allowlist.
- The active protections are **stated plainly** and shown in the dashboard's sandbox status — no implied protection that isn't active.

## 6. Operator responsibilities

- Restrict disk-level access to the factory tree at the host level. RBAC and RBAC-like controls govern commands through the kernel; raw file access is outside that model and must be constrained by the host (this limit is stated plainly in the spec).
- Keep `factory doctor` clean; a broken chain or unrepaired snapshot is a security-relevant condition.
- Review the assumptions ledger at approval — an assumption contains real decisions made on your behalf.
- Keep the adapter list honest: only conformance-passing adapters should be enabled.

## 7. Test suites that encode security guarantees

The following are verified by tests and must not regress:

- Stale fencing tokens are rejected (no zombie-writer corruption).
- Illegal state transitions raise.
- Invalid documents are rejected before reaching disk.
- The event chain detects tampering and gaps.
- Adapters cannot write outside the attempt directory and worktree.
- An injected-instruction fixture does not cause a gated action.

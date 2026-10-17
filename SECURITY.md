# Security Policy

Please report security vulnerabilities **privately** to the maintainers — do not open a public issue.

Full policy, including the non-disableable safety floor, the threat model and its mitigations, secret handling, and sandbox expectations:

➡️ **[docs/operations/SECURITY.md](docs/operations/SECURITY.md)**

## Reporting

Include: a description, reproduction steps, the affected component (kernel / adapter / dashboard / schema), and the potential impact. For prompt-injection issues, include the triggering fixture verbatim. Keep the report confidential until a fix ships.

## Safety floor (summary)

Some controls cannot be configured away by design: human gates on irreversible external effects, no
secrets in agent context, blocked destructive operations outside the worktree, hard budget caps,
always-on audit events, and agents unable to edit policy/budget/role/kernel files.

> **Honest status.** Not every item on that list is enforced by the kernel yet. Today the gates, the audit
> events, and the closed agent write path are real; diff secret scanning, budget caps, sandboxing, and
> blocking destructive operations are **not**. The
> [full security document](docs/operations/SECURITY.md) marks each control ✅ / ⚠️ / ❌, and the
> [architecture appendix](docs/architecture/ARCHITECTURE.md#appendix--implemented-vs-target-at-9948840)
> has the same table. Please read those before relying on any control — a security document that implies a
> protection that is not active is worse than one that admits the gap.

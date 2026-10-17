# Security Policy

Please report security vulnerabilities **privately** to the maintainers — do not open a public issue.

Full policy, including the non-disableable safety floor, the threat model and its mitigations, secret handling, and sandbox expectations:

➡️ **[docs/operations/SECURITY.md](docs/operations/SECURITY.md)**

## Reporting

Include: a description, reproduction steps, the affected component (kernel / adapter / dashboard / schema), and the potential impact. For prompt-injection issues, include the triggering fixture verbatim. Keep the report confidential until a fix ships.

## Safety floor (summary)

Some controls cannot be configured away: human gates on irreversible external effects, no secrets in agent context, blocked destructive operations outside the worktree, hard budget caps, always-on audit events, and agents unable to edit policy/budget/role/kernel files.

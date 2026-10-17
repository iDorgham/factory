# Troubleshooting

**Related:** [Runbook](RUNBOOK.md) · [Security](SECURITY.md) · [Testing](../development/TESTING.md)

Common problems and their fixes. When in doubt, run `./factory doctor` first.

---

## State and events

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `job.json` differs from what events say | Snapshot drifted (partial write, manual edit) | `./factory doctor` — the fold wins and rewrites the snapshot |
| "event chain broken" / chain verification fails | An event line was edited, deleted, or reordered | Restore `events.jsonl` from backup; do **not** silently repair. If unrecoverable, escalate per [Runbook §6](RUNBOOK.md) |
| `state/index.json` stale or missing | Derived file deleted or out of date | `./factory reindex` |
| `SchemaError` on a write | The document doesn't match `kernel/schemas/` | Inspect the reported path; fix the producer or the schema (see [Schema versioning](../development/SCHEMA-VERSIONING.md)) |
| Manual edit "didn't stick" | Only the kernel writes state | Make the change through the CLI/API, not the file |

## Locks and leases

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| "stale writer rejected" | An old process held an outdated fencing token | Expected behaviour — a crashed/zombie writer cannot corrupt state. Confirm the old process is gone |
| Job appears locked but nothing is running | Expired lease / stale guard file | The next acquire steals it; if stuck, confirm the owner is gone then clear and `doctor` |
| Lock errors on a network path | Network filesystems are unsupported for concurrent mode | Move the factory tree to local storage; `doctor` warns about network roots |

## Worktrees and jobs

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| "missing worktree" warning | `.work/<job-id>/` was deleted | Recreate via the kernel; don't hand-create directories |
| "orphan worktree" warning | A worktree exists with no matching job | Inspect and, if truly orphaned, remove it; `doctor` reports it |
| Job stuck in `blocked` | Blocking question or unmet epic dependency | `./factory job status <job-id>`; answer with `./factory job answer …` |
| Job stuck in `stalled` | No-progress detected (same fingerprint twice / empty diff) | Follow the escalation ladder: change strategy → switch model/adapter → re-plan → escalate |
| Repeat stalls on the same task | Plan is too coarse or the task is genuinely hard | Split the task; re-plan the failing task (Architect) |
| Attempt marked `interrupted` | Process crashed or heartbeat was lost | Normal recovery path: restore from the last checkpoint SHA ([Runbook §3.1](RUNBOOK.md)) |

## Checks

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| A check that "should pass" fails | The command itself fails, or `checks.json` is wrong | Run the exact command from `checks.json` by hand in the worktree |
| Agent claims tests pass but the check fails | Agent statements are never evidence | Trust the check result; the kernel runs checks itself |
| Check output truncated | Output is trimmed to the relevant failures by design | The full raw result is stored in the attempt's `checks.json` |
| Flaky check | Non-deterministic region | Mask it in config where possible; a flip without a code change is retried once then reported flaky — never silently passed |

## Context and budgets

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Agent seems to miss context | Manifest exceeded the token budget and degraded | Inspect `context.manifest.json`; raise the budget or trim includes. Degradation is ordered, never silent |
| Hard budget stop | Budget cap reached | Expected — raise the cap deliberately (audited) or split the job |
| Unexpected cost | A stage routed to a costlier model, or extra rounds | Check `usage.json` per attempt and the price table in `factory.json` |

## Environment

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Imports fail / `factory` not found | Package not installed | `pip install -e ".[dev]"` |
| Tests can't find the kernel | `pythonpath` not applied | Run `python -m pytest` from the repo root |
| Line-ending churn on Windows | Editor writing CRLF | Honour `.editorconfig` / `.gitattributes` (LF in repo) |
| Directory fsync error on Windows | Windows cannot fsync a directory | Expected — `atomic.py` skips directory fsync on unsupported platforms |

## When to escalate

Escalate to a maintainer when: `doctor` cannot repair the tree, the event chain fails to verify, or a schema migration does not apply cleanly. Attach `doctor` output, the relevant `events.jsonl` excerpt (secrets scrubbed), and the commands you ran.

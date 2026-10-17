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
| A run is costing more than expected | A stage routed to a costlier model, or extra rounds (a build stage may run up to `max_rounds` attempts) | Check `usage.json` per attempt and the price table in `factory.json`. Budget **stop** is not enforced yet — cancel deliberately |
| "Hard budget stop" expected but the run continued | Budget enforcement is still being wired (P2.2) | Not a bug you can fix in config. The cost arithmetic exists in `budgets.py`; the engine does not yet act on it. See [Runbook §3.7](RUNBOOK.md) |
| `BudgetError` on unpriced usage | A usage key shaped `X_tokens` has no matching `X_per_1m` rate in the usage's model tier | Add the metric to the tier, or report usage under a priced metric. Raising instead of silently costing $0 is deliberate — see [P2 plan](../plans/P2-trust-layer.md) |
| `BudgetError` because `soft_usd >= usd` | The stage declares a soft limit at or above its hard limit | Fix `kernel/stages/*.yaml`. The runtime will not reorder your limits for you |

## Guards (P2.1)

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| An attempt failed although every check passed | A **guard** tripped over the diff — guard verdicts trump check verdicts | Read `guards.json` in the attempt dir and the `guard.violation` events; fix the change, or authorize the exact path in the job's `authorizations.json` |
| A test deletion was blocked and the deletion was legitimate | Structural authorization is required | Add the **exact** path to `allowed_test_deletions` (no globs — wildcards never match) with `reason` / `authorized_by`, then re-run |
| A `guard_config` violation with kind `unknown_guard` | A stage profile declares a guard id that does not exist, so that guard **never ran** | Fix the id in `kernel/stages/*.yaml` or implement the guard; confirm with `./factory doctor` |
| `doctor` errors on `authorizations.json` | The file is kernel-owned policy and is malformed | Repair it to the schema. Absence means "nothing authorized"; a corrupt file must not be read that way |
| A manifest change was rejected | Dependency drift: a manifest changed while its lockfile did not | Update both together, or authorize the path via `allowed_dep_changes` |
| A job stalled right after a guard violation | Expected: guard ids + paths feed the no-progress fingerprint | Treat it as the system working. Re-authorize or change the plan rather than retrying |
| Job stalled repeatedly on the same check | Plan too coarse, or the task is genuinely hard | Split the task and re-plan the failing step |

## Environment

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Imports fail / `factory` not found | Package not installed | `pip install -e ".[dev]"` |
| Tests can't find the kernel | `pythonpath` not applied | Run `python -m pytest` from the repo root |
| Line-ending churn on Windows | Editor writing CRLF | Honour `.editorconfig` / `.gitattributes` (LF in repo) |
| Directory fsync error on Windows | Windows cannot fsync a directory | Expected — `atomic.py` skips directory fsync on unsupported platforms |

## When to escalate

Escalate to a maintainer when: `doctor` cannot repair the tree, the event chain fails to verify, or a schema migration does not apply cleanly. Attach `doctor` output, the relevant `events.jsonl` excerpt (secrets scrubbed), and the commands you ran.

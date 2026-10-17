# Operations Runbook

**Audience:** operators running the factory.
**Related:** [Troubleshooting](TROUBLESHOOTING.md) · [Security](SECURITY.md) · [Architecture §2](../architecture/ARCHITECTURE.md)

---

## 1. Health check: `factory doctor`

Run `doctor` after any crash, recovery, manual edit, or suspicious result. It verifies and repairs:

- **Schema conformance** — every event and snapshot against `kernel/schemas/`.
- **Event chain** — the `prev` hash chain end to end; it detects tampering, gaps, and reordering.
- **Snapshot divergence** — folds the events and rewrites `job.json` if it disagrees; **the fold wins**.
- **Leases** — warns on expired or orphaned leases.
- **Worktrees** — warns on missing or orphaned `.work/<job-id>/` directories.
- **Guard configuration integrity** — warns (advisory) when a stage profile in `kernel/stages/*.yaml`
  declares a guard id that does not exist in the registry, naming the file to fix. A typo here would
  otherwise disable a safeguard silently.
- **Guard authorizations** — validates each job's `authorizations.json` and reports **errors** (not
  warnings): a corrupt kernel-owned policy file must never read as "no authorization".
- **Network roots** — warns that network filesystems are unsupported for concurrent mode.

```bash
./factory doctor
```

Treat any warning as actionable: fix the underlying cause before starting new jobs. The two guard checks
are worth internalising: if `doctor` warns about an unknown guard id, the guard did **not** run — the
stage looked protected and was not.

### `doctor` will not tell you (yet)

Budget configuration checks (`soft_usd >= usd`, invalid price table) are specified and their tests are
written, but the `doctor` side is not implemented yet — it is the current P2.2 slice. Until it lands,
audit the price table by reading `factory.json` and `kernel/budgets.py` directly.

## 2. Rebuilding derived state: `factory reindex`

`state/index.json` is derived and disposable. If it looks stale or was deleted:

```bash
./factory reindex
```

This rebuilds the index from the event logs. It never touches `events.jsonl`. Safe to run at any time.

## 3. Recovery procedures

### 3.1 The process was killed mid-attempt

1. The attempt is marked `interrupted` (a crash is **never** treated as success).
2. Resume restores the worktree to the **last accepted checkpoint** — it does not rerun on a possibly dirty tree.
3. Every attempt's `usage.json` survives the crash, so cost accounting is not lost.
4. Run `./factory doctor` to confirm the tree is consistent.

> For `effects: external` stages, the spec's effect journal (completed effects are not repeated; incomplete
> effects run a `compensate` action or require a human gate) is **not implemented yet** — every stage in
> `lite.yaml` is `effects: local`. Do not rely on it.

### 3.2 `job.json` disagrees with the event log

Do nothing by hand. Run `./factory doctor`; it repairs the snapshot from the fold. Editing `job.json` manually is never correct.

### 3.3 A job is stuck / a lease looks held

1. Inspect the job's lock file in its job directory.
2. A lease that has expired is stolen on the next acquire; a stale guard file is likewise stolen.
3. Do not delete lock files while a run is live. Confirm the owning process is gone first.
4. After clearing, `./factory reindex` and `./factory doctor`.

### 3.4 A job is `blocked`

It is waiting on a blocking question, an epic dependency, or a resource.

```bash
./factory job status <job-id>     # shows the question or dependency
./factory job answer <job-id> <question-id> "<answer>"
```

### 3.5 A job is `stalled`

No-progress was detected (same failure fingerprint twice, or an empty diff). The escalation ladder is: change strategy → switch model/adapter → reduce scope + re-plan → escalate to a human. Inspect the event timeline to see which rung it reached.

Note that guard violations now feed the same fingerprint: an agent that repeatedly deletes tests or
changes a lockfile alone stalls rather than burning its rounds. Check `guards.json` in the attempt
directory before assuming the agent was simply stuck.

### 3.6 An attempt failed but every check passed

That is a guard verdict, not a check failure. Read
`projects/<p>/jobs/<id>/stages/<nn>-<stage>/attempt-<k>/guards.json`, then find the matching
`guard.violation` events in `events.jsonl`. Either fix what the agent did, or — if the change was
legitimate — authorize it structurally in the job's `authorizations.json` (exact paths only, no globs)
with a `reason` and `authorized_by`, then re-run.

If the violation is `guard_config` with kind `unknown_guard`, the stage profile declares a guard that
does not exist: that guard never ran. Fix the id in `kernel/stages/*.yaml` (or implement the guard) and
confirm with `./factory doctor`.

### 3.7 A run is costing more than expected

Budget enforcement is **not live yet** — there is no automatic stop. Until the P2.2 wiring lands:

1. Read `usage.json` in each attempt directory for real token counts (never estimated values).
2. Price them against `price_table` in `factory.json` (`input_per_1m`, `output_per_1m`, `cached_per_1m`).
3. Compare against the stage's `usd` / `soft_usd` in `kernel/stages/lite.yaml`.
4. Stop the run deliberately with `./factory job cancel <job-id>` rather than waiting.

Remember that retries cost twice: a build stage may run up to `max_rounds` attempts, and each attempt is
billed. A job oscillating between `failed` and `running` is the expensive failure mode to watch for.

## 4. Routine operations

```bash
./factory project list
./factory project status <name>
./factory job list
./factory job status <job-id>
./factory job cancel <job-id>
./factory provenance verify        # audit the commit history before a release or an audit
```

## 5. The file tree is the system

- **Source of truth:** `projects/<p>/jobs/<id>/events.jsonl` (append-only).
- **Derived, disposable:** `job.json`, `state/index.json`, board/dashboard views.
- **Never hand-edit events.** If history must change, it changes as a new audited event.
- **Never hand-edit kernel-owned policy files** (`authorizations.json`) without going through schema
  validation — `doctor` treats a malformed one as an error, for good reason.
- **Backups:** back up `projects/`, `state/`, and `kernel/` together; the event logs are the irreplaceable part.

## 6. Escalation to a maintainer

Escalate when `doctor` cannot repair the tree, the chain fails to verify, or a schema migration does not apply cleanly. Attach: `doctor` output, the failing `events.jsonl` excerpt (secrets scrubbed), and the exact commands run.

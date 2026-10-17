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
- **Network roots** — warns that network filesystems are unsupported for concurrent mode.

```bash
./factory doctor
```

Treat any warning as actionable: fix the underlying cause before starting new jobs.

## 2. Rebuilding derived state: `factory reindex`

`state/index.json` is derived and disposable. If it looks stale or was deleted:

```bash
./factory reindex
```

This rebuilds the index from the event logs. It never touches `events.jsonl`. Safe to run at any time.

## 3. Recovery procedures

### 3.1 The process was killed mid-attempt

1. The attempt is marked `interrupted` (a crash is **never** treated as success).
2. Resume restores the worktree to the **last accepted checkpoint SHA** — it does not rerun on a possibly dirty tree.
3. For `effects: external` stages, read the **effect journal**: completed effects are not repeated; incomplete effects run the stage's declared `compensate` action or require a human gate.
4. Run `./factory doctor` to confirm the tree is consistent.

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

## 4. Routine operations

```bash
./factory project list
./factory project status <name>
./factory job list
./factory job status <job-id>
./factory job cancel <job-id>
```

## 5. The file tree is the system

- **Source of truth:** `projects/<p>/jobs/<id>/events.jsonl` (append-only).
- **Derived, disposable:** `job.json`, `state/index.json`, board/dashboard views.
- **Never hand-edit events.** If history must change, it changes as a new audited event.
- **Backups:** back up `projects/`, `state/`, and `kernel/` together; the event logs are the irreplaceable part.

## 6. Escalation to a maintainer

Escalate when `doctor` cannot repair the tree, the chain fails to verify, or a schema migration does not apply cleanly. Attach: `doctor` output, the failing `events.jsonl` excerpt (secrets scrubbed), and the exact commands run.

# Schema change log

Per spec §27 ("every schema change is versioned with a migration"), each change
to a file under `kernel/schemas/` is recorded here with its migration.

The schema files do not carry an explicit `version` field yet; this log is the
interim record until schemas are versioned in their `$id` (planned for P1).

## `job.schema.json`

### 2026-10-16 — document rework fields on `approval`
- **Change:** added `decision` and `feedback` to the `approval` object's
  `properties`. Both were already accepted (the object has no
  `additionalProperties: false`), so this only makes the shape explicit.
- **Reason:** the fold now sets `approval` from *every* `human.approval` event —
  `decision` is `"approved"` or `"changes_requested"`, and `feedback` carries the
  human's note on a rework request. The Solo dashboard's "Change this…" action
  writes both.
- **Migration:** none required. Approved snapshots keep `by`/`sha`/`ts`; only
  rework snapshots add the two new keys.

### 2026-10-16 — add SHA-bound `approval`
- **Change:** added optional `approval` (`["object", "null"]`) with `by`, `sha`,
  `ts`; the event fold sets it from `human.approval` events.
- **Reason:** P1 SHA-bound approval needs the approved checkpoint SHA in the job
  snapshot so a changed result is visibly unapproved.
- **Migration:** none required. Existing snapshots omit `approval`; the fold now
  always emits `approval: null` for them, and `additionalProperties` still holds.

### 2026-10-16 — `lease` may be `null`
- **Change:** `lease` is now `["object", "null"]` instead of `"object"`.
- **Reason:** the event fold sets `lease: null` whenever no lease is held, so the
  strict schema rejected every freshly created job snapshot. Caught by the P0
  test suite.
- **Migration:** none required for existing data. Snapshots already stored
  `lease: null`; they merely failed validation under the old schema. No field
  renamed, no stored file rewritten.

## `event.schema.json`

- No changes yet.

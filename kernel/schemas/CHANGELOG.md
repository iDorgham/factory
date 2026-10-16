# Schema change log

Per spec §27 ("every schema change is versioned with a migration"), each change
to a file under `kernel/schemas/` is recorded here with its migration.

The schema files do not carry an explicit `version` field yet; this log is the
interim record until schemas are versioned in their `$id` (planned for P1).

## `job.schema.json`

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

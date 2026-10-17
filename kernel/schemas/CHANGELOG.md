# Schema change log

Per spec §27 ("every schema change is versioned with a migration"), each change
to a file under `kernel/schemas/` is recorded here with its migration.

The schema files do not carry an explicit `version` field yet; this log is the
interim record until schemas are versioned in their `$id` (planned for P1).

## `budget.schema.json` / `price_table.schema.json`

### 2026-10-17 — new file types (`P2.2 budgets and metering`)
- **Change:** two new schemas. `budget.schema.json` validates a stage budget
  object (`tokens`, `usd` = hard limit, `minutes`, optional `soft_usd` = soft
  limit; unknown keys rejected). `price_table.schema.json` validates the
  per-tier table in `factory.json` (`input_per_1m`/`output_per_1m`/
  `cached_per_1m`, all `>= 0`, tiers are free-form names plus the required
  fallback `default`).
- **Reason:** budgets move from "declared" to "enforced" (P2 gap #4). The
  kernel converts reported usage to cost with the price table, checks it
  against the stage's soft/hard limits, and records `budget.json` per attempt
  plus `budget.soft_exceeded` / `budget.hard_exceeded` events on breach.
  Canonical key names stay `usd`/`soft_usd` because shipped profiles already
  use them; the runtime vocabulary (`soft_limit`/`hard_limit`) is defined in
  the schema descriptions, mapping documented there.
- **Migration:** none required. `soft_usd` is optional; stages without it get
  a deterministic soft limit of `0.8 x usd` (rounded to cents).

## `event.schema.json`

### 2026-10-17 — budget event semantics noted (`P2.2 budgets and metering`)
- **Change:** no shape change. The enum values `budget.soft_exceeded` and
  `budget.hard_exceeded` were pre-provisioned in P0; this entry records their
  first producer (P2.2 budgets module) and consumer (engine attempt
  lifecycle, doctor). No `budget.checked` event will be added: per-attempt
  cost lives in the attempt's `budget.json` (events fire only on breach, per
  the Solo three-element promise).
- **Migration:** none.

## `authorizations.schema.json`

### 2026-10-17 — new file type (`P2.1 guards`)
- **Change:** new schema for a kernel-owned per-job `authorizations.json`
  (`allowed_test_deletions`, `allowed_dep_changes` — exact-path arrays, plus
  optional `reason`/`authorized_by`).
- **Reason:** guard authorization must be structurally validated, not parsed
  out of `plan.md` prose (spec §9.3: "without an explicit plan task that
  authorizes it"). The engine loads it from the job directory and validates it
  before any guard runs; a structurally invalid file fails hard rather than
  silently meaning "no authorization".
- **Migration:** none required. New optional file; absence is the empty default.

## `event.schema.json`

### 2026-10-17 — guard events (`P2.1 guards`)
- **Change:** added `guards.completed` and `guard.violation` to the event-type
  enum.
- **Reason:** guards (spec §9.3) run per attempt as kernel functions over the
  diff; their verdicts become first-class events like checks (`checks.completed`
  symmetry). Violations also feed the attempt fingerprint so a repeated
  identical violation triggers the existing stalled detection instead of
  burning every retry round.
- **Migration:** none required. Enum extension only; old logs contain neither
  type.

## `job.schema.json`

### 2026-10-16 — blocking-question ledger (`questions`)
- **Change:** added an optional `questions` array; each item carries `id`,
  `text`, `kind`, `options`, `stage`, `attempt`, `ts`, `answered`, `answer`.
- **Reason:** the Solo question budget (P1): the engine records adapter
  `question` events as `job.question_asked`, the fold surfaces them for the
  dashboard question card, and `human.answer` marks them answered.
- **Migration:** none required. The fold always emits `questions` (empty for
  older jobs), and the field is optional.

### 2026-10-16 — git checkpoints (`commit`) and the merge record (`merge`)
- **Change:** added `commit` (`["string", "null"]`) to each `checkpoints` item,
  and a new `merge` property (`["object", "null"]`) with `event`, `branch`,
  `base`, `merge_commit`, `conflicts`, `mode`, and `sha`.
- **Reason:** real git worktrees (spec §6, §7.1): each accepted attempt now
  records a checkpoint **commit** used to restore the worktree on resume, while
  the existing `sha` (content hash) still binds approval. The fold sets `merge`
  from `merge.completed` / `merge.conflict` / `merge.undone` so the dashboard can
  offer Undo.
- **Migration:** none required. `commit` is nullable, so older checkpoints
  without it still validate, and `merge` defaults to `null`.

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

### 2026-10-16 — blocking-question event
- **Change:** added `job.question_asked` to the event-type enum.
- **Reason:** the Solo question budget (P1): the engine records each adapter
  `question` event durably so questions survive resume, count against the
  per-job budget, and fold into the dashboard question card.
- **Migration:** none required; the enum only widens.

### 2026-10-16 — merge-queue events
- **Change:** added `merge.completed`, `merge.conflict`, and `merge.undone` to
  the event-type enum.
- **Reason:** the merge queue (§199) and Undo (§21.2) record their outcomes as
  events so they fold into the job snapshot and survive `reindex`.
- **Migration:** none required; the enum only widens.

- No other changes yet.

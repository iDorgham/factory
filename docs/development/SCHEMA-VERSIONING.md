# Schema Versioning & Migrations

**Related:** [Coding standards](CODING-STANDARDS.md) · [Architecture §2](../architecture/ARCHITECTURE.md) · [Runbook](../operations/RUNBOOK.md)

Every file format in the factory has a JSON Schema in `kernel/schemas/`, validated on every kernel write. Schemas are versioned, and every change is recorded.

---

## 1. Schemas in the tree

| Schema | Validates |
|--------|-----------|
| `event.schema.json` | Each line of `events.jsonl` — the source of truth |
| `job.schema.json` | The derived `job.json` snapshot |
| `project.schema.json` | `project.json` (mode, domain, profile, policy overrides) |
| `context.manifest.schema.json` | `context.manifest.json` built before every attempt |
| `authorizations.schema.json` | A job's kernel-owned `authorizations.json` — exact-path guard allowlists |
| `budget.schema.json` | A stage `budget` object (`tokens`, `usd` hard limit, `minutes`, optional `soft_usd`) |
| `price_table.schema.json` | The `price_table` block inside the global `factory.json` |

Validation uses Draft 2020-12 via `SchemaStore` (`kernel/src/factory_kernel/schemas.py`); all seven
kinds are registered there. An invalid document **never reaches disk**: the write path validates first and
raises `SchemaError` otherwise.

`kernel/schemas/CHANGELOG.md` records every schema change with its rationale and migration. Note the
current limitation: the schema files carry no `version` field yet, so that log — not a version number —
is the record of what changed. Adding `$id` versioning is deferred (see
[context gap #8](../context/PROJECT-CONTEXT.md)).

## 2. Versioning rules

| Change | Kind | Requirement |
|--------|------|-------------|
| Add an **optional** property | Minor | Update schema + CHANGELOG; existing files stay valid |
| Add a **required** property | Major | Migration required; every existing file must be upgraded |
| Widen a constraint (enum value, type union) | Minor | Update schema + CHANGELOG |
| Narrow/rename/remove a property | Major | Migration required |
| Change semantics without changing shape | Major | Migration or a documented re-interpretation with a repair path |

The rule of thumb: **if an existing valid file could become invalid, it's a major change and needs a migration.**

## 3. Adding a schema for a new file type

1. Create `kernel/schemas/<kind>.schema.json` (Draft 2020-12, `$schema`, `title`, `type`, `required`, `additionalProperties` as appropriate).
2. Register the kind in `SchemaStore` if it needs explicit wiring.
3. Call `schemas.validate("<kind>", obj)` on the write path **before** persisting.
4. Add a test to `tests/test_schemas.py`: one valid document passes, one invalid document is rejected on the write path.
5. Record the addition in `kernel/schemas/CHANGELOG.md`.
6. Update [Architecture §2](../architecture/ARCHITECTURE.md) if the file is part of the state model.

Two worked examples of the two shapes you will meet:

- **A kernel-owned file** (`authorizations.json`) is loaded and validated before anything reads it, and its
  absence means the empty default rather than an error.
- **A configuration block** (`price_table` inside `factory.json`) is validated at load time and is *not*
  a standalone file — the kind name exists only for validation.

**Validation-time-only kinds are the norm for anything that can make a safeguard weaker.** If an
invalid authorization file or price table can reach the kernel, a guard or a budget silently stops
working; rejecting it at load is the whole point.

## 4. Changing an existing schema

1. Decide minor vs major (table above).
2. Update the schema file.
3. **Minor:** no migration. Add a CHANGELOG entry and a test for the new optional field.
4. **Major:**
   - Write a migration that reads old files, transforms them, and writes valid new ones atomically (`atomic.atomic_write_json`).
   - Provide a dry-run/verify mode and wire it into `factory doctor` so operators can detect and repair drift.
   - Bump the version and document the rationale in the CHANGELOG.
   - Consider whether events (immutable, append-only) need a **synthetic migration event** rather than rewriting history. History must never be silently rewritten — see [Architecture §2.1](../architecture/ARCHITECTURE.md).
5. Update every producer (`state.py`, `kernel.py`, `engine.py`) and every test.

## 5. Events are special

`events.jsonl` is append-only and is the source of truth. Prefer these strategies, in order:

1. **Additive event fields** — new optional keys in `data`; old readers ignore them.
2. **New event type** — emit a new `type` with its own required fields; folds that don't know it ignore it.
3. **Synthetic import/migration event** — for genuine shape changes (as in the 2.1 → 3.0 migration), emit an `imported`/migration event that establishes the new baseline, rather than editing old lines.

Never edit or delete existing event lines except through an explicit, audited repair.

## 6. Checklist

- [ ] Schema updated and validates in a test
- [ ] `kernel/schemas/CHANGELOG.md` entry with version + rationale
- [ ] Migration written, dry-run/verify capable, and reachable from `factory doctor` (major changes only)
- [ ] All producers updated; all tests updated
- [ ] Existing files remain readable, or are upgraded by the migration
- [ ] [Architecture](../architecture/ARCHITECTURE.md) and spec updated if behavior changed

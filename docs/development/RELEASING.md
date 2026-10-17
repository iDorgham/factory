# Releasing

**Related:** [Contributing](CONTRIBUTING.md) · [Testing](TESTING.md) · [Roadmap](../plans/ROADMAP.md)

---

## 1. Versioning

The package is `factory-kernel` (see `pyproject.toml`). Versions track the **specification version**, with a patch component for fixes:

```
<spec-major>.<spec-minor>.<patch>      e.g. 0.4.0
```

- A new roadmap phase that changes behavior bumps the minor version.
- Schema/behavior-breaking changes bump the major version.
- Fixes and docs-only work bump the patch version.

The version lives in `pyproject.toml` (`[project].version`).

## 2. Changelog

The root [`CHANGELOG.md`](../../CHANGELOG.md) follows [Keep a Changelog](https://keepachangelog.com/) and is updated **in the same PR** as the change, under an `## [Unreleased]` section.

Categories: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`.

## 3. Release checklist

1. **Suite green**
   ```bash
   pip install -e ".[dev]"
   python -m pytest
   python -m flake8 kernel/src tests
   ```
   A deliberately TDD-red slice may not be released: the phase does not close until its named failing
   tests are green (see [Testing §4](TESTING.md#4-tdd-red-slices-are-a-technique-not-an-accident)).
2. **Provenance clean** — the same check CI runs, plus your own local template:
   ```bash
   ./factory provenance verify
   ./factory provenance verify --range <last-tag>..HEAD
   ```
3. **Health check against a scratch tree**
   ```bash
   ./factory project create demo --mode solo --domain web
   ./factory job run demo "release smoke test"
   ./factory job execute <job-id>
   ./factory doctor     # must be clean
   ./factory reindex
   ```
   For a phase touching the engine, prove the full loop: run → execute → approve → merge → undo.
4. **Docs current** — [PRD](../product/PRD.md), [Architecture](../architecture/ARCHITECTURE.md), [README](../../README.md), and the relevant [plan](../plans/ROADMAP.md) reflect the behavior being released. Check that the plan checklist items are ticked, and that no doc claims a control is enforced when it is not.
5. **Schemas migrated** — if any schema changed, the migration exists, `doctor` can apply/verify it, and `kernel/schemas/CHANGELOG.md` has an entry ([Schema versioning](SCHEMA-VERSIONING.md)).
6. **Bump the version** in `pyproject.toml`.
7. **Finalize the changelog** — move `[Unreleased]` items under the new version with today's date (ISO-8601).
8. **Tag** the release: annotated tag `vX.Y.Z` with a summary message.
9. **Report** the highlights: phase advanced, test count, notable fixes — and any control that is still declared-but-not-enforced.

## 4. What "done" means per phase

Aligned with the [roadmap](../plans/ROADMAP.md) definition of done:

| Phase | A release is ready when… |
|-------|--------------------------|
| P0 | All kernel invariants enforced and tested; snapshot repair works; chain verification passes |
| P1 | A beginner can type one sentence and get a previewable, checked result with ≤ 2 approval clicks |
| P2 | The factory can run unattended without exceeding budgets or performing ungated side effects |
| P3 | Measured improvement: later jobs pass more checks with fewer rounds on the same fixtures |
| P4 | Multiple people and adapters operate concurrently without corrupting each other's work |
| P5 | An enterprise can produce a verifiable audit trail and enforce RBAC, budgets, and change windows |

## 5. Rollback

- The kernel is packaged (`factory-kernel`) and installed from this tree rather than pulled from an index, so rollback means reverting to the previous commit or tag and reinstalling: `pip install -e .` from that checkout. Verify with `./factory provenance verify --range <tag>..HEAD` that no provenance-exempted commit slipped into the range.
- State is forward-migrated by schema changes; a **backward** migration is only guaranteed if the release notes say so. Prefer additive schema changes to keep downgrade paths open.
- Approval and audit history is never rewritten — rollbacks are recorded as events like any other action.

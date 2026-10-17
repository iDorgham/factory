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
2. **Health check against a scratch tree**
   ```bash
   ./factory project create demo --mode solo --domain web
   ./factory job run demo "release smoke test"
   ./factory doctor     # must be clean
   ./factory reindex
   ```
3. **Docs current** — [PRD](../product/PRD.md), [Architecture](../architecture/ARCHITECTURE.md), and the relevant [plan](../plans/ROADMAP.md) reflect the behavior being released. Check that the plan checklist items are ticked.
4. **Schemas migrated** — if any schema changed, the migration exists and `doctor` can apply/verify it ([Schema versioning](SCHEMA-VERSIONING.md)).
5. **Bump the version** in `pyproject.toml`.
6. **Finalize the changelog** — move `[Unreleased]` items under the new version with today's date (ISO-8601).
7. **Tag** the release: annotated tag `vX.Y.Z` with a summary message.
8. **Report** the highlights: phase advanced, test count, notable fixes.

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

- The kernel is distributed as a package, so rollback is `pip install factory-kernel==<previous>`.
- State is forward-migrated by schema changes; a **backward** migration is only guaranteed if the release notes say so. Prefer additive schema changes to keep downgrade paths open.
- Approval and audit history is never rewritten — rollbacks are recorded as events like any other action.

# Coding Standards

**Related:** [Contributing](CONTRIBUTING.md) · [Development guide](DEVELOPMENT.md) · [Testing](TESTING.md)

---

## 1. Language and tooling

| Setting | Value |
|---------|-------|
| Language | Python ≥ 3.11 |
| Formatter/linter | `flake8` (config in `.flake8`) |
| Max line length | 100 |
| Ignored rules | `E203`, `W503` |
| Excluded | `.git`, `__pycache__`, `build`, `dist`, `.work`, `.venv` |

Run before every commit:

```bash
python -m flake8 kernel/src tests
```

## 2. Style conventions

- 4-space indentation; no tabs. `.editorconfig` and `.gitattributes` are authoritative for line endings (LF in the repo).
- `from __future__ import annotations` at the top of modules that use modern type syntax.
- Type hints on public functions and methods; `Union[str, Path]` for path parameters that accept both.
- Prefer `pathlib.Path` over string path manipulation.
- Docstrings: one-line summary; add a body only when the behavior is non-obvious (see `atomic.py`, `lease.py`).
- Imports grouped stdlib → third-party → local, blank-line separated.

## 3. Naming

| Kind | Convention | Example |
|------|-----------|---------|
| Modules | `snake_case` | `kernel.py`, `atomic.py` |
| Classes | `PascalCase` | `Kernel`, `JobState`, `LeaseManager` |
| Functions/methods | `snake_case` | `atomic_write_json`, `append_event` |
| Constants | `UPPER_SNAKE` | `MAX_OUTPUT_LINES`, `GUARD_TIMEOUT_SECONDS` |
| Errors | `<Area>Error` | `KernelError`, `LeaseError`, `SchemaError` |
| Private helpers | leading underscore | `_fsync_dir`, `_doctor_job` |

## 4. Kernel-specific rules (enforced by review)

1. **Single writer for state.** Only `JobState` appends to `events.jsonl`; only the `Kernel` mutates project/job state via that path.
2. **Atomic I/O only.** All persistent writes use `atomic.atomic_write*` / `append_jsonl`. Direct `open(..., "w")` on state is a defect.
3. **Validate before persisting.** Every kernel write passes through `SchemaStore.validate(kind, obj)`.
4. **Explicit transitions.** State changes go through the transition table; never assign a state string directly.
5. **Fencing is mandatory.** Any state write performed under a lease carries the current fencing token and rejects stale tokens.
6. **Determinism.** No `datetime.now()` without timezone UTC, no `random`, no network, no environment-dependent branching in the kernel.
7. **Errors are typed.** Raise the module's `*Error` subclass with a clear message; do not `assert` on runtime input.
8. **Time formatting.** ISO-8601 UTC everywhere (`_iso` helpers already do this).
9. **Paths.** Accept `Union[str, Path]`, normalize with `Path(...)`, and never assume POSIX separators.

## 5. Adapters and roles

- Adapters translate only; they must not read or write state, and must respect the write boundary (attempt dir + worktree).
- Role definitions (`roles/*.md`) are contracts: change them deliberately and update the [Architecture](../architecture/ARCHITECTURE.md) role table when the contract changes.
- Stage profiles (`kernel/stages/*.yaml`) must validate against `profiles.validate_profile`; new keys need loader support.

## 6. Schemas

- Every file format has a JSON Schema in `kernel/schemas/`, Draft 2020-12.
- Additive changes are a minor bump; removals/renames are a major bump with a migration. See [Schema versioning](SCHEMA-VERSIONING.md).
- `kernel/schemas/CHANGELOG.md` records every schema change.

## 7. Comments and TODOs

- Comment the *why*, not the *what*.
- Use `TODO(<phase>):` so work is traceable to the [roadmap](../plans/ROADMAP.md), e.g. `# TODO(P1): replace placeholder worktree with git worktree add`.
- No commented-out code in commits.

## 8. Documentation in code

- Module docstrings state the module's single responsibility.
- Public APIs in `kernel.py`, `state.py`, `lease.py`, and `atomic.py` document invariants (atomicity, fencing, ordering) explicitly — these are the load-bearing contracts.

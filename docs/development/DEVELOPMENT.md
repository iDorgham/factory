# Development Guide

**Audience:** contributors working on the kernel, adapters, roles, and schemas.
**Related:** [Contributing](CONTRIBUTING.md) · [Coding standards](CODING-STANDARDS.md) · [Testing](TESTING.md) · [Releasing](RELEASING.md)

---

## 1. Prerequisites

| Requirement | Version |
|-------------|---------|
| Python | ≥ 3.11 |
| pip | current |
| git | current (worktree isolation, P1+) |

The kernel has no runtime dependencies beyond `PyYAML` and `jsonschema`.

## 2. Setup

```bash
git clone <repo-url> factory
cd factory

python -m venv .venv
# Windows (PowerShell): .\.venv\Scripts\Activate.ps1
# POSIX:               source .venv/bin/activate

pip install -e ".[dev]"     # installs kernel + pytest + flake8, editable
```

Editable install maps the `factory` console script to `factory_kernel.cli:main` and points the package at `kernel/src`.

## 3. Repository layout

```
factory/
├── factory.json                 # global config (price table, sandbox, budget defaults)
├── factory                      # CLI launcher (dev convenience)
├── pyproject.toml               # packaging + pytest + flake8 config
├── kernel/
│   ├── schemas/                 # JSON Schemas for every file type
│   ├── presets/                 # solo.json / team.json / enterprise.json
│   ├── stages/                  # lite.yaml, standard.yaml
│   └── src/factory_kernel/      # the Python reference kernel
├── tests/                       # hermetic pytest suite
├── roles/                       # markdown role contracts
├── adapters/                    # per-tool translators
├── projects/<name>/             # runtime state (git-ignored in practice)
└── state/index.json             # derived, rebuildable
```

Full module map: [Architecture §4](../architecture/ARCHITECTURE.md).

## 4. Everyday commands

```bash
# Test + lint
python -m pytest
python -m pytest tests/test_kernel.py -k transition
python -m flake8 kernel/src tests

# Run the CLI against a scratch tree (never against a real project tree while iterating)
./factory project create demo --mode solo --domain web
./factory job run demo "Build a landing page with hero and contact form"
./factory job list
./factory job status <job-id>
./factory doctor
./factory reindex
```

## 5. Editing rules that bite

1. **All disk writes go through `atomic.py`.** Never call `open(..., "w")` on state files directly — atomicity and cross-platform safety live in one place.
2. **Only `state.py` appends events.** If you need a new event type, add it to `kernel/schemas/event.schema.json` and emit it from `JobState`, not from a caller.
3. **Every new file type gets a schema** and is validated on write via `SchemaStore`.
4. **Transitions are declared, not implied.** Add to the transition table in `state.py` and to the spec; illegal moves must raise.
5. **The kernel stays deterministic and dependency-light.** No network calls, no clocks beyond `datetime.now(timezone.utc)`, no randomness outside ULID timestamps.

## 6. Debugging

| Symptom | First move |
|---------|-----------|
| State looks wrong | `./factory doctor` — it folds events and reports divergence |
| Snapshot corrupt | `./factory doctor` repairs `job.json` from the event fold |
| Index stale | `./factory reindex` |
| A test fails only on Windows | Check path handling and `_fsync_dir` (directory fsync is skipped on Windows) |
| Lease stuck | Inspect the job's lock file; a stale guard is stolen on the next acquire |

See [Troubleshooting](../operations/TROUBLESHOOTING.md) and the [Runbook](../operations/RUNBOOK.md) for procedures.

## 7. Definition of a good change

- Tests added or updated, suite green, `flake8` clean.
- Provenance trailers (`AI-Tool`, `AI-Model`) on every commit (see [Contributing §3.1](CONTRIBUTING.md)).
- Schemas updated with a migration note if a format changed ([Schema versioning](SCHEMA-VERSIONING.md)).
- Docs updated: [PRD](../product/PRD.md) for behavior, [Architecture](../architecture/ARCHITECTURE.md) for internals, the relevant [plan](../plans/ROADMAP.md) checklist for progress.
- No secrets, no non-atomic writes, no new runtime dependencies without justification.

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
├── factory                      # CLI launcher (dev convenience; no install required)
├── pyproject.toml               # packaging + pytest + flake8 config
├── .githooks/commit-msg         # opt-in local provenance enforcement
├── .gitmessage                  # commit template (provenance trailers pre-filled)
├── .provenance-allow            # grandfathered pre-convention commits
├── .github/workflows/           # CI: lint + test, plus the provenance gate
├── CHANGELOG.md CONTRIBUTING.md SECURITY.md
├── docs/                        # the documentation set (index: docs/README.md)
├── kernel/
│   ├── schemas/                 # 7 JSON Schemas for every file type + their change log
│   ├── presets/                 # solo.json / team.json / enterprise.json
│   ├── stages/                  # lite.yaml, standard.yaml
│   └── src/factory_kernel/      # the Python reference kernel (20 modules)
├── tests/                       # hermetic pytest suite (24 modules)
│   └── fixtures/adapters/       # slow, fake-browser, cli-echo-agent, cli-ask-agent, budget-burner
├── roles/                       # markdown role contracts (5 starter)
├── adapters/                    # echo, cli-agent (adapters) + visual-capture (a check producer)
├── projects/<name>/             # runtime state (git-ignored in practice)
├── .work/<job-id>/              # per-job git worktree on branch factory/<job-id>
└── state/index.json             # derived, rebuildable
```

Full module map: [Architecture §4](../architecture/ARCHITECTURE.md).

## 4. Everyday commands

```bash
# Test + lint (lint exactly as CI runs it)
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

# Adapters and provenance
./factory adapter test cli-agent      # conformance suite for the live backend
./factory provenance verify           # every commit carries its AI-Tool / AI-Model trailers
```

> **A red suite is not always a regression.** A phase may land a slice TDD-red on purpose: the failing
> tests are the contract for the next slice. The current one is P2.2 budget engine/doctor wiring — see
> [the roadmap](../plans/ROADMAP.md) and [P2 plan](../plans/P2-trust-layer.md). Read the failing test names
> before assuming something broke.

## 5. Editing rules that bite

1. **All disk writes go through `atomic.py`.** Never call `open(..., "w")` on state files directly — atomicity and cross-platform safety live in one place.
2. **Only `state.py` appends events.** If you need a new event type, add it to `kernel/schemas/event.schema.json` and emit it from `JobState`, not from a caller.
3. **Every new file type gets a schema** and is validated on write via `SchemaStore`.
4. **Transitions are declared, not implied.** Add to the transition table in `state.py` and to the spec; illegal moves must raise.
5. **The kernel stays deterministic and dependency-light.** No network calls, no clocks beyond `datetime.now(timezone.utc)`, no randomness outside ULID timestamps.
6. **`guards.py` and `budgets.py` are pure.** No file I/O, no subprocess, no network, no clock. They return verdicts as data; the engine turns those into events and writes files. This split is what makes both testable without a factory tree.
7. **Fail hard on anything a safeguard depends on.** An unknown guard id, a malformed `authorizations.json`, or a usage key with no matching price tier must raise — a safeguard that silently degrades into a no-op is worse than one that is absent, because it looks present.
8. **Authorization is structural.** `authorizations.json` is kernel-owned, schema-validated, and exact-path only; never parse allowlists out of `plan.md` prose.

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

- Tests added or updated, suite green, `flake8` clean. (If a red test is the *point* of the slice, say so
  in the commit body and link the plan item.)
- Provenance trailers (`AI-Tool`, `AI-Model`) on every commit — verified locally by
  `./factory provenance verify` and by CI (see [Contributing §3.1](CONTRIBUTING.md)).
- Schemas updated with a migration note if a format changed ([Schema versioning](SCHEMA-VERSIONING.md)).
- Docs updated: [PRD](../product/PRD.md) for behavior, [Architecture](../architecture/ARCHITECTURE.md) for internals, the relevant [plan](../plans/ROADMAP.md) checklist for progress, and [CHANGELOG.md](../../CHANGELOG.md) for the change itself.
- No secrets, no non-atomic writes, no new runtime dependencies without justification.
- Anything documented as shipped must actually be enforced in code — the reverse is the failure mode this
  repository keeps working to eliminate.

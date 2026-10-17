# Testing

**Related:** [Contributing](CONTRIBUTING.md) · [Coding standards](CODING-STANDARDS.md) · [Runbook](../operations/RUNBOOK.md)

---

## 1. Running the suite

```bash
pip install -e ".[dev]"
python -m pytest                       # whole suite
python -m pytest tests/test_state.py   # one module
python -m pytest -k fence              # by keyword
python -m pytest -x -vv                # stop on first failure, verbose
```

Pytest config lives in `pyproject.toml`: `testpaths = ["tests"]`, `pythonpath = ["kernel/src"]`, `addopts = "-q"`.

## 2. The hermetic principle

Tests **must never** touch a real project tree, network, or the developer's home directory. Every test builds a throwaway factory in `tmp_path` from the *real* schemas, presets, and stages, so schema/profile regressions surface immediately without depending on runtime state.

The fixtures in `tests/conftest.py`:

| Fixture | Provides |
|---------|----------|
| `repo_root` | Repository root (session-scoped) |
| `schemas_dir` | `kernel/schemas` (session-scoped) |
| `factory_root` | Temp tree with `kernel/{schemas,presets,stages}`, `adapters/`, and `factory.json` copied in |
| `kernel` | A `Kernel` bound to `factory_root` |
| `demo_job` | A created project + a freshly created job |

Use these fixtures rather than reimplementing setup.

## 3. Current coverage map

| Module | Test file | Focus |
|--------|-----------|-------|
| `atomic.py` | `test_atomic.py` | temp→rename, JSON/JSONL round-trips, durability |
| `ulid.py` | `test_ulid.py` | format, ordering, validation |
| `hashing.py` | `test_hashing.py` | event hash stability, content hashing |
| `lease.py` | `test_lease.py` | acquire/renew/release, fencing tokens, stale guard |
| `state.py` | `test_state.py` | append/fold/verify, snapshot write, chain tamper detection |
| transitions | `test_transitions.py` | legal vs illegal state moves |
| `profiles.py` | `test_profiles.py` | YAML validation, stage/profile shape |
| `schemas.py` | `test_schemas.py` | valid/invalid documents on the write path |
| `kernel.py` | `test_kernel.py` | project/job lifecycle, cancel, status/list |
| `doctor` | `test_doctor.py` | chain verification, snapshot repair, lease/worktree warnings |
| `engine.py` | `test_engine.py` | run orchestration, attempt handling, gates |
| `checks.py` | `test_checks.py` | required/optional, trimming, fingerprints |
| `context.py` | `test_context.py` | manifest building, token budgets, degradation |
| `adapters.py` | `test_adapters.py` | discovery, selection, run contract, write boundary |

## 4. What a good test looks like

- **Deterministic:** no `sleep` races, no reliance on wall-clock ordering beyond ULIDs, no network.
- **Isolated:** uses `tmp_path` / `factory_root`; leaves nothing behind.
- **Behavioral:** asserts on the invariant, not on internal implementation details.
- **Adversarial where it matters:** for state code, deliberately attempt the illegal thing (stale fence write, illegal transition, tampered event chain) and assert rejection.

### Example: testing an invariant

```python
def test_stale_fence_is_rejected(factory_root):
    from factory_kernel.kernel import Kernel
    from factory_kernel.lease import LeaseError

    k = Kernel(factory_root)
    k.project_create("demo", mode="solo", domain="web")
    job = k.job_run("demo", "x")
    # acquire a lease, capture the token, release, re-acquire (new token),
    # then assert a write carrying the old token is rejected.
```

## 5. Adding tests for new features

1. Put pure functions under unit tests in the matching `test_*.py`.
2. For a new event type or state: add a transition/round-trip test **and** a schema-validation test.
3. For a new adapter: add discovery/selection tests plus the conformance path (see [Adapters guide](ADAPTERS.md)).
4. For a new check kind: extend `test_checks.py` with required/optional and fingerprint-stability cases.
5. For the build loop (P1+): test fingerprint stability, `stalled` detection, checkpoint recovery, and `interrupted`-is-never-success.

## 6. Lint

```bash
python -m flake8 kernel/src tests
```

Lint is part of the definition of done and runs in CI alongside the suite.

## 7. Manual verification against a real tree

After changes to state, leases, or `doctor`, verify against a scratch tree:

```bash
./factory project create demo --mode solo --domain web
./factory job run demo "smoke test"
./factory doctor     # expect clean
./factory reindex    # rebuild derived state
```

Details and recovery scenarios: [Runbook](../operations/RUNBOOK.md).

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

**437 collected** at `77f32e9` (the task player's review round): **435 passed, 2 skipped, 0 failed** —
fully green.
The 2 skips are capability-gated conformance cases, not red contracts. If the suite is red on your
checkout of an in-progress slice, the failing test names are the next step's written contract, not
regressions; see [TDD-red slices](#4-tdd-red-slices-are-a-technique-not-an-accident).

| Module | Test file | Cases | Focus |
|--------|-----------|-------|-------|
| `atomic.py` | `test_atomic.py` | 8 | temp→rename, JSON/JSONL round-trips, durability |
| `ulid.py` | `test_ulid.py` | 5 | format, ordering, validation |
| `hashing.py` | `test_hashing.py` | 4 | event hash stability, content hashing |
| `lease.py` | `test_lease.py` | 12 | acquire/renew/release, fencing tokens, stale guard |
| `state.py` | `test_state.py` | 10 | append/fold/verify, snapshot write, chain tamper detection |
| transitions | `test_transitions.py` | 26 | legal vs illegal state moves (executable audit of the spec §7 matrix) |
| `profiles.py` | `test_profiles.py` | 17 | YAML validation, stage/profile shape |
| `schemas.py` | `test_schemas.py` | 10 | valid/invalid documents on the write path |
| `kernel.py` | `test_kernel.py` | 13 | project/job lifecycle, cancel, status/list |
| `doctor` | `test_doctor.py` | 6 | chain verification, snapshot repair, lease/worktree warnings |
| `engine.py` | `test_engine.py` | 21 | run orchestration, attempt handling, gates, guard hook |
| `checks.py` | `test_checks.py` | 9 | required/optional, trimming, fingerprints |
| `context.py` | `test_context.py` | 6 | manifest building, token budgets, degradation |
| `adapters.py` | `test_adapters.py` | 10 | discovery, selection, run contract, write boundary |
| `adapters/cli-agent` | `test_cli_agent.py` | 9 | live backend: NDJSON forwarding, failure classes, resume |
| `checkpoint.py` | `test_checkpoint.py` | 5 | content hash stability, SHA-bound approval |
| `conformance.py` | `test_conformance.py` | 5 | suite behaviour, capability-gated skips |
| `dashboard.py` | `test_dashboard.py` | 14 | view building, render, export, `dispatch` actions |
| `gitrepo.py` | `test_worktree.py` | 10 | worktrees, checkpoint commits, merge/conflict, undo, outer-checkout isolation |
| Solo question budget | `test_questions.py` | 9 | persistence, dedupe, ≤3 cap, answer→resume, validation |
| `visual-capture` | `test_visual_capture.py` | 16 | real producer (fake browser), theme probe, manifest, `changed_pct` |
| `guards.py` | `test_guards.py` | 40 | each guard, structural authorization, diff collection, engine hook, doctor authorizations |
| `budgets.py` | `test_budgets.py` | 24 | pricing, unpriced-usage error, soft/hard resolution, inclusive boundaries |
| `sandbox.py` | `test_sandbox.py` | 27 | schema validation, env sanitization, path containment, policy parsing, subprocess cwd/env contract, sandboxed engine run, doctor sandbox checks |
| `risk.py` | `test_risk.py` | 37 | `risk_scoring` schema/config contracts, signal scoring, ceiling bands, kernel-owned actions, config loading, engine gate wiring with `risk.computed`, doctor risk checks |
| `injection.py` | `test_injection.py` | 30 | `injection` schema contracts, kernel-owned baseline patterns, config loading, item scanning, manifest labeling, `injection.detected` events, the `injection_flagged` signal (weighted by `injection_flag`), doctor injection checks |
| `provenance.py` | `test_provenance.py` | 23 | trailer detection, grandfathering, allowlist, CLI |
| `cancel.py` | `test_cancel.py` | 8 | cancellable runs, process-tree termination, a cancelled job ending `cancelled` with the adapter dead |

Fixtures live in `tests/fixtures/adapters/`: `slow` (cancel/resume/heartbeat), `fake-browser.py`
(a stdlib headless-browser shim with a theme mapping *inverted* relative to the dev Edge, so the
runtime probe is genuinely exercised), `cli-echo-agent.py`, `cli-ask-agent.py` (ask modes), and
`budget-burner`, and `env-probe` (P2.3: reports the environment it can see and its cwd inside the
subprocess — kernel-recorded evidence for the sandbox tests).

## 4. TDD-red slices are a technique, not an accident

Within a phase, a slice may land with failing tests on purpose: the failing tests are the written
contract for the *next* slice, and shipping them first prevents "the test was written to match whatever
the code happened to do."

The rules that keep this honest:

1. The failing tests must be **named in the commit body** and linked to a plan item.
2. They must be **committed together with the slice they specify**, not left to drift.
3. `doctor` and lint stay clean; only the named tests are red.
4. The phase does not close until they are green.

If you are new to the repository and the suite is red, read the failing test names before you assume
something is broken. `python -m pytest -q` prints them in the summary.

## 5. What a good test looks like

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

## 6. Adding tests for new features

1. Put pure functions under unit tests in the matching `test_*.py`.
2. For a new event type or state: add a transition/round-trip test **and** a schema-validation test.
3. For a new adapter: add discovery/selection tests plus the conformance path (see [Adapters guide](ADAPTERS.md)).
4. For a new check kind: extend `test_checks.py` with required/optional and fingerprint-stability cases.
5. For the build loop: test fingerprint stability, `stalled` detection, checkpoint recovery, and `interrupted`-is-never-success.
6. For a new **guard**: test the violation *and* the authorized-silence path, plus the unknown-id fail-hard case. A guard that cannot be proven to stay quiet when authorized is not finished.
7. For a new **budget** rule: test the boundary itself (`==` soft, `==` hard) and the malformed-input path (unpriced usage, non-numeric counts, `soft_usd >= usd`).
8. For anything a dashboard action can do: assert the underlying kernel command, not the HTML. The page is a client; the command is the contract.

## 7. Lint

```bash
python -m flake8 kernel/src tests
```

Lint is part of the definition of done and runs in CI (`.github/workflows/ci.yml`) alongside the suite
and the provenance gate.

## 8. Manual verification against a real tree

Hermetic tests do not replace checking a real tree. After changes to state, leases, `doctor`, worktrees,
or the engine, verify against a scratch tree:

```bash
./factory project create demo --mode solo --domain web
./factory job run demo "smoke test"
./factory job execute <job-id>
./factory doctor     # expect clean
./factory reindex    # rebuild derived state
```

The P1 loop was proven this way end to end several times on real trees (run → execute → approve → merge
→ undo), which is the only way to know that the hermetic suite is not lying. Details and recovery
scenarios: [Runbook](../operations/RUNBOOK.md).

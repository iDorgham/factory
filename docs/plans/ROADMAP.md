# Roadmap — Enterprise AI Software Factory

**Related:** [PRD](../product/PRD.md) · [Architecture](../architecture/ARCHITECTURE.md) · [Specification v3.0](<../specification/Enterprise AI Software Factory — Specification v3.0.md>)

One engine, three presets (Solo / Team / Enterprise). Phases are ordered so that each depends only on what is already solid.

| Phase | Deliver | Status | Plan |
|-------|---------|--------|------|
| **P0 Kernel core** | `job.json` + `events.jsonl`, atomic writes, leases and fencing, schema validation, check runner, `factory doctor`, `factory reindex` | ✅ Implemented (236 collected: 234 passed, 2 skipped — shared suite) | [P0](P0-kernel-core.md) |
| **P1 Solo slice** | `lite` profile execution, adapter runtime + build loop, checkpoints + SHA-bound approval, conformance suite, `factory serve` dashboard, git worktrees + merge queue + Undo, live `cli-agent` backend, question budget, real visual capture | ✅ Complete — 236 collected: 234 passed, 2 skipped; proven end-to-end | [P1](P1-solo-slice.md) |
| **P2 Trust layer** | Budgets and metering, guards, sandbox hardening, injection handling, risk-scored gates, import with baseline verification | Planned | [P2](P2-trust-layer.md) |
| **P3 Learning** | Eval harness, skill packages and promotion, lessons ledger, repo map and memory | Planned | [P3](P3-learning.md) |
| **P4 Team** | More adapters via conformance suite, epics and dependencies, visual baselines, named users and reviewer assignment | Planned | [P4](P4-team.md) |
| **P5 Enterprise** | Control plane, RBAC, hash-chained audit and anchors, brand design systems with lint, compliance exports | Planned | [P5](P5-enterprise.md) |

## Ordering constraints

1. Do not build P4 or P5 features before P0 is solid and P1 is demonstrably reliable.
2. Every phase ends with the test suite green and `factory doctor` clean against a real tree.
3. New capabilities must default to off or to a zero-decision default in Solo mode.
4. Each phase updates this table and its plan file's checklist as work lands.

## Definition of done per phase

- **P0:** all kernel invariants enforced and tested; snapshot repair works; chain verification passes.
- **P1:** a beginner can type one sentence and get a previewable, checked result with ≤ 2 approval clicks.
- **P2:** the factory can be left running unattended without exceeding budgets or performing ungated side effects.
- **P3:** measurable improvement: later jobs pass more checks with fewer rounds than earlier ones on the same fixtures.
- **P4:** multiple people and multiple adapters operate concurrently without corrupting each other's work.
- **P5:** an enterprise can produce a verifiable audit trail and enforce RBAC, budgets, and change windows.

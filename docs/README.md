# Factory Documentation

**Enterprise AI Software Factory** — files are the protocol, events are the truth, a small kernel enforces, agents only propose.

## Structure

```
docs/
├── product/          # what we're building and why
├── architecture/     # how the system is designed
├── specification/    # canonical behavioral specification
├── plans/            # roadmap and per-phase implementation plans
├── development/      # contributor workflow, standards, testing, release
├── operations/       # running, recovering, and securing the factory
└── context/          # portable full-project briefing for other AI tools
```

## Product

| Document | Purpose |
|----------|---------|
| [PRD](product/PRD.md) | Product requirements: users, promises, features per mode, success metrics |

## Architecture & Specification

| Document | Purpose |
|----------|---------|
| [Architecture](architecture/ARCHITECTURE.md) | Design & architecture: layers, kernel internals, module map, data flow, invariants |
| [Specification v3.0](<specification/Enterprise AI Software Factory — Specification v3.0.md>) | Canonical specification (supersedes 2.1) — the source of truth for behavior |

## Plans

| Plan | Phase | Status |
|------|-------|--------|
| [Roadmap](plans/ROADMAP.md) | P0–P5 overview | Active |
| [P0 Kernel Core](plans/P0-kernel-core.md) | Safe state: events, leases, schemas, doctor | ✅ Implemented |
| [P1 Solo Slice](plans/P1-solo-slice.md) | Lite profile execution, adapter runtime, build loop, dashboard, worktrees + merge/undo, question budget, real visual capture | ✅ Complete (proven end-to-end; see P1 plan hardening log) |
| [P2 Trust Layer](plans/P2-trust-layer.md) | Budgets, guards, sandbox, risk-scored gates, import | In progress (P2.1 guards landed) |
| [P3 Learning](plans/P3-learning.md) | Eval harness, skill packages, lessons, memory | Planned |
| [P4 Team](plans/P4-team.md) | Multi-adapter, epics, visual baselines, named users | Planned |
| [P5 Enterprise](plans/P5-enterprise.md) | Control plane, RBAC, audit chain, brands, compliance | Planned |

## Development

| Document | Purpose |
|----------|---------|
| [Development guide](development/DEVELOPMENT.md) | Environment setup, dev workflow, debugging |
| [Contributing](development/CONTRIBUTING.md) | Process: branches, PRs, review, definition of done |
| [Coding standards](development/CODING-STANDARDS.md) | Python style, kernel rules, file I/O conventions |
| [Testing](development/TESTING.md) | Hermetic test strategy, fixtures, adding tests |
| [Adapters guide](development/ADAPTERS.md) | Building an adapter: manifest, run contract, conformance |
| [Schema versioning](development/SCHEMA-VERSIONING.md) | Adding/changing JSON Schemas with migrations |
| [Releasing](development/RELEASING.md) | Versioning, changelog, release checklist |

## Operations

| Document | Purpose |
|----------|---------|
| [Runbook](operations/RUNBOOK.md) | `doctor`, `reindex`, recovery procedures, lease/worktree maintenance |
| [Troubleshooting](operations/TROUBLESHOOTING.md) | Common failures and their fixes |
| [Security](operations/SECURITY.md) | Safety floor, threat model, secret handling, reporting |

## Context pack (for other AI tools)

| Document | Purpose |
|----------|---------|
| [Context README](context/README.md) | How to use this folder with Qwen, Grok, ChatGPT, Claude, etc. |
| [Project context](context/PROJECT-CONTEXT.md) | Full portable briefing: idea, architecture, features, roadmap, open questions |
| [History](context/HISTORY.md) | Complete git history and how work was ordered |
| [AI provenance](context/AI-PROVENANCE.md) | Which AI tool/model per phase (with honest gaps) |

## Source quick links

- Kernel source: `kernel/src/factory_kernel/`
- JSON Schemas: `kernel/schemas/`
- Policy presets: `kernel/presets/`
- Stage profiles: `kernel/stages/`
- Role contracts: `roles/`
- Adapters: `adapters/`
- Test suite: `tests/`

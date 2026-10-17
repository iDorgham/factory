# 🗂️ Factory Documentation

**Enterprise AI Software Factory** — files are the protocol, events are the truth, a small kernel
enforces, agents only propose.

> **If a document and the repository disagree, the repository wins.** These docs describe what the
> code does *today*; the [specification v3.0](specification/Enterprise%20AI%20Software%20Factory%20%E2%80%94%20Specification%20v3.0.md)
> describes what it *should* do. Where the two differ, the gap is stated rather than papered over.

**Snapshot:** 2026-10-17 at `1895f14` · **Status:** P0 and P1 complete · P2.1 guards landed · P2.2
budgets landed · **Suite:** 312 collected (310 passed, 2 skipped — fully green after the P2.2 close).

---

## 📂 Structure

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

Repository-level entry points live one level up: [`README.md`](../README.md) (overview and quick
start), [`CHANGELOG.md`](../CHANGELOG.md), [`CONTRIBUTING.md`](../CONTRIBUTING.md), and
[`SECURITY.md`](../SECURITY.md).

---

## 📄 Product

| Document | Purpose |
|----------|---------|
| [PRD](product/PRD.md) | Product requirements: users, promises, features per mode, success metrics |

## 🏗️ Architecture & Specification

| Document | Purpose |
|----------|---------|
| [Architecture](architecture/ARCHITECTURE.md) | Design & architecture: layers, kernel internals, module map, data flow, invariants |
| [Specification v3.0](<specification/Enterprise AI Software Factory — Specification v3.0.md>) | Canonical specification (supersedes 2.1) — the source of truth for behavior |

## 🗺️ Plans

| Plan | Phase | Status |
|------|-------|--------|
| [Roadmap](plans/ROADMAP.md) | P0–P5 overview | Active |
| [P0 Kernel Core](plans/P0-kernel-core.md) | Safe state: events, leases, schemas, doctor | ✅ Implemented |
| [P1 Solo Slice](plans/P1-solo-slice.md) | Lite profile execution, adapter runtime, build loop, dashboard, worktrees + merge/undo, question budget, real visual capture | ✅ Complete (proven end-to-end; see the P1 plan hardening log) |
| [P2 Trust Layer](plans/P2-trust-layer.md) | Budgets, guards, sandbox, risk-scored gates, import | 🚧 In progress — P2.1 guards landed; P2.2 budget schemas + cost math landed, engine/doctor wiring red |
| [P3 Learning](plans/P3-learning.md) | Eval harness, skill packages, lessons, memory | ⬜ Planned |
| [P4 Team](plans/P4-team.md) | Multi-adapter, epics, visual baselines, named users | ⬜ Planned |
| [P5 Enterprise](plans/P5-enterprise.md) | Control plane, RBAC, audit chain, brands, compliance | ⬜ Planned |

## 🛠️ Development

| Document | Purpose |
|----------|---------|
| [Development guide](development/DEVELOPMENT.md) | Environment setup, dev workflow, debugging |
| [Contributing](development/CONTRIBUTING.md) | Process: branches, PRs, review, provenance trailers, definition of done |
| [Coding standards](development/CODING-STANDARDS.md) | Python style, kernel rules, file I/O conventions |
| [Testing](development/TESTING.md) | Hermetic test strategy, fixtures, coverage map, adding tests |
| [Adapters guide](development/ADAPTERS.md) | Building an adapter: manifest, run contract, conformance, visual evidence |
| [Schema versioning](development/SCHEMA-VERSIONING.md) | Adding/changing JSON Schemas with migrations |
| [Releasing](development/RELEASING.md) | Versioning, changelog, release checklist |

## 🖥️ Operations

| Document | Purpose |
|----------|---------|
| [Runbook](operations/RUNBOOK.md) | `doctor`, `reindex`, recovery procedures, lease/worktree/guard maintenance |
| [Troubleshooting](operations/TROUBLESHOOTING.md) | Common failures and their fixes, including guard and budget triage |
| [Security](operations/SECURITY.md) | Safety floor, threat model, secret handling, reporting |

## 🧠 Context pack (for other AI tools)

| Document | Purpose |
|----------|---------|
| [Context README](context/README.md) | How to use this folder with Qwen, Grok, ChatGPT, Claude, etc. |
| [Project context](context/PROJECT-CONTEXT.md) | Full portable briefing: idea, architecture, features, roadmap, open questions |
| [History](context/HISTORY.md) | Complete git history and how work was ordered |
| [AI provenance](context/AI-PROVENANCE.md) | Which AI tool/model per phase (with honest gaps) |

---

## 🔗 Source quick links

| Path | What lives there |
|------|------------------|
| `kernel/src/factory_kernel/` | The reference kernel — 20 modules |
| `kernel/schemas/` | 7 JSON Schemas + `CHANGELOG.md` (the schema migration log) |
| `kernel/presets/` | `solo` / `team` / `enterprise` policy presets |
| `kernel/stages/` | `lite.yaml` and `standard.yaml` stage profiles |
| `roles/` | Markdown role contracts (5 starter) |
| `adapters/` | `echo`, the live `cli-agent` backend, and the `visual-capture` check producer |
| `tests/` | 24 hermetic test modules (312 cases) + adapter fixtures |

---

## 🧭 Where do I start?

| If you want to… | Read |
|-----------------|------|
| Understand the idea in 5 minutes | [README](../README.md) → *The one idea* |
| Know what the system must do | [Specification v3.0](<specification/Enterprise AI Software Factory — Specification v3.0.md>) |
| Know what the code does today | [Architecture](architecture/ARCHITECTURE.md) |
| Know what is next | [Roadmap](plans/ROADMAP.md) |
| Change the code | [Contributing](development/CONTRIBUTING.md) → [Coding standards](development/CODING-STANDARDS.md) → [Testing](development/TESTING.md) |
| Run or repair the factory | [Runbook](operations/RUNBOOK.md) → [Troubleshooting](operations/TROUBLESHOOTING.md) |
| Write a new coding-tool adapter | [Adapters guide](development/ADAPTERS.md) |
| Brief another AI tool | [Context pack](context/README.md) |
# Contributing

**Related:** [Development guide](DEVELOPMENT.md) · [Coding standards](CODING-STANDARDS.md) · [Testing](TESTING.md) · [AI provenance](../context/AI-PROVENANCE.md)

---

## 1. Guiding principle

The kernel is the only component whose bugs can corrupt state, so it is held to a higher bar than anything else: small, deterministic, and tested. Agents *propose*; the kernel *enforces*. Every contribution should preserve that separation.

## 2. Before you start

1. Read the [specification](../specification/Enterprise%20AI%20Software%20Factory%20—%20Specification%20v3.0.md) section you're touching, plus the matching [plan](../plans/ROADMAP.md).
2. Check the roadmap phase. **Do not build P4/P5 features before P0 is solid and P1 is demonstrably reliable.**
3. Open an issue describing the change if it touches the state model, event schema, or transition table.

## 3. Branching and commits

- Branch from the current base: `feature/<short-name>`, `fix/<short-name>`, `docs/<short-name>`.
- Keep commits focused; one logical change each.
- Commit messages: imperative subject ≤ 72 chars, blank line, then a body explaining **why** (the diff shows what).
- Reference the plan item or issue in the body, e.g. `Refs: plans/P1-solo-slice.md §2`.
- End every commit with the **provenance trailers** below.

### 3.1 Provenance trailers (required)

Because this project's whole thesis is auditable, verified claims, every commit records the tool and model
that produced it. Add these trailers to the end of the commit message:

```
AI-Tool: opencode
AI-Model: big-pickle
AI-Provider: opencode
AI-Session: ses_1234abcd          # optional: the tool's session id
Co-authored-by: Name <email>      # optional: human who reviewed/edited
```

| Trailer | Required | Notes |
|---------|----------|-------|
| `AI-Tool` | yes | The tool/agent used (e.g. `opencode`). Use `human` if no AI was involved. |
| `AI-Model` | yes | The model id (e.g. `big-pickle`). Use `human` if none. |
| `AI-Provider` | no | The provider (e.g. `opencode`). |
| `AI-Session` | no | The tool's session id, for traceability. |
| `Co-authored-by` | no | A human who materially edited or reviewed the change. |

**Example full message:**

```
P1: wire real git worktree isolation

- worktree.py: create .work/<job-id> on branch factory/<job-id> from base-sha
- doctor: detect orphan worktrees and stale bases
- tests: killed-mid-attempt -> interrupted; recovery restores checkpoint

Refs: plans/P1-solo-slice.md §1

AI-Tool: opencode
AI-Model: big-pickle
AI-Provider: opencode
```

**Note on existing history.** The P0/P1 commits predate this convention and carry no trailers; their
provenance is recorded as owner-attested in [AI-PROVENANCE.md](../context/AI-PROVENANCE.md).

#### Optional: add a commit-message template

A template is provided at `.gitmessage`. Enable it once per clone:

```bash
git config commit.template .gitmessage
```

#### Optional: enforce the trailers

A `commit-msg` hook can reject commits missing `AI-Tool`/`AI-Model`. Keep enforcement opt-in until the team
agrees; see [Review standards](#6-review-standards).

## 4. What needs a test

Every change to the following **must** ship a test:

| Area | Required test |
|------|---------------|
| Atomic writes | Write observed to be temp→rename; concurrent writers don't corrupt |
| Event log / fold | Append + fold round-trip; chain verification detects tampering |
| Transitions | Legal moves succeed; illegal moves raise |
| Leases / fencing | Stale token rejected; expiry behaviour |
| Schemas | Valid passes, invalid rejected on the write path |
| Profiles | YAML validation, missing/extra fields |
| Checks | Required/optional handling, output trimming, fingerprint stability |
| Engine | Stage/attempt orchestration, contract validation, gates |
| Adapters | Discovery, selection, run contract, write boundary |
| Checkpoints / approval | Content hash stability; SHA-bound approval refuses a changed result |
| Conformance | Suite passes for the echo adapter; capability-gated cases skip cleanly |

Hermetic test design is described in [Testing](TESTING.md).

## 5. Pull request checklist

- [ ] Suite green: `python -m pytest`
- [ ] Lint clean: `python -m flake8 kernel/src tests`
- [ ] `./factory doctor` clean against a scratch tree if you touched state, events, or leases
- [ ] Schemas updated + migration note if a file format changed
- [ ] Docs updated (PRD / Architecture / relevant plan)
- [ ] **Provenance trailers present** (`AI-Tool`, `AI-Model`) on every commit
- [ ] No secrets in code, tests, fixtures, or logs
- [ ] No new runtime dependency without justification in the PR body
- [ ] Transition table and spec/plan updated together if states changed

## 6. Review standards

- A change that weakens an invariant (atomicity, fencing, legal transitions, schema validation on write) is rejected unless the spec itself changed.
- Determinism is non-negotiable in the kernel: no hidden clocks, network calls, or randomness.
- New behavior in Solo mode must have a zero-decision default.
- When the spec and the kernel disagree, the kernel's conformance tests are authoritative and the **spec is corrected** — do both in the same PR.
- A PR without provenance trailers is **requested to add them** (blocking for merges).
- Adopting a `commit-msg` hook that enforces the trailers requires team agreement before it is enabled.

## 7. Reporting bugs and security issues

- Functional bugs: open a GitHub issue with reproduction steps, `factory doctor` output, and the relevant `events.jsonl` excerpt (scrub secrets).
- Security issues: do **not** open a public issue — see [Security](../operations/SECURITY.md).

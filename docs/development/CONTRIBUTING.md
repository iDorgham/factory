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

#### Enable the commit-message template

A template is provided at `.gitmessage`. Enable it once per clone:

```bash
git config commit.template .gitmessage
```

#### Enforce the trailers locally (recommended)

`.githooks/commit-msg` rejects any commit missing `AI-Tool` or `AI-Model`:

```bash
git config core.hooksPath .githooks
```

It is opt-in per clone so it never surprises anyone, but **CI enforces the same rule regardless** (the
`provenance` jobs in `.github/workflows/`), so a commit without trailers will be caught either way.
`git commit --no-verify` bypasses the local hook; it does not bypass CI.

#### Check the history

```bash
./factory provenance verify                        # whole history, allowlist applied
./factory provenance verify --range HEAD~5..HEAD   # only the commits you touched
./factory provenance verify --json                 # machine-readable, for scripting
```

`factory provenance verify` is the same deterministic check CI runs. Pre-convention history is
grandfathered through `.provenance-allow` rather than rewritten.

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
| Engine | Stage/attempt orchestration, contract validation, gates, guard hook, budget verdicts |
| Adapters | Discovery, selection, run contract, write boundary, failure classification |
| Checkpoints / approval | Content hash stability; SHA-bound approval refuses a changed result |
| Conformance | Suite passes for the echo adapter; capability-gated cases skip cleanly |
| Git / worktrees | Worktree creation, checkpoint commits, merge, conflict → blocked, undo, repo-less jobs never touching an outer checkout |
| Guards (P2) | Each guard's violation and its authorized-silence path; unknown guard id fails hard; guard violations reach the fingerprint |
| Budgets (P2) | Pricing against the table, unpriced usage raises, soft/hard resolution, inclusive boundaries, malformed usage rejected |
| Provenance | Trailer detection, grandfathering, and the allowlist path |
| Visual evidence | Manifest contract, synthetic labelling, `changed_pct` (including the "no number" cases) |

Guards and budgets carry a specific extra obligation: because they are *safety* mechanisms, a test that
only exercises the happy path is not enough. Assert what happens on the **malformed** input — an unknown
guard id, an invalid `authorizations.json`, a usage key with no price, `soft_usd >= usd`. Degrading
quietly is the failure mode these features exist to prevent.

Hermetic test design is described in [Testing](TESTING.md).

## 5. Pull request checklist

- [ ] Suite green: `python -m pytest` (or, for a deliberate TDD-red slice, the failing tests are named in the PR body and linked to a plan item)
- [ ] Lint clean: `python -m flake8 kernel/src tests`
- [ ] `./factory doctor` clean against a scratch tree if you touched state, events, or leases
- [ ] Schemas updated + migration note in `kernel/schemas/CHANGELOG.md` if a file format changed
- [ ] Docs updated (PRD / Architecture / relevant plan / CHANGELOG) — and no doc claims a control is shipped unless this PR ships it
- [ ] **Provenance trailers present** (`AI-Tool`, `AI-Model`); `./factory provenance verify` passes
- [ ] No secrets in code, tests, fixtures, or logs
- [ ] No new runtime dependency without justification in the PR body
- [ ] Transition table and spec/plan updated together if states changed

## 6. Review standards

- A change that weakens an invariant (atomicity, fencing, legal transitions, schema validation on write) is rejected unless the spec itself changed.
- Determinism is non-negotiable in the kernel: no hidden clocks, network calls, or randomness.
- New behavior in Solo mode must have a zero-decision default.
- When the spec and the kernel disagree, the kernel's conformance tests are authoritative and the **spec is corrected** — do both in the same PR.
- A PR without provenance trailers is **requested to add them** (blocking for merges). CI enforces this on every push, so a missing trailer fails the build rather than being caught in review.
- A safeguard that silently degrades into a no-op is treated as a bug, not a limitation: an unknown guard id, an invalid `authorizations.json`, or unpriced usage must fail loudly.
- A documentation change that overstates what is enforced is rejected on the same grounds as a code change that overstates it.

## 7. Reporting bugs and security issues

- Functional bugs: open an issue with reproduction steps, `factory doctor` output, and the relevant `events.jsonl` excerpt (scrub secrets).
- Security issues: do **not** open a public issue — see [Security](../operations/SECURITY.md).

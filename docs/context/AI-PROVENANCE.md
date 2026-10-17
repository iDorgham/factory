# AI Provenance — which tool and model developed each phase

> **Source note.** The mapping below is **owner-attested**: on 2026-10-16 the project owner stated that
> **P0 and P1 were developed using OpenCode with the Big Pickle model.** This is not independently
> machine-verified — the git history itself contains no tool/model trailers — so it is recorded as
> attestation rather than proof. Everything that *is* machine-verified is listed separately in §1.

Snapshot date: **2026-10-16**.

---

## 1. Verified facts (from the repository)

| Fact | Source |
|------|--------|
| All 8 commits are authored by `iDorgham` (`yasser.dorgham@gmail.com`) | `git log` |
| All commits dated 2026-10-16 | `git log --date` |
| No commit trailers, no tool footers, no `Co-authored-by` anywhere | `git log --format=%B` + repo-wide search |
| No model/tool strings in any source, config, or doc (besides the spec's illustrative `claude-code` adapter) | repo-wide search |
| The `docs/` tree, root `CHANGELOG/CONTRIBUTING/SECURITY`, and this context pack were written by **OpenCode** using model **Big Pickle** (provider `opencode`) | This documentation session |

## 2. Attested provenance (owner statement)

> "I used OpenCode Big Pickle for P0 and P1." — project owner, 2026-10-16

So every phase of code in the repository (P0 and all of P1) was produced with the same tool and model:

- **AI tool:** OpenCode
- **LLM model:** Big Pickle (provider `opencode`)

---

## 3. Per-phase table

| Phase | Commits | What it delivered | AI tool | Model | Confidence |
|-------|---------|-------------------|---------|-------|-----------|
| **P0 Kernel core** | `d328d49`, `b96c6c5`, `f1ffc41` | State/events, atomic writes, leases+fencing, schema validation, profiles, doctor, 109 tests | OpenCode | Big Pickle | Owner-attested |
| **P1 Solo slice** (1 — execution) | `fd06130` | Stage-graph engine, build loop, adapter runtime, check runner, echo adapter, CLI execute/approve | OpenCode | Big Pickle | Owner-attested |
| **P1 Solo slice** (2 — recovery/approval) | `92b0b2a` | Content-addressed checkpoints, SHA-bound approval, interrupted-attempt recovery, input-hash idempotency | OpenCode | Big Pickle | Owner-attested |
| **P1 Solo slice** (3 — conformance) | `a3fde93` | Adapter conformance suite (§20.3), `factory adapter test`, `slow` fixture | OpenCode | Big Pickle | Owner-attested |
| **P1 Solo slice** (4 — dashboard) | `5dfdf19` | Solo dashboard (`serve` SSE + `export-dashboard`), `request-changes` rework loop | OpenCode | Big Pickle | Owner-attested |
| **P1 Solo slice** (5 — worktrees/merge/undo) | `9398dfe` | Factory-managed git worktrees, checkpoint commits, merge queue (conflict → blocked), Undo (revert/reset) | OpenCode | Big Pickle | Owner-attested |
| **Documentation** | (uncommitted) | `docs/` tree, root CHANGELOG/CONTRIBUTING/SECURITY, context pack, provenance tool + CI | OpenCode | Big Pickle | Self-observed |
| **P2 Trust layer** (1 — guards) | `f5815b9`, `741bf84`, `12f231f`, `42b8ae6`, `8f2e8de`, `9010e60` | Guards over the diff: authorizations schema, `gitrepo.collect_diff`, three deterministic guards (`no_test_deletion`, `no_lockfile_surprise`, `no_secret_in_diff`), engine hook (attempt-base diff, events, fingerprint feed, stall on repeat), plain-language dashboard verdicts, doctor integrity checks | OpenCode | GLM-5.3-Flash Free (provider `opencode`) | **Machine-verified** (`AI-Tool`/`AI-Model` trailers carried per commit, enforced by the commit-msg hook) |
| **P2 Trust layer** (remaining) | — | Budgets/metering, sandbox, prompt-injection handling, risk-scored gates, import with baseline verification | not started | not started | — |
| **P3 Learning** | — | Eval harness, skills, lessons, memory | not started | not started | — |
| **P4 Team** | — | Multi-adapter, epics, visual baselines, named users | not started | not started | — |
| **P5 Enterprise** | — | Control plane, RBAC, audit chain, brands, compliance | not started | not started | — |

**Summary:** OpenCode + Big Pickle built P0 and P1 (owner-attested). **P2.1 is the first phase with
machine-verified provenance:** every commit since `f5815b9` carries `AI-Tool`/`AI-Model` trailers that
the repo's commit-msg hook refuses to merge without (`CONTRIBUTING.md` §3.1), so the tool/model claim
is now checked by git itself, not by memory. P0/P1 remain attestation because they predate the hook.

---

## 4. Why this matters (and the gap that remains)

For a project whose thesis is **auditability and verified claims**, the tool/model that produced each change
is exactly the kind of fact the system argues should be recorded. Right now it lives only in the owner's
memory and in this file: there is still no **machine-checkable link** between a commit and the tool/model
that produced it. Closing that loop is good dogfooding — see §5.

---

## 5. How to capture provenance going forward

Adopt one (or more) so future commits are self-describing:

### Option A — commit trailers (simplest, git-native)
```
P1: wire real git worktree isolation

- worktree.py: ...
- tests: ...

AI-Tool: opencode
AI-Model: big-pickle
AI-Session: ses_1234abcd
```

### Option B — a machine-readable provenance file per commit
Store `.prov/<commit-sha>.json`:
```json
{
  "commit": "5dfdf19…",
  "tool": "opencode",
  "model": "big-pickle",
  "provider": "opencode",
  "session": "ses_…",
  "started": "2026-10-16T22:00:00Z",
  "ended": "2026-10-16T23:04:04Z",
  "operator": "iDorgham"
}
```

### Option C — extend the factory's own audit story
The factory already has a hash-chained event log. A natural evolution is a **build-provenance event**
(`provenance.commit` with tool/model) appended when a human commits work — aligning with the spec's audit
goals (§22). Good P2/P3 material.

### Option D — enforce it in review — ✅ ADOPTED
**Adopted.** The convention is documented in [`docs/development/CONTRIBUTING.md` §3.1](../development/CONTRIBUTING.md).
Provenance is enforced by the deterministic checker [`factory provenance verify`](../development/CONTRIBUTING.md#31-provenance-trailers)
which is also run in CI. The pre-convention history is grandfathered via [`.provenance-allow`](../../.provenance-allow).
A commit template is provided at [`.gitmessage`](../../.gitmessage) and an **opt-in** `commit-msg` hook at
[`.githooks/commit-msg`](../../.githooks/commit-msg). Enable them once per clone:

```bash
git config commit.template .gitmessage
git config core.hooksPath .githooks      # optional (local) enforcement
```

The hook requires `AI-Tool` and `AI-Model` (use `human` when no AI was involved) and can be bypassed with
`git commit --no-verify`. CI enforces the same rule for all new commits.


---

## 6. Remaining questions (optional to close)

1. Was any of the P0/P1 code hand-written or hand-edited by a human rather than AI-generated?
2. Was a single OpenCode session used throughout, or several?
3. Are the phase timestamps in [HISTORY.md](HISTORY.md) accurate to how the work actually flowed?
4. ~~Should provenance be enforced going forward?~~ **Yes — adopted** (see Option D: template + opt-in hook).

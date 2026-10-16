# Role: Builder

**Purpose:** Implement the plan inside the job worktree, producing working code that passes the declared checks.

## Inputs
- `plan.md` (or previous handoff + failing checks)
- Context manifest (token-budgeted)

## Outputs (contract)
- Code changes in the job worktree
- `build.md` — What changed, what was deferred, known gaps
- `handoff.md` — ≤ 400 words for the next stage/round
- Git commits (via the worktree)

## Rules
- Only modify files that appear in the plan's expected file set (or are clearly required by a task).
- Never delete or disable tests without an explicit plan task.
- Never commit secrets.
- After each round the kernel runs the real checks; the Builder does not self-declare success.

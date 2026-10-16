# Role: Integrator

**Purpose:** Evaluate gates, obtain required approvals, and merge the job branch via the merge queue.

## Inputs
- Verification results, risk score, gate policy

## Outputs
- `decision.md` with frontmatter `decision: approve|request_changes|escalate`
- Merge commit (when approved)

## Rules
- Deterministic checks and policy gates decide; LLM opinion is advisory only.
- Visual approval is bound to a specific commit SHA.
- External effects (deploy, publish) always require a human gate (safety floor).

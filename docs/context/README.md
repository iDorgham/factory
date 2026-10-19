# Project Context — How to use this folder

This folder is a **portable, self-contained context pack** for discussing the
**Enterprise AI Software Factory** with any AI tool or model (Qwen, Grok,
ChatGPT, Claude, Gemini, local models, etc.).

Nothing here depends on OpenCode, a specific editor, or this repository's
tooling. Paste the files into another AI's context and it has everything needed
to reason about the project.

## Files

| File | Contents |
|------|----------|
| [PROJECT-CONTEXT.md](PROJECT-CONTEXT.md) | The full briefing: idea, architecture, features, repository map, roadmap, current state, open questions, and discussion prompts. **Start here.** |
| [HISTORY.md](HISTORY.md) | Complete git history (19 commits), what each delivered, and how work was ordered. |
| [AI-PROVENANCE.md](AI-PROVENANCE.md) | Which AI tool and LLM model were used per phase — owner-attested for P0/P1, machine-verified from P2.1 onward. |

## How to use with another AI

1. **Full context:** attach `PROJECT-CONTEXT.md` (and `HISTORY.md` if the model has room).
2. **Ask it to reason**, for example:
   - "Review the architecture in §5 and identify the weakest invariants."
   - "Given the roadmap in §10, what is the highest-risk item in the remaining P2 work?"
   - "Cost math is implemented as pure functions but the enforcing runtime is not. Where could a partial integration create a false sense of enforcement?"
   - "Where does the spec promise something the implementation does not yet keep?"
3. **Be explicit** that the code is a *reference implementation* of a specification, and the spec is the source of truth for intended behavior.

## Ground rules for these documents

- **Verified facts** are drawn directly from the repository (files, `git log`, the test suite).
- **Attested vs. verified** — AI provenance for P0/P1 is **owner-attested**, not machine-verified (those
  commits predate the convention). From P2.1 onward the tool and model are recorded in commit trailers and
  enforced by the `commit-msg` hook and CI, so they are **machine-verified**; see
  [AI-PROVENANCE.md](AI-PROVENANCE.md). Other unknowns are labeled as unknown — do not treat a blank as a fact.
- **Planned vs. shipped is always marked.** Where a control is spec'd but not implemented, the docs say so.
  If a statement conflicts with the repository, **the repository wins**. Snapshot date: **2026-10-19**
  (commit `d933adf`).

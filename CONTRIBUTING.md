# Contributing

Thanks for helping build the factory. Full guidance lives in the docs:

- **[Contributing guide](docs/development/CONTRIBUTING.md)** — process, branching, PR checklist, review standards
- **[Development guide](docs/development/DEVELOPMENT.md)** — environment setup, workflow, debugging
- **[Coding standards](docs/development/CODING-STANDARDS.md)** — Python style and kernel rules
- **[Testing](docs/development/TESTING.md)** — hermetic test strategy and how to add tests

## Quick start

```bash
python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1   |   POSIX: source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest
python -m flake8 kernel/src tests
```

No `git` remote? `./factory doctor` works straight from the checkout via the `factory` launcher
(`python .\factory doctor` on Windows PowerShell).

## The one rule that matters most

The kernel is the only writer of state; agents only propose. Any change that weakens atomicity, fencing, legal transitions, or schema validation on write will be rejected unless the specification itself changed.

The same logic applies to safeguards: a guard or budget that silently degrades into a no-op is treated as
a bug. An unknown guard id, a malformed `authorizations.json`, or an unpriced usage key must fail loudly.

## Commit provenance

Every commit must end with provenance trailers — this project is about auditable claims, so it records which tool and model produced each change:

```
AI-Tool: opencode
AI-Model: big-pickle
AI-Provider: opencode
```

Enable the helpers once per clone:

```bash
git config commit.template .gitmessage
git config core.hooksPath .githooks      # optional local enforcement
```

CI enforces the same rule on every push, and you can audit the history yourself at any time:

```bash
./factory provenance verify                       # whole history, allowlist applied
./factory provenance verify --range HEAD~3..HEAD  # recent commits only
./factory provenance verify --json                # machine-readable
```

Commits from before the convention are grandfathered through [`.provenance-allow`](.provenance-allow)
rather than rewritten.

Details: [Contributing §3.1](docs/development/CONTRIBUTING.md#31-provenance-trailers-required) · [AI provenance](docs/context/AI-PROVENANCE.md).

## Reporting bugs

Include reproduction steps, `factory doctor` output, and the relevant `events.jsonl` excerpt (scrub secrets). Add a line to [CHANGELOG.md](CHANGELOG.md) describing the change.

Security issues: **do not** open a public issue — see [Security](docs/operations/SECURITY.md).

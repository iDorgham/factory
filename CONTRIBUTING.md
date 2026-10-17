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

## The one rule that matters most

The kernel is the only writer of state; agents only propose. Any change that weakens atomicity, fencing, legal transitions, or schema validation on write will be rejected unless the specification itself changed.

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
git config core.hooksPath .githooks      # optional: enforce the trailers
```

Details: [Contributing §3.1](docs/development/CONTRIBUTING.md) · [AI provenance](docs/context/AI-PROVENANCE.md).

Security issues: **do not** open a public issue — see [Security](docs/operations/SECURITY.md).

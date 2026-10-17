"""Sandbox contract — the boundary between the kernel and agent code (P2.3).

Pure module: no subprocesses, no file I/O, no network. It answers two
questions deterministically:

1. What may an adapter subprocess *see* of the kernel's environment?
   ``sanitize_env`` keeps only the allowlist intersection of ``os.environ``:
   exact names or prefix wildcards ending in ``*``, matched
   case-insensitively (Windows env is case-insensitive; determinism beats
   platform drift). Everything else — provider tokens, SSH agents, proxies
   — is dropped by default (isolation by default, spec §3).
2. Where may adapter paths point? ``resolve_under`` restricts any
   path a handler accepts to sit inside its sandbox base; escapes raise
   ``SandboxError`` and the attempt fails deterministically (the same
   policy as ``BudgetError`` and ``GuardError``: config is truth, never
   silently reinterpreted).

The lone ``"*"`` entry is the explicit allow-everything opt-out: legal in
config, documented as the foot-gun it is — a "sandbox" that keeps everything
is not a sandbox, and doctor (Step 4) names it.

Config parsing is pure too: ``load_sandbox_policy`` maps a
``factory.json`` ``sandbox`` object to a ``SandboxPolicy``, raising
instead of guessing (missing ``type``, unknown type, empty allowlist,
malformed keys all fail hard).

Known limitation, documented: path containment is lexical — symlinks are
not resolved and do not change the verdict.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path, PurePath

# The documented default when factory.json names no env_allowlist:
# process essentials (PATH plus the Windows variables child processes
# need to even start) and the kernel-reserved FACTORY_* namespace.
DEFAULT_ENV_ALLOWLIST = [
    "PATH", "SYSTEMDRIVE", "SYSTEMROOT", "HOME", "TEMP", "TMP",
    "USERPROFILE", "FACTORY_*",
]


class SandboxError(Exception):
    """Sandbox configuration is invalid, or a path escape was detected."""


@dataclass
class SandboxPolicy:
    """The parsed sandbox contract for adapter subprocesses."""
    type: str                                    # "process" (only implemented)
    env_allowlist: list[str] = field(default_factory=list)
    strict_cwd: bool = False                     # adapter cwd locked to worktree
    # Declared by the schema, enforced by later slices — carried so kernel
    # code never has to re-read config for them when enforcement lands.
    network_allowlist: list[str] = field(default_factory=list)
    resource_limits: dict = field(default_factory=dict)

    @classmethod
    def from_config(cls, cfg) -> "SandboxPolicy":
        return load_sandbox_policy(cfg)


def sanitize_env(env: dict, allowlist: list[str]) -> dict:
    """Keep exactly the allowlist-intersection of ``env`` (pure).

    Matching is case-insensitive on both sides. An entry without ``*`` is
    an exact-name rule (no prefix matching: ``PATH`` never keeps
    ``PATH_TOKEN``); an entry ending in ``*`` keeps every name with that
    prefix; the lone ``"*"`` keeps everything (explicit opt-out). The
    output preserves the input's key order and values verbatim.
    """
    if not isinstance(env, dict):
        raise SandboxError("env must be a mapping")
    if not isinstance(allowlist, list):
        raise SandboxError("allowlist must be a list of strings")
    rules = []
    for entry in allowlist:
        if not isinstance(entry, str) or not entry:
            raise SandboxError(f"invalid allowlist entry: {entry!r}")
        rules.append(entry.upper())
    if "*" in rules:
        return dict(env)

    kept: dict = {}
    for key, value in env.items():
        name = str(key).upper()
        for rule in rules:
            if rule.endswith("*"):
                if name.startswith(rule[:-1]):
                    kept[key] = value
                    break
            elif name == rule:
                kept[key] = value
                break
    return kept


def resolve_under(base, path: str) -> Path:
    """Resolve ``path`` strictly inside ``base`` or fail (pure, lexical).

    Relative paths are rooted at ``base``; absolute paths must already sit
    inside it. ``..`` segments are collapsed lexically and any resulting
    escape raises ``SandboxError`` — nothing outside the base can be named
    through trickery like ``outputs\\..\\..\\secret``. Case handling follows
    the platform (``os.path.normcase``), and containment is compared after
    normalization. Symlinks are NOT resolved (documented limitation); the
    check stays free of filesystem access.
    """
    if not isinstance(path, str) or not path:
        raise SandboxError("empty or non-string path")
    try:
        dirt = Path(path)
        base_p = Path(base)
    except (TypeError, ValueError) as e:
        raise SandboxError(f"unusable path arguments: {e}")

    joined = dirt if dirt.is_absolute() else base_p / dirt
    normalized = PurePath(os.path.normpath(str(joined)))
    base_norm = PurePath(os.path.normpath(str(base_p)))
    here, there = os.path.normcase(str(base_norm)), \
        os.path.normcase(str(normalized))
    if there != here and not there.startswith(here + os.sep):
        raise SandboxError(
            f"path {path!r} escapes sandbox base {str(base_norm)!r}")
    return Path(normalized)


def load_sandbox_policy(factory_cfg) -> SandboxPolicy:
    """Parse a ``factory.json`` ``sandbox`` object into a policy (pure).

    Missing ``env_allowlist`` → documented default allowlist; missing
    ``strict_cwd`` → False (legacy cwd, back-compat). Unknown ``type``,
    an empty allowlist, or malformed keys raise ``SandboxError`` — the
    kernel never "just runs it anyway" on a broken sandbox config.
    """
    if not isinstance(factory_cfg, dict):
        raise SandboxError("sandbox config must be a mapping")
    kind = factory_cfg.get("type")
    if not isinstance(kind, str) or not kind:
        raise SandboxError("sandbox config requires a 'type' string")
    if kind != "process":
        raise SandboxError(
            f"unknown sandbox type '{kind}': only 'process' is implemented")

    raw_allowlist = factory_cfg.get("env_allowlist")
    if raw_allowlist is None:
        allowlist = list(DEFAULT_ENV_ALLOWLIST)
    else:
        if (not isinstance(raw_allowlist, list) or not raw_allowlist
                or not all(isinstance(e, str) and e for e in raw_allowlist)):
            raise SandboxError(
                "'env_allowlist' must be a non-empty list of strings")
        allowlist = list(raw_allowlist)

    strict = factory_cfg.get("strict_cwd", False)
    if not isinstance(strict, bool):
        raise SandboxError("'strict_cwd' must be a boolean")

    network = factory_cfg.get("network_allowlist", [])
    if (not isinstance(network, list)
            or not all(isinstance(h, str) and h for h in network)):
        raise SandboxError("'network_allowlist' must be a list of hostnames")

    limits = factory_cfg.get("resource_limits", {})
    if not isinstance(limits, dict):
        raise SandboxError("'resource_limits' must be a mapping")

    return SandboxPolicy(
        type=kind, env_allowlist=allowlist, strict_cwd=strict,
        network_allowlist=list(network), resource_limits=dict(limits))

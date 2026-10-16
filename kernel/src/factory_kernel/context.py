"""Context manifest builder (spec §10.2).

Before every attempt the kernel writes ``context.manifest.json`` describing
exactly what the agent may see. The manifest must satisfy
``kernel/schemas/context.manifest.schema.json``.

Note: the schema (authoritative per spec §27) uses ``files``/``summaries``/
``untrusted_content``, which differs slightly from the illustrative ``include``
shape in §10.2. The kernel builds to the schema.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

# Roles a file entry may have (schema enum).
ROLES = {"required", "context", "reference", "previous"}


def estimate_tokens(text: str) -> int:
    """Cheap, deterministic token estimate (~4 chars/token)."""
    return max(1, len(text) // 4)


def file_entry(
    path: str,
    role: str,
    text: str = "",
    summary: Optional[str] = None,
    mode: Optional[str] = None,
) -> dict:
    if role not in ROLES:
        raise ValueError(f"Invalid context role: {role}")
    entry = {"path": path, "role": role, "tokens": estimate_tokens(text)}
    if summary:
        entry["summary"] = summary
    if mode:
        # Not in the schema's declared properties, but items allow extras.
        entry["mode"] = mode
    return entry


def build_manifest(
    job_id: str,
    stage: str,
    attempt: int,
    token_budget: int,
    files: list[dict],
    summaries: Optional[dict] = None,
    repo_map: Optional[dict] = None,
    untrusted: Optional[list[str]] = None,
) -> dict:
    manifest: dict = {
        "job_id": job_id,
        "stage": stage,
        "attempt": attempt,
        "token_budget": max(1000, int(token_budget)),
        "files": files,
        "summaries": summaries or {},
    }
    if repo_map is not None:
        manifest["repo_map"] = repo_map
    if untrusted:
        manifest["untrusted_content"] = untrusted
    return manifest


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def collect_stage_context(
    project_dir: Union[str, Path],
    job_dir: Union[str, Path],
    stage: dict,
    attempt: int,
    token_budget: int,
) -> dict:
    """Assemble the manifest for an attempt from job files + project memory.

    ``stage['requires']`` names are resolved against the job dir first (job-level
    artifacts) and then against earlier attempts' ``outputs/`` directories.
    """
    project_dir = Path(project_dir)
    job_dir = Path(job_dir)

    files: list[dict] = []

    brief = job_dir / "brief.md"
    if brief.exists():
        files.append(file_entry("brief.md", "required", _read(brief)))

    for req in stage.get("requires", []):
        found = _resolve_required(job_dir, req)
        if found is not None:
            files.append(file_entry(req, "context", _read(found), mode="full"))

    for name, rel in (
        ("conventions", "memory/conventions.md"),
        ("decisions", "memory/decisions.md"),
    ):
        p = project_dir / rel
        if p.exists():
            files.append(file_entry(rel, "reference", _read(p), mode="summary"))

    summaries: dict = {}
    lessons = project_dir / "memory" / "lessons.jsonl"
    if lessons.exists():
        summaries["lessons"] = lessons.read_text(encoding="utf-8")[:2000]

    repo_map_path = project_dir / "memory" / "repo-map.json"
    repo_map = None
    if repo_map_path.exists():
        import json

        try:
            repo_map = json.loads(repo_map_path.read_text(encoding="utf-8"))
        except ValueError:
            repo_map = None

    return build_manifest(
        job_id=job_dir.name,
        stage=stage["id"],
        attempt=attempt,
        token_budget=token_budget,
        files=files,
        summaries=summaries,
        repo_map=repo_map,
    )


def _resolve_required(job_dir: Path, name: str) -> Optional[Path]:
    """Find a required artifact in the job dir or any prior attempt outputs/."""
    direct = job_dir / name
    if direct.exists():
        return direct
    stages = job_dir / "stages"
    if stages.exists():
        for attempt_dir in sorted(stages.glob("*/attempt-*"), reverse=True):
            candidate = attempt_dir / "outputs" / name
            if candidate.exists():
                return candidate
    return None

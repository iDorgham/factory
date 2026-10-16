#!/usr/bin/env python3
"""Factory CLI — the only public entry point for the kernel."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .kernel import Kernel, KernelError
from .lease import LeaseError
from .profiles import ProfileError
from .schemas import SchemaError
from .state import StateError


def _root() -> Path:
    # Default to the factory tree that contains this package
    # When installed, FACTORY_ROOT env or cwd is used.
    env = Path.cwd()
    if (env / "factory.json").exists():
        return env
    # Walk up looking for factory.json
    for parent in [env, *env.parents]:
        if (parent / "factory.json").exists():
            return parent
    # Fallback: the artifacts/factory location used in development
    dev = Path(__file__).resolve().parents[3]  # kernel/src/factory_kernel → factory/
    if (dev / "factory.json").exists():
        return dev
    return env


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="factory",
        description="Enterprise AI Software Factory — Kernel CLI",
    )
    parser.add_argument("--root", type=Path, help="Factory root directory")
    parser.add_argument("--actor", default="local", help="Actor identity")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # project
    p_proj = sub.add_parser("project", help="Project commands")
    p_proj_sub = p_proj.add_subparsers(dest="proj_cmd", required=True)

    p_create = p_proj_sub.add_parser("create")
    p_create.add_argument("name")
    p_create.add_argument("--mode", default="solo", choices=["solo", "team", "enterprise"])
    p_create.add_argument("--domain", default="web", choices=["web", "mobile", "desktop", "game", "generic"])
    p_create.add_argument("--brand", default=None)

    p_proj_sub.add_parser("list")
    p_status = p_proj_sub.add_parser("status")
    p_status.add_argument("name")

    # job
    p_job = sub.add_parser("job", help="Job commands")
    p_job_sub = p_job.add_subparsers(dest="job_cmd", required=True)

    p_run = p_job_sub.add_parser("run")
    p_run.add_argument("project")
    p_run.add_argument("description")
    p_run.add_argument("--epic", default=None)
    p_run.add_argument("--profile", default=None, choices=["lite", "standard"])

    p_jstatus = p_job_sub.add_parser("status")
    p_jstatus.add_argument("job_id")

    p_jlist = p_job_sub.add_parser("list")
    p_jlist.add_argument("--project", default=None)

    p_cancel = p_job_sub.add_parser("cancel")
    p_cancel.add_argument("job_id")
    p_cancel.add_argument("--reason", default="user cancelled")

    # ops
    sub.add_parser("doctor")
    sub.add_parser("reindex")

    args = parser.parse_args(argv)
    root = args.root or _root()
    k = Kernel(root, actor=args.actor)

    try:
        if args.cmd == "project":
            if args.proj_cmd == "create":
                result = k.project_create(args.name, mode=args.mode, domain=args.domain, brand=args.brand)
                print(json.dumps(result, indent=2))
            elif args.proj_cmd == "list":
                print(json.dumps(k.project_list(), indent=2))
            elif args.proj_cmd == "status":
                print(json.dumps(k.project_get(args.name), indent=2))

        elif args.cmd == "job":
            if args.job_cmd == "run":
                result = k.job_run(args.project, args.description, epic=args.epic, profile=args.profile)
                print(json.dumps(result, indent=2))
            elif args.job_cmd == "status":
                print(json.dumps(k.job_status(args.job_id), indent=2))
            elif args.job_cmd == "list":
                print(json.dumps(k.job_list(args.project), indent=2))
            elif args.job_cmd == "cancel":
                result = k.job_cancel(args.job_id, reason=args.reason)
                print(json.dumps(result, indent=2))

        elif args.cmd == "doctor":
            report = k.doctor()
            print(json.dumps(report, indent=2))
            return 0 if report["ok"] else 1

        elif args.cmd == "reindex":
            print(json.dumps(k.reindex(), indent=2))

        return 0

    except (KernelError, StateError, LeaseError, SchemaError, ProfileError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

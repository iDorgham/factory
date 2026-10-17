#!/usr/bin/env python3
"""Factory CLI — the only public entry point for the kernel."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .adapters import AdapterError
from .checks import CheckError
from .engine import EngineError
from .kernel import Kernel, KernelError
from .lease import LeaseError
from .profiles import ProfileError
from .provenance import DEFAULT_REQUIRED, ProvenanceError, verify
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


def _adapter_test(kernel, args) -> int:
    """Run the conformance suite (§20.3) for one adapter."""
    import tempfile

    from .adapters import discover_adapters
    from .conformance import overall_ok, record_results, run_suite

    adapters = discover_adapters(kernel.adapters_dir)
    if args.adapter_id not in adapters:
        print(f"error: adapter '{args.adapter_id}' not found", file=sys.stderr)
        return 1
    adapter = adapters[args.adapter_id]

    with tempfile.TemporaryDirectory(prefix="factory_conformance_") as tmp:
        results = run_suite(adapter, Path(tmp))

    recorded = None
    if not args.no_record:
        recorded = str(record_results(adapter, results))

    report = {
        "adapter": adapter.id,
        "passed": overall_ok(results),
        "recorded": recorded,
        "results": [r.to_dict() for r in results],
    }
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


def _provenance_verify(root: Path, args) -> int:
    """Verify build provenance (AI trailers) across the repository history."""
    required = tuple(s.strip() for s in args.require.split(",") if s.strip())
    allowlist = args.allowlist or (root / ".provenance-allow")
    report = verify(
        root,
        required=required,
        rev_range=args.rev_range,
        allow=args.allow,
        allow_all_before=args.all_before,
        allowlist_path=allowlist,
    )
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        status = "OK" if report["ok"] else "FAIL"
        print(
            f"provenance: {status} "
            f"({report['checked']} commits checked, required {', '.join(report['required'])})"
        )
        for v in report["violations"]:
            print(f"  missing {', '.join(v['missing'])}: {v['sha'][:12]} {v['subject']}")
    return 0 if report["ok"] else 1


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
    p_create.add_argument("--domain", default="web",
                          choices=["web", "mobile", "desktop", "game", "generic"])
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

    p_jexec = p_job_sub.add_parser("execute", help="Run or resume a job")
    p_jexec.add_argument("job_id")
    p_jexec.add_argument("--adapter", default=None, help="Force a specific adapter id")
    p_jexec.add_argument("--check-timeout", type=int, default=600)

    p_japprove = p_job_sub.add_parser("approve", help="Approve a job at a human gate")
    p_japprove.add_argument("job_id")
    p_japprove.add_argument("--adapter", default=None)
    p_japprove.add_argument("--sha", default=None,
                            help="Expected checkpoint SHA (defaults to the latest)")

    p_jlist = p_job_sub.add_parser("list")
    p_jlist.add_argument("--project", default=None)

    p_cancel = p_job_sub.add_parser("cancel")
    p_cancel.add_argument("job_id")
    p_cancel.add_argument("--reason", default="user cancelled")

    p_jundo = p_job_sub.add_parser("undo", help="Revert the merge of an approved job")
    p_jundo.add_argument("job_id")

    p_janswer = p_job_sub.add_parser("answer", help="Answer an open blocking question")
    p_janswer.add_argument("job_id")
    p_janswer.add_argument("question_id")
    p_janswer.add_argument("answer")
    p_janswer.add_argument("--adapter", default=None,
                           help="Adapter the job ran with (resume with the same one)")

    # ops
    sub.add_parser("doctor")
    sub.add_parser("reindex")

    p_serve = sub.add_parser("serve", help="Run the local dashboard server")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8787)
    p_serve.add_argument("--no-open", action="store_true", help="Do not open a browser")

    p_export = sub.add_parser("export-dashboard", help="Write a static dashboard snapshot")
    p_export.add_argument("--out", default=None)
    p_export.add_argument("--project", default=None)

    p_rc = sub.add_parser("request-changes", help="Send feedback from the approval card")
    p_rc.add_argument("job_id")
    p_rc.add_argument("feedback")
    p_rc.add_argument("--adapter", default=None,
                      help="Adapter the job ran with (resume with the same one)")

    # adapter
    p_adapter = sub.add_parser("adapter", help="Adapter commands")
    p_adapter_sub = p_adapter.add_subparsers(dest="adapter_cmd", required=True)
    p_atest = p_adapter_sub.add_parser("test", help="Run the conformance suite")
    p_atest.add_argument("adapter_id")
    p_atest.add_argument("--no-record", action="store_true",
                         help="Do not write conformance.json into the adapter folder")

    # provenance
    p_prov = sub.add_parser("provenance", help="Build provenance (AI trailers)")
    p_prov_sub = p_prov.add_subparsers(dest="prov_cmd", required=True)
    p_pverify = p_prov_sub.add_parser(
        "verify", help="Verify commits carry the required provenance trailers"
    )
    p_pverify.add_argument("--range", dest="rev_range", default=None,
                           help="git revision range, e.g. HEAD~5..HEAD")
    p_pverify.add_argument("--require", default=",".join(DEFAULT_REQUIRED),
                           help="Comma-separated required trailer keys")
    p_pverify.add_argument("--allow", action="append", default=[],
                           help="Exempt a SHA (repeatable)")
    p_pverify.add_argument("--all-before", default=None,
                           help="Grandfather this SHA and every older commit")
    p_pverify.add_argument("--allowlist", default=None,
                           help="Allowlist file (default: <root>/.provenance-allow)")
    p_pverify.add_argument("--json", action="store_true", help="Emit a JSON report")

    args = parser.parse_args(argv)
    root = args.root or _root()
    k = Kernel(root, actor=args.actor)

    try:
        if args.cmd == "project":
            if args.proj_cmd == "create":
                result = k.project_create(
                    args.name, mode=args.mode, domain=args.domain, brand=args.brand
                )
                print(json.dumps(result, indent=2))
            elif args.proj_cmd == "list":
                print(json.dumps(k.project_list(), indent=2))
            elif args.proj_cmd == "status":
                print(json.dumps(k.project_get(args.name), indent=2))

        elif args.cmd == "job":
            if args.job_cmd == "run":
                result = k.job_run(
                    args.project, args.description, epic=args.epic, profile=args.profile
                )
                print(json.dumps(result, indent=2))
            elif args.job_cmd == "status":
                print(json.dumps(k.job_status(args.job_id), indent=2))
            elif args.job_cmd == "execute":
                result = k.job_execute(
                    args.job_id, adapter_id=args.adapter, check_timeout=args.check_timeout
                )
                print(json.dumps(result, indent=2))
            elif args.job_cmd == "approve":
                result = k.job_approve(args.job_id, adapter_id=args.adapter, sha=args.sha)
                print(json.dumps(result, indent=2))
            elif args.job_cmd == "list":
                print(json.dumps(k.job_list(args.project), indent=2))
            elif args.job_cmd == "cancel":
                result = k.job_cancel(args.job_id, reason=args.reason)
                print(json.dumps(result, indent=2))
            elif args.job_cmd == "undo":
                result = k.job_undo(args.job_id)
                print(json.dumps(result, indent=2))
            elif args.job_cmd == "answer":
                result = k.job_answer(args.job_id, args.question_id, args.answer,
                                      adapter_id=args.adapter)
                print(json.dumps(result, indent=2))

        elif args.cmd == "doctor":
            report = k.doctor()
            print(json.dumps(report, indent=2))
            return 0 if report["ok"] else 1

        elif args.cmd == "adapter":
            if args.adapter_cmd == "test":
                return _adapter_test(k, args)

        elif args.cmd == "provenance":
            if args.prov_cmd == "verify":
                return _provenance_verify(root, args)

        elif args.cmd == "reindex":
            print(json.dumps(k.reindex(), indent=2))

        elif args.cmd == "serve":
            from .dashboard import serve

            serve(k, host=args.host, port=args.port, open_browser=not args.no_open)

        elif args.cmd == "export-dashboard":
            from .dashboard import export_dashboard

            out = export_dashboard(k, out=args.out, project=args.project)
            print(str(out))

        elif args.cmd == "request-changes":
            result = k.job_request_changes(args.job_id, args.feedback,
                                           adapter_id=args.adapter)
            print(json.dumps(result, indent=2))

        return 0

    except (KernelError, StateError, LeaseError, SchemaError, ProfileError,
            EngineError, CheckError, AdapterError, ProvenanceError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

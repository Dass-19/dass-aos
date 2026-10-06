"""Command Line Interface for DASS-AOS."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .bootstrap import init_project
from .constants import VERSION, configure_utf8_output
from .generator import generate_client
from .memory import run_memory_refresh
from .plans import create_new_plan
from .scanners import run_security_scans
from .sync import native_source_hash, sync_all_instructions
from .verifier import run_verification


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="aos",
        description=f"DASS-AOS — Agent Operating System (v{VERSION})",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"DASS-AOS {VERSION}",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. init
    init_p = subparsers.add_parser("init", help="Initialize DASS-AOS in a target repository")
    init_p.add_argument("--project-root", default=".", help="Root path of target project (default: current directory)")
    init_p.add_argument("--project-name", default=None, help="Name of the project (default: folder name)")
    init_p.add_argument("--force", action="store_true", help="Force overwrite existing configuration files")

    # 2. sync
    sync_p = subparsers.add_parser("sync", help="Synchronize CLAUDE.md, AGENTS.md, GEMINI.md, and editor rules")
    sync_p.add_argument("--project-root", default=".", help="Root path of target project (default: current directory)")
    sync_p.add_argument("--create-missing", action="store_true", default=True, help="Create files if they don't exist")

    native_p = subparsers.add_parser("native-hash", help="Print the source hash that adapt-native records in .aos/native/<tool>.json")
    native_p.add_argument("--project-root", default=".", help="Root path of target project (default: current directory)")

    # 3. refresh
    refresh_p = subparsers.add_parser("refresh", help="Session-start hook: refresh gotchas and memory status")
    refresh_p.add_argument("--project-root", default=".", help="Root path of target project (default: current directory)")
    refresh_p.add_argument("--gotchas-limit", type=int, default=5, help="Number of recent gotchas to display")

    # 4. scan
    scan_p = subparsers.add_parser("scan", help="Run Semgrep and Checkov security scans")
    scan_p.add_argument("--project-root", default=".", help="Directory to scan (default: current directory)")
    scan_p.add_argument("--tool", choices=["all", "semgrep", "checkov"], default="all", help="Tool to execute")
    scan_p.add_argument("--dry-run", action="store_true", help="Run in dry-run simulation mode")
    scan_p.add_argument("--strict", action="store_true", help="Exit with error if security tools are missing")

    # 5. verify
    verify_p = subparsers.add_parser("verify", help="Run project linters, tests, and migration checks")
    verify_p.add_argument("--project-root", default=".", help="Target project root (default: current directory)")
    verify_p.add_argument("--type", choices=["all", "lint", "test", "migration"], default="all", help="Verification type")
    verify_p.add_argument("--strict", action="store_true", help="Fail if no command is configured")

    # 6. generate-client
    gen_p = subparsers.add_parser("generate-client", help="Generate typed client stubs from OpenAPI contract")
    gen_p.add_argument("--contract", required=True, help="Path to OpenAPI spec (YAML or JSON)")
    gen_p.add_argument("--output", default="generated-client", help="Destination directory")
    gen_p.add_argument(
        "--generator",
        choices=["generic", "openapi-typescript", "openapi-generator", "datamodel-codegen"],
        default="generic",
        help="Client generator tool",
    )
    gen_p.add_argument("--language", default=None, help="Target language for openapi-generator")

    # 7. plan
    plan_p = subparsers.add_parser("plan", help="Manage task execution plans")
    plan_subparsers = plan_p.add_subparsers(dest="plan_command", required=True)
    plan_new_p = plan_subparsers.add_parser("new", help="Instantiate a new plan from template")
    plan_new_p.add_argument(
        "template",
        choices=["feature", "bugfix", "refactor", "security"],
        help="Template to base new plan on",
    )
    plan_new_p.add_argument("--title", required=True, help="Short descriptive title of the task")
    plan_new_p.add_argument("--project-root", default=".", help="Project root directory")

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI execution entrypoint."""
    configure_utf8_output()
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "init":
            root = Path(args.project_root).resolve()
            res = init_project(root, project_name=args.project_name, force=args.force)
            print(f"\n[aos init] Successfully initialized DASS-AOS in: {res['project_root']}")
            print(f"Local State Directory: {res['aos_dir']}")
            print("Instruction files updated:")
            for fname, action in res["sync_results"].items():
                print(f"  - {fname}: {action}")
            print("\nNext step: Run 'aos refresh' at the start of each agent session.")
            return 0

        elif args.command == "sync":
            root = Path(args.project_root).resolve()
            res = sync_all_instructions(root, create_missing=args.create_missing)
            print(f"\n[aos sync] Agent instruction sync complete for: {root}")
            for fname, action in res.items():
                print(f"  - {fname}: {action}")
            return 0

        elif args.command == "native-hash":
            print(native_source_hash(Path(args.project_root).resolve()))
            return 0

        elif args.command == "refresh":
            root = Path(args.project_root).resolve()
            run_memory_refresh(root, gotchas_limit=args.gotchas_limit)
            return 0

        elif args.command == "scan":
            root = Path(args.project_root).resolve()
            return run_security_scans(
                root,
                tool=args.tool,
                dry_run=args.dry_run,
                strict=args.strict,
            )

        elif args.command == "verify":
            root = Path(args.project_root).resolve()
            return run_verification(root, check_type=args.type, strict=args.strict)

        elif args.command == "generate-client":
            contract = Path(args.contract).resolve()
            output = Path(args.output).resolve()
            return generate_client(
                contract_path=contract,
                output_dir=output,
                generator=args.generator,
                language=args.language,
            )

        elif args.command == "plan":
            if args.plan_command == "new":
                root = Path(args.project_root).resolve()
                create_new_plan(root, template_type=args.template, title=args.title)
                return 0

    except Exception as exc:
        print(f"[aos ERROR]: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

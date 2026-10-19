"""Command Line Interface for DASS-AOS."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .bootstrap import init_project
from .constants import TOOL_FILES, VERSION, configure_utf8_output
from .generator import generate_client
from .doctor import run_doctor
from .memory import run_memory_refresh
from .plans import create_new_plan
from .scanners import run_security_scans
from .specs import SPEC_KINDS, create_new_spec
from .status import run_status
from .native import ADAPTERS, get_adapter
from .native.antigravity import refresh_hook
from .native.manifest import native_source_hash
from .sync import sync_all_instructions
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
    init_p = subparsers.add_parser("init", help="Initialize DASS-AOS for the AI tools you use")
    init_p.add_argument(
        "tools", nargs="*",
        help=f"AI tools: {', '.join(TOOL_FILES)} (default: those already configured or detected in the repo)",
    )
    init_p.add_argument("--project-root", default=".", help="Root path of target project (default: current directory)")
    init_p.add_argument("--project-name", default=None, help="Name of the project (default: folder name)")
    init_p.add_argument("--force", action="store_true", help="Force overwrite existing configuration files")

    # 2. sync
    sync_p = subparsers.add_parser("sync", help="Synchronize CLAUDE.md, AGENTS.md, GEMINI.md, and editor rules")
    sync_p.add_argument("--project-root", default=".", help="Root path of target project (default: current directory)")

    native_p = subparsers.add_parser("native-hash", help="Print the source hash that adapt-native records in .aos/native/<tool>.json")
    native_p.add_argument("--project-root", default=".", help="Root path of target project (default: current directory)")

    adapt_p = subparsers.add_parser("adapt-native", help="Generate the native files of an AI tool from .aos/ (ADR-005)")
    adapt_p.add_argument("tool", help=f"Tool id: {', '.join(sorted(ADAPTERS))} (others: skill adapt-native)")
    adapt_p.add_argument("--project-root", default=".", help="Root path of target project (default: current directory)")
    adapt_p.add_argument("--dry-run", action="store_true", help="Show the changes without writing anything")
    adapt_p.add_argument("--yes", action="store_true", help="Also write hooks/permissions (sensitive config)")

    # 3. refresh
    refresh_p = subparsers.add_parser("refresh", help="Session-start hook: refresh gotchas and memory status")
    refresh_p.add_argument("--project-root", default=".", help="Root path of target project (default: current directory)")
    refresh_p.add_argument("--gotchas-limit", type=int, default=5, help="Number of recent gotchas to display")
    refresh_p.add_argument("--hook", choices=["antigravity"], help="Run as a tool hook: read its JSON on stdin, answer JSON")

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

    # 8. spec
    spec_p = subparsers.add_parser("spec", help="Manage product/technical requirement documents (PRD/TRD)")
    spec_subparsers = spec_p.add_subparsers(dest="spec_command", required=True)
    spec_new_p = spec_subparsers.add_parser("new", help="Create a new PRD or TRD from template")
    spec_new_p.add_argument("kind", choices=list(SPEC_KINDS), help="prd (what/why) or trd (how)")
    spec_new_p.add_argument("--title", required=True, help="Feature title; the TRD reuses the PRD number")
    spec_new_p.add_argument("--project-root", default=".", help="Project root directory")

    # 9. doctor
    doctor_p = subparsers.add_parser("doctor", help="Read-only audit of the agent harness loaded from .aos/ (ADR-008)")
    doctor_p.add_argument("--project-root", default=".", help="Project root directory")
    doctor_p.add_argument("--strict", action="store_true", help="Exit 1 when there are error-level findings")

    # 10. status
    status_p = subparsers.add_parser("status", help="State of the work derived from files: Working/Checking/Ready/Needs decision")
    status_p.add_argument("--project-root", default=".", help="Project root directory")
    status_p.add_argument("--json", action="store_true", help="Machine-readable output")

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI execution entrypoint."""
    configure_utf8_output()
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "init":
            root = Path(args.project_root).resolve()
            res = init_project(root, project_name=args.project_name, force=args.force, tools=args.tools, native=True)
            print(f"\n[aos init] DASS-AOS inicializado en: {res['project_root']}")
            print(f"Herramientas: {', '.join(res['tools'])} (en .aos/config.json; añade otra con `aos init <herramienta>`)")
            print("Archivos de instrucciones:")
            for fname, action in res["sync_results"].items():
                print(f"  - {fname}: {action}")
            for tool, lines in res["native_results"].items():
                print(f"Nativos de {tool}:" + ("" if lines else " al día"))
                for line in lines:
                    print(f"  - {line}")
                if any("PENDIENTE" in line for line in lines):
                    print(f"  -> Revisa los hooks pendientes y aplícalos con `aos adapt-native {tool} --yes`.")
            print("\nSiguiente paso: 'aos refresh' al inicio de cada sesión del agente.")
            return 0

        elif args.command == "sync":
            root = Path(args.project_root).resolve()
            res = sync_all_instructions(root)
            print(f"\n[aos sync] Agent instruction sync complete for: {root}")
            for fname, action in res.items():
                print(f"  - {fname}: {action}")
            return 0

        elif args.command == "native-hash":
            print(native_source_hash(Path(args.project_root).resolve()))
            return 0

        elif args.command == "adapt-native":
            adapter = get_adapter(args.tool, Path(args.project_root).resolve())
            changes = adapter.run(dry_run=args.dry_run, yes=args.yes)
            prefix = "[aos adapt-native] (dry-run) " if args.dry_run else "[aos adapt-native] "
            print(prefix + (f"{len(changes)} cambio(s) en {args.tool}:" if changes else f"{args.tool} al día, sin cambios."))
            for line in changes + [f"AVISO: {w}" for w in adapter.warnings]:
                print(f"  - {line}")
            return 0

        elif args.command == "refresh":
            root = Path(args.project_root).resolve()
            if args.hook:
                try:
                    stdin = sys.stdin.buffer.read()
                except (OSError, ValueError, AttributeError):
                    stdin = b""
                print(refresh_hook(root, stdin))
                return 0
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

        elif args.command == "spec":
            if args.spec_command == "new":
                root = Path(args.project_root).resolve()
                create_new_spec(root, kind=args.kind, title=args.title)
                return 0

        elif args.command == "doctor":
            root = Path(args.project_root).resolve()
            return run_doctor(root, strict=args.strict)

        elif args.command == "status":
            root = Path(args.project_root).resolve()
            return run_status(root, as_json=args.json)

    except Exception as exc:
        print(f"[aos ERROR]: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

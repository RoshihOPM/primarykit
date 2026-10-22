"""Small offline command router, copied into every independent PrimaryKit client.

Invoke via: python -m apps.core.cli --help
No package install, network call, migration or deployment happens implicitly.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _run(command: list[str], *, cwd: Path) -> int:
    """Never invoke a shell or interpolate user-provided command text."""
    return subprocess.run(command, cwd=cwd, check=False).returncode


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="primarykit", description="PrimaryKit project CLI")
    commands = parser.add_subparsers(dest="command", required=True)

    new = commands.add_parser("new", help="Generate an independent project (source catalog only)")
    new.add_argument("destination", type=Path)
    new.add_argument("--name", help="Defaults to destination directory name")
    new.add_argument("--preset", help="Existing source preset")
    new.add_argument("--apps", nargs="*", default=[], help="Optional module names")
    new.add_argument("--git-init", action="store_true")
    new.add_argument("--dry-run", action="store_true")

    modules = commands.add_parser("modules", help="Inspect modules present in a project")
    modules_commands = modules.add_subparsers(dest="modules_command", required=True)
    listed = modules_commands.add_parser("list", help="List modules without Django initialization")
    listed.add_argument("--project", type=Path, default=Path.cwd())
    listed.add_argument("--json", action="store_true")

    add = commands.add_parser("add", help="Copy a trusted module into a generated client")
    add.add_argument("module")
    add.add_argument("--project", type=Path, default=Path.cwd())
    add.add_argument("--source", type=Path, required=True, help="Trusted PrimaryKit checkout")
    add.add_argument("--dry-run", action="store_true")

    doctor = commands.add_parser("doctor", help="Run offline project preflight")
    doctor.add_argument("--project", type=Path, default=Path.cwd())
    doctor.add_argument("--strict", action="store_true")
    doctor.add_argument("--json", action="store_true")

    upgrade = commands.add_parser("upgrade", help="Read-only module upgrade report")
    upgrade.add_argument("--project", type=Path, default=Path.cwd())
    upgrade.add_argument("--source", type=Path, required=True, help="Trusted source checkout")
    upgrade.add_argument("--dry-run", action="store_true", help="Explicit read-only intent (default)")
    upgrade.add_argument("--three-way-plan", action="store_true")
    upgrade.add_argument("--json", action="store_true")

    sdk = commands.add_parser("sdk", help="Frontend SDK generator")
    sdk_commands = sdk.add_subparsers(dest="sdk_command", required=True)
    ts = sdk_commands.add_parser("typescript", help="Generate typed frontend client from OpenAPI")
    ts.add_argument("--project", type=Path, default=Path.cwd())
    ts.add_argument("--frontend", type=Path, required=True, help="Frontend root with package.json")
    ts.add_argument("--out", type=Path, default=Path("src/api"), help="Inside frontend")
    ts.add_argument("--schema", type=Path, help="Optional local OpenAPI YAML/JSON file")
    ts.add_argument("--force", action="store_true", help="Replace existing generated files")
    ts.add_argument("--dry-run", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "new":
            script = ROOT / "scripts" / "new_project.py"
            if not script.is_file():
                parser.error("new is source-only; use a trusted PrimaryKit catalog checkout")
            command = [
                sys.executable,
                str(script),
                str(args.destination),
                "--name",
                args.name or args.destination.name,
            ]
            if args.preset:
                command += ["--preset", args.preset]
            if args.apps:
                command += ["--apps", *args.apps]
            if args.git_init:
                command.append("--git-init")
            if args.dry_run:
                command.append("--dry-run")
            return _run(command, cwd=ROOT)

        if args.command == "modules":
            from apps.core.doctor import inspect_project

            report = inspect_project(args.project.expanduser().resolve())
            if report.failed():
                raise ValueError(
                    "Project doctor failed: " + "; ".join(item.code for item in report.findings)
                )
            if args.json:
                print(json.dumps({"modules": list(report.modules)}, indent=2))
            else:
                print("\n".join(report.modules))
            return 0

        if args.command == "doctor":
            project = args.project.expanduser().resolve()
            if not (project / "apps" / "core" / "doctor.py").is_file():
                raise ValueError("Project must contain a PrimaryKit core doctor")
            command = [sys.executable, "-m", "apps.core.doctor"]
            if args.strict:
                command.append("--strict")
            if args.json:
                command.append("--json")
            return _run(command, cwd=project)

        if args.command == "add":
            project = args.project.expanduser().resolve()
            source = args.source.expanduser().resolve()
            if not (project / "manage.py").is_file() or not (source / "apps").is_dir():
                raise ValueError("Expected a Django client and a trusted PrimaryKit source")
            if project == source:
                raise ValueError("Cannot install modules from the current project")
            command = [
                sys.executable,
                "manage.py",
                "install_kit_module",
                args.module,
                "--source",
                str(source),
            ]
            if args.dry_run:
                command.append("--dry-run")
            return _run(command, cwd=project)

        if args.command == "upgrade":
            project = args.project.expanduser().resolve()
            source = args.source.expanduser().resolve()
            script = source / "scripts" / "module_upgrade.py"
            if not script.is_file() or not (project / "primarykit-origin.json").is_file():
                raise ValueError("Expected a trusted source updater and generated project provenance")
            command = [
                sys.executable,
                str(script),
                "--source",
                str(source),
                "--project",
                str(project),
            ]
            if args.three_way_plan:
                command.append("--three-way-plan")
            if args.json:
                command.append("--json")
            return _run(command, cwd=source)

        if args.command == "sdk" and args.sdk_command == "typescript":
            from apps.core.typescript_sdk import generate_typescript_sdk

            return generate_typescript_sdk(
                project=args.project,
                frontend=args.frontend,
                output=args.out,
                schema=args.schema,
                force=args.force,
                dry_run=args.dry_run,
            )
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"primarykit: {exc}", file=sys.stderr)
        return 1
    parser.error("Unknown command")


if __name__ == "__main__":
    raise SystemExit(main())

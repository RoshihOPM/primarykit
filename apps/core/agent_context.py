"""Offline, read-only project capability brief for AI coding agents.

This module lives in generated clients. It does not run Django, access secrets,
read environment variables, connect to databases or depend on the source kit.
"""

import argparse
import json
import tomllib
from pathlib import Path

from .doctor import _manifest, _mode, inspect_project

BASELINE = frozenset({"core", "users", "notifications"})
GUARDRAILS = (
    "Implement business-owned models and rules in a new client app, not in core.",
    "Read AGENTS.md and relevant domain/services/permissions before editing.",
    "Enforce authentication and owner/tenant scope in BOTH querysets and services.",
    "Do not assume optional modules exist; verify the installed module list first.",
    "Client owns committed migrations; never regenerate or delete existing migrations.",
    "Test denied permissions/IDOR and concurrent writes; use PostgreSQL for row locks.",
    "Do not deploy, migrate production, read secrets or modify upstream PrimaryKit.",
)


def build_context(root: Path) -> dict:
    """Discover capabilities from manifest metadata without importing Django apps."""
    root = root.resolve()
    report = inspect_project(root)
    if report.failed(strict=True):
        raise ValueError("Project doctor failed; resolve module/configuration issues first")
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    modules = {}
    for name in sorted(report.modules):
        modules[name] = {
            "requires": list(_manifest(root / "apps" / name / "manifest.py", name)),
            "optional": name not in BASELINE,
        }
    return {
        "project": pyproject["project"]["name"],
        "modules": modules,
        "schema_modes": {
            name: _mode(root / "config" / "settings" / "base.py", f"{name.upper()}_MODE")
            for name in ("catalog", "inventory")
            if name in modules
        },
        "project_owns_migrations": True,
        "has_upstream_runtime_dependency": False,
        "guardrails": list(GUARDRAILS),
        "checks": [
            "python -m apps.core.doctor --strict",
            "uv run ruff check .",
            "uv run ruff format --check .",
            "uv run python manage.py check --settings=config.settings.test",
            "uv run pytest",
        ],
    }


def render_markdown(context: dict) -> str:
    lines = [
        f"# AI agent brief — {context['project']}",
        "",
        "This is an independent Django/DRF backend. Do not reference source-only scripts.",
        "",
        "## Installed modules",
    ]
    for name, info in context["modules"].items():
        deps = ", ".join(info["requires"]) or "none"
        lines.append(f"- `{name}` (requires: {deps})")
    lines.extend(("", "## Pinned schema modes"))
    for name, mode in context["schema_modes"].items():
        lines.append(f"- {name}: {mode}")
    if not context["schema_modes"]:
        lines.append("- none")
    lines.extend(("", "## Mandatory implementation rules"))
    lines.extend(f"- {rule}" for rule in context["guardrails"])
    lines.extend(("", "## Local verification"))
    lines.extend(f"- `{cmd}`" for cmd in context["checks"])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print a read-only agent brief")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args(argv)
    context = build_context(args.root)
    print(
        json.dumps(context, indent=2, ensure_ascii=False)
        if args.format == "json"
        else render_markdown(context),
        end="\n" if args.format == "json" else "",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

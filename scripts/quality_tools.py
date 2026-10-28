#!/usr/bin/env python3
"""Explicit, SHA-pinned local installation of optional Robert C. Martin code-quality tools.

Never installs anything on import, during Django startup, or in generated clients.
All external code runs only after the developer explicitly invokes install/run.
"""

import argparse
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / ".quality-tools"
TOOL_REVISIONS = {
    "crapper": "6fd92c4c9bcc56efb64a2f8743d5a2993bcfd42d",
    "dryer": "66ff6d21a42c04afcad89c78a80066176d1294b0",
    "mutator": "a5a0cb803b66e0cdb8bf471b3b08af701d424a41",
}


def _python() -> Path:
    if (STORE / "venv" / "Scripts").is_dir():
        return STORE / "venv" / "Scripts" / "python.exe"
    return STORE / "venv" / "bin" / "python"


def _git_revision(folder: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(folder), "rev-parse", "--verify", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _verify_sources() -> None:
    if STORE.is_symlink():
        raise ValueError("Refusing symlinked quality-tools directory")
    for name, revision in TOOL_REVISIONS.items():
        folder = STORE / name
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError(f"{name} is not installed as a normal directory")
        if _git_revision(folder) != revision:
            raise ValueError(f"{name}: local revision differs from the pinned SHA")
        dirty = subprocess.run(
            ["git", "-C", str(folder), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        if dirty.strip():
            raise ValueError(f"{name}: local tool checkout has uncommitted changes")


def install() -> None:
    """Clone exact audited revisions, then install into one private venv using uv."""
    if not shutil.which("git") or not shutil.which("uv"):
        raise ValueError("Install requires git and uv on PATH")
    if STORE.is_symlink():
        raise ValueError("Refusing symlinked quality-tools directory")
    STORE.mkdir(exist_ok=True)
    for name, revision in TOOL_REVISIONS.items():
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError(f"{name}: source SHA is not immutable")
        folder = STORE / name
        if not folder.exists() and not folder.is_symlink():
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--quiet",
                    "--no-checkout",
                    f"https://github.com/unclebob/{name}.git",
                    str(folder),
                ],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(folder), "checkout", "--quiet", "--detach", revision],
                check=True,
            )
    _verify_sources()
    python = _python()
    if not python.is_file():
        subprocess.run(["uv", "venv", str(STORE / "venv"), "--python", "3.13"], check=True)
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            *(str(STORE / name) for name in TOOL_REVISIONS),
        ],
        check=True,
    )
    print("Installed pinned crapper, dryer and mutator in .quality-tools/venv")


def run_tool(tool: str, arguments: list[str]) -> int:
    """Execute a chosen tool. No auto-install or network access."""
    _verify_sources()
    python = _python()
    if not python.is_file():
        raise ValueError("Tools not installed; run: uv run python scripts/quality_tools.py install")
    return subprocess.run(
        [str(python), "-m", tool, *arguments],
        check=False,
        cwd=ROOT,
    ).returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("install", "verify", *TOOL_REVISIONS))
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    options = parser.parse_args(argv)
    try:
        if options.command == "install":
            if options.arguments:
                parser.error("install accepts no additional arguments")
            install()
        elif options.command == "verify":
            if options.arguments:
                parser.error("verify accepts no additional arguments")
            _verify_sources()
            if not _python().is_file():
                raise ValueError("Python virtual environment has not been installed")
            print("All three tools match their pinned source revisions")
        else:
            return run_tool(options.command, options.arguments)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        parser.exit(1, f"quality-tools: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

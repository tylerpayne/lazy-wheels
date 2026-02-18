"""CLI entry point for lazy-wheels."""

from __future__ import annotations

import argparse
import sys
from importlib.metadata import version as pkg_version
from pathlib import Path

from lazy_wheels.workflow_steps import run_pipeline

__version__ = pkg_version("lazy-wheels")
TEMPLATES_DIR = Path(__file__).parent / "templates"


def _version_range() -> str:
    """Compute pip version range: >=current,<next_minor."""
    v = __version__
    major, minor, *_ = v.split(".")
    return f'"lazy-wheels>={v},<{major}.{int(minor) + 1}.0"'


def _matrix_include_lines(package_runners: dict[str, list[str]]) -> str:
    lines: list[str] = []
    for package, runners in package_runners.items():
        for runner in runners:
            lines.append(f'          - package: "{package}"')
            lines.append(f'            runner: "{runner}"')
    return "\n".join(lines)


def _fatal(msg: str) -> None:
    """Print error and exit."""
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)


def cmd_init(args: argparse.Namespace) -> None:
    """Scaffold the GitHub Actions workflow into your repo."""
    root = Path.cwd()

    # Sanity checks
    if not (root / ".git").exists():
        _fatal("Not a git repository. Run from the repo root.")

    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        _fatal("No pyproject.toml found in current directory.")

    import tomlkit

    doc = tomlkit.parse(pyproject.read_text())
    members = doc.get("tool", {}).get("uv", {}).get("workspace", {}).get("members")
    if not members:
        _fatal(
            "No [tool.uv.workspace] members defined in pyproject.toml.\n"
            "lazy-wheels requires a uv workspace. Example:\n\n"
            "  [tool.uv.workspace]\n"
            '  members = ["packages/*"]'
        )

    # Write workflow
    dest_dir = root / args.workflow_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "release.yml"

    # Parse matrix entries: each -m gives a list [pkg, runner1, runner2, ...]
    package_runners: dict[str, list[str]] = {}
    if args.matrix:
        for entry in args.matrix:
            if len(entry) < 2:
                _fatal(
                    f"Invalid -m: need PKG and at least one runner, got: {' '.join(entry)}"
                )
            package, *runners = entry
            package_runners[package] = runners

    if package_runners:
        template = TEMPLATES_DIR / "release-matrix.yml"
        rendered = template.read_text().replace(
            "__MATRIX_INCLUDE__", _matrix_include_lines(package_runners)
        )
    else:
        template = TEMPLATES_DIR / "release.yml"
        rendered = template.read_text()

    # Pin lazy-wheels version range
    rendered = rendered.replace("__LAZY_WHEELS_VERSION__", _version_range())
    dest.write_text(rendered)

    print(f"✓ Wrote workflow to {dest.relative_to(root)}")
    print()
    print("Next steps:")
    print("  1. Commit and push the workflow file")
    print("  2. Trigger a release:")
    print("       lazy-wheels release")
    print("       lazy-wheels release -r r1")
    print("       lazy-wheels release --force-all")


def cmd_run(args: argparse.Namespace) -> None:
    """Run the release pipeline locally (usually called from CI)."""
    run_pipeline(release=args.release, force_all=args.force_all)


def cmd_release(args: argparse.Namespace) -> None:
    """Trigger a release via GitHub Actions workflow."""
    import json
    import subprocess
    import time

    cmd = ["gh", "workflow", "run", "release.yml"]
    if args.release:
        cmd.extend(["-f", f"release={args.release}"])
    if args.force_all:
        cmd.extend(["-f", "force_rebuild_all=true"])

    print(f"Triggering: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        _fatal("Failed to trigger workflow")

    # Wait for the run to be created and fetch its URL
    print("Waiting for workflow run...")
    time.sleep(2)

    result = subprocess.run(
        [
            "gh",
            "run",
            "list",
            "--workflow=release.yml",
            "--limit=1",
            "--json=url,status",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout:
        try:
            runs = json.loads(result.stdout)
            if runs:
                url = runs[0].get("url", "")
                status = runs[0].get("status", "")
                print(f"Status: {status}")
                print(f"Watch:  {url}")
        except json.JSONDecodeError:
            pass


def cli() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="lazy-wheels",
        description="Lazy monorepo wheel builder — only rebuilds what changed.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # init subcommand
    init_parser = subparsers.add_parser(
        "init", help="Scaffold the GitHub Actions workflow into your repo."
    )
    init_parser.add_argument(
        "--workflow-dir",
        default=".github/workflows",
        help="Directory to write the workflow file. (default: %(default)s)",
    )
    init_parser.add_argument(
        "-m",
        "--matrix",
        nargs="+",
        action="append",
        metavar="PKG RUNNER",
        help="Per-package runners: -m PKG runner1 runner2 (repeatable).",
    )
    init_parser.set_defaults(func=cmd_init)

    # run subcommand
    run_parser = subparsers.add_parser(
        "run", help="Run the release pipeline locally (usually called from CI)."
    )
    run_parser.add_argument(
        "-r",
        "--release",
        default=None,
        help="Release tag (e.g., r1, r2). Auto-generates if not provided.",
    )
    run_parser.add_argument(
        "--force-all", action="store_true", help="Rebuild all packages."
    )
    run_parser.set_defaults(func=cmd_run)

    # release subcommand
    release_parser = subparsers.add_parser(
        "release", help="Trigger a release via GitHub Actions workflow."
    )
    release_parser.add_argument(
        "-r",
        "--release",
        default=None,
        help="Release tag (e.g., r1, r2). Auto-generates if not provided.",
    )
    release_parser.add_argument(
        "--force-all", action="store_true", help="Force rebuild all packages."
    )
    release_parser.set_defaults(func=cmd_release)

    args = parser.parse_args()
    args.func(args)

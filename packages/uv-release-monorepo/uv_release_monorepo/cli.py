"""CLI entry point for uv-release-monorepo."""

from __future__ import annotations

import argparse
import re
import sys
from importlib.metadata import version as pkg_version
from pathlib import Path

from uv_release_monorepo.workflow_steps import run_pipeline

__version__ = pkg_version("uv-release-monorepo")
TEMPLATES_DIR = Path(__file__).parent / "templates"


def _matrix_include_lines(package_runners: dict[str, list[str]]) -> str:
    lines: list[str] = []
    for package, runners in sorted(package_runners.items()):
        for runner in runners:
            lines.append(f'          - package: "{package}"')
            lines.append(f'            runner: "{runner}"')
    return "\n".join(lines)


def _parse_existing_matrix(workflow_path: Path) -> dict[str, list[str]]:
    """Extract package/runner pairs from an existing generated workflow."""
    if not workflow_path.exists():
        return {}

    content = workflow_path.read_text()
    result: dict[str, list[str]] = {}

    # Match consecutive package/runner pairs in the matrix include block.
    # The generated YAML always has this exact indentation pattern.
    for match in re.finditer(r'- package: "([^"]+)"\n\s+runner: "([^"]+)"', content):
        pkg, runner = match.group(1), match.group(2)
        result.setdefault(pkg, []).append(runner)

    return result


def _print_matrix_status(package_runners: dict[str, list[str]]) -> None:
    """Print each package's build runners as a list."""
    if not package_runners:
        return

    names = sorted(package_runners.keys())
    w = max(len(n) for n in names)

    print()
    print("Build matrix:")
    for pkg in names:
        runners = package_runners[pkg]
        print(f"  {pkg.ljust(w)}  \u2192  {', '.join(runners)}")


def _discover_packages(root: Path | None = None) -> dict[str, tuple[str, list[str]]]:
    """Scan workspace members and return {name: (version, [internal_dep_names])}.

    Lightweight alternative to pipeline.discover_packages() — no git or
    shell calls, no stdout output.

    Args:
        root: Workspace root directory. Defaults to the current working directory.
    """
    import glob as globmod

    import tomlkit
    from packaging.utils import canonicalize_name

    root = root or Path.cwd()
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return {}

    doc = tomlkit.parse(pyproject.read_text())
    member_globs = (
        doc.get("tool", {}).get("uv", {}).get("workspace", {}).get("members", [])
    )

    # First pass: collect names, versions, and raw dependency strings
    packages: dict[str, tuple[str, list[str]]] = {}
    raw_deps: dict[str, list[str]] = {}
    for pattern in member_globs:
        for match in sorted(globmod.glob(str(root / pattern))):
            p = Path(match)
            pkg_toml = p / "pyproject.toml"
            if pkg_toml.exists():
                pkg_doc = tomlkit.parse(pkg_toml.read_text())
                raw_name = pkg_doc.get("project", {}).get("name", p.name)
                name = canonicalize_name(raw_name)
                version = pkg_doc.get("project", {}).get("version", "0.0.0")
                packages[name] = (version, [])
                # Gather all dependency strings
                dep_strs = list(pkg_doc.get("project", {}).get("dependencies", []))
                for group in (
                    pkg_doc.get("project", {}).get("optional-dependencies", {}).values()
                ):
                    dep_strs.extend(group)
                for group in pkg_doc.get("dependency-groups", {}).values():
                    dep_strs.extend(s for s in group if isinstance(s, str))
                raw_deps[name] = dep_strs

    # Second pass: resolve internal deps
    workspace_names = set(packages.keys())
    for name, dep_strs in raw_deps.items():
        for dep_str in dep_strs:
            # Extract bare name (before any version spec, extras, etc.)
            bare = re.split(r"[>=<!;\[\s]", dep_str, maxsplit=1)[0]
            dep_name = canonicalize_name(bare)
            if dep_name in workspace_names and dep_name != name:
                packages[name][1].append(dep_name)

    return packages


def _print_dependencies(
    packages: dict[str, tuple[str, list[str]]],
    *,
    direct_dirty: set[str] | None = None,
    transitive_dirty: set[str] | None = None,
) -> None:
    """Print each package's version and internal dependencies as a list."""
    if not packages:
        return

    direct_dirty = direct_dirty or set()
    transitive_dirty = transitive_dirty or set()
    names = sorted(packages.keys())
    w = max(len(n) for n in names)
    vw = max(len(packages[n][0]) for n in names)

    print()
    print("Dependencies:")
    for name in names:
        version, deps = packages[name]
        if name in direct_dirty:
            label = f"* {name}"
        elif name in transitive_dirty:
            label = f"+ {name}"
        else:
            label = f"  {name}"
        ver_col = version.ljust(vw)
        if deps:
            print(
                f"  {label.ljust(w + 2)}  {ver_col}  \u2192  {', '.join(sorted(deps))}"
            )
        else:
            print(f"  {label.ljust(w + 2)}  {ver_col}")
    has_direct = direct_dirty & set(names)
    has_transitive = transitive_dirty & set(names)
    if has_direct or has_transitive:
        print()
        if has_direct:
            print("  * = changed since last release")
        if has_transitive:
            print("  + = rebuild (dependency changed)")


def _discover_package_names() -> list[str]:
    """Scan workspace members and return sorted package names."""
    return sorted(_discover_packages().keys())


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
            "uvr requires a uv workspace. Example:\n\n"
            "  [tool.uv.workspace]\n"
            '  members = ["packages/*"]'
        )

    # Write workflow
    dest_dir = root / args.workflow_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "release.yml"

    # Start with existing matrix entries (additive)
    package_runners = _parse_existing_matrix(dest)

    # Overlay new -m entries (replace per-package)
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

    dest.write_text(rendered)

    print(f"\u2713 Wrote workflow to {dest.relative_to(root)}")
    _print_matrix_status(package_runners)
    print()
    print("Next steps:")
    print("  1. Commit and push the workflow file")
    print("  2. Trigger a release:")
    print("       uvr release")
    print("       uvr release -r r1")
    print("       uvr release --force-all")


def cmd_run(args: argparse.Namespace) -> None:
    """Run the release pipeline locally (usually called from CI)."""
    run_pipeline(
        release=args.release,
        force_all=args.force_all,
        push=not args.no_push,
        dry_run=args.dry_run,
    )


def cmd_release(args: argparse.Namespace) -> None:
    """Trigger a release via GitHub Actions workflow."""
    import json
    import subprocess
    import time

    cmd = ["gh", "workflow", "run", "release.yml"]
    cmd.extend(["-f", f"uvr_version={__version__}"])
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


def cmd_status(args: argparse.Namespace) -> None:
    """Show the current workflow configuration."""
    from uv_release_monorepo.pipeline import (
        detect_changes,
        discover_packages,
        find_dev_baselines,
    )

    root = Path.cwd()
    dest = root / args.workflow_dir / "release.yml"

    if not dest.exists():
        print("No release workflow found.")
        print("Run `uvr init` to create one.")
        return

    package_runners = _parse_existing_matrix(dest)
    packages = _discover_packages()
    if not package_runners:
        if packages:
            package_runners = {pkg: ["ubuntu-latest"] for pkg in packages}

    # Detect dirty packages using the pipeline's logic (suppress verbose output)
    import io

    direct_dirty: set[str] = set()
    transitive_dirty: set[str] = set()
    try:
        old_stdout = sys.stdout
        captured = io.StringIO()
        sys.stdout = captured
        try:
            pipeline_pkgs = discover_packages()
            dev_baselines = find_dev_baselines(pipeline_pkgs)
            all_dirty = set(
                detect_changes(pipeline_pkgs, dev_baselines, force_all=False)
            )
        finally:
            sys.stdout = old_stdout

        # Parse captured output to distinguish direct vs transitive
        for line in captured.getvalue().splitlines():
            stripped = line.strip()
            if "dirty (depends on" in stripped:
                pkg_name = stripped.split(":")[0]
                transitive_dirty.add(pkg_name)
        direct_dirty = all_dirty - transitive_dirty
    except (SystemExit, Exception):
        pass  # Non-fatal — just skip dirty markers if detection fails

    _print_matrix_status(package_runners)
    _print_dependencies(
        packages, direct_dirty=direct_dirty, transitive_dirty=transitive_dirty
    )


def cli() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="uvr",
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
    run_parser.add_argument(
        "--no-push",
        action="store_true",
        help="Skip git push (useful when workflow handles push separately).",
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be released without making any changes.",
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

    # status subcommand
    status_parser = subparsers.add_parser(
        "status", help="Show the current workflow configuration."
    )
    status_parser.add_argument(
        "--workflow-dir",
        default=".github/workflows",
        help="Directory containing the workflow file. (default: %(default)s)",
    )
    status_parser.set_defaults(func=cmd_status)

    args = parser.parse_args()
    args.func(args)

"""CLI entry point for uv-release-monorepo."""

from __future__ import annotations

import argparse
import json
import sys
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import NoReturn

from .pipeline import build_plan, execute_plan
from .toml import get_uvr_matrix, load_pyproject, save_pyproject, set_uvr_matrix
from .workflow_steps import run_pipeline

__version__ = pkg_version("uv-release-monorepo")
TEMPLATES_DIR = Path(__file__).parent / "templates"


def _read_matrix(root: Path) -> dict[str, list[str]]:
    """Read [tool.uvr.matrix] from the workspace pyproject.toml."""
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return {}
    return get_uvr_matrix(load_pyproject(pyproject))


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
    from packaging.requirements import Requirement
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
            try:
                dep_name = canonicalize_name(Requirement(dep_str).name)
            except Exception:
                continue
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


def _fatal(msg: str) -> NoReturn:
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

    doc = load_pyproject(pyproject)
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
    package_runners = _read_matrix(root)

    # Overlay new -m entries (replace per-package)
    if args.matrix:
        for entry in args.matrix:
            if len(entry) < 2:
                _fatal(
                    f"Invalid -m: need PKG and at least one runner, got: {' '.join(entry)}"
                )
            package, *runners = entry
            package_runners[package] = runners

    # Write matrix config to pyproject.toml
    set_uvr_matrix(doc, package_runners)
    save_pyproject(pyproject, doc)

    # Write workflow template
    template = TEMPLATES_DIR / "release.yml"
    dest.write_text(template.read_text())

    print(f"\u2713 Wrote workflow to {dest.relative_to(root)}")
    _print_matrix_status(package_runners)
    print()
    print("Next steps:")
    print("  1. Commit and push the workflow file")
    print("  2. Trigger a release:")
    print("       uvr release")
    print("       uvr release --force-all")


def cmd_run(args: argparse.Namespace) -> None:
    """Run the release pipeline locally (usually called from CI)."""
    if getattr(args, "plan", None):
        from uv_release_monorepo.models import ReleasePlan

        plan = ReleasePlan.model_validate_json(args.plan)
        execute_plan(plan, push=not args.no_push)
    else:
        run_pipeline(
            force_all=args.force_all,
            push=not args.no_push,
            dry_run=args.dry_run,
        )


def cmd_release(args: argparse.Namespace) -> None:
    """Generate a release plan locally and dispatch the executor workflow."""
    import subprocess
    import time

    root = Path.cwd()
    workflow_path = root / args.workflow_dir / "release.yml"
    if not workflow_path.exists():
        _fatal("No release workflow found. Run `uvr init` first.")

    # Read stored matrix from pyproject.toml
    package_runners = _read_matrix(root)

    # Build the plan locally (runs discovery + change detection)
    plan = build_plan(
        force_all=args.force_all,
        matrix=package_runners,
        uvr_version=__version__,
        python_version=args.python_version,
    )

    if not plan.changed:
        print("Nothing changed since last release. Use --force-all to rebuild all.")
        return

    if args.dry_run:
        print(json.dumps(plan.model_dump(), indent=2))
        return

    plan_json = plan.model_dump_json()
    cmd = [
        "gh",
        "workflow",
        "run",
        "release.yml",
        "-f",
        f"plan={plan_json}",
        "-f",
        f"uvr_version={__version__}",
    ]
    print(f"Triggering release for: {', '.join(sorted(plan.changed))}")
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

    package_runners = _read_matrix(root)
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


def _parse_install_spec(spec: str) -> tuple[str | None, str, str | None]:
    """Parse an install spec into (gh_repo, package, version).

    Accepted forms:
      package[@version]              — local workspace package
      org/repo/package[@version]     — remote GitHub repo
    """
    version: str | None = None
    if "@" in spec:
        spec, version = spec.rsplit("@", 1)

    parts = spec.split("/")
    if len(parts) == 1:
        return None, parts[0], version
    elif len(parts) == 3:
        org, repo, package = parts
        return f"{org}/{repo}", package, version
    else:
        _fatal(
            f"Invalid install spec '{spec}'. "
            "Expected 'package' or 'org/repo/package', optionally with '@version'."
        )


def _find_latest_release_tag(package: str, gh_repo: str | None = None) -> str | None:
    """Return the most recent non-dev release tag for a package.

    Queries GitHub releases for tags matching {package}/v*, excludes -dev tags,
    and returns the one with the highest version number.
    """
    import subprocess

    from packaging.version import Version

    cmd = ["gh", "release", "list", "--json", "tagName", "--limit", "200"]
    if gh_repo:
        cmd.extend(["--repo", gh_repo])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    try:
        releases = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

    prefix = f"{package}/v"
    tags = [
        r["tagName"]
        for r in releases
        if r["tagName"].startswith(prefix) and not r["tagName"].endswith("-dev")
    ]
    if not tags:
        return None
    return max(tags, key=lambda t: Version(t.split("/v")[-1]))


def cmd_install(args: argparse.Namespace) -> None:
    """Install a package and its transitive internal deps from GitHub releases."""
    import subprocess
    import tempfile

    gh_repo, package, version = _parse_install_spec(args.package)

    if gh_repo is None:
        # Local workspace: resolve transitive internal deps via workspace graph
        packages = _discover_packages()
        if package not in packages:
            _fatal(f"Package '{package}' not found in workspace.")

        order: list[str] = []
        visited: set[str] = set()
        stack = [package]
        while stack:
            pkg = stack.pop()
            if pkg in visited:
                continue
            visited.add(pkg)
            order.append(pkg)
            for dep in packages[pkg][1]:
                if dep not in visited:
                    stack.append(dep)
        order.reverse()  # deps before dependents
    else:
        # Remote: install only the requested package; pip resolves external deps
        order = [package]

    with tempfile.TemporaryDirectory() as tmp:
        wheels: list[str] = []
        for pkg in order:
            if pkg == package and version:
                tag = f"{pkg}/v{version}"
            else:
                tag = _find_latest_release_tag(pkg, gh_repo=gh_repo)
            if not tag:
                _fatal(f"No release found for '{pkg}'.")

            cmd = [
                "gh",
                "release",
                "download",
                tag,
                "--pattern",
                "*.whl",
                "--dir",
                tmp,
                "--clobber",
            ]
            if gh_repo:
                cmd.extend(["--repo", gh_repo])

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                _fatal(f"Failed to download release {tag}: {result.stderr.strip()}")

            found = list(Path(tmp).glob(f"{pkg.replace('-', '_')}-*.whl"))
            if not found:
                _fatal(f"No wheel found for '{pkg}' in release {tag}.")
            wheels.append(str(found[0]))
            print(f"  {found[0].name}")

        print(f"\nInstalling {len(wheels)} wheel(s)...")
        subprocess.run(["uv", "pip", "install", *wheels], check=True)


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
    run_parser.add_argument(
        "--plan",
        default=None,
        help="Execute a pre-computed release plan JSON instead of running discovery.",
    )
    run_parser.set_defaults(func=cmd_run)

    # release subcommand
    release_parser = subparsers.add_parser(
        "release",
        help="Generate a release plan locally and dispatch the executor workflow.",
    )
    release_parser.add_argument(
        "--force-all", action="store_true", help="Force rebuild all packages."
    )
    release_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the release plan as JSON without dispatching.",
    )
    release_parser.add_argument(
        "--python",
        default="3.12",
        metavar="VERSION",
        dest="python_version",
        help="Python version for CI builds. (default: %(default)s)",
    )
    release_parser.add_argument(
        "--workflow-dir",
        default=".github/workflows",
        help="Directory containing the workflow file. (default: %(default)s)",
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

    # install subcommand
    install_parser = subparsers.add_parser(
        "install",
        help="Install a workspace package and its internal deps from GitHub releases.",
    )
    install_parser.add_argument(
        "package",
        help="Package name, optionally pinned: PACKAGE[@VERSION]",
    )
    install_parser.set_defaults(func=cmd_install)

    args = parser.parse_args()
    args.func(args)

"""Shared CLI utilities — used by multiple CLI commands."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import NoReturn

from importlib.metadata import version as pkg_version

from .config import get_hooks, get_matrix
from .toml import read_pyproject

__version__ = pkg_version("uv-release-monorepo")


def fatal(msg: str) -> NoReturn:
    """Print error and exit."""
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)


def diff_stat(baseline_tag: str | None, pkg_path: str) -> tuple[str, str]:
    """Return (changes_str, commits_str) for a package since its baseline."""
    if not baseline_tag:
        return ("-", "-")

    result = subprocess.run(
        ["git", "diff", "--shortstat", f"{baseline_tag}..HEAD", "--", pkg_path],
        capture_output=True,
        text=True,
    )
    adds, dels = 0, 0
    if result.returncode == 0 and result.stdout.strip():
        for part in result.stdout.strip().split(","):
            part = part.strip()
            if "insertion" in part:
                adds = int(part.split()[0])
            elif "deletion" in part:
                dels = int(part.split()[0])
    changes = f"+{adds} / -{dels}"

    result = subprocess.run(
        ["git", "rev-list", "--count", f"{baseline_tag}..HEAD", "--", pkg_path],
        capture_output=True,
        text=True,
    )
    commits = result.stdout.strip() if result.returncode == 0 else "-"

    return changes, commits


def read_matrix(root: Path) -> dict[str, list[list[str]]]:
    """Read [tool.uvr.matrix] from the workspace pyproject.toml."""
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return {}
    return get_matrix(read_pyproject(pyproject))


def read_hooks(root: Path) -> dict[str, str]:
    """Read [tool.uvr.hooks] from the workspace pyproject.toml."""
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return {}
    return get_hooks(read_pyproject(pyproject))


def resolve_plan_json(raw: str | None) -> str:
    """Resolve plan JSON from a --plan arg, @file path, or UVR_PLAN env var."""
    import os

    value = raw or os.environ.get("UVR_PLAN", "")
    if value.startswith("@"):
        value = Path(value[1:]).read_text()
    if not value:
        fatal("No plan provided. Pass --plan JSON, --plan @file, or set UVR_PLAN.")
    return value


def parse_install_spec(spec: str) -> tuple[str, str, str | None]:
    """Parse an install spec into (gh_repo, package, version).

    Required form: ``org/repo/package[@version]``
    """
    version: str | None = None
    if "@" in spec:
        spec, version = spec.rsplit("@", 1)

    parts = spec.split("/")
    if len(parts) == 3:
        org, repo, package = parts
        return f"{org}/{repo}", package, version
    else:
        fatal(
            f"Invalid install spec '{spec}'. "
            "Expected 'org/repo/package', optionally with '@version'.\n"
            "  Example: uvr install myorg/myrepo/my-pkg@1.0.0"
        )


def discover_packages(root: Path | None = None) -> dict[str, tuple[str, list[str]]]:
    """Scan workspace members and return {name: (version, [internal_dep_names])}.

    Lightweight alternative to pipeline.discover_packages() — no git or
    shell calls, no stdout output.
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
                ver = pkg_doc.get("project", {}).get("version", "0.0.0")
                packages[name] = (ver, [])
                dep_strs = list(pkg_doc.get("project", {}).get("dependencies", []))
                for group in (
                    pkg_doc.get("project", {}).get("optional-dependencies", {}).values()
                ):
                    dep_strs.extend(group)
                for group in pkg_doc.get("dependency-groups", {}).values():
                    dep_strs.extend(s for s in group if isinstance(s, str))
                raw_deps[name] = dep_strs

    # Apply include/exclude filters from [tool.uvr.config]
    uvr_config = doc.get("tool", {}).get("uvr", {}).get("config", {})
    include = list(uvr_config.get("include", []))
    exclude = list(uvr_config.get("exclude", []))
    if include:
        packages = {n: p for n, p in packages.items() if n in include}
        raw_deps = {n: d for n, d in raw_deps.items() if n in packages}
    if exclude:
        for name in exclude:
            packages.pop(name, None)
            raw_deps.pop(name, None)

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


def discover_package_names() -> list[str]:
    """Scan workspace members and return sorted package names."""
    return sorted(discover_packages().keys())


def print_matrix_status(package_runners: dict[str, list[list[str]]]) -> None:
    """Print the build matrix grouped by runner."""
    if not package_runners:
        return

    runner_to_pkgs: dict[str, list[str]] = {}
    for pkg, runners in package_runners.items():
        for labels in runners:
            key = f"[{', '.join(labels)}]"
            runner_to_pkgs.setdefault(key, []).append(pkg)

    print()
    print("Build matrix:")
    for runner in sorted(runner_to_pkgs):
        print(f"  {runner}")
        for pkg in sorted(runner_to_pkgs[runner]):
            print(f"    {pkg}")


def print_dependencies(
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
        ver, deps = packages[name]
        if name in direct_dirty:
            label = f"* {name}"
        elif name in transitive_dirty:
            label = f"+ {name}"
        else:
            label = f"  {name}"
        ver_col = ver.ljust(vw)
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

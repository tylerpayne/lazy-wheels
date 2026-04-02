"""Package discovery: scan workspace and find packages."""

from __future__ import annotations

import glob as _glob
from pathlib import Path

import tomlkit
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from .config import get_config
from ..models import PackageInfo
from .shell import exit_fatal, print_step
from .toml import get_path, read_pyproject

from .dependencies import _get_dependency_sections


def canonicalize_dependency(dep_str: str) -> str:
    """Extract the canonical package name from a PEP 508 dependency string.

    Handles version specifiers, extras, and normalizes the name per PEP 503
    (lowercase, hyphens instead of underscores).

    Examples:
        "requests>=2.0" -> "requests"
        "My_Package[extra]~=1.0" -> "my-package"
    """
    return canonicalize_name(Requirement(dep_str).name)


def get_dependencies(doc: tomlkit.TOMLDocument) -> list[str]:
    """Collect all dependency strings from a pyproject.toml.

    Gathers dependencies from four locations:
    - [build-system].requires (build-time deps)
    - [project].dependencies (main runtime deps)
    - [project].optional-dependencies.* (extras like [dev], [test])
    - [dependency-groups].* (PEP 735 dependency groups)

    Returns raw PEP 508 strings like "requests>=2.0" or "pkg[extra]~=1.0".
    """
    deps: list[str] = list(get_path(doc, "build-system", "requires", default=[]))
    for dep_list in _get_dependency_sections(doc):
        deps.extend(dep_list)
    return deps


def find_packages(root: Path | None = None) -> dict[str, PackageInfo]:
    """Scan the workspace and discover all packages.

    Reads [tool.uv.workspace].members from root pyproject.toml to find
    package directories, then extracts name, version, and internal deps
    from each package's pyproject.toml.

    Args:
        root: Workspace root directory. Defaults to the current working directory.

    Returns:
        Map of package name to PackageInfo.
    """
    print_step("Discovering workspace packages")

    root = root or Path.cwd()
    root_doc = read_pyproject(root / "pyproject.toml")

    # Inline get_workspace_member_globs logic
    members = get_path(root_doc, "tool", "uv", "workspace", "members")
    if not members:
        exit_fatal("No [tool.uv.workspace] members defined in root pyproject.toml")
    member_globs = list(members)

    # Expand globs to find all package directories
    member_dirs: list[Path] = []
    for pattern in member_globs:
        for match in sorted(_glob.glob(str(root / pattern))):
            p = Path(match)
            if (p / "pyproject.toml").exists():
                member_dirs.append(p)

    if not member_dirs:
        exit_fatal(
            "No packages found matching workspace members. "
            "Run from repo root; check [tool.uv.workspace].members in pyproject.toml."
        )

    # First pass: collect basic info from each package
    packages: dict[str, PackageInfo] = {}
    raw_deps: dict[str, list[str]] = {}

    for d in member_dirs:
        doc = read_pyproject(d / "pyproject.toml")
        name = canonicalize_name(get_path(doc, "project", "name", default=d.name))
        packages[name] = PackageInfo(
            path=str(d.relative_to(root)),
            version=get_path(doc, "project", "version", default="0.0.0"),
        )
        # Use [project].dependencies and [build-system].requires for build
        # order. Optional deps and dependency groups are not required.
        raw_deps[name] = list(get_path(doc, "project", "dependencies", default=[]))
        raw_deps[name].extend(get_path(doc, "build-system", "requires", default=[]))

    # Apply include/exclude filters from [tool.uvr.config]
    uvr_config = get_config(root_doc)
    include = uvr_config["include"]
    exclude = uvr_config["exclude"]
    if include:
        packages = {n: p for n, p in packages.items() if n in include}
        raw_deps = {n: d for n, d in raw_deps.items() if n in packages}
    if exclude:
        for name in exclude:
            packages.pop(name, None)
            raw_deps.pop(name, None)

    # Second pass: identify which deps are internal (within workspace)
    workspace_names = set(packages.keys())
    for name, deps in raw_deps.items():
        seen: set[str] = set()
        for dep_str in deps:
            dep_name = canonicalize_dependency(dep_str)
            # Only track internal deps, ignore external packages
            if dep_name in workspace_names and dep_name not in seen:
                packages[name].deps.append(dep_name)
                seen.add(dep_name)

    # Print discovered packages for user feedback
    for name, info in packages.items():
        deps = f" -> [{', '.join(info.deps)}]" if info.deps else ""
        print(f"  {name} {info.version} ({info.path}){deps}")

    return packages

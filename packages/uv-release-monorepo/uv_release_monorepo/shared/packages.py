"""Package discovery: scan workspace and find release/baseline tags."""

from __future__ import annotations

import glob as _glob
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import tomlkit
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

if TYPE_CHECKING:
    import semver

from .config import get_config
from .models import PackageInfo
from .shell import exit_fatal, print_step
from .toml import get_path, read_pyproject


# ---------------------------------------------------------------------------
# Private helpers (absorbed from deps.py and discovery.py)
# ---------------------------------------------------------------------------


def _canonicalize_dependency(dep_str: str) -> str:
    """Extract the canonical package name from a PEP 508 dependency string.

    Handles version specifiers, extras, and normalizes the name per PEP 503
    (lowercase, hyphens instead of underscores).

    Examples:
        "requests>=2.0" -> "requests"
        "My_Package[extra]~=1.0" -> "my-package"
    """
    return canonicalize_name(Requirement(dep_str).name)


def _get_dependency_sections(doc: tomlkit.TOMLDocument) -> Iterator[list]:
    """Yield every mutable dependency list from a pyproject.toml.

    Covers [project].dependencies, [project].optional-dependencies.*,
    and [dependency-groups].*.  Does NOT include [build-system].requires.
    """
    project = doc.get("project", {})
    deps = project.get("dependencies")
    if isinstance(deps, list):
        yield deps
    for group in project.get("optional-dependencies", {}).values():
        if isinstance(group, list):
            yield group
    for group in doc.get("dependency-groups", {}).values():
        if isinstance(group, list):
            yield group


def _get_dependencies(doc: tomlkit.TOMLDocument) -> list[str]:
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


def _parse_version(version_str: str) -> semver.Version:
    """Parse a version string into a semver.Version object.

    Strips all dev/pre/post suffixes first, then handles incomplete versions
    by padding with zeros.
    """
    import semver as _semver

    from .planner._versions import get_base_version

    cleaned = get_base_version(version_str)
    parts = cleaned.split(".")
    while len(parts) < 3:
        parts.append("0")
    return _semver.Version.parse(".".join(parts[:3]))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


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
        raw_deps[name] = _get_dependencies(doc)

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
            dep_name = _canonicalize_dependency(dep_str)
            # Only track internal deps, ignore external packages
            if dep_name in workspace_names and dep_name not in seen:
                packages[name].deps.append(dep_name)
                seen.add(dep_name)

    # Print discovered packages for user feedback
    for name, info in packages.items():
        deps = f" -> [{', '.join(info.deps)}]" if info.deps else ""
        print(f"  {name} {info.version} ({info.path}){deps}")

    return packages


def find_release_tags(
    packages: dict[str, PackageInfo],
    gh_releases: set[str],
) -> dict[str, str | None]:
    """Find the most recent GitHub release tag for each package.

    Queries actual GitHub releases (not git tags) to find the most recent
    release whose version is less than the package's current base version.
    This ensures baseline tags and unreleased tags are never matched.

    Args:
        packages: Map of package name -> PackageInfo.
        gh_releases: Set of GitHub release tag names (from :func:`git.remote.list_release_tag_names`).

    Returns:
        Map of package name to its last release tag, or None if no release exists.
    """
    print_step("Finding last release tags")

    release_tag_names = gh_releases
    release_tags: dict[str, str | None] = {}
    for name, info in packages.items():
        current_base = _parse_version(info.version)
        # Filter to this package's releases, sorted by version descending
        pkg_releases = []
        prefix = f"{name}/v"
        for tag in release_tag_names:
            if not tag.startswith(prefix):
                continue
            tag_ver_str = tag[len(prefix) :]
            try:
                tag_ver = _parse_version(tag_ver_str)
            except (ValueError, TypeError):
                continue
            if tag_ver < current_base:
                pkg_releases.append((tag_ver, tag))
        # Pick the highest version
        pkg_releases.sort(reverse=True)
        release_tags[name] = pkg_releases[0][1] if pkg_releases else None
        print(f"  {name}: {release_tags[name] or '<none>'}")

    return release_tags


def find_baseline_tags(
    packages: dict[str, PackageInfo],
    all_tags: set[str],
) -> dict[str, str | None]:
    """Derive baseline tags from each package's pyproject.toml version.

    The baseline tag is ``{name}/v{version}-base`` where *version* comes from
    pyproject.toml. If the tag does not exist, returns None for that package.

    Args:
        packages: Map of package name -> PackageInfo.
        all_tags: Set of all git tag names (from :func:`git.local.list_tags`).

    Returns:
        Map of package name to its baseline tag, or None if no tag exists.
    """
    print_step("Finding baselines")

    baselines: dict[str, str | None] = {}
    for name, info in packages.items():
        base_tag = f"{name}/v{info.version}-base"
        baselines[name] = base_tag if base_tag in all_tags else None
        print(f"  {name}: {baselines[name] or '<none>'}")

    return baselines

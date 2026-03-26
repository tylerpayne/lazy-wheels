"""Package discovery: scan workspace and find release/baseline tags."""

from __future__ import annotations

import glob as _glob
from pathlib import Path


from .deps import dep_canonical_name
from .models import PackageInfo
from .shell import fatal, git, step
from .toml import (
    get_all_dependency_strings,
    get_project_name,
    get_project_version,
    get_uvr_config,
    get_workspace_member_globs,
    load_pyproject,
)


def discover_packages(root: Path | None = None) -> dict[str, PackageInfo]:
    """Scan the workspace and discover all packages.

    Reads [tool.uv.workspace].members from root pyproject.toml to find
    package directories, then extracts name, version, and internal deps
    from each package's pyproject.toml.

    Args:
        root: Workspace root directory. Defaults to the current working directory.

    Returns:
        Map of package name to PackageInfo.
    """
    step("Discovering workspace packages")

    root = root or Path.cwd()
    root_doc = load_pyproject(root / "pyproject.toml")
    member_globs = get_workspace_member_globs(root_doc)

    # Expand globs to find all package directories
    member_dirs: list[Path] = []
    for pattern in member_globs:
        for match in sorted(_glob.glob(str(root / pattern))):
            p = Path(match)
            if (p / "pyproject.toml").exists():
                member_dirs.append(p)

    if not member_dirs:
        fatal(
            "No packages found matching workspace members. "
            "Run from repo root; check [tool.uv.workspace].members in pyproject.toml."
        )

    # First pass: collect basic info from each package
    packages: dict[str, PackageInfo] = {}
    raw_deps: dict[str, list[str]] = {}

    for d in member_dirs:
        doc = load_pyproject(d / "pyproject.toml")
        name = get_project_name(doc, d.name)
        packages[name] = PackageInfo(
            path=str(d.relative_to(root)),
            version=get_project_version(doc),
        )
        raw_deps[name] = get_all_dependency_strings(doc)

    # Apply include/exclude filters from [tool.uvr.config]
    uvr_config = get_uvr_config(root_doc)
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
            dep_name = dep_canonical_name(dep_str)
            # Only track internal deps, ignore external packages
            if dep_name in workspace_names and dep_name not in seen:
                packages[name].deps.append(dep_name)
                seen.add(dep_name)

    # Print discovered packages for user feedback
    for name, info in packages.items():
        deps = f" -> [{', '.join(info.deps)}]" if info.deps else ""
        print(f"  {name} {info.version} ({info.path}){deps}")

    return packages


def find_release_tags(packages: dict[str, PackageInfo]) -> dict[str, str | None]:
    """Find the most recent release tag for each package.

    The release tag is the most recent ``{name}/v{version}`` tag whose
    version is less than or equal to the package's current base version.
    Baseline tags (``-base``) are excluded.

    Args:
        packages: Map of package name -> PackageInfo.

    Returns:
        Map of package name to its last release tag, or None if no tag exists.
    """
    from .versions import parse_version

    step("Finding last release tags")

    release_tags: dict[str, str | None] = {}
    for name, info in packages.items():
        current_base = parse_version(info.version)
        tags = git("tag", "--list", f"{name}/v*", "--sort=-v:refname", check=False)
        found = None
        for tag in tags.splitlines():
            if tag.endswith("-base"):
                continue
            # Extract version and check it's a real release at or below current
            tag_ver_str = tag.split("/v", 1)[-1]
            try:
                tag_ver = parse_version(tag_ver_str)
            except (ValueError, TypeError):
                continue
            if tag_ver <= current_base:
                found = tag
                break
        release_tags[name] = found
        print(f"  {name}: {found or '<none>'}")

    return release_tags


def get_baseline_tags(packages: dict[str, PackageInfo]) -> dict[str, str | None]:
    """Derive baseline tags from each package's pyproject.toml version.

    The baseline tag is ``{name}/v{version}-base`` where *version* comes from
    pyproject.toml. If the tag does not exist, returns None for that package.

    Args:
        packages: Map of package name -> PackageInfo.

    Returns:
        Map of package name to its baseline tag, or None if no tag exists.
    """
    step("Finding baselines")

    baselines: dict[str, str | None] = {}
    for name, info in packages.items():
        base_tag = f"{name}/v{info.version}-base"
        result = git("tag", "--list", base_tag, check=False)
        if result.strip():
            baselines[name] = base_tag
        else:
            baselines[name] = None
        print(f"  {name}: {baselines[name] or '<none>'}")

    return baselines

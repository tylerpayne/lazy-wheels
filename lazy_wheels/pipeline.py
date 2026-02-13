"""Release pipeline: discover → diff → build → tag → bump → publish.

This module orchestrates the lazy-wheels release process:
1. Discover all packages in the workspace
2. Detect which packages changed since last release
3. Fetch unchanged wheels from previous release (avoid rebuilding)
4. Build only the changed packages
5. Create a git tag for the release
6. Bump versions for next development cycle
7. Publish wheels to GitHub Releases

The key optimization is that unchanged packages are not rebuilt - their
wheels are reused from the previous release.
"""

from __future__ import annotations

import glob
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from packaging.utils import canonicalize_name

from .deps import dep_canonical_name, rewrite_pyproject
from .graph import topo_sort
from .models import PackageInfo, VersionBump
from .shell import fatal, git, run, step
from .toml import (
    get_all_dependency_strings,
    get_project_name,
    get_project_version,
    get_workspace_member_globs,
    load_pyproject,
)
from .versions import bump_patch


def discover_packages() -> tuple[dict[str, PackageInfo], list[str]]:
    """Scan the workspace and discover all packages.

    Reads [tool.uv.workspace].members from root pyproject.toml to find
    package directories, then extracts name, version, and internal deps
    from each package's pyproject.toml.

    Returns:
        Tuple of (packages dict, topologically sorted build order).
    """
    step("Discovering workspace packages")

    root = Path.cwd()
    root_doc = load_pyproject(root / "pyproject.toml")
    member_globs = get_workspace_member_globs(root_doc)

    # Expand globs to find all package directories
    member_dirs: list[Path] = []
    for pattern in member_globs:
        for match in sorted(glob.glob(str(root / pattern))):
            p = Path(match)
            if (p / "pyproject.toml").exists():
                member_dirs.append(p)

    if not member_dirs:
        fatal("No packages found matching workspace members")

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

    # Sort packages so dependencies come before dependents
    order = topo_sort(packages)

    # Print discovered packages for user feedback
    for name in order:
        info = packages[name]
        deps = f" → [{', '.join(info.deps)}]" if info.deps else ""
        print(f"  {name} {info.version} ({info.path}){deps}")

    return packages, order


def find_last_tag() -> str | None:
    """Find the most recent release tag (v* pattern).

    Tags are sorted by version, so v2024.01.15-abc comes after v2024.01.14-xyz.
    Returns None if no release tags exist yet.
    """
    step("Finding last release tag")
    tags = git("tag", "--list", "v*", "--sort=-v:refname", check=False)
    tag = tags.splitlines()[0] if tags else None
    print(f"  {tag or '<none — will build everything>'}")
    return tag


def detect_changes(
    packages: dict[str, PackageInfo],
    topo_order: list[str],
    last_tag: str | None,
    force_all: bool,
) -> tuple[list[str], list[str]]:
    """Determine which packages need to be rebuilt.

    A package is "dirty" and needs rebuilding if:
    1. force_all is True (rebuild everything)
    2. Any file in the package directory changed since last_tag
    3. Root pyproject.toml or uv.lock changed (affects all packages)
    4. Any of its dependencies are dirty (transitive dirtiness)

    Args:
        packages: Map of package name → PackageInfo.
        topo_order: Packages in topological order.
        last_tag: Previous release tag, or None for first release.
        force_all: If True, mark all packages as dirty.

    Returns:
        Tuple of (packages to build, unchanged packages).
    """
    step("Detecting changes")

    # Get list of changed files since last release
    if not last_tag:
        # First release: everything is "changed"
        changed_files = set(git("ls-files").splitlines())
    else:
        changed_files = set(git("diff", "--name-only", last_tag, "HEAD").splitlines())

    if force_all:
        dirty = set(packages.keys())
        print("  Force rebuild: all packages marked dirty")
    else:
        dirty: set[str] = set()
        # Check each package for direct changes
        for name, info in packages.items():
            prefix = info.path.rstrip("/") + "/"
            if any(f.startswith(prefix) for f in changed_files):
                dirty.add(name)
                print(f"  {name}: changed")

        # Root config changes affect all packages
        if changed_files & {"pyproject.toml", "uv.lock"}:
            dirty = set(packages.keys())
            print("  Root config changed: all packages marked dirty")

    # Propagate dirtiness to dependents (if A is dirty, anything
    # depending on A must also be rebuilt)
    reverse_deps: dict[str, list[str]] = {n: [] for n in packages}
    for name, info in packages.items():
        for dep in info.deps:
            reverse_deps[dep].append(name)

    # Walk in topo order to propagate dirtiness correctly
    for node in topo_order:
        if node in dirty:
            for dependent in reverse_deps[node]:
                if dependent not in dirty:
                    print(f"  {dependent}: dirty (depends on {node})")
                    dirty.add(dependent)

    # Split into build list and unchanged list, preserving topo order
    changed = [n for n in topo_order if n in dirty]
    unchanged = [n for n in topo_order if n not in dirty]
    return changed, unchanged


def fetch_unchanged_wheels(unchanged: list[str], last_tag: str | None) -> None:
    """Download wheels for unchanged packages from the previous release.

    This avoids rebuilding packages that haven't changed - we just reuse
    the previously-built wheels from the GitHub release.
    """
    if not unchanged or not last_tag:
        return

    step("Fetching unchanged wheels from previous release")

    # Wheel filenames use underscores, not hyphens
    expected = {canonicalize_name(p).replace("-", "_") for p in unchanged}
    tmp_dir = Path("/tmp/prev-wheels")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # Download all wheels from the previous release
    run(
        "gh",
        "release",
        "download",
        last_tag,
        "--dir",
        str(tmp_dir),
        "--pattern",
        "*.whl",
        check=False,
    )

    # Copy only the wheels we need to dist/
    for whl in tmp_dir.glob("*.whl"):
        whl_pkg_name = whl.name.split("-")[0].lower()
        if whl_pkg_name in expected:
            print(f"  Reusing: {whl.name}")
            (Path("dist") / whl.name).write_bytes(whl.read_bytes())


def build_packages(packages: dict[str, PackageInfo], changed: list[str]) -> None:
    """Build wheels for the specified packages using uv build."""
    step(f"Building {len(changed)} packages")

    for pkg in changed:
        pkg_dir = packages[pkg].path
        print(f"\n  {pkg} ({pkg_dir})")
        result = run("uv", "build", pkg_dir, "--out-dir", "dist/", check=False)
        if result.returncode != 0:
            fatal(f"Failed to build {pkg}")


def create_tag() -> str:
    """Create and push a release tag with format vYYYY.MM.DD-<short-sha>."""
    step("Tagging release")
    short_sha = git("rev-parse", "--short", "HEAD")
    date = datetime.now(timezone.utc).strftime("%Y.%m.%d")
    tag = f"v{date}-{short_sha}"
    git("tag", tag)
    git("push", "origin", tag)
    print(f"  {tag}")
    return tag


def bump_versions(
    packages: dict[str, PackageInfo], changed: list[str]
) -> dict[str, VersionBump]:
    """Bump patch versions for built packages, preparing for next release.

    After releasing 1.2.3, bumps to 1.2.4 so the next release will have
    a higher version. Also updates internal dep pins to match new versions.
    """
    step("Bumping versions for next release")

    # Calculate new versions for all built packages
    bumped: dict[str, VersionBump] = {}
    for name in changed:
        old = packages[name].version
        bumped[name] = VersionBump(old=old, new=bump_patch(old))

    # Build a complete version map (bumped packages get new version,
    # unchanged packages keep current version)
    all_versions: dict[str, str] = {
        name: bumped[name].new if name in bumped else info.version
        for name, info in packages.items()
    }

    # Rewrite pyproject.toml for each built package
    for name in changed:
        pkg_path = Path(packages[name].path)
        # Get versions of internal deps for pinning
        internal_dep_versions = {dep: all_versions[dep] for dep in packages[name].deps}
        rewrite_pyproject(
            pkg_path / "pyproject.toml", bumped[name].new, internal_dep_versions
        )
        print(f"  {name}: {bumped[name].old} → {bumped[name].new}")

    return bumped


def commit_bumps(
    packages: dict[str, PackageInfo], bumped: dict[str, VersionBump]
) -> None:
    """Commit and push the version bump changes."""
    # Stage all modified pyproject.toml files
    for name in bumped:
        git("add", packages[name].path + "/pyproject.toml")

    # Check if there are actually changes to commit
    result = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True)
    if result.returncode == 0:
        print("  No changes to commit")
        return

    # Create commit with summary of version bumps
    summary = "\n".join(f"  {n}: {b.old} → {b.new}" for n, b in bumped.items())
    git("commit", "-m", "chore: prepare next release", "-m", summary)
    git("push")
    print("  Committed and pushed")


def publish_release(
    packages: dict[str, PackageInfo],
    changed: list[str],
    unchanged: list[str],
    tag: str,
) -> None:
    """Create a GitHub release with all wheels attached."""
    step("Creating GitHub release")

    wheels = sorted(str(p) for p in Path("dist").glob("*.whl"))
    if not wheels:
        fatal("No wheels found in dist/")

    # Build release notes
    lines: list[str] = []
    if changed:
        lines.append("**Released:**")
        for pkg in changed:
            lines.append(f"- {pkg} {packages[pkg].version}")
    if unchanged:
        lines.append("")
        lines.append("**Unchanged:** " + ", ".join(unchanged))

    print(f"  {tag} with {len(wheels)} wheels")
    run(
        "gh",
        "release",
        "create",
        tag,
        *wheels,
        "--title",
        f"Release {tag}",
        "--notes",
        "\n".join(lines),
    )


def run_release(*, force_all: bool = False) -> None:
    """Execute the full release pipeline.

    Args:
        force_all: If True, rebuild all packages regardless of changes.
    """
    Path("dist").mkdir(parents=True, exist_ok=True)

    # Phase 1: Discovery
    packages, topo_order = discover_packages()
    last_tag = find_last_tag()
    changed, unchanged = detect_changes(packages, topo_order, last_tag, force_all)

    if not changed:
        print("\nNothing changed since last release.")
        return

    # Phase 2: Build
    fetch_unchanged_wheels(unchanged, last_tag)
    build_packages(packages, changed)

    # Phase 3: Release
    tag = create_tag()
    bumped = bump_versions(packages, changed)
    commit_bumps(packages, bumped)
    publish_release(packages, changed, unchanged, tag)

    print(f"\n{'=' * 60}\nDone!\n{'=' * 60}")

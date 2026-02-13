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
import json
from collections.abc import Mapping
from pathlib import Path

from packaging.utils import canonicalize_name

from .deps import dep_canonical_name, rewrite_pyproject
from .graph import topo_sort
from .models import PackageInfo, VersionBump
from .shell import fatal, gh, git, run, step
from .toml import (
    get_all_dependency_strings,
    get_project_name,
    get_project_version,
    get_workspace_member_globs,
    load_pyproject,
)
from .versions import bump_patch


def discover_packages() -> dict[str, PackageInfo]:
    """Scan the workspace and discover all packages.

    Reads [tool.uv.workspace].members from root pyproject.toml to find
    package directories, then extracts name, version, and internal deps
    from each package's pyproject.toml.

    Returns:
        Map of package name to PackageInfo.
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

    # Print discovered packages for user feedback
    for name, info in packages.items():
        deps = f" → [{', '.join(info.deps)}]" if info.deps else ""
        print(f"  {name} {info.version} ({info.path}){deps}")

    return packages


def find_last_tags(packages: dict[str, PackageInfo]) -> dict[str, str | None]:
    """Find the most recent release tag for each package.

    Tags follow the pattern {package-name}/v{version}.

    Args:
        packages: Map of package name → PackageInfo.

    Returns:
        Map of package name to its last tag, or None if no tag exists.
    """
    step("Finding last release tags")

    last_tags: dict[str, str | None] = {}
    for name in packages:
        # Get tags matching this package's pattern, sorted by version
        tags = git("tag", "--list", f"{name}/v*", "--sort=-v:refname", check=False)
        tag = tags.splitlines()[0] if tags else None
        last_tags[name] = tag
        print(f"  {name}: {tag or '<none>'}")

    return last_tags


def detect_changes(
    packages: dict[str, PackageInfo],
    last_tags: Mapping[str, str | None],
    force_all: bool,
) -> list[str]:
    """Determine which packages need to be rebuilt.

    A package is "dirty" and needs rebuilding if:
    1. force_all is True (rebuild everything)
    2. No previous tag exists for the package (first release)
    3. Any file in the package directory changed since its last tag
    4. Root pyproject.toml or uv.lock changed since its last tag
    5. Any of its dependencies are dirty (transitive dirtiness)

    Args:
        packages: Map of package name → PackageInfo.
        last_tags: Map of package name → last release tag (or None).
        force_all: If True, mark all packages as dirty.

    Returns:
        List of changed package names.
    """
    step("Detecting changes")

    if force_all:
        dirty = set(packages.keys())
        print("  Force rebuild: all packages marked dirty")
    else:
        dirty: set[str] = set()
        # Check each package for direct changes since its own last tag
        for name, info in packages.items():
            last_tag = last_tags.get(name)
            if not last_tag:
                # First release for this package
                dirty.add(name)
                print(f"  {name}: new package")
                continue

            # Get files changed since this package's last tag
            changed_files = set(
                git("diff", "--name-only", last_tag, "HEAD").splitlines()
            )

            # Check if package directory changed
            prefix = info.path.rstrip("/") + "/"
            if any(f.startswith(prefix) for f in changed_files):
                dirty.add(name)
                print(f"  {name}: changed since {last_tag}")
            # Root config changes affect this package
            elif changed_files & {"pyproject.toml", "uv.lock"}:
                dirty.add(name)
                print(f"  {name}: root config changed since {last_tag}")

    # Build reverse dependency map
    reverse_deps: dict[str, list[str]] = {n: [] for n in packages}
    for name, info in packages.items():
        for dep in info.deps:
            reverse_deps[dep].append(name)

    # Propagate dirtiness to dependents using BFS
    queue = list(dirty)
    while queue:
        node = queue.pop(0)
        for dependent in reverse_deps[node]:
            if dependent not in dirty:
                print(f"  {dependent}: dirty (depends on {node})")
                dirty.add(dependent)
                queue.append(dependent)

    return list(dirty)


def get_existing_wheels() -> set[str]:
    """Fetch all wheel filenames from all GitHub releases.

    Queries GitHub releases to build a set of all wheel files that have
    already been published. Used to prevent duplicate version releases.

    Returns:
        Set of wheel filenames (e.g., {"pkg_a-1.0.0-py3-none-any.whl"}).
        Returns empty set if no releases exist or gh CLI fails.
    """
    output = gh("release", "list", "--json", "tagName", "--limit", "100", check=False)
    if not output:
        return set()

    try:
        releases = json.loads(output)
    except json.JSONDecodeError:
        return set()

    existing_wheels: set[str] = set()

    for release in releases:
        tag = release.get("tagName", "")
        if not tag:
            continue

        assets_output = gh("release", "view", tag, "--json", "assets", check=False)
        if assets_output:
            try:
                assets_data = json.loads(assets_output)
                for asset in assets_data.get("assets", []):
                    name = asset.get("name", "")
                    if name.endswith(".whl"):
                        existing_wheels.add(name)
            except json.JSONDecodeError:
                continue

    return existing_wheels


def check_for_existing_wheels(changed: dict[str, PackageInfo]) -> None:
    """Check if any package version already exists in GitHub releases.

    Prevents accidentally releasing the same version twice by comparing
    the versions of packages about to be built against wheels already
    published in GitHub releases.

    Args:
        changed: Map of changed package names to PackageInfo.

    Raises:
        SystemExit: If any version already exists in releases.
    """
    step("Checking for duplicate versions")

    existing_wheels = get_existing_wheels()
    if not existing_wheels:
        print("  No existing releases found")
        return

    duplicates: list[str] = []

    for pkg_name, info in changed.items():
        # Wheel names use underscores, not hyphens
        wheel_prefix = (
            f"{canonicalize_name(pkg_name).replace('-', '_')}-{info.version}-"
        )

        for wheel in existing_wheels:
            if wheel.startswith(wheel_prefix):
                duplicates.append(f"{pkg_name} {info.version} (found: {wheel})")
                break

    if duplicates:
        fatal(
            "The following package versions already exist in releases:\n"
            + "\n".join(f"  - {d}" for d in duplicates)
            + "\n\nBump the version in pyproject.toml before releasing."
        )

    print("  No duplicates found")


def fetch_unchanged_wheels(unchanged: dict[str, PackageInfo]) -> None:
    """Download wheels for unchanged packages from GitHub releases.

    This avoids rebuilding packages that haven't changed - we just reuse
    the previously-built wheels. Searches all releases to find matching wheels.
    """
    if not unchanged:
        return

    step("Fetching unchanged wheels from releases")

    # Build map of expected wheel prefix → package name
    # Wheel filenames use underscores, not hyphens
    expected: dict[str, str] = {}
    for name, info in unchanged.items():
        wheel_name = canonicalize_name(name).replace("-", "_")
        wheel_prefix = f"{wheel_name}-{info.version}-"
        expected[wheel_prefix] = name

    # Get list of releases
    output = gh("release", "list", "--json", "tagName", "--limit", "100", check=False)
    if not output:
        print("  No releases found")
        return

    try:
        releases = json.loads(output)
    except json.JSONDecodeError:
        print("  Failed to parse releases")
        return

    tmp_dir = Path("/tmp/prev-wheels")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    found: set[str] = set()

    # Search releases for matching wheels
    for release in releases:
        if len(found) == len(expected):
            break  # Found all wheels we need

        tag = release.get("tagName", "")
        if not tag:
            continue

        # Download wheels from this release
        run(
            "gh",
            "release",
            "download",
            tag,
            "--dir",
            str(tmp_dir),
            "--pattern",
            "*.whl",
            "--clobber",
            check=False,
        )

        # Check for matching wheels
        for whl in tmp_dir.glob("*.whl"):
            for prefix, pkg_name in expected.items():
                if whl.name.startswith(prefix) and pkg_name not in found:
                    print(f"  Reusing: {whl.name}")
                    (Path("dist") / whl.name).write_bytes(whl.read_bytes())
                    found.add(pkg_name)
                    break

    # Report any missing wheels
    missing = set(expected.values()) - found
    for name in missing:
        print(f"  Warning: no wheel found for {name}")


def build_packages(changed: dict[str, PackageInfo]) -> None:
    """Build wheels for the specified packages using uv build.

    Packages are built in topological order so dependencies are built
    before the packages that depend on them.
    """
    step(f"Building {len(changed)} packages")

    # Build in dependency order
    build_order = topo_sort(changed)
    for pkg in build_order:
        info = changed[pkg]
        print(f"\n  {pkg} ({info.path})")
        result = run("uv", "build", info.path, "--out-dir", "dist/", check=False)
        if result.returncode != 0:
            fatal(f"Failed to build {pkg}")


def find_next_release_tag() -> str:
    """Find the next release tag (r1, r2, r3, ...).

    Looks for existing tags matching the r<N> pattern and returns
    the next sequential number.

    Returns:
        The next release tag (e.g., "r1" if no releases exist, "r5" if r4 is latest).
    """
    tags = git("tag", "--list", "r*", "--sort=-v:refname", check=False)
    if not tags:
        return "r1"

    # Find the highest numbered release tag
    for tag in tags.splitlines():
        if tag.startswith("r") and tag[1:].isdigit():
            return f"r{int(tag[1:]) + 1}"

    return "r1"


def tag_changed_packages(changed: dict[str, PackageInfo]) -> None:
    """Create per-package git tags with format {package-name}/v{version}.

    Args:
        changed: Map of changed package names to PackageInfo.
    """
    step("Creating package tags")

    for name, info in changed.items():
        tag = f"{name}/v{info.version}"
        git("tag", tag)
        print(f"  {tag}")


def bump_versions(changed: dict[str, PackageInfo], unchanged: dict[str, PackageInfo]):
    """Bump patch versions for built packages, preparing for next release.

    After releasing 1.2.3, bumps to 1.2.4 so the next release will have
    a higher version. Also updates internal dep pins to match new versions.
    """
    step("Bumping versions for next release")

    # Calculate new versions for all built packages
    bumped: dict[str, VersionBump] = {}
    for name, info in changed.items():
        bumped[name] = VersionBump(old=info.version, new=bump_patch(info.version))

    # Build a complete version map (bumped packages get new version,
    # unchanged packages keep current version)
    all_versions: dict[str, str] = {name: bumped[name].new for name in changed} | {
        name: info.version for name, info in unchanged.items()
    }

    # Rewrite pyproject.toml for each built package
    for name, info in changed.items():
        pkg_path = Path(info.path)
        # Get versions of internal deps for pinning
        internal_dep_versions = {dep: all_versions[dep] for dep in info.deps}
        rewrite_pyproject(
            pkg_path / "pyproject.toml", bumped[name].new, internal_dep_versions
        )
        print(f"  {name}: {bumped[name].old} → {bumped[name].new}")

    return bumped


def commit_bumps(
    changed: dict[str, PackageInfo], bumped: dict[str, VersionBump]
) -> None:
    """Commit and push the version bump changes."""
    # Stage all modified pyproject.toml files
    for name in bumped:
        git("add", changed[name].path + "/pyproject.toml")

    # Check if there are actually changes to commit
    staged = git("diff", "--cached", "--name-only", check=False)
    if not staged:
        fatal("No changes to commit")

    # Create commit with summary of version bumps
    summary = "\n".join(f"  {n}: {b.old} → {b.new}" for n, b in bumped.items())
    git("commit", "-m", "chore: prepare next release", "-m", summary)
    print("  Committed")


def publish_release(
    changed: dict[str, PackageInfo],
    unchanged: dict[str, PackageInfo],
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
        for pkg, info in changed.items():
            lines.append(f"- {pkg} {info.version}")
    if unchanged:
        lines.append("")
        lines.append("**Unchanged:** " + ", ".join(unchanged.keys()))

    print(f"  {tag} with {len(wheels)} wheels")
    gh(
        "release",
        "create",
        tag,
        *wheels,
        "--title",
        f"Release {tag}",
        "--notes",
        "\n".join(lines),
    )


def run_release(*, release: str | None = None, force_all: bool = False) -> None:
    """Execute the full release pipeline.

    Args:
        release: Release tag (e.g., "r1", "r2"). If not provided, auto-generates
                 the next sequential release number.
        force_all: If True, rebuild all packages regardless of changes.
    """
    Path("dist").mkdir(parents=True, exist_ok=True)

    # Determine release tag
    if not release:
        release = find_next_release_tag()
        step(f"Auto-generated release tag: {release}")

    # Phase 1: Discovery
    packages = discover_packages()
    last_tags = find_last_tags(packages)
    changed_names = detect_changes(packages, last_tags, force_all)

    if not changed_names:
        fatal("Nothing changed since last release.")

    # Split packages into changed and unchanged dicts
    changed = {name: packages[name] for name in changed_names}
    unchanged = {name: info for name, info in packages.items() if name not in changed}

    # Check for duplicate versions before any build work
    check_for_existing_wheels(changed)

    # Phase 2: Build
    fetch_unchanged_wheels(unchanged)
    build_packages(changed)

    # Phase 3: Release
    tag_changed_packages(changed)
    bumped = bump_versions(changed, unchanged)
    commit_bumps(changed, bumped)
    publish_release(changed, unchanged, release)
    step("Pushing commits and tags.")
    git("push", "--tags")

    print(f"\n{'=' * 60}\nDone!\n{'=' * 60}")

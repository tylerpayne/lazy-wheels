"""Change detection: determine which packages need rebuilding."""

from __future__ import annotations

import json
from collections.abc import Mapping

from packaging.utils import canonicalize_name


from .models import PackageInfo
from .shell import fatal, gh, git, step


def detect_changes(
    packages: dict[str, PackageInfo],
    baselines: Mapping[str, str | None],
    rebuild_all: bool,
) -> list[str]:
    """Determine which packages need to be rebuilt.

    A package is "dirty" and needs rebuilding if:
    1. rebuild_all is True (rebuild everything)
    2. No previous baseline tag exists for the package (first release)
    3. Any file in the package directory changed since its baseline
    4. Root pyproject.toml changed since its baseline (workspace-level config
       such as dependency overrides or build settings can affect any package,
       so root changes conservatively trigger a rebuild for all packages)
    5. Any of its dependencies are dirty (transitive dirtiness)

    The baseline tag ({pkg}/v{version}-base) is placed on the version
    bump commit after each release, so only real work after the bump
    shows up in the diff.

    Args:
        packages: Map of package name -> PackageInfo.
        baselines: Map of package name -> baseline tag (or None).
        rebuild_all: If True, mark all packages as dirty.

    Returns:
        List of changed package names.
    """
    step("Detecting changes")

    if rebuild_all:
        dirty = set(packages.keys())
        print("  Force rebuild: all packages marked dirty")
    else:
        dirty: set[str] = set()
        # Check each package for direct changes since its baseline
        for name, info in packages.items():
            baseline = baselines.get(name)
            if not baseline:
                # First release for this package
                dirty.add(name)
                print(f"  {name}: new package")
                continue

            # Get files changed since this package's dev baseline
            changed_files = set(
                git("diff", "--name-only", baseline, "HEAD").splitlines()
            )

            # Filter to files in this package's directory
            prefix = info.path.rstrip("/") + "/"
            pkg_changed_files = {f for f in changed_files if f.startswith(prefix)}

            if pkg_changed_files:
                dirty.add(name)
                print(f"  {name}: changed since {baseline}")

            # Root config changes affect this package
            elif "pyproject.toml" in changed_files:
                dirty.add(name)
                print(f"  {name}: root config changed since {baseline}")

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


def get_existing_wheels(package_name: str | None = None) -> set[str]:
    """Fetch wheel filenames from GitHub releases.

    When *package_name* is provided, only the release tagged for that
    package is inspected (``{package_name}/v*``). Otherwise all releases
    are scanned (kept for backward compatibility but discouraged).

    Args:
        package_name: If given, scope the search to this package's releases.

    Returns:
        Set of wheel filenames (e.g., {"pkg_a-1.0.0-py3-none-any.whl"}).
        Returns empty set if no releases exist or gh CLI fails.
    """
    if package_name is not None:
        # Scope to this package's releases only
        output = gh(
            "release", "list", "--json", "tagName", "--limit", "100", check=False
        )
        if not output:
            return set()
        try:
            releases = json.loads(output)
        except json.JSONDecodeError:
            return set()
        # Filter to tags belonging to this package
        releases = [
            r for r in releases if r.get("tagName", "").startswith(f"{package_name}/v")
        ]
    else:
        output = gh(
            "release", "list", "--json", "tagName", "--limit", "100", check=False
        )
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

    # Check each package against its own releases rather than scanning all
    existing_wheels: set[str] = set()
    for pkg_name in changed:
        existing_wheels |= get_existing_wheels(package_name=pkg_name)
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

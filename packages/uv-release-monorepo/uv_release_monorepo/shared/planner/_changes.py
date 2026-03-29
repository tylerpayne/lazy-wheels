"""Change detection: determine which packages need rebuilding."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

import pygit2

from ..git.local import diff_files
from ..models import PackageInfo
from ..shell import print_step

from ._graph import _build_graph_maps

if TYPE_CHECKING:
    from ..context import RepositoryContext


def _check_package(
    repo: pygit2.Repository, name: str, info: PackageInfo, baseline: str
) -> tuple[str, str | None]:
    """Check a single package for changes since its baseline.

    Returns ``(name, reason)`` where *reason* is a human-readable string
    if the package is dirty, or ``None`` if it is clean.
    """
    changed_files = diff_files(repo, baseline)

    prefix = info.path.rstrip("/") + "/"
    if any(f.startswith(prefix) for f in changed_files):
        return name, f"changed since {baseline}"

    return name, None


def detect_changes(
    packages: dict[str, PackageInfo],
    baselines: Mapping[str, str | None],
    rebuild_all: bool,
    *,
    ctx: RepositoryContext | None = None,
    repo: pygit2.Repository | None = None,
) -> list[str]:
    """Determine which packages need to be rebuilt.

    A package is "dirty" and needs rebuilding if:
    1. rebuild_all is True (rebuild everything)
    2. No previous baseline tag exists for the package (first release)
    3. Any file in the package directory changed since its baseline
    4. Any of its dependencies are dirty (transitive dirtiness)

    The baseline tag ({pkg}/v{version}-base) is placed on the version
    bump commit after each release, so only real work after the bump
    shows up in the diff.

    Args:
        packages: Map of package name -> PackageInfo.
        baselines: Map of package name -> baseline tag (or None).
        rebuild_all: If True, mark all packages as dirty.
        ctx: RepositoryContext providing the repo. Preferred over *repo*.
        repo: Pre-opened pygit2 Repository. Opened automatically if None.

    Returns:
        List of changed package names.
    """
    print_step("Detecting changes")

    if ctx is not None:
        repo = ctx.repo
    elif repo is None:
        from ..git.local import open_repo

        repo = open_repo()

    if rebuild_all:
        dirty = set(packages.keys())
        print("  Force rebuild: all packages marked dirty")
    else:
        dirty: set[str] = set()

        # Packages without baselines are automatically dirty (first release)
        to_check: list[tuple[str, PackageInfo, str]] = []
        for name, info in packages.items():
            baseline = baselines.get(name)
            if not baseline:
                dirty.add(name)
                print(f"  {name}: new package")
            else:
                to_check.append((name, info, baseline))

        # Check remaining packages (pygit2 is not thread-safe, so run sequentially)
        for name, info, baseline in to_check:
            name, reason = _check_package(repo, name, info, baseline)
            if reason:
                dirty.add(name)
                print(f"  {name}: {reason}")

    # Build reverse dependency map
    _, reverse_deps = _build_graph_maps(packages)

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

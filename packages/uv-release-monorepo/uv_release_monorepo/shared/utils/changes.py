"""Change detection: determine which packages need rebuilding."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

import pygit2

from ..models import PackageInfo
from .git import _resolve_tag, path_changed
from .shell import print_step
from .versions import detect_release_type_for_version, is_dev

from ..planner._graph import build_graph_maps

if TYPE_CHECKING:
    from ..context import RepositoryContext


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

    Uses subtree comparison for O(depth) per package instead of full repo
    diffs. Caches baseline commit resolution to avoid redundant work when
    multiple packages share the same baseline tag.

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
        from .git import open_repo

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

        # Cache baseline commit lookups — multiple packages may share a baseline
        commit_cache: dict[str, pygit2.Commit | None] = {}
        head = repo.revparse_single("HEAD")

        for name, info, baseline in to_check:
            # If the version is clean (no .dev suffix) and its release
            # tag exists, use the release tag as the baseline instead.
            # This handles post-release branches where the dev baseline
            # tag is on a different branch.
            effective_baseline = baseline
            if not is_dev(info.version):
                release_tag = f"{name}/v{info.version}"
                if repo.references.get(f"refs/tags/{release_tag}") is not None:
                    effective_baseline = release_tag

            if effective_baseline not in commit_cache:
                commit_cache[effective_baseline] = _resolve_tag(
                    repo, effective_baseline
                )

            base_commit = commit_cache[effective_baseline]
            if base_commit is None:
                dirty.add(name)
                print(f"  {name}: baseline tag missing ({effective_baseline})")
                continue

            if path_changed(repo, base_commit, head, info.path):  # type: ignore[arg-type]
                dirty.add(name)
                print(f"  {name}: changed since {baseline}")

    # Build reverse dependency map
    _, reverse_deps = build_graph_maps(packages)

    # Propagate dirtiness to dependents using BFS.
    # Post-release packages don't propagate — a post-fix only affects the
    # package in question, not its dependents.
    queue = list(dirty)
    while queue:
        node = queue.pop(0)
        if detect_release_type_for_version(packages[node].version) == "post":
            continue
        for dependent in reverse_deps[node]:
            if dependent not in dirty:
                print(f"  {dependent}: dirty (depends on {node})")
                dirty.add(dependent)
                queue.append(dependent)

    return list(dirty)

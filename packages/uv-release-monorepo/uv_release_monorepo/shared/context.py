"""RepositoryContext: pre-fetched repository state for release planning."""

from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field

import pygit2

from .git.local import list_tags, open_repo
from .models import PackageInfo, PlanConfig
from .utils.packages import find_packages
from .utils.shell import Progress
from .utils.tags import find_baseline_tags


@dataclass
class RepositoryContext:
    """Pre-fetched local repository state.

    Contains only data from the local repo — no network calls.
    """

    repo: pygit2.Repository
    git_tags: set[str]
    packages: dict[str, PackageInfo]
    baselines: dict[str, str | None]


@dataclass
class ReleaseContext(RepositoryContext):
    """Repository state enriched with GitHub release data.

    Built by the planner after change detection — defers the network
    call until we know packages actually changed.
    """

    github_releases: set[str] = dataclass_field(default_factory=set)
    release_tags: dict[str, str | None] = dataclass_field(default_factory=dict)


def build_context(
    config: PlanConfig,
    *,
    progress: Progress | None = None,
) -> RepositoryContext:
    """Fetch local repository state — no network calls.

    Uses *config* to skip unnecessary work:
    - ``rebuild_all``: skip baseline lookup (all packages are dirty)
    - ``final``/``dev``: skip full tag scan (only pre/post need it)
    - Baselines use direct pygit2 ref lookup — no tag scan needed
    """
    if progress:
        progress.update("Opening repository")
    repo = open_repo()

    # Discover packages first — determines what else to scan
    if progress:
        progress.update("Discovering packages")
    packages = find_packages()
    if progress:
        progress.complete(f"Discovered {len(packages)} packages")

    if not packages:
        return RepositoryContext(
            repo=repo,
            git_tags=set(),
            packages=packages,
            baselines={},
        )

    # Baselines: direct ref lookup per package (O(1) each, no scan)
    # Skip entirely if rebuild_all (everything is dirty anyway)
    if config.rebuild_all:
        baselines: dict[str, str | None] = {name: None for name in packages}
        if progress:
            progress.complete("Skipped baselines (--rebuild-all)")
    else:
        if progress:
            progress.update("Finding baselines")
        baselines = find_baseline_tags(packages, repo=repo)
        baselined = sum(1 for b in baselines.values() if b)
        if progress:
            progress.complete(f"Found {baselined} baselines")

    # Scan git tags filtered to package prefixes — needed for:
    # - Release tag detection (all release types)
    # - Pre/post version numbering (pre/post only)
    if progress:
        progress.update("Scanning git tags")
    tag_prefixes = [f"{name}/v" for name in packages]
    git_tags = set(list_tags(repo, prefixes=tag_prefixes))
    if progress:
        progress.complete(f"Scanned {len(git_tags)} git tags")

    return RepositoryContext(
        repo=repo,
        git_tags=git_tags,
        packages=packages,
        baselines=baselines,
    )

"""RepositoryContext: pre-fetched repository state for release planning."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import pygit2

from .git.local import list_tags, open_repo
from .git.remote import list_release_tag_names
from .models import PackageInfo
from .utils.packages import find_packages
from .utils.shell import Progress
from .utils.tags import find_baseline_tags, find_release_tags


@dataclass
class RepositoryContext:
    """Pre-fetched repository state."""

    repo: pygit2.Repository
    git_tags: set[str]
    github_releases: set[str]
    packages: dict[str, PackageInfo]
    release_tags: dict[str, str | None]
    baselines: dict[str, str | None]


def build_context(*, progress: Progress | None = None) -> RepositoryContext:
    """Fetch all repository state in one pass.

    Optimizations:
    - Discovers packages first — skips GitHub API if no packages found
    - Fetches GitHub releases in parallel with baseline scanning
    - GitHub releases use ETag caching (304 on unchanged)
    """
    if progress:
        progress.update("Opening repository")
    repo = open_repo()
    all_git_tags = list_tags(repo)
    git_tags = set(all_git_tags)
    if progress:
        progress.complete(f"Scanned {len(git_tags)} git tags")

    # Discover packages first — skip GitHub API if none found
    if progress:
        progress.update("Discovering packages")
    packages = find_packages()
    if progress:
        progress.complete(f"Discovered {len(packages)} packages")

    if not packages:
        return RepositoryContext(
            repo=repo,
            git_tags=git_tags,
            github_releases=set(),
            packages=packages,
            release_tags={},
            baselines={},
        )

    # Fetch GitHub releases and find baselines in parallel
    # (network I/O overlaps with local git operations)
    if progress:
        progress.update("Fetching releases and baselines")

    with ThreadPoolExecutor(max_workers=2) as pool:
        releases_future = pool.submit(list_release_tag_names)
        baselines_future = pool.submit(find_baseline_tags, packages, all_tags=git_tags)
        github_releases = releases_future.result()
        baselines = baselines_future.result()

    baselined = sum(1 for b in baselines.values() if b)
    if progress:
        progress.complete(
            f"Fetched {len(github_releases)} releases, found {baselined} baselines"
        )

    # Find release tags (needs GitHub releases, so must be sequential)
    if progress:
        progress.update("Finding release tags")
    release_tags = find_release_tags(packages, gh_releases=github_releases)
    tagged = sum(1 for t in release_tags.values() if t)
    if progress:
        progress.complete(f"Found {tagged} release tags")

    return RepositoryContext(
        repo=repo,
        git_tags=git_tags,
        github_releases=github_releases,
        packages=packages,
        release_tags=release_tags,
        baselines=baselines,
    )

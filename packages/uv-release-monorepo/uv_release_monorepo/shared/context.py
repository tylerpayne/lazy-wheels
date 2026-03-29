"""RepositoryContext: pre-fetched repository state for release planning."""

from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field

import pygit2

from .utils.git import open_repo
from .models import PackageInfo
from .utils.packages import find_packages
from .utils.shell import Progress


@dataclass
class RepositoryContext:
    """Pre-fetched local repository state.

    Contains only data from the local repo — no network calls, no tag scans.
    Baselines and release tags are resolved by the planner per release type.
    """

    repo: pygit2.Repository
    packages: dict[str, PackageInfo]


@dataclass
class ReleaseContext(RepositoryContext):
    """Repository state with pre-computed baselines and release tags.

    Used by tests to inject baseline/release tag data directly.
    """

    baselines: dict[str, str | None] = dataclass_field(default_factory=dict)
    release_tags: dict[str, str | None] = dataclass_field(default_factory=dict)


def build_context(
    *,
    progress: Progress | None = None,
) -> RepositoryContext:
    """Fetch local repository state — no network calls, no tag scans.

    Discovers packages only. Baselines are resolved by the planner
    based on the release type.
    """
    if progress:
        progress.update("Discovering packages")
    repo = open_repo()
    packages = find_packages()
    if progress:
        progress.complete(f"Discovered {len(packages)} packages")

    return RepositoryContext(
        repo=repo,
        packages=packages,
    )

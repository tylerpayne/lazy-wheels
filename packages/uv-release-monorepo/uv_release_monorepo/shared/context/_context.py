"""RepositoryContext: pre-fetched repository state for release planning."""

from __future__ import annotations

import pygit2
from pydantic import BaseModel, ConfigDict

from ..git.local import list_tags, open_repo
from ..git.remote import list_release_tag_names
from ..models import PackageInfo
from ..utils.packages import find_packages
from ..utils.tags import find_baseline_tags, find_release_tags


class RepositoryContext(BaseModel):
    """Pre-fetched repository state."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    repo: pygit2.Repository
    git_tags: set[str]
    github_releases: set[str]
    packages: dict[str, PackageInfo]
    release_tags: dict[str, str | None]
    baselines: dict[str, str | None]


def build_context() -> RepositoryContext:
    """Fetch all repository state in one pass."""
    repo = open_repo()
    all_git_tags = list_tags(repo)
    git_tags = set(all_git_tags)
    github_releases = list_release_tag_names()

    packages = find_packages()
    release_tags = find_release_tags(packages, gh_releases=github_releases)
    baselines = find_baseline_tags(packages, all_tags=git_tags)

    return RepositoryContext(
        repo=repo,
        git_tags=git_tags,
        github_releases=github_releases,
        packages=packages,
        release_tags=release_tags,
        baselines=baselines,
    )

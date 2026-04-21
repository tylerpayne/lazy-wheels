"""GitHub API state: latest release tags."""

from __future__ import annotations

from pydantic import Field

from .base import State
from .worktree import Worktree


class LatestReleaseTags(State):
    """Latest release tags per package, fetched from GitHub."""

    tags: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def parse(cls, *, worktree: Worktree) -> LatestReleaseTags:
        """Fetch latest release tag for each package via gh CLI.

        One gh release list call, builds a full package to tag mapping.
        """
        if not worktree.repo:
            return LatestReleaseTags()

        releases = _fetch_releases(worktree.repo)
        if releases is None:
            return LatestReleaseTags()

        tags: dict[str, str] = {}
        for release in releases:
            tag_name = release.get("tagName", "")
            if not tag_name or "/" not in tag_name:
                continue
            package = tag_name.split("/v", 1)[0]
            if package not in tags:
                tags[package] = tag_name

        return LatestReleaseTags(tags=tags)


def _fetch_releases(gh_repo: str) -> list[dict[str, str]] | None:
    """Fetch release list from GitHub via gh CLI."""
    import json
    import subprocess

    result = subprocess.run(
        [
            "gh",
            "release",
            "list",
            "--repo",
            gh_repo,
            "--json",
            "tagName",
            "--limit",
            "50",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        return None

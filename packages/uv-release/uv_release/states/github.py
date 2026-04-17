"""Shared GitHub helpers for download and install intents."""

from __future__ import annotations

from ..types import Tag


def infer_gh_repo() -> str | None:
    """Infer GitHub repo from git remote origin URL."""
    try:
        import pygit2

        repo = pygit2.Repository(".")
        if "origin" not in repo.remotes.names():
            return None
        remote = repo.remotes["origin"]
        url = remote.url
        if url is None:
            return None
        # Handle SSH: git@github.com:owner/repo.git
        if url.startswith("git@"):
            path = url.split(":", 1)[1]
            return path.removesuffix(".git")
        # Handle HTTPS: https://github.com/owner/repo.git
        if "github.com" in url:
            parts = url.rstrip("/").removesuffix(".git").split("github.com/", 1)
            if len(parts) == 2:
                return parts[1]
        return None
    except Exception:
        return None


def find_latest_release_tag(package: str, gh_repo: str) -> str | None:
    """Find the latest release tag for a package via gh CLI."""
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
        releases = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        return None

    prefix = Tag.tag_prefix(package)
    tags = [r["tagName"] for r in releases if r["tagName"].startswith(prefix)]
    return tags[0] if tags else None

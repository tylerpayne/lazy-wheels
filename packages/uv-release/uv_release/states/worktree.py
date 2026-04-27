"""Parse git worktree state."""

from __future__ import annotations


from diny import provider

from ..utils.git import GitRepo
from .base import State


class Worktree(State):
    """Snapshot of the git worktree: cleanliness and remote identity."""

    is_dirty: bool = False
    is_ahead_or_behind: bool = False
    repo: str = ""


@provider(Worktree)
def parse_worktree(git_repo: GitRepo) -> Worktree:
    """Read worktree state from git."""
    return Worktree(
        is_dirty=git_repo.is_dirty(),
        is_ahead_or_behind=git_repo.is_ahead_or_behind(),
        repo=_parse_gh_repo(git_repo.remote_url()) or "",
    )


def _parse_gh_repo(url: str | None) -> str | None:
    """Extract owner/repo from a GitHub remote URL."""
    if url is None:
        return None
    if url.startswith("git@"):
        path = url.split(":", 1)[1]
        return path.removesuffix(".git")
    if "github.com" in url:
        parts = url.rstrip("/").removesuffix(".git").split("github.com/", 1)
        if len(parts) == 2:
            return parts[1]
    return None

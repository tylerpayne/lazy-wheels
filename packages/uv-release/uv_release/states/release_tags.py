"""Resolve verified release tags for unchanged packages."""

from __future__ import annotations

from pydantic import Field

from ..git import GitRepo
from ..types import Tag
from .base import State
from .workspace import Workspace


class ReleaseTags(State):
    """Verified release tags for unchanged packages, resolved from git."""

    tags: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def parse(cls, *, workspace: Workspace, git_repo: GitRepo) -> ReleaseTags:
        """Find release tags that exist in git for non-dev packages."""
        tags: dict[str, str] = {}
        for name, pkg in workspace.packages.items():
            if pkg.version.is_dev:
                continue
            tag_name = Tag.release_tag_name(name, pkg.version)
            if git_repo.find_tag(tag_name) is not None:
                tags[name] = tag_name
        return ReleaseTags(tags=tags)

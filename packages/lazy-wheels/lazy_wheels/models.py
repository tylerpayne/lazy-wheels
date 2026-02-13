"""Data models for lazy-wheels.

These Pydantic models represent the core data structures used throughout
the release pipeline.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PackageInfo(BaseModel):
    """Metadata for a single package in the monorepo workspace.

    Attributes:
        path: Relative path from workspace root to the package directory.
        version: Current version string from pyproject.toml.
        deps: List of internal (workspace) dependency names. External deps
              are not tracked here since we only need to manage internal
              version pinning.
    """

    path: str
    version: str
    deps: list[str] = Field(default_factory=list)


class VersionBump(BaseModel):
    """Records a version change for a package.

    Used to track what versions were bumped during a release so we can
    generate commit messages and update dependent packages.

    Attributes:
        old: The version before bumping.
        new: The version after bumping.
    """

    old: str
    new: str

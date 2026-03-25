"""Data models for uv-release-monorepo.

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


class PublishedPackage(BaseModel):
    """Captures the published state of a package in a release cycle.

    Records which version of the package is now on PyPI (just built or
    fetched from a prior release). Used by bump_versions() to write
    correct '>=' dependency constraints into dependent packages.

    Attributes:
        info: Original package metadata.
        published_version: The version now available on PyPI for this cycle.
            For changed packages: the version that was just built and published.
            For unchanged packages: the version fetched from the last release tag.
        changed: True if the package was newly built; False if reused.
    """

    info: PackageInfo
    published_version: str
    changed: bool


class BumpPlan(BaseModel):
    """Pre-computed version bump for a single package.

    Computed locally during planning so CI only needs to apply the patch
    bump — dep pin updates are applied locally before the release is triggered.

    Attributes:
        new_version: The patch-bumped version to write into pyproject.toml.
    """

    new_version: str


class MatrixEntry(BaseModel):
    """A single (package, runner) pair in the build matrix."""

    package: str
    runner: str
    path: str = ""
    version: str = ""


class PublishEntry(BaseModel):
    """A single entry in the publish matrix — one GitHub release per package."""

    package: str
    version: str
    tag: str
    title: str
    body: str
    make_latest: bool = False
    dist_name: str = ""


class ReleasePlan(BaseModel):
    """Self-contained release plan generated locally and executed by CI.

    Contains everything the executor workflow needs: which packages changed,
    what their last release tags were, which runners to use for each build,
    and the pre-computed version bumps. The executor never needs to run git
    commands, change detection, or version arithmetic.
    """

    schema_version: int = 4
    uvr_version: str
    python_version: str = "3.12"
    rebuild_all: bool
    changed: dict[str, PackageInfo]
    unchanged: dict[str, PackageInfo]
    release_tags: dict[str, str | None]
    matrix: list[MatrixEntry]
    runners: list[str] = Field(default_factory=list)
    bumps: dict[str, BumpPlan] = Field(default_factory=dict)
    publish_matrix: list[PublishEntry] = Field(default_factory=list)
    ci_publish: bool = False

"""Tagging: create release and baseline tags."""

from __future__ import annotations


from .models import PackageInfo, VersionBump
from .shell import git, step


def tag_changed_packages(changed: dict[str, PackageInfo]) -> None:
    """Create per-package git tags with format {package-name}/v{version}.

    Args:
        changed: Map of changed package names to PackageInfo.
    """
    step("Creating package tags")

    for name, info in changed.items():
        tag = f"{name}/v{info.version}"
        git("tag", tag)
        print(f"  {tag}")


def tag_baselines(bumped: dict[str, VersionBump]) -> None:
    """Create baseline tags for each bumped package.

    These tags mark the version bump commit as the diff baseline for the
    next release. Format: {package-name}/v{new_version}-base.

    Args:
        bumped: Map of package names to VersionBump (old -> new versions).
    """
    step("Creating baseline tags")

    for name, bump in bumped.items():
        tag = f"{name}/v{bump.new}-base"
        git("tag", tag)
        print(f"  {tag}")

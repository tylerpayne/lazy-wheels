"""Release tag discovery: find the most recent GitHub release for each package."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import semver

from ..models import PackageInfo
from ..shell import print_step


def _parse_version(version_str: str) -> semver.Version:
    """Parse a version string into a semver.Version object.

    Strips all dev/pre/post suffixes first, then handles incomplete versions
    by padding with zeros.
    """
    import semver as _semver

    from ..planner._versions import get_base_version

    cleaned = get_base_version(version_str)
    parts = cleaned.split(".")
    while len(parts) < 3:
        parts.append("0")
    return _semver.Version.parse(".".join(parts[:3]))


def find_release_tags(
    packages: dict[str, PackageInfo],
    gh_releases: set[str],
) -> dict[str, str | None]:
    """Find the most recent GitHub release tag for each package.

    Queries actual GitHub releases (not git tags) to find the most recent
    release whose version is less than the package's current base version.
    This ensures baseline tags and unreleased tags are never matched.

    Args:
        packages: Map of package name -> PackageInfo.
        gh_releases: Set of GitHub release tag names.

    Returns:
        Map of package name to its last release tag, or None if no release exists.
    """
    print_step("Finding last release tags")

    release_tag_names = gh_releases
    release_tags: dict[str, str | None] = {}
    for name, info in packages.items():
        current_base = _parse_version(info.version)
        # Filter to this package's releases, sorted by version descending
        pkg_releases = []
        prefix = f"{name}/v"
        for tag in release_tag_names:
            if not tag.startswith(prefix):
                continue
            tag_ver_str = tag[len(prefix) :]
            try:
                tag_ver = _parse_version(tag_ver_str)
            except (ValueError, TypeError):
                continue
            if tag_ver < current_base:
                pkg_releases.append((tag_ver, tag))
        # Pick the highest version
        pkg_releases.sort(reverse=True)
        release_tags[name] = pkg_releases[0][1] if pkg_releases else None
        print(f"  {name}: {release_tags[name] or '<none>'}")

    return release_tags

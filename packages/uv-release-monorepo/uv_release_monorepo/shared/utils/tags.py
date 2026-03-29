"""Tag discovery: find baseline and release tags for packages."""

from __future__ import annotations

import pygit2

from ..models import PackageInfo
from .shell import print_step

from .versions import parse_version


def find_baseline_tags(
    packages: dict[str, PackageInfo],
    *,
    repo: pygit2.Repository | None = None,
    all_tags: set[str] | None = None,
) -> dict[str, str | None]:
    """Derive baseline tags from each package's pyproject.toml version.

    The baseline tag is ``{name}/v{version}-base`` where *version* comes from
    pyproject.toml. Uses direct ref lookup via pygit2 if *repo* is provided
    (O(1) per package), otherwise falls back to *all_tags* set membership.
    """
    print_step("Finding baselines")

    baselines: dict[str, str | None] = {}
    for name, info in packages.items():
        base_tag = f"{name}/v{info.version}-base"
        if repo is not None:
            exists = repo.references.get(f"refs/tags/{base_tag}") is not None
        elif all_tags is not None:
            exists = base_tag in all_tags
        else:
            exists = False
        baselines[name] = base_tag if exists else None
        print(f"  {name}: {baselines[name] or '<none>'}")

    return baselines


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
        current_base = parse_version(info.version)
        # Filter to this package's releases, sorted by version descending
        pkg_releases = []
        prefix = f"{name}/v"
        for tag in release_tag_names:
            if not tag.startswith(prefix):
                continue
            tag_ver_str = tag[len(prefix) :]
            try:
                tag_ver = parse_version(tag_ver_str)
            except (ValueError, TypeError):
                continue
            if tag_ver < current_base:
                pkg_releases.append((tag_ver, tag))
        # Pick the highest version
        pkg_releases.sort(reverse=True)
        release_tags[name] = pkg_releases[0][1] if pkg_releases else None
        print(f"  {name}: {release_tags[name] or '<none>'}")

    return release_tags

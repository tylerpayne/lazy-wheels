"""Find baseline tags for change detection."""

from __future__ import annotations

from packaging.version import InvalidVersion
from packaging.version import Version as PkgVersion

from ..git import GitRepo
from ..types import Tag, Version, VersionState


def find_baseline_tag(
    name: str,
    version: Version,
    repo: GitRepo,
) -> Tag | None:
    """Find the baseline TAG to diff against for a package.

    Returns None if no baseline exists (first release).
    """
    state = version.state

    if state in (
        VersionState.DEV0_STABLE,
        VersionState.DEV0_PRE,
        VersionState.DEV0_POST,
    ):
        tag_name = Tag.baseline_tag_name(name, version)
        return _lookup_tag(
            name, tag_name, is_baseline=True, repo=repo
        ) or _find_previous_release(name, version, repo)

    if state in (
        VersionState.DEVK_STABLE,
        VersionState.DEVK_PRE,
        VersionState.DEVK_POST,
    ):
        dev0 = version.with_dev(0)
        tag_name = Tag.baseline_tag_name(name, dev0)
        return _lookup_tag(
            name, tag_name, is_baseline=True, repo=repo
        ) or _find_previous_release(name, version, repo)

    if state in (
        VersionState.CLEAN_STABLE,
        VersionState.CLEAN_PREN,
        VersionState.CLEAN_PRE0,
    ):
        return _find_previous_release(name, version, repo)

    if state in (VersionState.CLEAN_POST0, VersionState.CLEAN_POSTM):
        base_version = Version.build(version.base)
        tag_name = Tag.release_tag_name(name, base_version)
        return _lookup_tag(name, tag_name, is_baseline=False, repo=repo)

    return None


def _find_previous_release(name: str, version: Version, repo: GitRepo) -> Tag | None:
    """Find the highest release tag below the current version."""
    target = PkgVersion(version.base if version.is_dev else version.raw)

    candidates: list[tuple[PkgVersion, str]] = []
    prefix = Tag.tag_prefix(name)
    for tag_name in repo.list_tags(prefix):
        ver_str = tag_name[len(prefix) :]
        if Tag.is_baseline_tag_name(tag_name):
            continue
        try:
            pv = PkgVersion(ver_str)
        except InvalidVersion:
            continue
        if pv < target:
            candidates.append((pv, ver_str))

    if not candidates:
        return None

    candidates.sort(reverse=True)
    best_ver_str = candidates[0][1]
    tag_name = Tag.release_tag_name(name, Version.parse(best_ver_str))
    return _lookup_tag(name, tag_name, is_baseline=False, repo=repo)


def _lookup_tag(
    package_name: str, tag_name: str, *, is_baseline: bool, repo: GitRepo
) -> Tag | None:
    """Resolve a tag name to a Tag object with commit SHA."""
    commit = repo.find_tag(tag_name)
    if commit is None:
        return None

    ver_str = Tag.parse_version_from_tag_name(tag_name)

    return Tag(
        package_name=package_name,
        raw=tag_name,
        version=Version.parse(ver_str),
        is_baseline=is_baseline,
        commit=commit,
    )

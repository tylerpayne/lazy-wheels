"""Detect which packages changed since their baselines."""

from __future__ import annotations

from collections import defaultdict

from packaging.version import InvalidVersion
from packaging.version import Version as PkgVersion

from diny import provider

from ..utils.git import GitRepo
from ..types import (
    Change,
    Package,
    PlanParams,
    Tag,
    Version,
    VersionState,
)
from .base import State
from .workspace import Workspace


class Changes(State):
    """All detected changes in the workspace. Produced by parse."""

    items: tuple[Change, ...] = ()


@provider(Changes)
def parse_changes(
    workspace: Workspace, params: PlanParams, git_repo: GitRepo
) -> Changes:
    """Detect which packages changed since their baselines."""
    head = git_repo.head_commit()
    packages = workspace.packages

    dirty: set[str] = set()
    baselines: dict[str, Tag] = {}
    reasons: dict[str, str] = {}

    if params.all_packages:
        dirty = set(packages.keys())
        reasons = {n: "all packages" for n in dirty}
    elif params.packages:
        dirty = set(params.packages & set(packages.keys()))
        reasons = {n: "selected" for n in dirty}
    else:
        for name, pkg in packages.items():
            baseline = _find_baseline_tag(name, pkg.version, git_repo)
            if baseline is None:
                dirty.add(name)
                reasons[name] = "initial release"
                continue
            baselines[name] = baseline
            if git_repo.path_changed(baseline.commit, head, pkg.path):
                dirty.add(name)
                reasons[name] = "files changed"

    before_propagation = set(dirty)
    dirty = _propagate_dirtiness(dirty, packages)
    for name in dirty - before_propagation:
        reasons[name] = "dependency changed"

    if params.packages:
        allowed: set[str] = set()
        for name in params.packages:
            allowed |= _collect_transitive_deps(name, packages)
        dirty &= allowed

    changes: list[Change] = []
    for name in sorted(dirty):
        pkg = packages[name]
        baseline = baselines.get(name)
        if baseline is None:
            commit_log = "initial release"
            diff_stats = None
        else:
            commit_log = git_repo.commit_log(baseline.commit, head, pkg.path)
            diff_stats = git_repo.diff_stats(baseline.commit, head, pkg.path)
        changes.append(
            Change(
                package=pkg,
                baseline=baseline,
                diff_stats=diff_stats,
                commit_log=commit_log,
                reason=reasons.get(name, ""),
            )
        )

    return Changes(items=tuple(changes))


# ---------------------------------------------------------------------------
# Baseline tag resolution (private)
# ---------------------------------------------------------------------------


def _find_baseline_tag(
    name: str,
    version: Version,
    repo: GitRepo,
) -> Tag | None:
    """Find the baseline tag to diff against for a package."""
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


# ---------------------------------------------------------------------------
# Dependency propagation (private)
# ---------------------------------------------------------------------------

_POST_RELEASE_STATES = frozenset(
    {
        VersionState.CLEAN_POST0,
        VersionState.CLEAN_POSTM,
        VersionState.DEV0_POST,
        VersionState.DEVK_POST,
    }
)


def _propagate_dirtiness(
    dirty: set[str],
    packages: dict[str, Package],
) -> set[str]:
    """BFS: if B depends on A and A is dirty, B becomes dirty."""
    if not dirty or not packages:
        return set(dirty)

    reverse_deps: dict[str, list[str]] = defaultdict(list)
    for name, pkg in packages.items():
        for dep in pkg.dependencies:
            if dep in packages:
                reverse_deps[dep].append(name)

    result = set(dirty)
    queue = list(dirty)

    while queue:
        current = queue.pop(0)
        pkg = packages.get(current)
        if pkg is None:
            continue
        if pkg.version.state in _POST_RELEASE_STATES:
            continue
        for dependent in reverse_deps.get(current, []):
            if dependent not in result:
                result.add(dependent)
                queue.append(dependent)

    return result


def _collect_transitive_deps(name: str, packages: dict[str, Package]) -> set[str]:
    """Collect all transitive dependencies of a package (including itself)."""
    result: set[str] = {name}
    queue = [name]
    while queue:
        current = queue.pop(0)
        pkg = packages.get(current)
        if pkg is None:
            continue
        for dep in pkg.dependencies:
            if dep in packages and dep not in result:
                result.add(dep)
                queue.append(dep)
    return result

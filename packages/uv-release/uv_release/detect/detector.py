"""Detect which packages changed since their baselines."""

from __future__ import annotations

from ..git import GitRepo
from ..types import (
    Change,
    Package,
    PlanParams,
    Tag,
    Workspace,
)
from .baselines import find_baseline_tag
from .propagation import propagate_dirtiness


def detect_changes(
    workspace: Workspace,
    params: PlanParams,
) -> list[Change]:
    """Detect which packages changed since their baselines."""
    repo = GitRepo()
    head = repo.head_commit()
    packages = workspace.packages

    # Step 1: Detect direct changes per package
    dirty: set[str] = set()
    baselines: dict[str, Tag] = {}
    reasons: dict[str, str] = {}

    for name, pkg in packages.items():
        baseline = find_baseline_tag(name, pkg.version, repo)

        if baseline is None:
            dirty.add(name)
            reasons[name] = "initial release"
            continue

        baselines[name] = baseline

        if repo.path_changed(baseline.commit, head, pkg.path):
            dirty.add(name)
            reasons[name] = "files changed"

    # Step 2: Apply rebuild_all and rebuild overrides
    if params.rebuild_all:
        for name in packages:
            if name not in dirty:
                reasons[name] = "rebuild all"
        dirty = set(packages.keys())
    else:
        for name in params.rebuild & set(packages.keys()):
            if name not in dirty:
                reasons[name] = "forced rebuild"
        dirty |= params.rebuild & set(packages.keys())

    # Step 3: Propagate dirtiness through dependency graph
    before_propagation = set(dirty)
    dirty = propagate_dirtiness(dirty, packages)
    for name in dirty - before_propagation:
        reasons[name] = "dependency changed"

    # Step 4: Apply restrict_packages filter
    if params.restrict_packages:
        allowed: set[str] = set()
        for name in params.restrict_packages:
            allowed |= _collect_transitive_deps(name, packages)
        dirty &= allowed

    # Step 5: Build Change objects
    changes: list[Change] = []
    for name in sorted(dirty):
        pkg = packages[name]
        baseline = baselines.get(name)

        if baseline is None:
            commit_log = "initial release"
            diff_stats = None
        else:
            commit_log = repo.commit_log(baseline.commit, head, pkg.path)
            diff_stats = repo.diff_stats(baseline.commit, head, pkg.path)

        changes.append(
            Change(
                package=pkg,
                baseline=baseline,
                diff_stats=diff_stats,
                commit_log=commit_log,
                reason=reasons.get(name, ""),
            )
        )

    return changes


def _collect_transitive_deps(name: str, packages: dict[str, Package]) -> set[str]:
    """Collect all transitive dependencies of a package (including itself)."""
    result: set[str] = {name}
    queue = [name]
    while queue:
        current = queue.pop(0)
        pkg = packages.get(current)
        if pkg is None:
            continue
        for dep in pkg.deps:
            if dep in packages and dep not in result:
                result.add(dep)
                queue.append(dep)
    return result

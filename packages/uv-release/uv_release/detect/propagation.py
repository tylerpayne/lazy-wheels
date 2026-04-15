"""BFS propagation of dirtiness through the dependency graph."""

from __future__ import annotations

from collections import defaultdict

from ..types import Package, VersionState


# Post-release states do not propagate dirtiness to dependents
_POST_RELEASE_STATES = frozenset(
    {
        VersionState.CLEAN_POST0,
        VersionState.CLEAN_POSTM,
        VersionState.DEV0_POST,
        VersionState.DEVK_POST,
    }
)


def propagate_dirtiness(
    dirty: set[str],
    packages: dict[str, Package],
) -> set[str]:
    """BFS propagation: if B depends on A and A is dirty, B becomes dirty.

    Post-release packages do not propagate dirtiness to their dependents.
    Returns a new set containing all dirty package names (original + propagated).
    """
    if not dirty or not packages:
        return set(dirty)

    # Build reverse dependency map: dependency -> list of dependents
    reverse_deps: dict[str, list[str]] = defaultdict(list)
    for name, pkg in packages.items():
        for dep in pkg.deps:
            if dep in packages:
                reverse_deps[dep].append(name)

    result = set(dirty)
    queue = list(dirty)

    while queue:
        current = queue.pop(0)
        pkg = packages.get(current)
        if pkg is None:
            continue

        # Post-release packages are dirty themselves but do not propagate
        if pkg.version.state in _POST_RELEASE_STATES:
            continue

        for dependent in reverse_deps.get(current, []):
            if dependent not in result:
                result.add(dependent)
                queue.append(dependent)

    return result

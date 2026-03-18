"""Dependency graph utilities.

Provides topological sorting for determining build order in a monorepo.
Packages must be built in dependency order so that when package A depends
on package B, B is built first.
"""

from __future__ import annotations

from .models import PackageInfo


def topo_sort(packages: dict[str, PackageInfo]) -> list[str]:
    """Topologically sort packages by their internal dependencies.

    Uses Kahn's algorithm to produce a build order where dependencies
    come before dependents. Packages with no dependencies are sorted
    alphabetically for deterministic output.

    Args:
        packages: Map of package name → PackageInfo with deps list.

    Returns:
        List of package names in build order (dependencies first).

    Raises:
        RuntimeError: If a dependency cycle is detected.

    Example:
        If A depends on B, and B depends on C:
        topo_sort({A, B, C}) → [C, B, A]
    """
    # Count incoming edges (dependencies) for each package
    in_degree = {n: 0 for n in packages}
    # Track reverse dependencies (who depends on each package)
    reverse_deps: dict[str, list[str]] = {n: [] for n in packages}

    for name, info in packages.items():
        for dep in info.deps:
            # Only count dependencies that are within the packages we're sorting
            # (external deps or unchanged packages are already built)
            if dep in packages:
                in_degree[name] += 1
                reverse_deps[dep].append(name)

    # Start with packages that have no dependencies (in_degree == 0)
    # Sort alphabetically for deterministic ordering
    queue = sorted(n for n, d in in_degree.items() if d == 0)
    order: list[str] = []

    while queue:
        node = queue.pop(0)
        order.append(node)
        # Decrement in_degree for all packages that depend on this one
        for dependent in sorted(reverse_deps[node]):
            in_degree[dependent] -= 1
            # When a package has all deps satisfied, add to queue
            if in_degree[dependent] == 0:
                queue.append(dependent)

    # If we didn't process all packages, there must be a cycle
    if len(order) != len(packages):
        remaining = set(packages) - set(order)
        raise RuntimeError(f"Dependency cycle detected involving: {remaining}")

    return order

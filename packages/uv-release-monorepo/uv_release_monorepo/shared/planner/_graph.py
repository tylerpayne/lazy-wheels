"""Dependency graph utilities.

Provides topological sorting for determining build order in a monorepo.
Packages must be built in dependency order so that when package A depends
on package B, B is built first.
"""

from __future__ import annotations

from ..models import PackageInfo


def build_graph_maps(
    packages: dict[str, PackageInfo],
) -> tuple[dict[str, int], dict[str, list[str]]]:
    """Build in-degree and reverse-dependency maps for Kahn's algorithm."""
    in_degree = {n: 0 for n in packages}
    reverse_deps: dict[str, list[str]] = {n: [] for n in packages}
    for name, info in packages.items():
        for dep in info.deps:
            if dep in packages:
                in_degree[name] += 1
                reverse_deps[dep].append(name)
    return in_degree, reverse_deps


def topo_layers(packages: dict[str, PackageInfo]) -> dict[str, int]:
    """Assign each package a build layer based on dependency depth.

    Layer 0 = packages with no internal deps among input packages.
    Layer N = packages whose deepest internal dependency is in layer N-1.

    Uses modified Kahn's algorithm: instead of a flat order, each node
    gets a layer number equal to the max layer of its dependencies + 1.

    Args:
        packages: Map of package name -> PackageInfo with deps list.

    Returns:
        Dict mapping package name -> layer number.

    Raises:
        RuntimeError: If a dependency cycle is detected.
    """
    in_degree, reverse_deps = build_graph_maps(packages)
    layers: dict[str, int] = {}
    queue = sorted(n for n, d in in_degree.items() if d == 0)
    for n in queue:
        layers[n] = 0

    while queue:
        node = queue.pop(0)
        for dependent in sorted(reverse_deps[node]):
            in_degree[dependent] -= 1
            layers[dependent] = max(layers.get(dependent, 0), layers[node] + 1)
            if in_degree[dependent] == 0:
                queue.append(dependent)

    if len(layers) != len(packages):
        remaining = set(packages) - set(layers)
        raise RuntimeError(f"Dependency cycle detected involving: {remaining}")

    return layers

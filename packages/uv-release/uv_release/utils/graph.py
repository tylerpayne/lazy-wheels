"""Topological sorting for DAGs (package deps, job ordering)."""

from __future__ import annotations

from collections import defaultdict

from ..types import Package


def topo_sort(nodes: dict[str, list[str]]) -> list[str]:
    """Topological sort of a DAG. Returns nodes in dependency order.

    Args:
        nodes: mapping of node name to its dependencies (names it depends ON).

    Returns:
        List of node names in topological order (dependencies first).

    Raises RuntimeError on cycles.
    """
    if not nodes:
        return []

    in_degree: dict[str, int] = {name: 0 for name in nodes}
    dependents: dict[str, list[str]] = defaultdict(list)

    for name, deps in nodes.items():
        for dep in deps:
            if dep in nodes:
                in_degree[name] += 1
                dependents[dep].append(name)

    queue = sorted(name for name, deg in in_degree.items() if deg == 0)
    order: list[str] = []

    while queue:
        node = queue.pop(0)
        order.append(node)
        for dep in sorted(dependents[node]):
            in_degree[dep] -= 1
            if in_degree[dep] == 0:
                queue.append(dep)

    if len(order) != len(nodes):
        msg = f"Dependency cycle detected: processed {len(order)} of {len(nodes)} nodes"
        raise RuntimeError(msg)

    return order


def topo_layers(packages: dict[str, Package]) -> dict[str, int]:
    """Assign each package a build layer based on dependency depth.

    Layer 0 = packages with no internal deps.
    Layer N = packages whose deepest dependency is in layer N-1.

    Raises RuntimeError on dependency cycles.
    """
    if not packages:
        return {}

    in_degree: dict[str, int] = {name: 0 for name in packages}
    reverse_deps: dict[str, list[str]] = defaultdict(list)

    for name, pkg in packages.items():
        for dep in pkg.dependencies:
            if dep in packages:
                in_degree[name] += 1
                reverse_deps[dep].append(name)

    queue: list[str] = [name for name, deg in in_degree.items() if deg == 0]
    layers: dict[str, int] = {name: 0 for name in queue}

    processed = 0
    while queue:
        node = queue.pop(0)
        processed += 1
        for dependent in reverse_deps[node]:
            in_degree[dependent] -= 1
            layers[dependent] = max(layers.get(dependent, 0), layers[node] + 1)
            if in_degree[dependent] == 0:
                queue.append(dependent)

    if processed != len(packages):
        msg = f"Dependency cycle detected: processed {processed} of {len(packages)} packages"
        raise RuntimeError(msg)

    return layers

"""BuildPackages: packages selected for building."""

from __future__ import annotations

from diny import singleton, provider

from ...types.base import Frozen
from ..shared.changed_packages import ChangedPackages
from ...types.package import Package
from ..params.package_selection import PackageSelection
from ..config.uvr_config import UvrConfig
from ..shared.workspace_packages import WorkspacePackages


@singleton
class BuildPackages(Frozen):
    """Packages to build in this run (the release targets)."""

    items: dict[str, Package]


@provider(BuildPackages)
def provide_build_packages(
    workspace_packages: WorkspacePackages,
    changed_packages: ChangedPackages,
    package_selection: PackageSelection,
    uvr_config: UvrConfig,
) -> BuildPackages:
    # Selection: --all > --packages > auto-detect from changes.
    if package_selection.all_packages:
        items = dict(workspace_packages.items)
    elif package_selection.packages:
        items = {
            n: workspace_packages.items[n]
            for n in package_selection.packages
            if n in workspace_packages.items
        }
    else:
        items = {
            name: workspace_packages.items[name]
            for name in changed_packages.names
            if name in workspace_packages.items
        }

    # --and-build-system-requirements / --and-dependencies: pull workspace
    # packages reachable through the selected axes into the target set so
    # they're built from source into dist/ rather than downloaded as released
    # wheels. Walk transitively along whichever axes are enabled. Done before
    # exclusion so explicit excludes still take precedence.
    if (
        package_selection.and_build_system_requirements
        or package_selection.and_dependencies
    ):
        queue = list(items.keys())
        while queue:
            name = queue.pop(0)
            pkg = workspace_packages.items.get(name)
            if pkg is None:
                continue
            edges: list[str] = []
            if package_selection.and_build_system_requirements:
                edges += pkg.build_dep_names
            if package_selection.and_dependencies:
                edges += pkg.dep_names
            for dep_name in edges:
                if dep_name in items or dep_name not in workspace_packages.items:
                    continue
                items[dep_name] = workspace_packages.items[dep_name]
                queue.append(dep_name)

    # Apply CLI exclusions, then config include/exclude filters.
    if package_selection.exclude_packages:
        items = {
            n: p
            for n, p in items.items()
            if n not in package_selection.exclude_packages
        }
    if uvr_config.include:
        items = {n: p for n, p in items.items() if n in uvr_config.include}
    items = {n: p for n, p in items.items() if n not in uvr_config.exclude}

    return BuildPackages(items=items)

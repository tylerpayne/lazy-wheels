"""WorkspacePackages: all packages in the workspace."""

from __future__ import annotations

from pathlib import Path


import tomlkit
from diny import singleton, provider
from packaging.utils import canonicalize_name

from ...types.base import Frozen
from ...types.dependency import Dependency
from ...types.package import Package
from ...types.pyproject import PackagePyProject, RootPyProject
from ...types.version import Version


@singleton
class WorkspacePackages(Frozen):
    """All packages discovered from the workspace."""

    items: dict[str, Package]
    root: Path


@provider(WorkspacePackages)
def provide_workspace_packages() -> WorkspacePackages:
    root = Path(".")
    root_doc = RootPyProject.model_validate(
        tomlkit.loads((root / "pyproject.toml").read_text())
    )

    has_root_project = bool(root_doc.project.name)
    has_workspace = bool(root_doc.tool.uv.workspace.members)

    # A root that is both a package and a workspace root is ambiguous: it
    # would appear twice (once as itself, once via a glob like `.`), and
    # uv-release does not yet support that layout. Reject early with a
    # clear message rather than discovering inconsistent state.
    if has_root_project and has_workspace:
        msg = (
            "Root pyproject.toml has both [project] and [tool.uv.workspace]. "
            "uv-release does not yet support a workspace root that is also a "
            "package. Pick one shape (single-package or multi-package workspace)."
        )
        raise ValueError(msg)

    packages: dict[str, Package] = {}

    # Single-package layout: the root pyproject IS the only package. Emit it
    # at path "." so downstream code (git pathspecs, build cwd, etc.) treats
    # the workspace root as the package root.
    if has_root_project:
        packages.update(_packages_from_root(root_doc, root))
    else:
        # Multi-package workspace (existing behavior). An empty workspace
        # block yields an empty dict, which several commands handle.
        packages.update(_packages_from_members(root_doc, root))

    return WorkspacePackages(items=packages, root=root)


def _packages_from_root(root_doc: RootPyProject, root: Path) -> dict[str, Package]:
    name = canonicalize_name(root_doc.project.name)
    if not root_doc.project.version:
        msg = (
            f"Package {name} (./pyproject.toml) has no [project].version. "
            "Set a version before running uvr."
        )
        raise ValueError(msg)
    version = Version.parse(root_doc.project.version)
    deps = [Dependency.parse(d) for d in root_doc.project.dependencies]
    build_deps = [Dependency.parse(d) for d in root_doc.build_system.requires]
    return {
        name: Package(
            name=name,
            path=str(root),
            version=version,
            dependencies=deps,
            build_dependencies=build_deps,
        )
    }


def _packages_from_members(root_doc: RootPyProject, root: Path) -> dict[str, Package]:
    packages: dict[str, Package] = {}
    for pattern in root_doc.tool.uv.workspace.members:
        for pkg_dir in sorted(root.glob(pattern)):
            pyproject_path = pkg_dir / "pyproject.toml"
            if not pyproject_path.exists():
                continue

            pkg_doc = PackagePyProject.model_validate(
                tomlkit.loads(pyproject_path.read_text())
            )
            name = canonicalize_name(pkg_doc.project.name or pkg_dir.name)
            if not pkg_doc.project.version:
                msg = (
                    f"Package {name} ({pyproject_path}) has no [project].version. "
                    "Set a version before running uvr."
                )
                raise ValueError(msg)
            version = Version.parse(pkg_doc.project.version)

            deps = [Dependency.parse(d) for d in pkg_doc.project.dependencies]

            # Include build-system.requires workspace deps in build plan (#23).
            build_deps = [Dependency.parse(d) for d in pkg_doc.build_system.requires]

            packages[name] = Package(
                name=name,
                path=str(pkg_dir),
                version=version,
                dependencies=deps,
                build_dependencies=build_deps,
            )
    return packages

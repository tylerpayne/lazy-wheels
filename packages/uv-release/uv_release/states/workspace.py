"""Parse the workspace from the filesystem into a frozen Workspace."""

from __future__ import annotations

from pathlib import Path

import tomlkit
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from ..types import Package, PackagePyProject, RootPyProject, Version
from .base import State


class Workspace(State):
    """The workspace as parsed from disk. Frozen."""

    root: Path
    packages: dict[str, Package]

    @classmethod
    def parse(cls) -> Workspace:
        """Read the workspace root and all package directories."""
        root = Path.cwd()
        doc = tomlkit.loads((root / "pyproject.toml").read_text())
        root_pyproject = RootPyProject.model_validate(doc)

        uvr = root_pyproject.tool.uvr

        package_dirs: list[Path] = []
        for pattern in root_pyproject.tool.uv.workspace.members:
            package_dirs.extend(sorted(root.glob(pattern)))

        member_names: set[str] = set()
        for pkg_dir in package_dirs:
            if not (pkg_dir / "pyproject.toml").exists():
                continue
            pkg_doc = tomlkit.loads((pkg_dir / "pyproject.toml").read_text())
            name = pkg_doc.get("project", {}).get("name")
            if name:
                member_names.add(name)

        workspace_members = frozenset(member_names)

        packages: dict[str, Package] = {}
        for pkg_dir in package_dirs:
            if not (pkg_dir / "pyproject.toml").exists():
                continue
            pkg = _parse_package(pkg_dir, workspace_members)
            packages[pkg.name] = pkg

        include = frozenset(uvr.config.include)
        exclude = frozenset(uvr.config.exclude)
        if include:
            packages = {n: p for n, p in packages.items() if n in include}
        if exclude:
            packages = {n: p for n, p in packages.items() if n not in exclude}

        return Workspace(root=root, packages=packages)


def _parse_package(path: Path, workspace_members: frozenset[str]) -> Package:
    """Read a package pyproject.toml and return a frozen Package."""
    doc = tomlkit.loads((path / "pyproject.toml").read_text())
    pyproject = PackagePyProject.model_validate(doc)

    version = Version.parse(pyproject.project.version)

    all_dep_specs = pyproject.project.dependencies + pyproject.build_system.requires
    dependencies = [
        str(canonicalize_name(Requirement(d).name))
        for d in all_dep_specs
        if canonicalize_name(Requirement(d).name) in workspace_members
    ]

    try:
        rel_path = path.resolve().relative_to(Path.cwd())
    except ValueError:
        rel_path = path

    return Package(
        name=pyproject.project.name,
        path=str(rel_path),
        version=version,
        dependencies=dependencies,
    )

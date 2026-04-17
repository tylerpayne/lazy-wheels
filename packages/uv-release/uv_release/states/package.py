"""Parse a pyproject.toml into a frozen Package."""

from __future__ import annotations

from pathlib import Path

import tomlkit
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from ..types import Package, PackagePyProject, Version


def parse_package(path: Path, *, workspace_members: frozenset[str]) -> Package:
    """Read a package directory's pyproject.toml and return a frozen Package.

    Dependencies are filtered to only include workspace members.
    """
    doc = tomlkit.loads((path / "pyproject.toml").read_text())
    pyproject = PackagePyProject.model_validate(doc)

    version = Version.parse(pyproject.project.version)

    all_dep_specs = pyproject.project.dependencies + pyproject.build_system.requires
    dependencies = [
        str(canonicalize_name(Requirement(d).name))
        for d in all_dep_specs
        if canonicalize_name(Requirement(d).name) in workspace_members
    ]

    # Store path relative to cwd so git tree lookups work
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

"""Parse a pyproject.toml into a frozen Package."""

from __future__ import annotations

from pathlib import Path

import tomlkit
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from pydantic import BaseModel, ConfigDict, Field

from ..types import Package, Version


class _ProjectTable(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    version: str
    dependencies: list[str] = []


class _BuildSystem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    requires: list[str] = []


class _PyProject(BaseModel):
    model_config = ConfigDict(extra="ignore")

    project: _ProjectTable
    build_system: _BuildSystem = Field(
        default_factory=_BuildSystem, alias="build-system"
    )


def create_package(path: Path, *, workspace_members: frozenset[str]) -> Package:
    """Read a package directory's pyproject.toml and return a frozen Package.

    Dependencies are filtered to only include workspace members.
    """
    doc = tomlkit.loads((path / "pyproject.toml").read_text())
    pyproject = _PyProject.model_validate(doc)

    version = Version.parse(pyproject.project.version)

    all_dep_specs = pyproject.project.dependencies + pyproject.build_system.requires
    deps = [
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
        deps=deps,
    )

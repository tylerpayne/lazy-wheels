"""Dependency handling utilities for the planner.

Provides functions for pinning internal workspace dependencies to exact versions
in pyproject.toml files.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import tomlkit
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from tomlkit.items import Table

from ..toml import read_pyproject, write_pyproject


def _get_dependency_sections(doc: tomlkit.TOMLDocument) -> Iterator[list]:
    """Yield every mutable dependency list from a pyproject.toml.

    Covers [project].dependencies, [project].optional-dependencies.*,
    and [dependency-groups].*.  Does NOT include [build-system].requires.
    """
    project = doc.get("project", {})
    deps = project.get("dependencies")
    if isinstance(deps, list):
        yield deps
    for group in project.get("optional-dependencies", {}).values():
        if isinstance(group, list):
            yield group
    for group in doc.get("dependency-groups", {}).values():
        if isinstance(group, list):
            yield group


def _pin(dep_str: str, version: str) -> str:
    """Pin a PEP 508 dependency to a minimum version.

    Preserves any extras specified in the original dependency string,
    but replaces the version specifier with a >= pin.

    Examples:
        _pin("requests>=2.0", "2.31.0") -> "requests>=2.31.0"
        _pin("pkg[extra1,extra2]~=1.0", "1.5.0") -> "pkg[extra1,extra2]>=1.5.0"
    """
    req = Requirement(dep_str)
    # Sort extras alphabetically for consistent output
    extras = f"[{','.join(sorted(req.extras))}]" if req.extras else ""
    return f"{req.name}{extras}>={version}"


def _apply_pins(deps: list, versions: dict[str, str]) -> list[tuple[str, str]]:
    """Pin internal dependencies in a list, modifying in place.

    Iterates through a list of PEP 508 dependency strings and replaces
    any that match internal packages with exact-pinned versions.

    Args:
        deps: List of dependency strings (modified in place).
        versions: Map of canonical package name -> version to pin.

    Returns:
        List of (old_spec, new_spec) pairs for each changed entry.
    """
    changes: list[tuple[str, str]] = []
    for i, dep_str in enumerate(deps):
        name = canonicalize_name(Requirement(str(dep_str)).name)
        if name in versions:
            new = _pin(str(dep_str), versions[name])
            if new != str(dep_str):
                deps[i] = new
                changes.append((str(dep_str), new))
    return changes


def set_version(pyproject_path: Path, new_version: str) -> None:
    """Update a package's version in pyproject.toml.

    Uses tomlkit to preserve formatting and comments.

    Args:
        pyproject_path: Path to the pyproject.toml file.
        new_version: New version string to set.
    """
    doc = read_pyproject(pyproject_path)
    project = doc.get("project")
    if not isinstance(project, Table):
        return
    project["version"] = new_version
    write_pyproject(pyproject_path, doc)


def pin_dependencies(
    pyproject_path: Path,
    internal_dep_versions: dict[str, str],
) -> None:
    """Pin internal dependencies in pyproject.toml.

    Pins internal deps in all locations:
    - [project].dependencies
    - [project].optional-dependencies.*
    - [dependency-groups].*

    Uses tomlkit to preserve formatting and comments.
    No-op if internal_dep_versions is empty.

    Args:
        pyproject_path: Path to the pyproject.toml file.
        internal_dep_versions: Map of package name -> version for internal deps.
    """
    if not internal_dep_versions:
        return
    doc = read_pyproject(pyproject_path)
    for dep_list in _get_dependency_sections(doc):
        _apply_pins(dep_list, internal_dep_versions)
    write_pyproject(pyproject_path, doc)

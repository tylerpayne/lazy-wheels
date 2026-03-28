"""Dependency handling utilities.

Provides functions for parsing PEP 508 dependency strings and rewriting
pyproject.toml files to pin internal workspace dependencies to exact versions.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import tomlkit
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from tomlkit.items import Table

from .toml import load_pyproject, save_pyproject


def iter_dep_lists(doc: tomlkit.TOMLDocument) -> Iterator[list]:
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


def get_all_dependency_strings(doc: tomlkit.TOMLDocument) -> list[str]:
    """Collect all dependency strings from a pyproject.toml.

    Gathers dependencies from four locations:
    - [build-system].requires (build-time deps)
    - [project].dependencies (main runtime deps)
    - [project].optional-dependencies.* (extras like [dev], [test])
    - [dependency-groups].* (PEP 735 dependency groups)

    Returns raw PEP 508 strings like "requests>=2.0" or "pkg[extra]~=1.0".
    """
    deps: list[str] = list(doc.get("build-system", {}).get("requires", []))
    for dep_list in iter_dep_lists(doc):
        deps.extend(dep_list)
    return deps


def dep_canonical_name(dep_str: str) -> str:
    """Extract the canonical package name from a PEP 508 dependency string.

    Handles version specifiers, extras, and normalizes the name per PEP 503
    (lowercase, hyphens instead of underscores).

    Examples:
        "requests>=2.0" → "requests"
        "My_Package[extra]~=1.0" → "my-package"
    """
    return canonicalize_name(Requirement(dep_str).name)


def pin_dep(dep_str: str, version: str) -> str:
    """Pin a PEP 508 dependency to an exact version.

    Preserves any extras specified in the original dependency string,
    but replaces the version specifier with an exact pin.

    Examples:
        pin_dep("requests>=2.0", "2.31.0") → "requests==2.31.0"
        pin_dep("pkg[extra1,extra2]~=1.0", "1.5.0") → "pkg[extra1,extra2]==1.5.0"
    """
    req = Requirement(dep_str)
    # Sort extras alphabetically for consistent output
    extras = f"[{','.join(sorted(req.extras))}]" if req.extras else ""
    return f"{req.name}{extras}>={version}"


def set_version(pyproject_path: Path, new_version: str) -> None:
    """Update a package's version in pyproject.toml.

    Uses tomlkit to preserve formatting and comments.

    Args:
        pyproject_path: Path to the pyproject.toml file.
        new_version: New version string to set.
    """
    doc = load_pyproject(pyproject_path)
    project = doc.get("project")
    if not isinstance(project, Table):
        return
    project["version"] = new_version
    save_pyproject(pyproject_path, doc)


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
        internal_dep_versions: Map of package name → version for internal deps.
    """
    if not internal_dep_versions:
        return
    doc = load_pyproject(pyproject_path)
    for dep_list in iter_dep_lists(doc):
        _pin_dep_list(dep_list, internal_dep_versions)
    save_pyproject(pyproject_path, doc)


def rewrite_pyproject(
    pyproject_path: Path,
    new_version: str,
    internal_dep_versions: dict[str, str],
) -> None:
    """Update a package's version and pin its internal dependencies.

    Thin wrapper that calls set_version() + pin_dependencies() for backward
    compatibility.

    Args:
        pyproject_path: Path to the pyproject.toml file.
        new_version: New version string to set.
        internal_dep_versions: Map of package name → version for internal deps.
    """
    set_version(pyproject_path, new_version)
    pin_dependencies(pyproject_path, internal_dep_versions)


def _pin_dep_list(deps: list, versions: dict[str, str]) -> list[tuple[str, str]]:
    """Pin internal dependencies in a list, modifying in place.

    Iterates through a list of PEP 508 dependency strings and replaces
    any that match internal packages with exact-pinned versions.

    Args:
        deps: List of dependency strings (modified in place).
        versions: Map of canonical package name → version to pin.

    Returns:
        List of (old_spec, new_spec) pairs for each changed entry.
    """
    changes: list[tuple[str, str]] = []
    for i, dep_str in enumerate(deps):
        name = dep_canonical_name(str(dep_str))
        if name in versions:
            new = pin_dep(str(dep_str), versions[name])
            if new != str(dep_str):
                deps[i] = new
                changes.append((str(dep_str), new))
    return changes

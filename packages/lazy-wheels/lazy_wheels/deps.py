"""Dependency handling utilities.

Provides functions for parsing PEP 508 dependency strings and rewriting
pyproject.toml files to pin internal workspace dependencies to exact versions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from .toml import load_pyproject, save_pyproject


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
    return f"{req.name}{extras}=={version}"


def rewrite_pyproject(
    pyproject_path: Path,
    new_version: str,
    internal_dep_versions: dict[str, str],
) -> None:
    """Update a package's version and pin its internal dependencies.

    This function:
    1. Updates [project].version to new_version
    2. Finds all internal deps and pins them to exact versions

    Internal deps are pinned in all locations:
    - [project].dependencies
    - [project].optional-dependencies.*
    - [dependency-groups].*

    Uses tomlkit to preserve formatting and comments.

    Args:
        pyproject_path: Path to the pyproject.toml file.
        new_version: New version string to set.
        internal_dep_versions: Map of package name → version for internal deps.
    """
    doc = load_pyproject(pyproject_path)
    # Cast needed because tomlkit types are complex unions
    project = cast(dict[str, Any], doc["project"])
    project["version"] = new_version

    if internal_dep_versions:
        # Pin deps in [project].dependencies
        deps = project.get("dependencies")
        if isinstance(deps, list):
            _pin_dep_list(deps, internal_dep_versions)

        # Pin deps in [project].optional-dependencies.*
        opt_deps = project.get("optional-dependencies")
        if isinstance(opt_deps, dict):
            for group in opt_deps.values():
                if isinstance(group, list):
                    _pin_dep_list(group, internal_dep_versions)

        # Pin deps in [dependency-groups].*
        dep_groups = doc.get("dependency-groups")
        if isinstance(dep_groups, dict):
            for group in dep_groups.values():
                if isinstance(group, list):
                    _pin_dep_list(group, internal_dep_versions)

    save_pyproject(pyproject_path, doc)


def _pin_dep_list(deps: list, versions: dict[str, str]) -> None:
    """Pin internal dependencies in a list, modifying in place.

    Iterates through a list of PEP 508 dependency strings and replaces
    any that match internal packages with exact-pinned versions.

    Args:
        deps: List of dependency strings (modified in place).
        versions: Map of canonical package name → version to pin.
    """
    for i, dep_str in enumerate(deps):
        name = dep_canonical_name(str(dep_str))
        if name in versions:
            deps[i] = pin_dep(str(dep_str), versions[name])

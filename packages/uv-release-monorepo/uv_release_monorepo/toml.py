"""TOML reading and writing utilities.

Uses tomlkit to preserve formatting and comments when modifying pyproject.toml
files. This is important for maintaining readable, diff-friendly files.
"""

from __future__ import annotations

from pathlib import Path

import tomlkit
from packaging.utils import canonicalize_name

from .shell import fatal


def load_pyproject(path: Path) -> tomlkit.TOMLDocument:
    """Load and parse a pyproject.toml file.

    Returns a TOMLDocument that preserves formatting when modified and saved.
    """
    return tomlkit.parse(path.read_text())


def save_pyproject(path: Path, doc: tomlkit.TOMLDocument) -> None:
    """Save a TOMLDocument back to disk, preserving original formatting."""
    path.write_text(tomlkit.dumps(doc))


def get_project_name(doc: tomlkit.TOMLDocument, fallback: str) -> str:
    """Extract the canonical package name from [project].name.

    Names are normalized per PEP 503 (lowercase, hyphens instead of
    underscores) for consistent comparison.

    Args:
        doc: Parsed pyproject.toml document.
        fallback: Value to return if name is not specified.
    """
    return canonicalize_name(doc.get("project", {}).get("name", fallback))


def get_project_version(doc: tomlkit.TOMLDocument) -> str:
    """Extract version from [project].version, defaulting to '0.0.0'."""
    return doc.get("project", {}).get("version", "0.0.0")


def get_all_dependency_strings(doc: tomlkit.TOMLDocument) -> list[str]:
    """Collect all dependency strings from a pyproject.toml.

    Gathers dependencies from three locations:
    - [project].dependencies (main runtime deps)
    - [project].optional-dependencies.* (extras like [dev], [test])
    - [dependency-groups].* (PEP 735 dependency groups)

    Returns raw PEP 508 strings like "requests>=2.0" or "pkg[extra]~=1.0".
    """
    project = doc.get("project", {})
    deps: list[str] = list(project.get("dependencies", []))
    # Collect optional dependency groups (e.g., [project.optional-dependencies.dev])
    for group_deps in project.get("optional-dependencies", {}).values():
        deps.extend(group_deps)
    # Collect PEP 735 dependency groups (e.g., [dependency-groups.test])
    for group_deps in doc.get("dependency-groups", {}).values():
        deps.extend(group_deps)
    return deps


def get_workspace_member_globs(doc: tomlkit.TOMLDocument) -> list[str]:
    """Extract workspace member glob patterns from [tool.uv.workspace].

    These patterns (e.g., "packages/*", "libs/*") define which directories
    contain workspace packages.

    Raises:
        SystemExit: If no workspace members are defined.
    """
    members = doc.get("tool", {}).get("uv", {}).get("workspace", {}).get("members")
    if not members:
        fatal("No [tool.uv.workspace] members defined in root pyproject.toml")
    return list(members)

"""uvr configuration: workspace, hooks, matrix, and editor settings.

Functions extracted from toml.py that deal with [tool.uvr.*] configuration
sections in pyproject.toml.
"""

from __future__ import annotations

import tomlkit
from tomlkit.container import OutOfOrderTableProxy
from tomlkit.items import Table

from .shell import exit_fatal
from .toml import get_path


def get_workspace_member_globs(doc: tomlkit.TOMLDocument) -> list[str]:
    """Extract workspace member glob patterns from [tool.uv.workspace].

    These patterns (e.g., "packages/*", "libs/*") define which directories
    contain workspace packages.

    Raises:
        SystemExit: If no workspace members are defined.
    """
    members = get_path(doc, "tool", "uv", "workspace", "members")
    if not members:
        exit_fatal("No [tool.uv.workspace] members defined in root pyproject.toml")
    return list(members)


def get_config(doc: tomlkit.TOMLDocument) -> dict:
    """Extract [tool.uvr.config] as a dict.

    Supported keys:
        include: list of package names to allowlist (only these are considered).
        exclude: list of package names to denylist (these are skipped).
        latest: package name whose GitHub release should be marked "Latest".
        editor: preferred editor for conflict resolution.

    If ``include`` is set, only listed packages are considered.
    ``exclude`` is applied after ``include``.
    """
    raw = get_path(doc, "tool", "uvr", "config", default={})
    return {
        "include": list(raw.get("include", [])),
        "exclude": list(raw.get("exclude", [])),
        "latest": raw.get("latest", ""),
        "editor": raw.get("editor", ""),
    }


def get_hooks(doc: tomlkit.TOMLDocument) -> dict[str, str]:
    """Extract [tool.uvr.hooks] as a dict.

    Supported keys:
        file: Path to a Python module containing a :class:`ReleaseHook`
              subclass, optionally with ``:ClassName`` suffix.  When the
              class name is omitted it defaults to ``Hook``.
    """
    raw = get_path(doc, "tool", "uvr", "hooks", default={})
    return {str(k): str(v) for k, v in raw.items()}


def get_matrix(doc: tomlkit.TOMLDocument) -> dict[str, list[list[str]]]:
    """Extract [tool.uvr.matrix] as {package: [[label, ...], ...]}."""
    raw = get_path(doc, "tool", "uvr", "matrix", default={})
    result: dict[str, list[list[str]]] = {}
    for k, v in raw.items():
        runners: list[list[str]] = []
        for entry in v:
            if isinstance(entry, list):
                runners.append(list(entry))
            else:
                # Bare string -> single-label list for backward compat
                runners.append([str(entry)])
        result[k] = runners
    return result


def set_matrix(doc: tomlkit.TOMLDocument, matrix: dict[str, list[list[str]]]) -> None:
    """Write {package: [[label, ...], ...]} into [tool.uvr.matrix]."""
    if "tool" not in doc:
        doc["tool"] = tomlkit.table()
    tool = doc["tool"]
    assert isinstance(tool, (Table, OutOfOrderTableProxy))
    if "uvr" not in tool:
        tool["uvr"] = tomlkit.table()
    uvr = tool["uvr"]
    assert isinstance(uvr, Table)
    matrix_table = tomlkit.table()
    for pkg, runners in sorted(matrix.items()):
        arr = tomlkit.array()
        for labels in runners:
            inner = tomlkit.array()
            for label in labels:
                inner.append(label)
            arr.append(inner)
        matrix_table[pkg] = arr
    uvr["matrix"] = matrix_table

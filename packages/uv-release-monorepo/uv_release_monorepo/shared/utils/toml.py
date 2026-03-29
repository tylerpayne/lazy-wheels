"""TOML reading and writing utilities.

Uses tomlkit to preserve formatting and comments when modifying pyproject.toml
files. This is important for maintaining readable, diff-friendly files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import tomlkit


def read_pyproject(path: Path) -> tomlkit.TOMLDocument:
    """Load and parse a pyproject.toml file.

    Returns a TOMLDocument that preserves formatting when modified and saved.
    """
    return tomlkit.parse(path.read_text())


def write_pyproject(path: Path, doc: tomlkit.TOMLDocument) -> None:
    """Save a TOMLDocument back to disk, preserving original formatting."""
    path.write_text(tomlkit.dumps(doc))


def get_path(doc: Any, *keys: str, default: Any = None) -> Any:
    """Safely traverse nested dicts/TOMLDocuments and return the value.

    Args:
        doc: Root mapping (typically a TOMLDocument).
        *keys: Sequence of keys to descend into.
        default: Value returned when any key is missing.

    Examples:
        get_path(doc, "tool", "uvr", "config") -> doc["tool"]["uvr"]["config"]
        get_path(doc, "missing", default={}) -> {}
    """
    current: Any = doc
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current

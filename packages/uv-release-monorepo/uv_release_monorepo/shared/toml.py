"""TOML reading and writing utilities.

Uses tomlkit to preserve formatting and comments when modifying pyproject.toml
files. This is important for maintaining readable, diff-friendly files.
"""

from __future__ import annotations

from pathlib import Path

import tomlkit


def load_pyproject(path: Path) -> tomlkit.TOMLDocument:
    """Load and parse a pyproject.toml file.

    Returns a TOMLDocument that preserves formatting when modified and saved.
    """
    return tomlkit.parse(path.read_text())


def save_pyproject(path: Path, doc: tomlkit.TOMLDocument) -> None:
    """Save a TOMLDocument back to disk, preserving original formatting."""
    path.write_text(tomlkit.dumps(doc))

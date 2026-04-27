"""Shared merge-base file helpers for state modules."""

from __future__ import annotations

from pathlib import Path


def read_merge_base(root: Path, rel_path: str) -> str:
    """Read a merge base from .uvr/bases/<rel_path>, or empty string if absent."""
    base_file = root / ".uvr" / "bases" / rel_path
    if base_file.exists():
        return base_file.read_text()
    return ""

"""Template loading and merge base management for .uvr/bases/."""

from __future__ import annotations

from pathlib import Path


def store_base(content: str, relative_path: str, uvr_dir: Path | None = None) -> Path:
    """Store a merge base file in .uvr/bases/.

    Returns the path to the stored base file.
    """
    if uvr_dir is None:
        uvr_dir = Path.cwd() / ".uvr"
    bases_dir = uvr_dir / "bases"
    base_path = bases_dir / relative_path
    base_path.parent.mkdir(parents=True, exist_ok=True)
    base_path.write_text(content)
    return base_path


def load_base(relative_path: str, uvr_dir: Path | None = None) -> Path:
    """Return the path to a stored merge base. May not exist."""
    if uvr_dir is None:
        uvr_dir = Path.cwd() / ".uvr"
    return uvr_dir / "bases" / relative_path

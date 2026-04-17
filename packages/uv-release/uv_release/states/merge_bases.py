"""Read merge bases and resolve editor for upgrade intents."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

_BASES_DIR = ".uvr/bases"

_FALLBACK_EDITORS = ("code", "vim", "vi", "nano")


def read_base(root: Path, rel_path: str) -> str:
    """Read a merge base from .uvr/bases/<rel_path>, or empty string if absent."""
    base_file = root / _BASES_DIR / rel_path
    if base_file.exists():
        return base_file.read_text()
    return ""


def resolve_editor(cli_editor: str | None) -> str | None:
    """Resolve editor: CLI arg > $VISUAL > $EDITOR > fallback."""
    if cli_editor:
        return cli_editor

    env_editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if env_editor:
        return env_editor

    for name in _FALLBACK_EDITORS:
        if shutil.which(name):
            return name

    return None

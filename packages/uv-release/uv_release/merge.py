"""Merge execution helpers used by MergeUpgradeCommand."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

_WAIT_EDITORS = {"code", "codium", "subl", "atom", "zed"}


def merge_texts(current: str, base: str, incoming: str) -> tuple[str, bool]:
    """Three-way merge of three strings. Returns (merged_text, has_conflicts).

    All inputs are text strings. Uses git merge-file under the hood.
    """
    with (
        tempfile.NamedTemporaryFile(
            mode="w", suffix=".toml", prefix="current-", delete=False
        ) as current_f,
        tempfile.NamedTemporaryFile(
            mode="w", suffix=".toml", prefix="base-", delete=False
        ) as base_f,
        tempfile.NamedTemporaryFile(
            mode="w", suffix=".toml", prefix="incoming-", delete=False
        ) as incoming_f,
    ):
        current_f.write(current)
        current_f.flush()
        base_f.write(base)
        base_f.flush()
        incoming_f.write(incoming)
        incoming_f.flush()
        current_path = Path(current_f.name)
        base_path = Path(base_f.name)
        incoming_path = Path(incoming_f.name)

    try:
        result = subprocess.run(
            [
                "git",
                "merge-file",
                "-p",
                "-L",
                "current",
                "-L",
                "base",
                "-L",
                "incoming",
                str(current_path),
                str(base_path),
                str(incoming_path),
            ],
            capture_output=True,
            text=True,
        )
    finally:
        current_path.unlink(missing_ok=True)
        base_path.unlink(missing_ok=True)
        incoming_path.unlink(missing_ok=True)

    if result.returncode < 0:
        msg = f"git merge-file failed: {result.stderr}"
        raise ValueError(msg)

    return result.stdout, result.returncode > 0


def parse_editor_command(editor: str) -> list[str]:
    """Build the editor command, adding --wait for GUI editors that need it."""
    base = Path(editor).stem
    if base in _WAIT_EDITORS:
        return [editor, "--wait"]
    return [editor]

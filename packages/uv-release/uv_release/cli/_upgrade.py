"""Shared upgrade/merge-base helpers for workflow and skill upgrade commands."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

UVR_DIR = ".uvr"
BASES_DIR = f"{UVR_DIR}/bases"

FALLBACK_EDITORS = ("code", "vim", "vi", "nano")
WAIT_EDITORS = {"code", "codium", "subl", "atom", "zed"}


def write_base(root: Path, rel_path: str, content: str) -> None:
    """Save a merge base to .uvr/bases/<rel_path>."""
    base_file = root / BASES_DIR / rel_path
    base_file.parent.mkdir(parents=True, exist_ok=True)
    base_file.write_text(content)


def read_base(root: Path, rel_path: str) -> str:
    """Read a merge base from .uvr/bases/<rel_path>, or empty string if absent."""
    base_file = root / BASES_DIR / rel_path
    if base_file.exists():
        return base_file.read_text()
    return ""


def three_way_merge(dest: Path, base_text: str, fresh_text: str) -> tuple[str, bool]:
    """Run git merge-file and return (merged_text, has_conflicts)."""
    with (
        tempfile.NamedTemporaryFile(
            mode="w", suffix=".yml", prefix="base-", delete=False
        ) as base_f,
        tempfile.NamedTemporaryFile(
            mode="w", suffix=".yml", prefix="fresh-", delete=False
        ) as fresh_f,
    ):
        base_f.write(base_text)
        base_f.flush()
        fresh_f.write(fresh_text)
        fresh_f.flush()
        base_path = Path(base_f.name)
        fresh_path = Path(fresh_f.name)

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
                "template",
                str(dest),
                str(base_path),
                str(fresh_path),
            ],
            capture_output=True,
            text=True,
        )
    finally:
        base_path.unlink(missing_ok=True)
        fresh_path.unlink(missing_ok=True)

    if result.returncode < 0:
        print(f"ERROR: git merge-file failed:\n{result.stderr}")
        raise SystemExit(1)

    return result.stdout, result.returncode > 0


def editor_cmd(editor: str) -> list[str]:
    """Build the editor command, adding --wait for GUI editors that need it."""
    base = Path(editor).stem
    if base in WAIT_EDITORS:
        return [editor, "--wait"]
    return [editor]


def resolve_editor(cli_editor: str | None, root: Path) -> str | None:
    """Resolve editor: CLI arg > $VISUAL > $EDITOR > fallback."""
    if cli_editor:
        return cli_editor

    env_editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if env_editor:
        return env_editor

    for name in FALLBACK_EDITORS:
        if shutil.which(name):
            return name

    return None

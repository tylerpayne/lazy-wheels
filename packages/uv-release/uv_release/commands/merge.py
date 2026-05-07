"""Three-way merge command with optional editor for conflict resolution."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Literal

from ..ui.console import console
from .base import Command
from ..utils.merge import merge_texts


class MergeUpgradeCommand(Command):
    """Three-way merge of a file using git merge-file.

    Reads base content from `base_path` (a transient cache path, populated
    earlier in the same job by a FetchWorkflowBaseCommand or
    FetchSkillBasesCommand). Merges with `incoming_content` and the file
    currently on disk at `file_path`. The base path is not modified by this
    command; the authoritative version record lives in pyproject.toml and is
    updated by a separate UpdateTomlCommand only on successful merge.
    """

    type: Literal["merge_upgrade"] = "merge_upgrade"
    file_path: str
    base_path: str
    incoming_content: str
    editor: str = ""

    def execute(self) -> int:
        if self.label:
            console.print(f"  {self.label}")
        current_path = Path(self.file_path)
        base = Path(self.base_path)
        # Missing base means we have no common ancestor to compare against.
        # That should have been caught upstream (the fetch command runs first).
        base_content = base.read_text(encoding="utf-8") if base.exists() else ""
        current = current_path.read_text(encoding="utf-8")
        merged, has_conflicts = merge_texts(
            current, base_content, self.incoming_content
        )
        if merged == current:
            console.print(f"    {self.file_path}: already up to date")
            return 0
        current_path.write_text(merged, encoding="utf-8")
        if has_conflicts:
            return self._resolve_conflicts(current_path, current)
        return 0

    def _resolve_conflicts(self, path: Path, original: str) -> int:
        """Open editor for conflict resolution if configured.

        On revert, the file is restored to `original`. Returning a non-zero
        exit code halts the surrounding job, so any UpdateTomlCommand queued
        after this command will not run, leaving workflow-version unchanged.
        """
        if not self.editor:
            console.print(
                f"    {self.file_path}: merged with conflicts (resolve manually)"
            )
            return 0
        try:
            answer = (
                input(f"    {self.file_path}: conflicts. Open in {self.editor}? [Y/n] ")
                .strip()
                .lower()
            )
        except (EOFError, KeyboardInterrupt):
            console.print()
            return 0
        if answer == "n":
            return 0
        subprocess.run([self.editor, str(path)])
        content = path.read_text(encoding="utf-8")
        if "<<<<<<< " in content:
            try:
                revert = (
                    input("    Unresolved conflicts. Revert? [Y/n] ").strip().lower()
                )
            except (EOFError, KeyboardInterrupt):
                console.print()
                return 1
            if revert != "n":
                path.write_text(original, encoding="utf-8")
                console.print(f"    Reverted {self.file_path}")
            return 1
        console.print(f"    Conflicts resolved in {self.file_path}")
        return 0

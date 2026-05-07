"""Filesystem commands."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from ..ui.console import console
from .base import Command


class WriteFileCommand(Command):
    """Write content to a file, creating parent directories as needed."""

    type: Literal["write_file"] = "write_file"
    path: str
    content: str

    def execute(self) -> int:
        if self.label:
            console.print(f"  {self.label}")
        p = Path(self.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.content)
        return 0


class MakeDirectoryCommand(Command):
    """Create a directory, including parents."""

    type: Literal["make_directory"] = "make_directory"
    path: str

    def execute(self) -> int:
        if self.label:
            console.print(f"  {self.label}")
        Path(self.path).mkdir(parents=True, exist_ok=True)
        return 0


class RemoveDirectoryCommand(Command):
    """Remove a directory tree."""

    type: Literal["remove_directory"] = "remove_directory"
    path: str

    def execute(self) -> int:
        import shutil

        if self.label:
            console.print(f"  {self.label}")
        p = Path(self.path)
        if p.exists():
            shutil.rmtree(p)
        return 0

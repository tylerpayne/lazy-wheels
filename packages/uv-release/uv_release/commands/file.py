"""Commands for filesystem operations."""

from __future__ import annotations

from typing import Literal

from ..types import Command


class MakeDirectoryCommand(Command):
    """Create a directory, including parent directories."""

    type: Literal["make_directory"] = "make_directory"
    path: str

    def execute(self) -> int:
        from pathlib import Path

        Path(self.path).mkdir(parents=True, exist_ok=True)
        return 0


class WriteFileCommand(Command):
    """Write content to a file, creating parent directories as needed."""

    type: Literal["write_file"] = "write_file"
    path: str
    content: str

    def execute(self) -> int:
        from pathlib import Path

        dest = Path(self.path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(self.content, encoding="utf-8")
        return 0

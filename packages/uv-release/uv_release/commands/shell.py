"""Shell and git tag commands."""

from __future__ import annotations

import subprocess
from typing import Literal

from ..ui.console import console
from .base import Command


class ShellCommand(Command):
    """Run a subprocess."""

    type: Literal["shell"] = "shell"
    args: list[str]

    def execute(self) -> int:
        if self.label:
            console.print(f"  {self.label}")
        result = subprocess.run(self.args)
        return result.returncode


class CreateTagCommand(Command):
    """Create an annotated git tag. Skips if the tag already exists.

    Annotated (not lightweight) so ``git push --follow-tags`` will push it.
    """

    type: Literal["create_tag"] = "create_tag"
    tag_name: str

    def execute(self) -> int:
        check = subprocess.run(
            ["git", "tag", "-l", self.tag_name],
            capture_output=True,
            text=True,
        )
        if check.stdout.strip() == self.tag_name:
            if self.label:
                console.print(f"  {self.label} (already exists, skipping)")
            return 0
        if self.label:
            console.print(f"  {self.label}")
        result = subprocess.run(
            ["git", "tag", "-a", "-m", self.tag_name, self.tag_name]
        )
        return result.returncode

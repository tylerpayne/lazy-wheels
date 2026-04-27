"""Shell and git tag commands."""

from __future__ import annotations

from typing import Literal

from ..types import Command


class ShellCommand(Command):
    """Run a subprocess."""

    type: Literal["shell"] = "shell"
    args: list[str]

    def execute(self) -> int:
        import subprocess

        result = subprocess.run(self.args)
        return result.returncode


class CreateTagCommand(Command):
    """Create a git tag via subprocess.

    Uses ``git tag`` so the tag is visible to ``git push --follow-tags``.
    """

    type: Literal["create_tag"] = "create_tag"
    tag_name: str

    def execute(self) -> int:
        import subprocess

        subprocess.run(
            ["git", "tag", "-a", "-m", self.tag_name, self.tag_name],
            check=True,
        )
        return 0

"""Command base class."""

from __future__ import annotations

from ..types.base import Frozen


class Command(Frozen):
    """Base command."""

    type: str
    label: str = ""
    check: bool = True

    def execute(self) -> int:
        raise NotImplementedError

    def to_shell(self) -> str:
        """Return a shell-like representation suitable for showing the user.

        For commands that wrap a subprocess (`uv lock`, `git push`), this
        returns the literal shell command. For pure-Python commands that
        edit files in place (toml/version edits), this returns the closest
        equivalent `uvr` invocation when one exists, or a `# comment` line
        describing what would happen. Defaults to the label so commands
        without an override still render *something* reasonable.
        """
        return self.label

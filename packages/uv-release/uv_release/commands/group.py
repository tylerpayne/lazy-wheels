"""Command group with optional user confirmation."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from ..ui.console import console
from .base import Command


class CommandGroup(Command):
    """A container of commands that optionally prompts for confirmation."""

    type: Literal["command_group"] = "command_group"
    commands: list[Any] = Field(default_factory=list)
    needs_confirmation: bool = False

    def execute(self) -> int:
        if self.label:
            console.print(f"  {self.label}")
        if self.needs_confirmation:
            try:
                answer = input("    Execute? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                console.print()
                return 0
            if answer != "y":
                return 0
        for cmd in self.commands:
            returncode = cmd.execute()
            if cmd.check and returncode != 0:
                return returncode
        return 0

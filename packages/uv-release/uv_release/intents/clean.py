"""CleanIntent: remove uvr caches."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..commands import ShellCommand
from ..states.workspace import Workspace
from ..types import Command, Job, Plan


class CleanIntent(BaseModel):
    """Intent to remove uvr caches and ephemeral files."""

    model_config = ConfigDict(frozen=True)

    type: Literal["clean"] = "clean"

    def guard(self, *, workspace: Workspace) -> None:
        """No preconditions for clean."""

    def plan(self, *, workspace: Workspace) -> Plan:
        """(state, intent) -> plan."""
        commands: list[Command] = [
            ShellCommand(
                label="Remove project cache",
                args=["rm", "-rf", str(workspace.root / ".uvr" / "cache")],
            ),
            ShellCommand(
                label="Remove user cache",
                args=["rm", "-rf", str(Path.home() / ".uvr" / "cache")],
            ),
        ]
        return Plan(jobs=[Job(name="clean", commands=commands)])

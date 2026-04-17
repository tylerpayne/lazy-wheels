"""CleanIntent: remove uvr caches."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..commands import ShellCommand
from ..types import Command, Job, Plan, Workspace


class CleanIntent(BaseModel):
    """Intent to remove uvr caches and ephemeral files."""

    model_config = ConfigDict(frozen=True)

    type: Literal["clean"] = "clean"

    def guard(self, workspace: Workspace) -> None:
        """No preconditions for clean."""

    def plan(self, workspace: Workspace) -> Plan:
        """(state, intent) -> plan."""
        commands: list[Command] = []
        cache_dir = Path.cwd() / ".uvr" / "cache"
        if cache_dir.is_dir():
            commands.append(
                ShellCommand(
                    label=f"Remove {cache_dir}",
                    args=["rm", "-rf", str(cache_dir)],
                )
            )

        home_cache = Path.home() / ".uvr" / "cache"
        if home_cache.is_dir():
            commands.append(
                ShellCommand(
                    label=f"Remove {home_cache}",
                    args=["rm", "-rf", str(home_cache)],
                )
            )

        return Plan(jobs=[Job(name="clean", commands=commands)])

"""ConfigureIntent: manage [tool.uvr.config] in the root pyproject.toml."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..commands import UpdateTomlCommand
from ..types import Command, Job, Plan, Workspace


class ConfigureIntent(BaseModel):
    """Intent to update [tool.uvr.config] settings."""

    model_config = ConfigDict(frozen=True)

    type: Literal["configure"] = "configure"
    updates: dict[str, str] = Field(default_factory=dict)
    add_include: list[str] = Field(default_factory=list)
    add_exclude: list[str] = Field(default_factory=list)
    remove_packages: list[str] = Field(default_factory=list)
    clear: bool = False

    def guard(self, workspace: Workspace) -> None:
        """Check pyproject.toml exists."""
        if not Path("pyproject.toml").exists():
            msg = "No pyproject.toml found."
            raise ValueError(msg)

    def plan(self, workspace: Workspace) -> Plan:
        """(state, intent) -> plan."""
        commands: list[Command] = []

        if self.clear:
            for key, val in [
                ("include", []),
                ("exclude", []),
                ("latest", ""),
                ("editor", ""),
            ]:
                commands.append(
                    UpdateTomlCommand(label=f"Clear {key}", key=key, value=val)
                )
            return Plan(jobs=[Job(name="configure", commands=commands)])

        # Scalar updates
        for key, value in sorted(self.updates.items()):
            commands.append(
                UpdateTomlCommand(
                    label=f"Set {key} = {value}",
                    key=key,
                    value=value,
                )
            )

        # List mutations
        if self.add_include or self.add_exclude or self.remove_packages:
            include = list(workspace.config.include)
            exclude = list(workspace.config.exclude)

            for pkg in self.add_include:
                if pkg not in include:
                    include.append(pkg)
            for pkg in self.add_exclude:
                if pkg not in exclude:
                    exclude.append(pkg)
            for pkg in self.remove_packages:
                if pkg in include:
                    include.remove(pkg)
                if pkg in exclude:
                    exclude.remove(pkg)

            if self.add_include or self.remove_packages:
                commands.append(
                    UpdateTomlCommand(
                        label=f"Set include = {include}",
                        key="include",
                        value=include,
                    )
                )
            if self.add_exclude or self.remove_packages:
                commands.append(
                    UpdateTomlCommand(
                        label=f"Set exclude = {exclude}",
                        key="exclude",
                        value=exclude,
                    )
                )

        if not commands:
            return Plan()

        return Plan(jobs=[Job(name="configure", commands=commands)])

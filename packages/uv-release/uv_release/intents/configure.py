"""ConfigureIntent: manage [tool.uvr.config] in the root pyproject.toml."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..commands import UpdateTomlCommand
from .shared.lists import apply_list_mutations
from ..states.uvr_state import UvrState
from ..states.workspace import Workspace
from ..types import Command, Job, Plan


class ConfigureIntent(BaseModel):
    """Intent to update [tool.uvr.config] settings."""

    model_config = ConfigDict(frozen=True)

    type: Literal["configure"] = "configure"
    updates: dict[str, str] = Field(default_factory=dict)
    add_include: list[str] = Field(default_factory=list)
    add_exclude: list[str] = Field(default_factory=list)
    remove_packages: list[str] = Field(default_factory=list)
    clear: bool = False

    def guard(self, *, workspace: Workspace) -> None:
        """No preconditions. Workspace parse already validates pyproject.toml."""

    def plan(self, *, uvr_state: UvrState) -> Plan:
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
            include, exclude = apply_list_mutations(
                list(uvr_state.config.include),
                list(uvr_state.config.exclude),
                add_include=self.add_include,
                add_exclude=self.add_exclude,
                remove=self.remove_packages,
            )

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

"""ConfigurePublishIntent: manage [tool.uvr.publish] in root pyproject.toml."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..commands import WriteUvrSectionCommand
from ..states.uvr_state import UvrState
from ..states.workspace import Workspace
from ..types import Command, Job, Plan


class ConfigurePublishIntent(BaseModel):
    """Intent to update [tool.uvr.publish] settings."""

    model_config = ConfigDict(frozen=True)

    type: Literal["configure_publish"] = "configure_publish"
    index: str | None = None
    environment: str | None = None
    trusted_publishing: str | None = None
    add_include: list[str] = Field(default_factory=list)
    add_exclude: list[str] = Field(default_factory=list)
    remove_packages: list[str] = Field(default_factory=list)
    clear: bool = False

    def guard(self, *, workspace: Workspace) -> None:
        """No preconditions. Workspace parse already validates pyproject.toml."""

    def plan(self, *, uvr_state: UvrState) -> Plan:
        """(state, intent) -> plan."""
        has_mutations = any(
            [
                self.index is not None,
                self.environment is not None,
                self.trusted_publishing is not None,
                self.add_include,
                self.add_exclude,
                self.remove_packages,
                self.clear,
            ]
        )
        if not has_mutations:
            return Plan()

        pub = uvr_state.publishing
        data: dict[str, Any] = {
            "index": pub.index,
            "environment": pub.environment,
            "trusted-publishing": pub.trusted_publishing,
            "include": list(pub.include),
            "exclude": list(pub.exclude),
        }

        if self.clear:
            data = {
                "index": "",
                "environment": "",
                "trusted-publishing": "automatic",
                "include": [],
                "exclude": [],
            }
        else:
            if self.index is not None:
                data["index"] = self.index
            if self.environment is not None:
                data["environment"] = self.environment
            if self.trusted_publishing is not None:
                data["trusted-publishing"] = self.trusted_publishing

            include: list[str] = list(data["include"])
            exclude: list[str] = list(data["exclude"])

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

            data["include"] = include
            data["exclude"] = exclude

        commands: list[Command] = [
            WriteUvrSectionCommand(
                label="Update publish config",
                section="publish",
                data=data,
            )
        ]
        return Plan(jobs=[Job(name="configure_publish", commands=commands)])

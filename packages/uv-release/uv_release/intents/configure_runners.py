"""ConfigureRunnersIntent: manage [tool.uvr.runners] in root pyproject.toml."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..commands import WriteUvrSectionCommand
from ..states.uvr_state import UvrState
from ..types import Command, Job, Plan


class ConfigureRunnersIntent(BaseModel):
    """Intent to update [tool.uvr.runners] settings."""

    model_config = ConfigDict(frozen=True)

    type: Literal["configure_runners"] = "configure_runners"
    package: str = ""
    add: list[str] = Field(default_factory=list)
    remove: list[str] = Field(default_factory=list)
    clear: bool = False

    def guard(self, *, uvr_state: UvrState) -> None:
        """Check preconditions."""
        if self.remove and self.package:
            runners = list(uvr_state.runners.get(self.package, []))
            for runner in self.remove:
                labels = [s.strip() for s in runner.split(",")]
                if labels not in runners:
                    msg = f"[{', '.join(labels)}] not in runners for '{self.package}'"
                    raise ValueError(msg)

    def plan(self, *, uvr_state: UvrState) -> Plan:
        """(state, intent) -> plan."""
        has_mutations = bool(self.add or self.remove or self.clear)
        if not has_mutations:
            return Plan()

        matrix: dict[str, list[list[str]]] = {
            k: [list(r) for r in v] for k, v in uvr_state.runners.items()
        }

        if self.clear:
            if self.package and self.package in matrix:
                del matrix[self.package]
            elif not self.package:
                matrix = {}
        elif self.add:
            runners = list(matrix.get(self.package, []))
            for runner in self.add:
                labels = [s.strip() for s in runner.split(",")]
                if labels not in runners:
                    runners.append(labels)
            matrix[self.package] = runners
        elif self.remove:
            runners = list(matrix.get(self.package, []))
            for runner in self.remove:
                labels = [s.strip() for s in runner.split(",")]
                if labels in runners:
                    runners.remove(labels)
            if runners:
                matrix[self.package] = runners
            elif self.package in matrix:
                del matrix[self.package]

        label = (
            f"Update runners for {self.package}" if self.package else "Clear runners"
        )
        commands: list[Command] = [
            WriteUvrSectionCommand(
                label=label,
                section="runners",
                data=matrix,
            )
        ]
        return Plan(jobs=[Job(name="configure_runners", commands=commands)])

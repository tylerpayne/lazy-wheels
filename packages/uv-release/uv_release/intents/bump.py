"""BumpIntent: bump package versions in the workspace."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..commands import PinDepsCommand, SetVersionCommand, ShellCommand
from .shared.versioning import compute_bumped_version
from ..types import (
    BumpType,
    Command,
    Job,
    Package,
    Plan,
    Workspace,
)


class BumpIntent(BaseModel):
    """Intent to bump versions. No change detection needed."""

    model_config = ConfigDict(frozen=True)

    type: Literal["bump"] = "bump"
    bump_type: BumpType
    packages: frozenset[str] = frozenset()
    pin: bool = True
    commit: bool = True

    def guard(self, workspace: Workspace) -> None:
        """Check preconditions. Raises ValueError on failure."""
        # Check requested packages exist
        for name in self.packages:
            if name not in workspace.packages:
                available = ", ".join(sorted(workspace.packages.keys()))
                msg = f"Unknown package '{name}'. Available: {available}"
                raise ValueError(msg)

        # Check bump type is legal for each target package's version state
        for name, pkg in self._target_packages(workspace).items():
            # Delegate to compute_bumped_version which raises ValueError on invalid transitions
            compute_bumped_version(pkg.version, self.bump_type)

    def plan(self, workspace: Workspace) -> Plan:
        """(state, intent) -> plan."""
        targets = self._target_packages(workspace)
        bumped_packages: dict[str, Package] = {}
        commands: list[Command] = []

        # 1. Compute bumped versions and add SetVersionCommand for each
        for name, pkg in targets.items():
            bumped = compute_bumped_version(pkg.version, self.bump_type)
            bumped_packages[name] = Package(
                name=pkg.name,
                path=pkg.path,
                version=bumped,
                dependencies=pkg.dependencies,
            )
            commands.append(
                SetVersionCommand(
                    label=f"Bump {name} to {bumped.raw}",
                    package=pkg,
                    version=bumped,
                )
            )

        # 2. Pin internal deps
        if self.pin:
            for name, pkg in targets.items():
                pkg_pins = {
                    dep: bumped_packages[dep]
                    for dep in pkg.dependencies
                    if dep in bumped_packages
                }
                if pkg_pins:
                    commands.append(
                        PinDepsCommand(
                            label=f"Pin deps for {name}",
                            package=pkg,
                            pins=pkg_pins,
                        )
                    )

        # 3. Sync lockfile
        commands.append(
            ShellCommand(
                label="Sync lockfile",
                args=["uv", "sync", "--all-groups", "--all-extras", "--all-packages"],
                check=False,
            )
        )

        # 4. Commit
        if self.commit:
            body = "\n".join(
                f"{name} {bumped_packages[name].version.raw}"
                for name in sorted(bumped_packages)
            )
            commands.append(
                ShellCommand(
                    label="Commit version bumps",
                    args=[
                        "git",
                        "commit",
                        "-am",
                        "chore: bump to next dev versions",
                        "-m",
                        body,
                    ],
                )
            )

        bump_job = Job(name="bump", commands=commands)
        return Plan(jobs=[bump_job])

    def _target_packages(self, workspace: Workspace) -> dict[str, Package]:
        """Return the packages this intent targets."""
        if self.packages:
            return {
                name: workspace.packages[name]
                for name in sorted(self.packages)
                if name in workspace.packages
            }
        return dict(sorted(workspace.packages.items()))

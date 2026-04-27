"""VersionFix: guard-phase check for dev versions that need stabilizing."""

from __future__ import annotations

from diny import provider
from pydantic import BaseModel, ConfigDict

from ...commands import SetVersionCommand, ShellCommand
from ...states.changes import Changes
from ...types import Command, CommandGroup, Package, Version
from ..shared.dep_pins import compute_dep_pins
from ..shared.packages import format_version_body
from ..shared.versioning import compute_release_version
from .params import ReleaseParams


class VersionFix(BaseModel):
    """Commands to fix dev versions before release, or None if not needed."""

    model_config = ConfigDict(frozen=True)

    group: CommandGroup | None = None


@provider(VersionFix)
def compute_version_fix(changes: Changes, params: ReleaseParams) -> VersionFix:
    """Build a CommandGroup to fix dev versions, or None if nothing to fix."""
    if params.dev_release:
        return VersionFix()

    needs_fix: dict[str, tuple[Package, Version]] = {}
    for change in changes.items:
        release_version = compute_release_version(change.package.version)
        if change.package.version != release_version:
            needs_fix[change.package.name] = (change.package, release_version)

    if not needs_fix:
        return VersionFix()

    commands: list[Command] = []
    pinned_packages: dict[str, Package] = {}
    for name, (pkg, version) in sorted(needs_fix.items()):
        commands.append(
            SetVersionCommand(
                label=f"Set {name} to {version.raw}",
                package=pkg,
                version=version,
            )
        )
        pinned_packages[name] = pkg.with_version(version)

    commands.extend(
        compute_dep_pins(
            [change.package for change in changes.items],
            pinned_packages,
        )
    )

    body = format_version_body(
        {name: version.raw for name, (_, version) in needs_fix.items()}
    )
    commands.append(
        ShellCommand(
            label="Commit release versions",
            args=["git", "commit", "-am", "chore: set release versions", "-m", body],
        )
    )

    if params.target == "ci":
        commands.append(ShellCommand(label="Push", args=["git", "push"]))

    return VersionFix(
        group=CommandGroup(
            label="Set release versions and commit",
            needs_user_confirmation=True,
            commands=commands,
        )
    )

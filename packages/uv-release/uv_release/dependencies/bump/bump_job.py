"""BumpJob: standalone version bump (`uvr bump --minor`)."""

from __future__ import annotations

from diny import singleton, provider

from .bump_versions import BumpVersions
from .dependency_pins import BumpDependencyPins
from ...commands import (
    AnyCommand,
    CommitCommand,
    PinDepsCommand,
    PushCommand,
    SetVersionCommand,
    SyncLockfileCommand,
)
from ...types.job import Job
from ..params.bump_params import NoPinDeps
from ..params.no_commit import NoCommit
from ..params.no_push import NoPush
from ..shared.workspace_packages import WorkspacePackages


@singleton
class BumpJob(Job):
    """Standalone bump: set versions, pin deps, sync, commit."""


@provider(BumpJob)
def provide_bump_job(
    bump_versions: BumpVersions,
    dependency_pins: BumpDependencyPins,
    workspace_packages: WorkspacePackages,
    no_commit: NoCommit,
    no_push: NoPush,
    no_pin_deps: NoPinDeps,
) -> BumpJob:
    if not bump_versions.items:
        return BumpJob(name="bump")

    commands: list[AnyCommand] = []

    for name, new_version in bump_versions.items.items():
        pkg = workspace_packages.items[name]
        commands.append(
            SetVersionCommand(
                label=f"Bump {name} to {new_version.raw}",
                package_path=pkg.path,
                version=new_version.raw,
            )
        )

    for pin in [] if no_pin_deps.value else dependency_pins.items:
        commands.append(
            PinDepsCommand(
                label=f"Pin deps in {pin.package_path}",
                package_path=pin.package_path,
                pins=pin.pins,
            )
        )

    commands.append(SyncLockfileCommand(label="Sync lockfile"))

    if not no_commit.value:
        body_lines = [f"  {n}: {v.raw}" for n, v in bump_versions.items.items()]
        commands.append(
            CommitCommand(
                label="Commit version bumps",
                message="chore: bump to next dev versions",
                body="\n".join(body_lines),
            )
        )

        if not no_push.value:
            commands.append(PushCommand(label="Push", follow_tags=True))

    return BumpJob(name="bump", commands=commands)

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
from ...types.bump_kind import BumpKind
from ...types.job import Job
from ..params.bump_params import NoPinDeps
from ..params.bump_type import BumpType
from ..params.no_commit import NoCommit
from ..params.no_push import NoPush
from ..params.version_mode import VersionMode, VersionOp
from ..shared.workspace_packages import WorkspacePackages


# Each `uvr version` invocation lands in this job, so the commit message
# is keyed off the actual CLI intent: --set X gives a "set versions"
# commit; --bump <axis> picks an axis-specific message; --bump stable
# gives a release commit. No inference from resulting versions.
_BUMP_MESSAGES: dict[BumpKind, str] = {
    BumpKind.STABLE: "chore: set release versions",
    BumpKind.DEV: "chore: bump to next dev versions",
    BumpKind.MAJOR: "chore: bump major versions",
    BumpKind.MINOR: "chore: bump minor versions",
    BumpKind.PATCH: "chore: bump patch versions",
    BumpKind.POST: "chore: bump post versions",
    BumpKind.ALPHA: "chore: bump alpha versions",
    BumpKind.BETA: "chore: bump beta versions",
    BumpKind.RC: "chore: bump rc versions",
    BumpKind.RELEASE: "chore: strip dev versions",
    BumpKind.AUTO: "chore: bump versions",
}


@singleton
class BumpJob(Job):
    """Standalone bump: set versions, pin deps, sync, commit."""


@provider(BumpJob)
def provide_bump_job(
    bump_versions: BumpVersions,
    dependency_pins: BumpDependencyPins,
    workspace_packages: WorkspacePackages,
    bump_type: BumpType,
    version_mode: VersionMode,
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
                package_name=pkg.name,
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
        # `--set X` is its own intent (set, not bump); for `--bump <axis>`
        # the axis names what happened.
        if version_mode.value == VersionOp.SET:
            message = "chore: set versions"
        else:
            message = _BUMP_MESSAGES[bump_type.value]
        body_lines = [f"  {n}: {v.raw}" for n, v in bump_versions.items.items()]
        commands.append(
            CommitCommand(
                label="Commit version bumps",
                message=message,
                body="\n".join(body_lines),
            )
        )

        if not no_push.value:
            commands.append(PushCommand(label="Push", follow_tags=True))

    return BumpJob(name="bump", commands=commands)

"""ReleaseBumpJob: post-release version bumps, dep pins, baseline tags, push."""

from __future__ import annotations

from diny import singleton, provider

from .release_bump_versions import ReleaseBumpVersions
from ...commands import (
    AnyCommand,
    CommitCommand,
    ConfigureGitIdentityCommand,
    CreateTagCommand,
    PinDepsCommand,
    PullRebaseCommand,
    PushCommand,
    SetVersionCommand,
    SyncLockfileCommand,
)
from .release_dependency_pins import ReleaseDependencyPins
from ...types.job import Job
from ..params.no_commit import NoCommit
from ..params.no_push import NoPush
from ..params.release_target import ReleaseTarget
from ..shared.workspace_packages import WorkspacePackages
from ...types.tag import Tag


@singleton
class ReleaseBumpJob(Job):
    """Post-release bump: set next versions, pin deps, tag baselines, push."""


@provider(ReleaseBumpJob)
def provide_release_bump_job(
    bump_versions: ReleaseBumpVersions,
    dependency_pins: ReleaseDependencyPins,
    workspace_packages: WorkspacePackages,
    release_target: ReleaseTarget,
    no_commit: NoCommit,
    no_push: NoPush,
) -> ReleaseBumpJob:
    if not bump_versions.items:
        return ReleaseBumpJob(name="bump")

    is_local = release_target.value == "local"

    commands: list[AnyCommand] = []

    if not is_local:
        commands.append(ConfigureGitIdentityCommand(label="Configure git identity"))
        # Pull --rebase BEFORE making bump commits and creating baseline tags.
        # If we rebased after tagging, the tags would point at orphaned commits
        # and `git push --follow-tags` would not push them. The release_job
        # already pushed the release commits and tags, so this rebases against
        # whatever state landed concurrently (usually a no-op).
        commands.append(PullRebaseCommand(label="Pull before bump"))

    for name, next_version in bump_versions.items.items():
        pkg = workspace_packages.items[name]
        commands.append(
            SetVersionCommand(
                label=f"Bump {name} to {next_version.raw}",
                package_name=pkg.name,
                package_path=pkg.path,
                version=next_version.raw,
            )
        )

    for pin in dependency_pins.items:
        commands.append(
            PinDepsCommand(
                label=f"Pin deps in {pin.package_path}",
                package_path=pin.package_path,
                pins=pin.pins,
            )
        )

    commands.append(SyncLockfileCommand(label="Sync lockfile"))

    skip_commit = is_local and no_commit.value
    skip_push = is_local and no_push.value

    if not skip_commit:
        body_lines = [f"  {n}: {v.raw}" for n, v in bump_versions.items.items()]
        commands.append(
            CommitCommand(
                label="Commit version bumps",
                message="chore: bump to next dev versions",
                body="\n".join(body_lines),
            )
        )

        for name, version in bump_versions.items.items():
            baseline_tag = Tag.baseline_tag_name(name, version)
            commands.append(
                CreateTagCommand(
                    label=f"Baseline {baseline_tag}", tag_name=baseline_tag
                )
            )

        if not skip_push:
            commands.append(PushCommand(label="Push", follow_tags=True))

    return ReleaseBumpJob(name="bump", commands=commands)

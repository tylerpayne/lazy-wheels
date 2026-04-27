"""BumpJob: version bumps, baseline tags, and push after release."""

from __future__ import annotations

from diny import provider
from pydantic import BaseModel, ConfigDict

from ...commands import CreateTagCommand, SetVersionCommand, ShellCommand
from ...types import Command, CommandGroup, Job, Tag
from ..shared.dep_pins import compute_dep_pins
from ..shared.packages import format_version_body
from .params import ReleaseParams
from .releases import Releases


class BumpJob(BaseModel):
    """Bump job: set next versions, pin deps, tag baselines, push."""

    model_config = ConfigDict(frozen=True)

    job: Job = Job(name="bump")


@provider(BumpJob)
def compute_bump_job(releases: Releases, params: ReleaseParams) -> BumpJob:
    """Compute the bump job, or return an empty job if skipped."""
    if "bump" in params.skip or not releases.items:
        return BumpJob()

    commands: list[Command] = []

    for name, release in releases.items.items():
        commands.append(
            SetVersionCommand(
                label=f"Bump {name} to {release.next_version.raw}",
                package=release.package,
                version=release.next_version,
            )
        )

    bumped_packages = {
        name: release.package.with_version(release.next_version)
        for name, release in releases.items.items()
    }
    commands.extend(
        compute_dep_pins(
            [release.package for release in releases.items.values()],
            bumped_packages,
        )
    )

    commands.append(
        ShellCommand(
            label="Sync lockfile",
            args=["uv", "sync", "--all-groups", "--all-extras", "--all-packages"],
            check=False,
        )
    )

    body = format_version_body(
        {name: release.next_version.raw for name, release in releases.items.items()}
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

    for name, release in releases.items.items():
        baseline_tag = Tag.baseline_tag_name(name, release.next_version)
        commands.append(
            CreateTagCommand(label=f"Baseline {baseline_tag}", tag_name=baseline_tag)
        )

    commands.append(
        ShellCommand(label="Pull before push", args=["git", "pull", "--rebase"])
    )
    commands.append(ShellCommand(label="Push", args=["git", "push", "--follow-tags"]))

    if params.target == "local":
        commands = [
            CommandGroup(
                label="Confirm bump commands",
                commands=commands,
                needs_user_confirmation=True,
            )
        ]

    return BumpJob(job=Job(name="bump", commands=commands))

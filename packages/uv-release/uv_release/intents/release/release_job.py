"""ReleaseJob: git tags and GitHub releases."""

from __future__ import annotations

from diny import provider
from pydantic import BaseModel, ConfigDict

from ...commands import CreateReleaseCommand, CreateTagCommand, ShellCommand
from ...types import Command, Job, Tag
from .download import DownloadCommands
from .params import ReleaseParams
from .releases import Releases


class ReleaseJob(BaseModel):
    """Release job: download artifacts, create tags, create GitHub releases."""

    model_config = ConfigDict(frozen=True)

    job: Job = Job(name="release")


@provider(ReleaseJob)
def compute_release_job(
    releases: Releases, download: DownloadCommands, params: ReleaseParams
) -> ReleaseJob:
    """Compute the release job, or return an empty job if skipped."""
    if "release" in params.skip or params.reuse_release or not releases.items:
        return ReleaseJob()

    commands: list[Command] = list(download.commands)

    for name, release in releases.items.items():
        tag_name = Tag.release_tag_name(name, release.release_version)
        commands.append(CreateTagCommand(label=f"Tag {tag_name}", tag_name=tag_name))

    commands.append(ShellCommand(label="Push tags", args=["git", "push", "--tags"]))

    non_latest = [(n, r) for n, r in releases.items.items() if not r.make_latest]
    latest = [(n, r) for n, r in releases.items.items() if r.make_latest]

    for _, release in non_latest + latest:
        commands.append(
            CreateReleaseCommand(
                label=f"Release {release.package.name} {release.release_version.raw}",
                release=release,
            )
        )

    return ReleaseJob(job=Job(name="release", commands=commands))

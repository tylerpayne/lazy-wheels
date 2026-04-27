"""PublishJob: publish wheels to a package index."""

from __future__ import annotations

from diny import provider
from pydantic import BaseModel, ConfigDict

from ...commands import PublishToIndexCommand
from ...states.uvr_state import UvrState
from ...types import Command, Job
from .download import DownloadCommands
from .params import ReleaseParams
from .releases import Releases


class PublishJob(BaseModel):
    """Publish job: download artifacts and publish to index."""

    model_config = ConfigDict(frozen=True)

    job: Job = Job(name="publish")


@provider(PublishJob)
def compute_publish_job(
    releases: Releases,
    uvr_state: UvrState,
    download: DownloadCommands,
    params: ReleaseParams,
) -> PublishJob:
    """Compute the publish job, or return an empty job if skipped."""
    if "publish" in params.skip or not uvr_state.publishing.index or not releases.items:
        return PublishJob()

    publishable = set(releases.items.keys())
    if uvr_state.publishing.include:
        publishable &= uvr_state.publishing.include
    publishable -= uvr_state.publishing.exclude

    if not publishable:
        return PublishJob()

    commands: list[Command] = list(download.commands)
    for name in sorted(publishable):
        release = releases.items[name]
        commands.append(
            PublishToIndexCommand(
                label=f"Publish {name} {release.release_version.raw}",
                release=release,
                publishing=uvr_state.publishing,
            )
        )

    return PublishJob(job=Job(name="publish", commands=commands))

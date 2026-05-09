"""PublishJob: download wheels from GitHub release, then publish to index."""

from __future__ import annotations

from diny import singleton, provider

from ...commands import (
    AnyCommand,
    DownloadWheelsCommand,
    MakeDirectoryCommand,
    PublishToIndexCommand,
)
from ...types.job import Job
from ...types.tag import Tag
from ..params.release_target import ReleaseTarget
from ..shared.github_repo import GitHubRepo
from .publish_packages import PublishPackages
from .release_versions import ReleaseVersions
from ..config.uvr_publishing import UvrPublishing


@singleton
class PublishJob(Job):
    """Publish job: download wheels from GitHub releases, push to index."""


@provider(PublishJob)
def provide_publish_job(
    publish_packages: PublishPackages,
    release_versions: ReleaseVersions,
    uvr_publishing: UvrPublishing,
    release_target: ReleaseTarget,
    github_repo: GitHubRepo,
) -> PublishJob:
    if not publish_packages.items:
        return PublishJob(name="publish")

    is_ci = release_target.value == "ci"

    commands: list[AnyCommand] = []

    # In CI, download wheels from the GitHub releases created by the release job.
    # Locally, wheels are already in dist/ from the build job.
    if is_ci:
        commands.append(MakeDirectoryCommand(label="Create dist/", path="dist"))
        for name in publish_packages.items:
            version = release_versions.items[name]
            tag_name = Tag.release_tag_name(name, version)
            commands.append(
                DownloadWheelsCommand(
                    label=f"Download {name} wheels",
                    tag_name=tag_name,
                    pattern="*.whl",
                    output_dir="dist",
                    repo=github_repo.name,
                )
            )

    for name, version in publish_packages.items.items():
        commands.append(
            PublishToIndexCommand(
                label=f"Publish {name} {version.raw}",
                package_name=name,
                index=uvr_publishing.index,
            )
        )

    return PublishJob(name="publish", commands=commands)

"""ReleaseJob: download build artifacts, create tags and GitHub releases."""

from __future__ import annotations

from diny import singleton, provider

from ..build.build_packages import BuildPackages
from ...commands import (
    AnyCommand,
    ConfigureGitIdentityCommand,
    CreateReleaseCommand,
    CreateTagCommand,
    DownloadRunArtifactsCommand,
    MakeDirectoryCommand,
    ShellCommand,
)
from ...types.job import Job
from .release_notes import ReleaseNotes
from ..params.release_target import ReleaseTarget
from ..params.reuse_releases import ReuseReleases
from ..params.skip_jobs import SkipJobs
from .release_versions import ReleaseVersions
from ...types.tag import Tag
from ..config.uvr_config import UvrConfig


@singleton
class ReleaseJob(Job):
    """Release job: download artifacts, tag, create GitHub releases with wheels."""


@provider(ReleaseJob)
def provide_release_job(
    build_packages: BuildPackages,
    release_versions: ReleaseVersions,
    release_notes: ReleaseNotes,
    uvr_config: UvrConfig,
    release_target: ReleaseTarget,
    reuse_releases: ReuseReleases,
    skip_jobs: SkipJobs,
) -> ReleaseJob:
    if not build_packages.items or "release" in skip_jobs.value or reuse_releases.value:
        return ReleaseJob(name="release")

    commands: list[AnyCommand] = []

    is_ci = release_target.value == "ci"

    # In CI, download build artifacts from the run that built them.
    # Locally, wheels are already in dist/ from the build job.
    if is_ci:
        commands.append(MakeDirectoryCommand(label="Create dist/", path="dist"))
        commands.append(DownloadRunArtifactsCommand(label="Download build artifacts"))

    commands.append(ConfigureGitIdentityCommand(label="Configure git identity"))

    for name in build_packages.items:
        version = release_versions.items[name]
        tag_name = Tag.release_tag_name(name, version)
        commands.append(CreateTagCommand(label=f"Tag {tag_name}", tag_name=tag_name))

    commands.append(ShellCommand(label="Push tags", args=["git", "push", "--tags"]))

    # Create latest_package last so GitHub marks it as "Latest".
    non_latest = [
        (n, v)
        for n, v in release_versions.items.items()
        if n != uvr_config.latest_package
    ]
    latest = [
        (n, v)
        for n, v in release_versions.items.items()
        if n == uvr_config.latest_package
    ]

    for name, version in non_latest + latest:
        tag_name = Tag.release_tag_name(name, version)
        notes = release_notes.items.get(name, "")
        dist_name = name.replace("-", "_")
        commands.append(
            CreateReleaseCommand(
                label=f"Release {name} {version.raw}",
                tag_name=tag_name,
                title=f"{name} {version.raw}",
                notes=notes,
                files=[f"dist/{dist_name}-*.whl"],
                make_latest=(name == uvr_config.latest_package),
            )
        )

    return ReleaseJob(name="release", commands=commands)

"""Generate the publish job: upload wheels to package index."""

from __future__ import annotations

from ..commands import PublishToIndexCommand
from ..types import Command, Job, Publishing, Release


def plan_publish_job(releases: dict[str, Release], publishing: Publishing) -> Job:
    """Generate the publish job filtered by publishing config."""
    if not releases or not publishing.index:
        return Job(name="publish")

    publishable = set(releases.keys())
    if publishing.include:
        publishable &= publishing.include
    publishable -= publishing.exclude

    if not publishable:
        return Job(name="publish")

    commands: list[Command] = []
    for name in sorted(publishable):
        release = releases[name]
        commands.append(
            PublishToIndexCommand(
                label=f"Publish {name} {release.release_version.raw}",
                release=release,
                publishing=publishing,
            )
        )

    return Job(name="publish", commands=commands)

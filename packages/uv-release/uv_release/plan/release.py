"""Generate the release job: git tag and GitHub release commands."""

from __future__ import annotations

from ..commands import CreateReleaseCommand, CreateTagCommand, ShellCommand
from ..types import Command, Job, Release, Tag


def plan_release_job(releases: dict[str, Release]) -> Job:
    """Generate the release job: git tag + GitHub release commands.

    Tags all packages first, pushes tags, then creates GitHub releases.
    The make_latest=True package is created last.
    """
    if not releases:
        return Job(name="release")

    commands: list[Command] = []

    for name, release in releases.items():
        tag_name = Tag.release_tag_name(name, release.release_version)
        commands.append(CreateTagCommand(label=f"Tag {tag_name}", tag_name=tag_name))

    commands.append(ShellCommand(label="Push tags", args=["git", "push", "--tags"]))

    non_latest = [(n, r) for n, r in releases.items() if not r.make_latest]
    latest = [(n, r) for n, r in releases.items() if r.make_latest]

    for _name, release in non_latest + latest:
        commands.append(
            CreateReleaseCommand(
                label=f"Release {release.package.name} {release.release_version.raw}",
                release=release,
            )
        )

    return Job(name="release", commands=commands)

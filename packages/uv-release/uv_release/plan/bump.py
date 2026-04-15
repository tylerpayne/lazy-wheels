"""Generate the bump job: version bumps, baseline tags, and push."""

from __future__ import annotations

from ..commands import CreateTagCommand, PinDepsCommand, SetVersionCommand, ShellCommand
from ..types import Command, CommandGroup, Job, PlanParams, Release, Tag, Version


def plan_bump_job(releases: dict[str, Release], *, params: PlanParams) -> Job:
    """Generate the bump job: version bumps + baseline tags + push."""
    if not releases:
        return Job(name="bump")

    commands: list[Command] = []

    # 1. Set all versions
    for name, release in releases.items():
        commands.append(
            SetVersionCommand(
                label=f"Bump {name} to {release.next_version.raw}",
                package=release.package,
                version=release.next_version,
            )
        )

    # 2. Pin internal deps
    if params.pin:
        pins: dict[str, Version] = {
            name: release.next_version for name, release in releases.items()
        }
        for name, release in releases.items():
            pkg_pins = {dep: pins[dep] for dep in release.package.deps if dep in pins}
            if pkg_pins:
                commands.append(
                    PinDepsCommand(
                        label=f"Pin deps for {name}",
                        package=release.package,
                        pins=pkg_pins,
                    )
                )

    commands.append(
        ShellCommand(
            label="Sync lockfile",
            args=["uv", "sync", "--all-groups", "--all-extras", "--all-packages"],
            check=False,
        )
    )

    if params.commit:
        body = "\n".join(
            f"{name} {release.next_version.raw}"
            for name, release in sorted(releases.items())
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

    if params.tag:
        for name, release in releases.items():
            baseline_tag = Tag.baseline_tag_name(name, release.next_version)
            commands.append(
                CreateTagCommand(
                    label=f"Baseline {baseline_tag}", tag_name=baseline_tag
                )
            )

    if params.push:
        commands.append(
            ShellCommand(label="Push", args=["git", "push", "--follow-tags"])
        )

    if params.target == "local":
        commands = [
            CommandGroup(
                label="Confirm bump commands",
                commands=commands,
                needs_user_confirmation=True,
            )
        ]

    return Job(name="bump", commands=commands)

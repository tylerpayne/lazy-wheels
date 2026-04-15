"""Generate the validate job: version-fix commands for dev packages."""

from __future__ import annotations

from ..commands import PinDepsCommand, SetVersionCommand, ShellCommand
from ..types import Command, CommandGroup, Job, PlanParams, Release, Version


def plan_validate_job(
    releases: dict[str, Release],
    params: PlanParams,
) -> Job:
    """Build the validate job, including version-fix commands when needed."""
    if params.dev_release:
        return Job(name="validate")

    commands = _build_version_fix_commands(releases, push=params.target == "ci")

    if params.target == "local" and commands:
        commands = [
            CommandGroup(
                label="Set release versions and commit",
                needs_user_confirmation=True,
                commands=commands,
            )
        ]

    return Job(name="validate", commands=commands)


def _build_version_fix_commands(
    releases: dict[str, Release],
    *,
    push: bool = False,
) -> list[Command]:
    """Build SetVersion + PinDeps + git commit commands for dev packages."""
    needs_fix = {
        name: release
        for name, release in releases.items()
        if release.package.version != release.release_version
    }
    if not needs_fix:
        return []

    commands: list[Command] = []

    # Set release version for each package that needs it
    pins: dict[str, Version] = {}
    for name, release in sorted(needs_fix.items()):
        commands.append(
            SetVersionCommand(
                label=f"Set {name} to {release.release_version.raw}",
                package=release.package,
                version=release.release_version,
            )
        )
        pins[name] = release.release_version

    # Pin internal deps
    if pins:
        for name, release in sorted(releases.items()):
            pkg_pins = {dep: pins[dep] for dep in release.package.deps if dep in pins}
            if pkg_pins:
                commands.append(
                    PinDepsCommand(
                        label=f"Pin deps for {name}",
                        package=release.package,
                        pins=pkg_pins,
                    )
                )

    # Commit
    body = "\n".join(
        f"{name} {release.release_version.raw}"
        for name, release in sorted(needs_fix.items())
    )
    commands.append(
        ShellCommand(
            label="Commit release versions",
            args=["git", "commit", "-am", "chore: set release versions", "-m", body],
        )
    )

    if push:
        commands.append(ShellCommand(label="Push", args=["git", "push"]))

    return commands

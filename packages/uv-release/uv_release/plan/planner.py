"""Orchestrator: parse -> detect -> plan. Single entry point for building a Plan."""

from __future__ import annotations

import sys

from ..commands import PinDepsCommand, SetVersionCommand, ShellCommand
from ..detect.detector import detect_changes
from ..parse.hooks import parse_hooks
from ..parse.workspace import parse_workspace
from ..types import (
    BumpType,
    Change,
    Command,
    CommandGroup,
    Config,
    Job,
    Plan,
    PlanParams,
    Release,
    Version,
    Workspace,
)
from .build import plan_build_job
from .bump import plan_bump_job
from .publish import plan_publish_job
from .release import plan_release_job
from .versioning import (
    compute_bumped_version,
    compute_next_version,
    compute_release_version,
)
from .workflow import create_workflow


def create_plan(params: PlanParams) -> Plan:
    """Orchestrate parse -> detect -> plan and return a frozen Plan."""
    from ..git import GitRepo

    repo = GitRepo()
    if repo.is_dirty():
        if params.require_clean_worktree:
            print(
                "ERROR: Working tree is not clean. Commit or stash changes first.",
                file=sys.stderr,
            )
            sys.exit(1)
        else:
            print("WARNING: Working tree is not clean.", file=sys.stderr)
    if repo.is_ahead_or_behind():
        if params.require_clean_worktree:
            print(
                "ERROR: Local HEAD differs from remote. Pull or push first.",
                file=sys.stderr,
            )
            sys.exit(1)
        else:
            print("WARNING: Local HEAD differs from remote.", file=sys.stderr)

    hooks = parse_hooks()

    # pre_plan hook runs before anything else
    if hooks:
        params = hooks.pre_plan(params)

    workspace = parse_workspace(params)
    changes = detect_changes(workspace, params)
    plan = _create_plan(workspace, changes, params)

    # post_plan hook can modify the final plan
    if hooks:
        plan = hooks.post_plan(plan)

    return plan


def _create_plan(
    workspace: Workspace,
    changes: list[Change],
    params: PlanParams,
) -> Plan:
    """Assemble a Plan from a workspace and its detected changes."""
    if not changes:
        return Plan(workspace=workspace)

    releases: dict[str, Release] = {}
    for change in changes:
        release = _create_release(change, params, workspace.config)
        releases[change.package.name] = release

    skip = params.skip

    # Version-fix commands for local target when version != release_version
    validate_job = _plan_validate_job(releases, params)

    build_job = (
        plan_build_job(workspace, releases)
        if "build" not in skip
        else Job(name="build")
    )
    release_job = (
        plan_release_job(releases) if "release" not in skip else Job(name="release")
    )
    publish_job = (
        plan_publish_job(releases, workspace.publishing)
        if "publish" not in skip
        else Job(name="publish")
    )
    bump_job = (
        plan_bump_job(releases, params=params)
        if "bump" not in skip
        else Job(name="bump")
    )

    workflow = create_workflow(
        validate_job=validate_job,
        build_job=build_job,
        release_job=release_job,
        publish_job=publish_job,
        bump_job=bump_job,
    )

    changes_dict = {c.package.name: c for c in changes}

    return Plan(
        workspace=workspace,
        changes=changes_dict,
        releases=releases,
        workflow=workflow,
        target=params.target,
    )


def _create_release(
    change: Change,
    params: PlanParams,
    config: Config,
) -> Release:
    """Create a frozen Release from a Change."""
    name = change.package.name

    release_version = compute_release_version(
        change.package.version,
        dev_release=params.dev_release,
    )

    if params.bump_type == BumpType.DEV:
        next_version = compute_next_version(
            change.package.version,
            dev_release=params.dev_release,
        )
    else:
        next_version = compute_bumped_version(
            change.package.version,
            params.bump_type,
        )

    notes = ""
    if params.release_notes and name in params.release_notes:
        notes = params.release_notes[name]
    else:
        notes = change.commit_log

    return Release(
        package=change.package,
        release_version=release_version,
        next_version=next_version,
        release_notes=notes,
        make_latest=(name == config.latest_package),
    )


def _plan_validate_job(
    releases: dict[str, Release],
    params: PlanParams,
) -> Job:
    """Build the validate job, including version-fix commands when needed."""
    if params.dev_release:
        return Job(name="validate")

    commands = _build_version_fix_commands(releases)

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

    return commands

"""ReleaseIntent: plan and execute a full release."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..commands import (
    CreateReleaseCommand,
    CreateTagCommand,
    PinDepsCommand,
    PublishToIndexCommand,
    SetVersionCommand,
    ShellCommand,
)
from ..states.changes import Changes
from ..states.release_tags import ReleaseTags
from ..states.uvr_state import UvrState
from ..states.workspace import Workspace
from ..states.worktree import Worktree
from ..types import (
    Change,
    Command,
    CommandGroup,
    Job,
    Package,
    Plan,
    Publishing,
    Release,
    Tag,
    UserRecoverableError,
    Version,
)
from .shared.jobs import compute_build_job, compute_download_commands
from .shared.versioning import (
    compute_next_version,
    compute_release_version,
)


class ReleaseIntent(BaseModel):
    """Intent to release changed packages."""

    model_config = ConfigDict(frozen=True)

    type: Literal["release"] = "release"
    dev_release: bool = False
    release_notes: dict[str, str] = Field(default_factory=dict)
    target: Literal["ci", "local"] = "local"
    skip: frozenset[str] = frozenset()
    reuse_run: str = ""
    reuse_release: bool = False

    def guard(self, *, worktree: Worktree, changes: Changes) -> None:
        """Check preconditions. Raises ValueError on failure."""
        if worktree.is_dirty:
            msg = "Working tree is not clean. Commit or stash changes first."
            raise ValueError(msg)
        if self.target == "ci" and worktree.is_ahead_or_behind:
            msg = "Local HEAD differs from remote. Pull or push first."
            raise ValueError(msg)

        if not self.dev_release:
            fix = _build_version_fix_group(changes, push=self.target == "ci")
            if fix is not None:
                raise UserRecoverableError(
                    "Some packages have dev versions that need to be set to stable.",
                    fix=fix,
                )

    def plan(
        self,
        *,
        workspace: Workspace,
        uvr_state: UvrState,
        changes: Changes,
        release_tags: ReleaseTags,
    ) -> Plan:
        """(state, intent) -> plan. Full release pipeline."""
        if not changes.items:
            return Plan()

        releases: dict[str, Release] = {}
        for change in changes.items:
            release = self._compute_release(change, uvr_state)
            releases[change.package.name] = release

        jobs: list[Job] = []
        skip = set(self.skip)

        if self.reuse_run:
            skip.add("build")
        if self.reuse_release:
            skip.add("release")

        # Validate job (version-fix is handled by guard, not the plan)
        jobs.append(Job(name="validate"))

        download = compute_download_commands(reuse_run=self.reuse_run)

        # Build job
        if "build" not in skip:
            jobs.append(
                compute_build_job(workspace, releases, release_tags, uvr_state.runners)
            )
        else:
            jobs.append(Job(name="build"))

        # Release job (download artifacts + tags + GitHub releases)
        if "release" not in skip:
            jobs.append(_compute_release_job(releases, download))
        else:
            jobs.append(Job(name="release"))

        # Publish job (download artifacts + publish to index)
        if "publish" not in skip and uvr_state.publishing.index:
            jobs.append(_compute_publish_job(releases, uvr_state.publishing, download))
        else:
            skip.add("publish")
            jobs.append(Job(name="publish"))

        # Bump job
        if "bump" not in skip:
            jobs.append(_compute_bump_job(releases, target=self.target))
        else:
            jobs.append(Job(name="bump"))

        # Collect unique runner sets for CI build matrix
        runner_sets: list[list[str]] = []
        for name in releases:
            pkg_runners = uvr_state.runners.get(name, [["ubuntu-latest"]])
            for runner in pkg_runners:
                if runner not in runner_sets:
                    runner_sets.append(runner)

        return Plan(
            build_matrix=runner_sets or [["ubuntu-latest"]],
            python_version=uvr_state.config.python_version,
            publish_environment=uvr_state.publishing.environment,
            skip=sorted(skip),
            reuse_run=self.reuse_run,
            reuse_release=self.reuse_release,
            jobs=jobs,
        )

    def _compute_release(self, change: Change, uvr_state: UvrState) -> Release:
        """Create a frozen Release from a Change."""
        name = change.package.name
        release_version = compute_release_version(
            change.package.version, dev_release=self.dev_release
        )
        if self.dev_release:
            next_version = compute_next_version(
                change.package.version, dev_release=True
            )
        else:
            next_version = compute_next_version(
                change.package.version, dev_release=False
            )

        notes = ""
        if self.release_notes and name in self.release_notes:
            notes = self.release_notes[name]
        else:
            notes = change.commit_log

        return Release(
            package=change.package,
            release_version=release_version,
            next_version=next_version,
            release_notes=notes,
            make_latest=(name == uvr_state.config.latest_package),
        )


# ---------------------------------------------------------------------------
# Job builders (private)
# ---------------------------------------------------------------------------


def _build_version_fix_group(
    changes: Changes,
    *,
    push: bool = False,
) -> CommandGroup | None:
    """Build a CommandGroup to fix dev versions for release.

    Returns None if no packages need fixing.
    """
    needs_fix: dict[str, tuple[Package, Version]] = {}
    for change in changes.items:
        release_version = compute_release_version(change.package.version)
        if change.package.version != release_version:
            needs_fix[change.package.name] = (change.package, release_version)

    if not needs_fix:
        return None

    commands: list[Command] = []
    pinned_packages: dict[str, Package] = {}
    for name, (pkg, version) in sorted(needs_fix.items()):
        commands.append(
            SetVersionCommand(
                label=f"Set {name} to {version.raw}",
                package=pkg,
                version=version,
            )
        )
        pinned_packages[name] = Package(
            name=pkg.name,
            path=pkg.path,
            version=version,
            dependencies=pkg.dependencies,
        )

    if pinned_packages:
        for change in changes.items:
            pkg_pins = {
                dep: pinned_packages[dep]
                for dep in change.package.dependencies
                if dep in pinned_packages
            }
            if pkg_pins:
                commands.append(
                    PinDepsCommand(
                        label=f"Pin deps for {change.package.name}",
                        package=change.package,
                        pins=pkg_pins,
                    )
                )

    body = "\n".join(
        f"{name} {version.raw}" for name, (_pkg, version) in sorted(needs_fix.items())
    )
    commands.append(
        ShellCommand(
            label="Commit release versions",
            args=["git", "commit", "-am", "chore: set release versions", "-m", body],
        )
    )

    if push:
        commands.append(ShellCommand(label="Push", args=["git", "push"]))

    return CommandGroup(
        label="Set release versions and commit",
        needs_user_confirmation=True,
        commands=commands,
    )


def _compute_release_job(releases: dict[str, Release], download: list[Command]) -> Job:
    """Generate download + git tag + GitHub release commands."""
    if not releases:
        return Job(name="release")

    commands: list[Command] = list(download)
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


def _compute_publish_job(
    releases: dict[str, Release], publishing: Publishing, download: list[Command]
) -> Job:
    """Generate download + publish commands filtered by publishing config."""
    if not releases or not publishing.index:
        return Job(name="publish")

    publishable = set(releases.keys())
    if publishing.include:
        publishable &= publishing.include
    publishable -= publishing.exclude

    if not publishable:
        return Job(name="publish")

    commands: list[Command] = list(download)
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


def _compute_bump_job(
    releases: dict[str, Release],
    *,
    target: str,
) -> Job:
    """Generate bump job: version bumps + baseline tags + push."""
    if not releases:
        return Job(name="bump")

    from ..commands import CreateTagCommand as TagCmd

    commands: list[Command] = []

    for name, release in releases.items():
        commands.append(
            SetVersionCommand(
                label=f"Bump {name} to {release.next_version.raw}",
                package=release.package,
                version=release.next_version,
            )
        )

    bumped_packages: dict[str, Package] = {
        name: Package(
            name=release.package.name,
            path=release.package.path,
            version=release.next_version,
            dependencies=release.package.dependencies,
        )
        for name, release in releases.items()
    }
    for name, release in releases.items():
        pkg_pins = {
            dep: bumped_packages[dep]
            for dep in release.package.dependencies
            if dep in bumped_packages
        }
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

    for name, release in releases.items():
        baseline_tag = Tag.baseline_tag_name(name, release.next_version)
        commands.append(TagCmd(label=f"Baseline {baseline_tag}", tag_name=baseline_tag))

    commands.append(
        ShellCommand(label="Pull before push", args=["git", "pull", "--rebase"])
    )
    commands.append(ShellCommand(label="Push", args=["git", "push", "--follow-tags"]))

    if target == "local":
        commands = [
            CommandGroup(
                label="Confirm bump commands",
                commands=commands,
                needs_user_confirmation=True,
            )
        ]

    return Job(name="bump", commands=commands)

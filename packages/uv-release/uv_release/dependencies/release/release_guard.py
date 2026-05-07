"""ReleaseGuard: precondition checks before release planning."""

from __future__ import annotations

from diny import singleton, provider

from ...types.base import Frozen
from ...types.job import Job
from ...types.tag import Tag
from ..build.build_packages import BuildPackages
from ..shared.git_repo import GitRepo
from ..shared.workflow_state import WorkflowState
from ..shared.workspace_packages import WorkspacePackages
from ..shared.worktree import Worktree
from ..params.release_target import ReleaseTarget
from .release_versions import ReleaseVersions
from .version_fix import StripDev


class UserRecoverableError(ValueError):
    """A guard failure that can be automatically fixed.

    Carries a Job with commands that resolve the issue. The CLI catches this,
    executes the fix (with user confirmation), then restarts the process so
    the DI container re-resolves everything from the now-corrected disk state.
    """

    def __init__(self, message: str, fix_job: Job) -> None:
        super().__init__(message)
        self.fix_job = fix_job


@singleton
class ReleaseGuard(Frozen):
    """Construction proves all release preconditions passed."""


@provider(ReleaseGuard)
def provide_release_guard(
    worktree: Worktree,
    release_target: ReleaseTarget,
    strip_dev: StripDev,
    workflow_state: WorkflowState,
    release_versions: ReleaseVersions,
    build_packages: BuildPackages,
    workspace_packages: WorkspacePackages,
    git_repo: GitRepo,
) -> ReleaseGuard:
    if not workflow_state.exists:
        raise ValueError(
            f"Workflow file not found at {workflow_state.file_path}. "
            "Run 'uvr workflow install' to create it."
        )
    if worktree.is_dirty:
        raise ValueError("Working tree is dirty. Commit or stash changes first.")
    if release_target.value == "ci" and worktree.is_ahead_or_behind:
        raise ValueError("Local HEAD differs from remote. Pull or push first.")
    # Reject if any release version already has a tag.
    already_tagged = [
        f"{name} ({Tag.release_tag_name(name, ver)})"
        for name, ver in release_versions.items.items()
        if git_repo.find_tag(Tag.release_tag_name(name, ver)) is not None
    ]
    if already_tagged:
        raise ValueError(
            "Release tags already exist for: "
            + ", ".join(already_tagged)
            + ". Bump versions before releasing."
        )
    # Strip .devN suffixes last because the fix itself commits.
    if strip_dev.job.commands:
        raise UserRecoverableError(
            "Dev versions need .devN stripped before release.",
            fix_job=strip_dev.job,
        )
    # Warn if any build target depends on a workspace package at a dev version
    # that is not being released in this same release. The released wheel will
    # carry the dep spec from pyproject.toml, and if no stable version of that
    # dep exists on PyPI, pip install will fail.
    releasing = set(build_packages.items.keys())
    warnings: list[str] = []
    for name in releasing:
        pkg = workspace_packages.items.get(name)
        if pkg is None:
            continue
        for dep in pkg.dep_names:
            if dep in releasing or dep not in workspace_packages.items:
                continue
            dep_pkg = workspace_packages.items[dep]
            if dep_pkg.version.is_dev:
                warnings.append(f"{name} depends on {dep} ({dep_pkg.version.raw})")
    if warnings:
        from ...ui.console import err_console

        err_console.print(
            "[uvr.changed]warning:[/] Build targets depend on unreleased dev versions:"
        )
        for w in warnings:
            err_console.print(f"  {w}")
        err_console.print("These deps may not be installable from PyPI.")
        err_console.print()
    return ReleaseGuard()

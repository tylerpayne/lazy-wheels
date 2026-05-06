"""uvr version: read, set, or bump package versions."""

from __future__ import annotations

from diny import inject

from ..dependencies.bump.bump_job import BumpJob
from ..dependencies.params.version_mode import VersionMode, VersionOp
from ..dependencies.shared.hooks import Hooks
from ..dependencies.shared.workspace_packages import WorkspacePackages
from ..execute import execute_job
from ._display import format_table


@inject
def cmd_version(
    workspace: WorkspacePackages,
    bump_job: BumpJob,
    version_mode: VersionMode,
    hooks: Hooks,
) -> None:
    # Read-only mode: no --set or --bump.
    if version_mode.value == VersionOp.READ:
        print()
        print("Packages")
        print("--------")
        headers = ("PACKAGE", "VERSION")
        rows = [
            (name, pkg.version.raw) for name, pkg in sorted(workspace.items.items())
        ]
        for line in format_table(headers, rows):
            print(line)
        print()
        return

    if not bump_job.commands:
        print("Nothing to update.")
        return

    execute_job(bump_job, hooks)

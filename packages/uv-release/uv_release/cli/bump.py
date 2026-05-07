"""uvr bump: bump package versions."""

from __future__ import annotations

from diny import inject

from .. import ui
from ..dependencies.bump.bump_job import BumpJob
from ..dependencies.shared.hooks import Hooks
from ..execute import execute_job


@inject
def cmd_bump(bump_job: BumpJob, hooks: Hooks) -> None:
    if not bump_job.commands:
        ui.console.print("Nothing to bump.")
        return

    execute_job(bump_job, hooks)

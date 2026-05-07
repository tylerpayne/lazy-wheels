"""uvr clean: remove build caches."""

from __future__ import annotations

from diny import inject

from .. import ui
from ..dependencies.clean.clean_job import CleanJob
from ..execute import execute_job


@inject
def cmd_clean(clean_job: CleanJob) -> None:
    if not clean_job.commands:
        ui.console.print("Nothing to clean.")
        return

    execute_job(clean_job)

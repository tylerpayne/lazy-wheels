"""uvr configure-runners: manage per-package CI runner configuration."""

from __future__ import annotations

from diny import inject

from .. import ui
from ..dependencies.config.uvr_runners import UvrRunners
from ..dependencies.configure.configure_runners_job import ConfigureRunnersJob
from ..execute import execute_job


@inject
def cmd_configure_runners(runners: UvrRunners, job: ConfigureRunnersJob) -> None:
    if not job.commands:
        if not runners.items:
            ui.console.print(
                "No runners configured. Default: [uvr.value]ubuntu-latest[/]"
            )
            return
        ui.section("Runners ([tool.uvr.runners])")
        for pkg, runner_list in sorted(runners.items.items()):
            for labels in runner_list:
                ui.console.print(f"  [uvr.accent]{pkg}[/]: [{', '.join(labels)}]")
        return

    execute_job(job)
    ui.hint("Updated runners.")

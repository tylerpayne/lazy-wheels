"""uvr configure: manage workspace configuration."""

from __future__ import annotations

from diny import inject

from .. import ui
from ..dependencies.config.uvr_config import UvrConfig
from ..dependencies.configure.configure_job import ConfigureJob
from ..execute import execute_job


@inject
def cmd_configure(config: UvrConfig, job: ConfigureJob) -> None:
    if not job.commands:
        ui.section("Configuration ([tool.uvr.config])")
        ui.kv(
            {
                "latest": config.latest_package or "[uvr.dim](not set)[/]",
                "python_version": config.python_version,
                "include": ", ".join(sorted(config.include)) or "[uvr.dim](all)[/]",
                "exclude": ", ".join(sorted(config.exclude)) or "[uvr.dim](none)[/]",
            }
        )
        return

    execute_job(job)
    ui.hint("Updated configuration.")

"""uvr configure-publish: manage publishing configuration."""

from __future__ import annotations

from diny import inject

from .. import ui
from ..dependencies.config.uvr_publishing import UvrPublishing
from ..dependencies.configure.configure_publish_job import ConfigurePublishJob
from ..execute import execute_job


@inject
def cmd_configure_publish(publishing: UvrPublishing, job: ConfigurePublishJob) -> None:
    if not job.commands:
        ui.section("Publishing configuration ([tool.uvr.publish])")
        ui.kv(
            {
                "index": publishing.index or "[uvr.dim](not set)[/]",
                "environment": publishing.environment or "[uvr.dim](not set)[/]",
                "trusted-publishing": str(publishing.trusted_publishing),
                "include": ", ".join(sorted(publishing.include)) or "[uvr.dim](all)[/]",
                "exclude": ", ".join(sorted(publishing.exclude))
                or "[uvr.dim](none)[/]",
            }
        )
        return

    execute_job(job)
    ui.hint("Updated publishing configuration.")

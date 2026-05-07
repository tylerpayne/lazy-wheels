"""uvr download: download wheels from a GitHub release or CI run."""

from __future__ import annotations

from diny import inject

from .. import ui
from ..dependencies.download.download_job import DownloadJob
from ..execute import execute_job


@inject
def cmd_download(download_job: DownloadJob) -> None:
    execute_job(download_job)
    ui.console.print()
    ui.hint("Done.")

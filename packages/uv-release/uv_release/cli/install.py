"""uvr install: install packages from wheels."""

from __future__ import annotations

from diny import inject

from .. import ui
from ..dependencies.install.install_job import InstallJob
from ..execute import execute_job


@inject
def cmd_install(install_job: InstallJob) -> None:
    execute_job(install_job)
    ui.console.print()
    ui.hint("Installed.")

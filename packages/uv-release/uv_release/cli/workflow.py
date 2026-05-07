"""uvr workflow: dispatch to validate or upgrade subcommands."""

from __future__ import annotations

import sys

from diny import inject

from .. import ui
from ..dependencies.params.workflow_params import WorkflowParams


@inject
def cmd_workflow(params: WorkflowParams) -> None:
    match params.subcommand:
        case "validate":
            from .workflow_validate import cmd_workflow_validate

            cmd_workflow_validate()
        case "install":
            from .workflow_upgrade import cmd_workflow_upgrade

            cmd_workflow_upgrade()
        case _:
            ui.error("Usage: uvr workflow {validate,install}")
            sys.exit(1)

"""uvr workflow upgrade: scaffold or upgrade the release workflow."""

from __future__ import annotations

import sys

from diny import inject

from .. import ui
from ..dependencies.params.workflow_params import WorkflowParams
from ..dependencies.shared.workflow_template import WorkflowTemplate
from ..dependencies.workflow.upgrade_job import WorkflowUpgradeJob
from ..execute import execute_job


@inject
def cmd_workflow_upgrade(
    params: WorkflowParams,
    template: WorkflowTemplate,
    upgrade_job: WorkflowUpgradeJob,
) -> None:
    # --print-template short-circuits all other logic. Used by --upgrade via
    # `uvx --with uv-release=={prev} ...` to fetch the base for three-way merge.
    # MUST stay byte-exact (no Rich), since the consumer parses raw YAML.
    if params.print_template:
        sys.stdout.write(template.content)
        return

    if not upgrade_job.commands:
        ui.console.print("Workflow is already up to date.")
        return

    execute_job(upgrade_job)

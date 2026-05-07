"""uvr workflow validate: check workflow against template."""

from __future__ import annotations

import difflib

import yaml
from diny import inject

from .. import ui
from ..dependencies.params.workflow_params import WorkflowParams
from ..dependencies.shared.workflow_state import WorkflowState
from ..dependencies.shared.workflow_template import WorkflowTemplate


@inject
def cmd_workflow_validate(
    params: WorkflowParams,
    state: WorkflowState,
    template: WorkflowTemplate,
) -> None:
    if not state.exists:
        ui.error(
            "Workflow file does not exist.",
            detail={"expected": state.file_path},
            fixes=["uvr workflow install"],
        )
        return

    errors: list[str] = []
    warnings: list[str] = []

    try:
        doc = yaml.safe_load(state.content)
    except yaml.YAMLError as e:
        ui.error(f"Invalid YAML in {state.file_path}: {e}")
        return

    if not isinstance(doc, dict):
        ui.error(f"{state.file_path} is not a valid workflow (expected mapping).")
        return

    jobs = doc.get("jobs", {})
    required_jobs = ["validate", "build", "release", "publish", "bump"]
    for job_name in required_jobs:
        if job_name not in jobs:
            errors.append(f"Required job {job_name!r} is missing.")

    if template.content and state.content.strip() != template.content.strip():
        warnings.append("Workflow differs from bundled template.")

    if errors:
        ui.section("Validation errors")
        for e in errors:
            ui.console.print(f"  [uvr.err]-[/] {e}")
    if warnings:
        ui.section("Warnings")
        for w in warnings:
            ui.console.print(f"  [uvr.changed]-[/] {w}")
    if not errors and not warnings:
        ui.console.print("[uvr.ok]✓[/] Workflow is valid.")

    if params.show_diff and template.content:
        diff = difflib.unified_diff(
            template.content.splitlines(keepends=True),
            state.content.splitlines(keepends=True),
            fromfile="template",
            tofile=state.file_path,
        )
        diff_text = "".join(diff)
        if diff_text:
            ui.console.print()
            ui.section("Diff from template")
            # Print the diff as raw text so colors/markup don't interfere.
            ui.console.print(diff_text)
        else:
            ui.console.print()
            ui.console.print("No diff from template.")

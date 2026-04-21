"""ValidateWorkflowIntent: check release.yml structure against template."""

from __future__ import annotations

from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

from ..states.workflow import WorkflowState
from ..states.workspace import Workspace
from ..types import Plan

_REQUIRED_JOBS = {"validate", "build", "release", "publish", "bump"}


class ValidateWorkflowIntent(BaseModel):
    """Intent to validate the release workflow. Read-only."""

    model_config = ConfigDict(frozen=True)

    type: Literal["validate_workflow"] = "validate_workflow"
    workflow_dir: str = ".github/workflows"
    show_diff: bool = False

    def guard(self, *, workspace: Workspace, workflow_state: WorkflowState) -> None:
        """Check that the workflow file exists."""
        if not workflow_state.file_exists:
            msg = (
                f"No workflow found at {self.workflow_dir}/release.yml. "
                f"Run `uvr workflow init` first."
            )
            raise ValueError(msg)

    def plan(self, *, workflow_state: WorkflowState) -> Plan:
        """(state, intent) -> plan. Read-only, returns validation results."""
        errors, warnings = _validate(workflow_state)
        return Plan(
            validation_errors=tuple(errors),
            validation_warnings=tuple(warnings),
        )


def _validate(workflow_state: WorkflowState) -> tuple[list[str], list[str]]:
    """Run validation checks. Returns (errors, warnings)."""
    existing = yaml.safe_load(workflow_state.file_content)

    errors: list[str] = []
    warnings: list[str] = []

    if existing and "jobs" in existing:
        job_names = set(existing["jobs"].keys())
        missing = _REQUIRED_JOBS - job_names
        for job in sorted(missing):
            errors.append(f"Required job '{job}' is missing")
    elif existing:
        errors.append("No 'jobs' section found in release.yml")

    has_diff = workflow_state.template.rstrip() != workflow_state.file_content.rstrip()
    if has_diff:
        warnings.append("Workflow differs from bundled template")

    return errors, warnings

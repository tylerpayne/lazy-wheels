"""Tests for ValidateWorkflowIntent: guard and plan."""

from __future__ import annotations

from pathlib import Path

import pytest

from uv_release.intents.validate_workflow import ValidateWorkflowIntent
from uv_release.states.workflow import WorkflowState
from uv_release.states.workspace import Workspace
from uv_release.types import Plan


def _workspace() -> Workspace:
    return Workspace(root=Path("."), packages={})


def _workflow_state(
    *,
    file_exists: bool = False,
    template: str = "name: release\n",
    file_content: str = "",
) -> WorkflowState:
    return WorkflowState(
        template=template,
        file_content=file_content,
        file_exists=file_exists,
    )


class TestValidateWorkflowIntent:
    def test_type_discriminator(self) -> None:
        assert ValidateWorkflowIntent().type == "validate_workflow"

    def test_guard_no_workflow_raises(self) -> None:
        intent = ValidateWorkflowIntent()
        wfs = _workflow_state(file_exists=False)
        with pytest.raises(ValueError, match="No workflow"):
            intent.guard(workspace=_workspace(), workflow_state=wfs)

    def test_guard_valid_workflow_passes(self) -> None:
        intent = ValidateWorkflowIntent()
        wfs = _workflow_state(file_exists=True, file_content="name: test\n")
        intent.guard(workspace=_workspace(), workflow_state=wfs)

    def test_plan_returns_plan(self) -> None:
        content = (
            "name: test\njobs:\n  validate: {}\n  build: {}\n"
            "  release: {}\n  publish: {}\n  bump: {}\n"
        )
        wfs = _workflow_state(file_exists=True, file_content=content)
        result = ValidateWorkflowIntent().plan(workflow_state=wfs)
        assert isinstance(result, Plan)
        assert result.jobs == []  # read-only, no commands

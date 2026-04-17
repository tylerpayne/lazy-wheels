"""Tests for ValidateWorkflowIntent: guard and plan."""

from __future__ import annotations

from pathlib import Path

import pytest

from uv_release.intents.validate_workflow import ValidateWorkflowIntent
from uv_release.types import Config, Plan, Publishing, Workspace


def _workspace() -> Workspace:
    return Workspace(
        packages={},
        config=Config(uvr_version="0.1.0"),
        runners={},
        publishing=Publishing(),
    )


class TestValidateWorkflowIntent:
    def test_type_discriminator(self) -> None:
        assert ValidateWorkflowIntent().type == "validate_workflow"

    def test_guard_no_workflow_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        intent = ValidateWorkflowIntent()
        with pytest.raises(ValueError, match="No workflow"):
            intent.guard(_workspace())

    def test_guard_valid_workflow_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        wf = tmp_path / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "release.yml").write_text("name: test\n")
        intent = ValidateWorkflowIntent()
        intent.guard(_workspace())

    def test_plan_returns_plan(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        wf = tmp_path / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "release.yml").write_text(
            "name: test\njobs:\n  validate: {}\n  build: {}\n  release: {}\n  publish: {}\n  bump: {}\n"
        )
        result = ValidateWorkflowIntent().plan(_workspace())
        assert isinstance(result, Plan)
        assert result.jobs == []  # read-only, no commands

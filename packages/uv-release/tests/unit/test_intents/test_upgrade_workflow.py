"""Tests for UpgradeWorkflowIntent: guard and plan."""

from __future__ import annotations

from pathlib import Path

import pytest

from uv_release.intents.upgrade_workflow import UpgradeWorkflowIntent
from uv_release.states.workflow import WorkflowState
from uv_release.types import (
    Plan,
)

from ..conftest import make_uvr_state, make_workspace


def _workflow_state(
    *,
    file_exists: bool = False,
    has_uncommitted: bool = False,
    template: str = "name: release\n",
    file_content: str = "",
    merge_base: str = "",
) -> WorkflowState:
    return WorkflowState(
        template=template,
        file_content=file_content,
        merge_base=merge_base,
        has_uncommitted=has_uncommitted,
        file_exists=file_exists,
    )


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestUpgradeWorkflowConstruction:
    def test_type_discriminator(self) -> None:
        intent = UpgradeWorkflowIntent()
        assert intent.type == "upgrade_workflow"

    def test_defaults(self) -> None:
        intent = UpgradeWorkflowIntent()
        assert intent.force is False
        assert intent.workflow_dir == ".github/workflows"

    def test_frozen(self) -> None:
        intent = UpgradeWorkflowIntent()
        with pytest.raises(Exception):
            intent.force = True


# ---------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------


class TestUpgradeWorkflowGuard:
    def test_valid_repo_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        (tmp_path / "pyproject.toml").write_text(
            '[tool.uv.workspace]\nmembers = ["packages/*"]\n'
        )
        ws = make_workspace()
        wfs = _workflow_state()
        intent = UpgradeWorkflowIntent(force=True)
        intent.guard(workspace=ws, workflow_state=wfs)  # should not raise


# ---------------------------------------------------------------------------
# Plan - init mode (force=True, no existing file)
# ---------------------------------------------------------------------------


class TestUpgradeWorkflowPlanInit:
    def test_returns_plan_with_job(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        (tmp_path / "pyproject.toml").write_text(
            '[tool.uv.workspace]\nmembers = ["packages/*"]\n'
        )
        uvr = make_uvr_state()
        wfs = _workflow_state()
        intent = UpgradeWorkflowIntent(force=True)
        result = intent.plan(
            workspace=make_workspace(), uvr_state=uvr, workflow_state=wfs
        )
        assert isinstance(result, Plan)
        assert len(result.jobs) == 1
        assert result.jobs[0].name == "upgrade_workflow"

    def test_job_has_commands(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        (tmp_path / "pyproject.toml").write_text(
            '[tool.uv.workspace]\nmembers = ["packages/*"]\n'
        )
        uvr = make_uvr_state()
        wfs = _workflow_state()
        intent = UpgradeWorkflowIntent(force=True)
        result = intent.plan(
            workspace=make_workspace(), uvr_state=uvr, workflow_state=wfs
        )
        assert len(result.jobs[0].commands) > 0


# ---------------------------------------------------------------------------
# Plan - upgrade mode (existing file)
# ---------------------------------------------------------------------------


class TestUpgradeWorkflowPlanUpgrade:
    def test_existing_file_without_force_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        (tmp_path / "pyproject.toml").write_text(
            '[tool.uv.workspace]\nmembers = ["packages/*"]\n'
        )
        dest = tmp_path / ".github" / "workflows"
        dest.mkdir(parents=True)
        (dest / "release.yml").write_text("existing content")
        ws = make_workspace()
        wfs = _workflow_state(file_exists=True)
        intent = UpgradeWorkflowIntent(force=False)
        with pytest.raises(ValueError, match="already exists"):
            intent.guard(workspace=ws, workflow_state=wfs)

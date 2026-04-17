"""Tests for UpgradeWorkflowIntent: guard and plan."""

from __future__ import annotations

from pathlib import Path

import pytest

from uv_release.intents.upgrade_workflow import UpgradeWorkflowIntent
from uv_release.types import (
    Config,
    Plan,
    Publishing,
    Workspace,
)


def _workspace() -> Workspace:
    return Workspace(
        packages={},
        config=Config(uvr_version="0.1.0"),
        runners={},
        publishing=Publishing(),
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
    def test_no_git_repo_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        ws = _workspace()
        intent = UpgradeWorkflowIntent(force=True)
        with pytest.raises(ValueError, match="Not a git repository"):
            intent.guard(ws)

    def test_no_pyproject_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        ws = _workspace()
        intent = UpgradeWorkflowIntent(force=True)
        with pytest.raises(ValueError, match="pyproject.toml"):
            intent.guard(ws)

    def test_valid_repo_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        (tmp_path / "pyproject.toml").write_text(
            '[tool.uv.workspace]\nmembers = ["packages/*"]\n'
        )
        ws = _workspace()
        intent = UpgradeWorkflowIntent(force=True)
        intent.guard(ws)  # should not raise


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
        ws = _workspace()
        intent = UpgradeWorkflowIntent(force=True)
        result = intent.plan(ws)
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
        ws = _workspace()
        intent = UpgradeWorkflowIntent(force=True)
        result = intent.plan(ws)
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
        ws = _workspace()
        intent = UpgradeWorkflowIntent(force=False)
        with pytest.raises(ValueError, match="already exists"):
            intent.guard(ws)

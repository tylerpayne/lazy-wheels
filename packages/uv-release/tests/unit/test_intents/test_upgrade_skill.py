"""Tests for UpgradeSkillIntent: guard and plan."""

from __future__ import annotations

from pathlib import Path

import pytest

from uv_release.intents.upgrade_skill import UpgradeSkillIntent
from uv_release.states.skill import SkillState
from uv_release.states.uvr_state import UvrState
from uv_release.states.workspace import Workspace
from uv_release.types import (
    Config,
    Plan,
    Publishing,
)


def _workspace() -> Workspace:
    return Workspace(root=Path("."), packages={})


def _uvr_state() -> UvrState:
    return UvrState(
        config=Config(uvr_version="0.1.0"),
        runners={},
        publishing=Publishing(),
        uvr_version="0.1.0",
    )


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestUpgradeSkillConstruction:
    def test_type_discriminator(self) -> None:
        intent = UpgradeSkillIntent()
        assert intent.type == "upgrade_skill"

    def test_defaults(self) -> None:
        intent = UpgradeSkillIntent()
        assert intent.force is False

    def test_frozen(self) -> None:
        intent = UpgradeSkillIntent()
        with pytest.raises(Exception):
            intent.force = True


# ---------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------


class TestUpgradeSkillGuard:
    def test_valid_repo_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        ws = _workspace()
        intent = UpgradeSkillIntent()
        intent.guard(workspace=ws)  # should not raise


# ---------------------------------------------------------------------------
# Plan - init mode
# ---------------------------------------------------------------------------


class TestUpgradeSkillPlanInit:
    def test_returns_plan(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        uvr = _uvr_state()
        skill = SkillState.parse()
        intent = UpgradeSkillIntent(force=True)
        result = intent.plan(workspace=_workspace(), uvr_state=uvr, skill_state=skill)
        assert isinstance(result, Plan)
        assert len(result.jobs) == 1
        assert result.jobs[0].name == "upgrade_skill"

    def test_job_has_commands(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        uvr = _uvr_state()
        skill = SkillState.parse()
        intent = UpgradeSkillIntent(force=True)
        result = intent.plan(workspace=_workspace(), uvr_state=uvr, skill_state=skill)
        assert len(result.jobs[0].commands) > 0

    def test_writes_skill_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Init mode writes all skill files to .claude/skills/."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        uvr = _uvr_state()
        skill = SkillState.parse()
        intent = UpgradeSkillIntent(force=True)
        plan = intent.plan(workspace=_workspace(), uvr_state=uvr, skill_state=skill)

        # Execute the commands
        for cmd in plan.jobs[0].commands:
            cmd.execute()

        skill_dir = tmp_path / ".claude" / "skills" / "release"
        assert skill_dir.exists()
        assert (skill_dir / "SKILL.md").exists()

"""Tests for UpgradeSkillIntent: guard and plan."""

from __future__ import annotations

from pathlib import Path

import pytest

from uv_release.intents.upgrade_skill import UpgradeSkillIntent
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
    def test_no_git_repo_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        ws = _workspace()
        intent = UpgradeSkillIntent()
        with pytest.raises(ValueError, match="Not a git repository"):
            intent.guard(ws)

    def test_valid_repo_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        ws = _workspace()
        intent = UpgradeSkillIntent()
        intent.guard(ws)  # should not raise


# ---------------------------------------------------------------------------
# Plan - init mode
# ---------------------------------------------------------------------------


class TestUpgradeSkillPlanInit:
    def test_returns_plan(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        ws = _workspace()
        intent = UpgradeSkillIntent(force=True)
        result = intent.plan(ws)
        assert isinstance(result, Plan)
        assert len(result.jobs) == 1
        assert result.jobs[0].name == "upgrade_skill"

    def test_job_has_commands(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        ws = _workspace()
        intent = UpgradeSkillIntent(force=True)
        result = intent.plan(ws)
        assert len(result.jobs[0].commands) > 0

    def test_writes_skill_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Init mode writes all skill files to .claude/skills/."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        ws = _workspace()
        intent = UpgradeSkillIntent(force=True)
        plan = intent.plan(ws)

        # Execute the commands
        for cmd in plan.jobs[0].commands:
            cmd.execute()

        skill_dir = tmp_path / ".claude" / "skills" / "release"
        assert skill_dir.exists()
        assert (skill_dir / "SKILL.md").exists()

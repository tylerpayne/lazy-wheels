"""Tests for ConfigureIntent: guard and plan."""

from __future__ import annotations

from pathlib import Path

import pytest

from uv_release.commands import UpdateTomlCommand
from uv_release.intents.configure import ConfigureIntent
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
# ConfigureIntent construction
# ---------------------------------------------------------------------------


class TestConfigureIntentConstruction:
    """ConfigureIntent is a frozen Pydantic model with correct defaults."""

    def test_type_discriminator(self) -> None:
        intent = ConfigureIntent()
        assert intent.type == "configure"

    def test_defaults(self) -> None:
        intent = ConfigureIntent()
        assert intent.updates == {}

    def test_frozen(self) -> None:
        intent = ConfigureIntent()
        with pytest.raises((AttributeError, Exception)):
            setattr(intent, "type", "other")


# ---------------------------------------------------------------------------
# ConfigureIntent.guard
# ---------------------------------------------------------------------------


class TestConfigureGuard:
    """guard validates preconditions for configure intent."""

    def test_pyproject_exists_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        ws = _workspace()
        intent = ConfigureIntent()
        intent.guard(workspace=ws)  # should not raise


# ---------------------------------------------------------------------------
# ConfigureIntent.plan
# ---------------------------------------------------------------------------


class TestConfigurePlan:
    """plan() produces UpdateTomlCommand for each key."""

    def test_plan_returns_plan(self) -> None:
        uvr = _uvr_state()
        intent = ConfigureIntent(updates={"latest": "my-pkg"})
        result = intent.plan(uvr_state=uvr)
        assert isinstance(result, Plan)

    def test_plan_produces_update_commands(self) -> None:
        uvr = _uvr_state()
        intent = ConfigureIntent(updates={"latest": "my-pkg", "python_version": "3.13"})
        result = intent.plan(uvr_state=uvr)
        job = result.jobs[0]
        assert job.name == "configure"
        update_cmds = [c for c in job.commands if isinstance(c, UpdateTomlCommand)]
        assert len(update_cmds) == 2

    def test_plan_commands_sorted_by_key(self) -> None:
        uvr = _uvr_state()
        intent = ConfigureIntent(updates={"z_key": "z_val", "a_key": "a_val"})
        result = intent.plan(uvr_state=uvr)
        job = result.jobs[0]
        update_cmds = [c for c in job.commands if isinstance(c, UpdateTomlCommand)]
        assert update_cmds[0].key == "a_key"
        assert update_cmds[1].key == "z_key"

    def test_plan_command_values(self) -> None:
        uvr = _uvr_state()
        intent = ConfigureIntent(updates={"latest": "my-pkg"})
        result = intent.plan(uvr_state=uvr)
        job = result.jobs[0]
        cmd = job.commands[0]
        assert isinstance(cmd, UpdateTomlCommand)
        assert cmd.key == "latest"
        assert cmd.value == "my-pkg"

    def test_empty_updates_produces_empty_plan(self) -> None:
        uvr = _uvr_state()
        intent = ConfigureIntent(updates={})
        result = intent.plan(uvr_state=uvr)
        assert result.jobs == []

"""Tests for CleanIntent: guard and plan."""

from __future__ import annotations

from pathlib import Path

import pytest

from uv_release.intents.clean import CleanIntent
from uv_release.states.workspace import Workspace
from uv_release.types import Plan


def _workspace() -> Workspace:
    return Workspace(root=Path("."), packages={})


class TestCleanIntent:
    def test_type_discriminator(self) -> None:
        assert CleanIntent().type == "clean"

    def test_guard_always_passes(self) -> None:
        CleanIntent().guard(workspace=_workspace())

    def test_plan_returns_plan(self) -> None:
        result = CleanIntent().plan(workspace=_workspace())
        assert isinstance(result, Plan)

    def test_plan_has_job(self) -> None:
        result = CleanIntent().plan(workspace=_workspace())
        assert len(result.jobs) == 1
        assert result.jobs[0].name == "clean"

    def test_removes_cache_dirs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        cache = tmp_path / ".uvr" / "cache"
        cache.mkdir(parents=True)
        (cache / "somefile").write_text("data")

        plan = CleanIntent().plan(workspace=_workspace())
        for cmd in plan.jobs[0].commands:
            cmd.execute()

        assert not cache.exists()

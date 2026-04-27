"""Tests for BuildIntent: guard and plan."""

from __future__ import annotations

import pytest

from uv_release.intents.build import BuildIntent
from uv_release.commands import BuildCommand, ShellCommand
from uv_release.states.changes import Changes
from uv_release.states.release_tags import ReleaseTags
from uv_release.types import (
    Plan,
)

from ..conftest import make_changes_for, make_package, make_uvr_state, make_workspace


# ---------------------------------------------------------------------------
# BuildIntent construction
# ---------------------------------------------------------------------------


class TestBuildIntentConstruction:
    """BuildIntent is a frozen Pydantic model with correct defaults."""

    def test_type_discriminator(self) -> None:
        intent = BuildIntent()
        assert intent.type == "build"

    def test_frozen(self) -> None:
        intent = BuildIntent()
        with pytest.raises(Exception):
            intent.type = "build"


# ---------------------------------------------------------------------------
# BuildIntent.plan
# ---------------------------------------------------------------------------


class TestBuildPlanWithChanges:
    """plan() detects changes and builds a build job."""

    def test_returns_plan(self) -> None:
        pkgs = {"a": make_package("a")}
        ws = make_workspace(pkgs)
        changes = make_changes_for(pkgs)
        intent = BuildIntent()
        result = intent.plan(
            workspace=ws,
            uvr_state=make_uvr_state(),
            changes=Changes(items=tuple(changes)),
            release_tags=ReleaseTags(),
        )
        assert isinstance(result, Plan)

    def test_has_build_job(self) -> None:
        pkgs = {"a": make_package("a")}
        ws = make_workspace(pkgs)
        changes = make_changes_for(pkgs)
        intent = BuildIntent()
        result = intent.plan(
            workspace=ws,
            uvr_state=make_uvr_state(),
            changes=Changes(items=tuple(changes)),
            release_tags=ReleaseTags(),
        )
        assert len(result.jobs) == 1
        assert result.jobs[0].name == "build"

    def test_build_job_has_build_command(self) -> None:
        pkgs = {"a": make_package("a")}
        ws = make_workspace(pkgs)
        changes = make_changes_for(pkgs)
        intent = BuildIntent()
        result = intent.plan(
            workspace=ws,
            uvr_state=make_uvr_state(),
            changes=Changes(items=tuple(changes)),
            release_tags=ReleaseTags(),
        )
        job = result.jobs[0]
        build_cmds = [c for c in job.commands if isinstance(c, BuildCommand)]
        assert len(build_cmds) == 1

    def test_two_packages_two_build_commands(self) -> None:
        pkgs = {"a": make_package("a"), "b": make_package("b")}
        ws = make_workspace(pkgs)
        changes = make_changes_for(pkgs)
        intent = BuildIntent()
        result = intent.plan(
            workspace=ws,
            uvr_state=make_uvr_state(),
            changes=Changes(items=tuple(changes)),
            release_tags=ReleaseTags(),
        )
        job = result.jobs[0]
        build_cmds = [c for c in job.commands if isinstance(c, BuildCommand)]
        assert len(build_cmds) == 2

    def test_has_mkdir_command(self) -> None:
        pkgs = {"a": make_package("a")}
        ws = make_workspace(pkgs)
        changes = make_changes_for(pkgs)
        intent = BuildIntent()
        result = intent.plan(
            workspace=ws,
            uvr_state=make_uvr_state(),
            changes=Changes(items=tuple(changes)),
            release_tags=ReleaseTags(),
        )
        job = result.jobs[0]
        shell_cmds = [c for c in job.commands if isinstance(c, ShellCommand)]
        mkdir_cmds = [c for c in shell_cmds if "mkdir" in c.args]
        assert len(mkdir_cmds) == 1


class TestBuildPlanNoChanges:
    """When no changes are detected, plan returns empty Plan."""

    def test_no_changes_empty_plan(self) -> None:
        ws = make_workspace({"a": make_package("a")})
        intent = BuildIntent()
        result = intent.plan(
            workspace=ws,
            uvr_state=make_uvr_state(),
            changes=Changes(),
            release_tags=ReleaseTags(),
        )
        assert result.jobs == []

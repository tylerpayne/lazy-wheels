"""Tests for BuildIntent: guard and plan."""

from __future__ import annotations

from pathlib import Path
import pytest

from uv_release.intents.build import BuildIntent
from uv_release.commands import BuildCommand, ShellCommand
from uv_release.states.changes import Changes
from uv_release.states.release_tags import ReleaseTags
from uv_release.states.uvr_state import UvrState
from uv_release.states.workspace import Workspace
from uv_release.types import (
    Change,
    Config,
    Package,
    Plan,
    Publishing,
    Tag,
    Version,
)


def _version(raw: str) -> Version:
    return Version.parse(raw)


def _package(
    name: str, version: str = "1.0.0.dev0", dependencies: list[str] | None = None
) -> Package:
    return Package(
        name=name,
        path=f"packages/{name}",
        version=_version(version),
        dependencies=dependencies or [],
    )


def _workspace(packages: dict[str, Package]) -> Workspace:
    return Workspace(root=Path("."), packages=packages)


def _uvr_state(
    *,
    runners: dict[str, list[list[str]]] | None = None,
) -> UvrState:
    return UvrState(
        config=Config(uvr_version="0.1.0"),
        runners=runners or {},
        publishing=Publishing(),
        uvr_version="0.1.0",
    )


def _changes_for(packages: dict[str, Package]) -> list[Change]:
    """Build a list of Changes for each package."""
    return [
        Change(
            package=pkg,
            baseline=Tag(
                package_name=name,
                raw=f"{name}/v{pkg.version.raw}-base",
                version=pkg.version,
                is_baseline=True,
                commit="abc123",
            ),
            reason="files changed",
        )
        for name, pkg in packages.items()
    ]


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
        pkgs = {"a": _package("a")}
        ws = _workspace(pkgs)
        changes = _changes_for(pkgs)
        intent = BuildIntent()
        result = intent.plan(
            workspace=ws,
            uvr_state=_uvr_state(),
            changes=Changes(items=tuple(changes)),
            release_tags=ReleaseTags(),
        )
        assert isinstance(result, Plan)

    def test_has_build_job(self) -> None:
        pkgs = {"a": _package("a")}
        ws = _workspace(pkgs)
        changes = _changes_for(pkgs)
        intent = BuildIntent()
        result = intent.plan(
            workspace=ws,
            uvr_state=_uvr_state(),
            changes=Changes(items=tuple(changes)),
            release_tags=ReleaseTags(),
        )
        assert len(result.jobs) == 1
        assert result.jobs[0].name == "build"

    def test_build_job_has_build_command(self) -> None:
        pkgs = {"a": _package("a")}
        ws = _workspace(pkgs)
        changes = _changes_for(pkgs)
        intent = BuildIntent()
        result = intent.plan(
            workspace=ws,
            uvr_state=_uvr_state(),
            changes=Changes(items=tuple(changes)),
            release_tags=ReleaseTags(),
        )
        job = result.jobs[0]
        build_cmds = [c for c in job.commands if isinstance(c, BuildCommand)]
        assert len(build_cmds) == 1

    def test_two_packages_two_build_commands(self) -> None:
        pkgs = {"a": _package("a"), "b": _package("b")}
        ws = _workspace(pkgs)
        changes = _changes_for(pkgs)
        intent = BuildIntent()
        result = intent.plan(
            workspace=ws,
            uvr_state=_uvr_state(),
            changes=Changes(items=tuple(changes)),
            release_tags=ReleaseTags(),
        )
        job = result.jobs[0]
        build_cmds = [c for c in job.commands if isinstance(c, BuildCommand)]
        assert len(build_cmds) == 2

    def test_has_mkdir_command(self) -> None:
        pkgs = {"a": _package("a")}
        ws = _workspace(pkgs)
        changes = _changes_for(pkgs)
        intent = BuildIntent()
        result = intent.plan(
            workspace=ws,
            uvr_state=_uvr_state(),
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
        ws = _workspace({"a": _package("a")})
        intent = BuildIntent()
        result = intent.plan(
            workspace=ws,
            uvr_state=_uvr_state(),
            changes=Changes(),
            release_tags=ReleaseTags(),
        )
        assert result.jobs == []

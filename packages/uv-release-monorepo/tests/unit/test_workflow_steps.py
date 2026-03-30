"""Tests for CI workflow subcommands (uvr jobs build, bump, release)."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch


from uv_release_monorepo.shared.models import (
    BuildStage,
    ChangedPackage,
    PackageInfo,
    ReleasePlan,
    ShellCommand,
)
from uv_release_monorepo.cli import cli

_SUBPROCESS_RUN = "uv_release_monorepo.shared.models.plan.subprocess.run"


def _make_plan_json(
    changed: list[str],
    unchanged: list[str],
    *,
    ci_publish: bool = False,
    build_commands: dict | None = None,
    bump_commands: list | None = None,
) -> str:
    """Helper to build a minimal ReleasePlan JSON string."""
    changed_pkgs = {
        name: ChangedPackage(
            path=f"packages/{name}",
            version="1.0.0",
            deps=[],
            current_version="1.0.0",
            release_version="1.0.0",
            next_version="1.0.1.dev0",
            runners=[["ubuntu-latest"]],
        )
        for name in changed
    }
    unchanged_pkgs = {
        name: PackageInfo(path=f"packages/{name}", version="1.0.0", deps=[])
        for name in unchanged
    }
    plan = ReleasePlan(
        uvr_version="0.3.0",
        rebuild_all=False,
        changed=changed_pkgs,
        unchanged=unchanged_pkgs,
        ci_publish=ci_publish,
        build_commands=build_commands or {},
        bump_commands=bump_commands or [],
    )
    return plan.model_dump_json()


@patch(_SUBPROCESS_RUN)
def test_build_runs_commands(mock_run: MagicMock) -> None:
    """uvr build runs the pre-computed build stages for a runner."""
    mock_run.return_value = MagicMock(returncode=0)
    plan_json = _make_plan_json(
        changed=["pkg-a"],
        unchanged=[],
        build_commands={
            ("ubuntu-latest",): [
                BuildStage(setup=[ShellCommand(args=["mkdir", "-p", "dist"])]),
                BuildStage(
                    packages={
                        "pkg-a": [
                            ShellCommand(
                                args=["uv", "build", "packages/pkg-a"],
                                label="Build pkg-a",
                            )
                        ]
                    }
                ),
            ],
        },
    )
    with patch.object(
        sys,
        "argv",
        ["uvr", "jobs", "build", "--plan", plan_json, "--runner", '["ubuntu-latest"]'],
    ):
        cli()
    assert mock_run.call_count == 2


@patch(_SUBPROCESS_RUN)
def test_bump_runs_commands(mock_run: MagicMock) -> None:
    """uvr jobs bump runs the pre-computed bump commands."""
    mock_run.return_value = MagicMock(returncode=0)
    plan_json = _make_plan_json(
        changed=["pkg-a"],
        unchanged=[],
        bump_commands=[
            ShellCommand(args=["git", "tag", "pkg-a/v1.0.0"]).model_dump(),
            ShellCommand(args=["git", "push"]).model_dump(),
        ],
    )
    with patch.object(sys, "argv", ["uvr", "jobs", "bump", "--plan", plan_json]):
        cli()
    assert mock_run.call_count == 2


@patch(_SUBPROCESS_RUN)
def test_build_no_commands_for_runner(mock_run: MagicMock) -> None:
    """uvr build is a no-op when no commands exist for the runner."""
    plan_json = _make_plan_json(changed=["pkg-a"], unchanged=[])
    with patch.object(
        sys,
        "argv",
        ["uvr", "jobs", "build", "--plan", plan_json, "--runner", '["macos-latest"]'],
    ):
        cli()
    mock_run.assert_not_called()


@patch("uv_release_monorepo.shared.utils.dependencies.pin_dependencies")
def test_pin_deps_command_calls_pin_dependencies(mock_pd: MagicMock) -> None:
    """PinDepsCommand.execute() calls pin_dependencies directly."""
    from pathlib import Path

    from uv_release_monorepo.shared.models import PinDepsCommand

    cmd = PinDepsCommand(
        path="foo/pyproject.toml",
        versions={"alpha": "1.0", "beta": "2.0"},
    )
    result = cmd.execute()
    assert result.returncode == 0
    mock_pd.assert_called_once_with(
        Path("foo/pyproject.toml"), {"alpha": "1.0", "beta": "2.0"}
    )

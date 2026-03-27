"""Tests for CI workflow subcommands (uvr build, finalize, set-version, pin-deps)."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch


from uv_release_monorepo.shared.models import (
    MatrixEntry,
    PackageInfo,
    PlanCommand,
    ReleasePlan,
)
from uv_release_monorepo.cli import cli


def _make_plan_json(
    changed: list[str],
    unchanged: list[str],
    *,
    ci_publish: bool = False,
    build_commands: dict | None = None,
    finalize_commands: list | None = None,
) -> str:
    """Helper to build a minimal ReleasePlan JSON string."""
    all_pkgs = changed + unchanged
    packages = {
        name: PackageInfo(path=f"packages/{name}", version="1.0.0", deps=[])
        for name in all_pkgs
    }
    plan = ReleasePlan(
        uvr_version="0.3.0",
        rebuild_all=False,
        changed={name: packages[name] for name in changed},
        unchanged={name: packages[name] for name in unchanged},
        release_tags={name: None for name in all_pkgs},
        matrix=[
            MatrixEntry(
                package=name,
                runner=["ubuntu-latest"],
                path=f"packages/{name}",
                version="1.0.0",
            )
            for name in changed
        ],
        ci_publish=ci_publish,
        build_commands=build_commands or {},
        finalize_commands=finalize_commands or [],
    )
    return plan.model_dump_json()


@patch("uv_release_monorepo.shared.execute.subprocess.run")
def test_build_runs_commands(mock_run: MagicMock) -> None:
    """uvr build runs the pre-computed build commands for a runner."""
    mock_run.return_value = MagicMock(returncode=0)
    plan_json = _make_plan_json(
        changed=["pkg-a"],
        unchanged=[],
        build_commands={
            '["ubuntu-latest"]': [
                PlanCommand(args=["mkdir", "-p", "dist"]).model_dump(),
                PlanCommand(
                    args=["uv", "build", "packages/pkg-a"], label="Build pkg-a"
                ).model_dump(),
            ],
        },
    )
    with patch.object(
        sys,
        "argv",
        ["uvr", "build", "--plan", plan_json, "--runner", "ubuntu-latest"],
    ):
        cli()
    assert mock_run.call_count == 2


@patch("uv_release_monorepo.shared.execute.subprocess.run")
def test_finalize_runs_commands(mock_run: MagicMock) -> None:
    """uvr finalize runs the pre-computed finalize commands."""
    mock_run.return_value = MagicMock(returncode=0)
    plan_json = _make_plan_json(
        changed=["pkg-a"],
        unchanged=[],
        finalize_commands=[
            PlanCommand(args=["git", "tag", "pkg-a/v1.0.0"]).model_dump(),
            PlanCommand(args=["git", "push"]).model_dump(),
        ],
    )
    with patch.object(sys, "argv", ["uvr", "finalize", "--plan", plan_json]):
        cli()
    assert mock_run.call_count == 2


@patch("uv_release_monorepo.shared.execute.subprocess.run")
def test_build_no_commands_for_runner(mock_run: MagicMock) -> None:
    """uvr build is a no-op when no commands exist for the runner."""
    plan_json = _make_plan_json(changed=["pkg-a"], unchanged=[])
    with patch.object(
        sys,
        "argv",
        ["uvr", "build", "--plan", plan_json, "--runner", "macos-latest"],
    ):
        cli()
    mock_run.assert_not_called()


@patch("uv_release_monorepo.shared.deps.set_version")
def test_set_version_writes(mock_sv: MagicMock) -> None:
    """uvr set-version calls set_version."""
    with patch.object(
        sys,
        "argv",
        ["uvr", "set-version", "--path", "foo/pyproject.toml", "--version", "1.2.3"],
    ):
        cli()
    mock_sv.assert_called_once()


@patch("uv_release_monorepo.shared.deps.pin_dependencies")
def test_pin_deps_writes(mock_pd: MagicMock) -> None:
    """uvr pin-deps calls pin_dependencies."""
    with patch.object(
        sys,
        "argv",
        [
            "uvr",
            "pin-deps",
            "--path",
            "foo/pyproject.toml",
            "alpha>=1.0",
            "beta>=2.0",
        ],
    ):
        cli()
    mock_pd.assert_called_once()
    versions = mock_pd.call_args[0][1]
    assert versions == {"alpha": "1.0", "beta": "2.0"}

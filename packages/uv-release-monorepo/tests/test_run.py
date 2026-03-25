"""Tests for the run command."""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

from uv_release_monorepo.cli import cmd_run

from tests._helpers import _make_plan


@patch("uv_release_monorepo.cli.run_pipeline")
def test_run_command_uses_workflow_steps_runner(mock_run_pipeline: MagicMock) -> None:
    """run command dispatches through workflow_steps.run_pipeline."""
    args = argparse.Namespace(rebuild_all=True, no_push=False, dry_run=False, plan=None)
    cmd_run(args)

    mock_run_pipeline.assert_called_once_with(
        rebuild_all=True, push=True, dry_run=False
    )


@patch("uv_release_monorepo.cli.run_pipeline")
def test_run_command_no_push_flag(mock_run_pipeline: MagicMock) -> None:
    """run command passes push=False when --no-push is set."""
    args = argparse.Namespace(rebuild_all=False, no_push=True, dry_run=False, plan=None)
    cmd_run(args)

    mock_run_pipeline.assert_called_once_with(
        rebuild_all=False, push=False, dry_run=False
    )


@patch("uv_release_monorepo.cli.run_pipeline")
def test_run_command_dry_run_flag(mock_run_pipeline: MagicMock) -> None:
    """run command passes dry_run=True when --dry-run is set."""
    args = argparse.Namespace(rebuild_all=False, no_push=False, dry_run=True, plan=None)
    cmd_run(args)

    mock_run_pipeline.assert_called_once_with(
        rebuild_all=False, push=True, dry_run=True
    )


@patch("uv_release_monorepo.cli.execute_plan")
def test_run_with_plan_calls_execute_plan(
    mock_execute_plan: MagicMock,
) -> None:
    """cmd_run --plan calls execute_plan with the parsed plan."""
    plan = _make_plan(changed=["pkg-alpha"])
    plan_json = plan.model_dump_json()

    args = argparse.Namespace(
        plan=plan_json, no_push=False, rebuild_all=False, dry_run=False
    )
    cmd_run(args)

    mock_execute_plan.assert_called_once()
    (called_plan,) = mock_execute_plan.call_args[0]
    assert called_plan.changed == plan.changed

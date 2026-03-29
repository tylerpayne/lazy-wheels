"""Tests for the unified release command (--where local, --plan)."""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

from uv_release_monorepo.cli import cmd_release

from tests._helpers import _make_plan


@patch("uv_release_monorepo.cli.ReleaseExecutor")
def test_release_with_plan_calls_executor(mock_executor_cls: MagicMock) -> None:
    """cmd_release --plan creates a ReleaseExecutor and calls .run()."""
    plan = _make_plan(changed=["pkg-alpha"])
    plan_json = plan.model_dump_json()

    args = argparse.Namespace(
        plan=plan_json,
        where="local",
        rebuild_all=False,
        dry_run=False,
        no_push=False,
        yes=False,
        python_version="3.12",
        workflow_dir=".github/workflows",
        skip=None,
        skip_to=None,
        reuse_run=None,
        reuse_release=False,
        json=False,
    )
    cmd_release(args)

    mock_executor_cls.assert_called_once()
    called_plan = mock_executor_cls.call_args[0][0]
    assert called_plan.changed == plan.changed
    mock_executor_cls.return_value.run.assert_called_once()

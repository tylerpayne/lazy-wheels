"""Tests for the release command."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from uv_release_monorepo.cli import cmd_release

from tests._helpers import _make_plan, _write_workspace_repo


def _release_args(**overrides: object) -> argparse.Namespace:
    """Create default release command args."""
    defaults: dict[str, object] = dict(
        where="ci",
        rebuild_all=False,
        yes=False,
        dry_run=False,
        no_push=False,
        plan=None,
        workflow_dir=".github/workflows",
        python_version="3.12",
        skip=None,
        skip_to=None,
        reuse_run=None,
        reuse_release=False,
        json=False,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


class TestCmdRelease:
    """Tests for cmd_release()."""

    @patch("uv_release_monorepo.cli.ReleasePlanner")
    def test_release_exits_early_when_nothing_changed(
        self,
        mock_planner_cls: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """cmd_release exits early if plan has no changed packages."""
        _write_workspace_repo(tmp_path, ["pkg-alpha"])
        monkeypatch.chdir(tmp_path)

        from uv_release_monorepo.cli import cmd_init

        cmd_init(argparse.Namespace(workflow_dir=".github/workflows"))

        mock_planner_cls.return_value.plan.return_value = _make_plan(
            changed=[], unchanged=["pkg-alpha"]
        )

        cmd_release(_release_args())

        output = capsys.readouterr().out
        assert "Nothing changed" in output

    @patch("uv_release_monorepo.cli.ReleasePlanner")
    def test_release_prints_human_summary(
        self,
        mock_planner_cls: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """cmd_release prints a human-readable summary."""
        _write_workspace_repo(tmp_path, ["pkg-alpha"])
        monkeypatch.chdir(tmp_path)

        from uv_release_monorepo.cli import cmd_init

        cmd_init(argparse.Namespace(workflow_dir=".github/workflows"))

        plan = _make_plan(changed=["pkg-alpha"])
        mock_planner_cls.return_value.plan.return_value = plan

        cmd_release(_release_args(dry_run=True))

        output = capsys.readouterr().out
        assert "Packages" in output
        assert "pkg-alpha" in output
        assert "Pipeline" in output
        assert "changed" in output

    @patch("subprocess.run")
    @patch("uv_release_monorepo.cli.ReleasePlanner")
    def test_release_dispatches_with_yes_flag(
        self,
        mock_planner_cls: MagicMock,
        mock_subprocess_run: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """cmd_release --yes dispatches via gh without prompting."""
        _write_workspace_repo(tmp_path, ["pkg-alpha"])
        monkeypatch.chdir(tmp_path)

        from uv_release_monorepo.cli import cmd_init

        cmd_init(argparse.Namespace(workflow_dir=".github/workflows"))

        plan = _make_plan(changed=["pkg-alpha"])
        mock_planner_cls.return_value.plan.return_value = plan

        def _fake_run(cmd, **kwargs):
            if cmd[0] == "git" and "branch" in cmd:
                return MagicMock(returncode=0, stdout="main\n")
            if cmd[0] == "git":
                return MagicMock(returncode=0, stdout="")
            return MagicMock(returncode=0, stdout="[]")

        mock_subprocess_run.side_effect = _fake_run

        cmd_release(_release_args(yes=True))

        calls = [c for c in mock_subprocess_run.call_args_list]
        # Find the gh workflow run call
        trigger_call = None
        for c in calls:
            args = c[0][0]
            if args[0] == "gh" and "workflow" in args:
                trigger_call = args
                break
        assert trigger_call is not None
        joined = " ".join(str(a) for a in trigger_call)
        assert "--ref" in joined
        assert "plan=" in joined

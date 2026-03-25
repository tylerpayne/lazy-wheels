"""Tests for the release command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from uv_release_monorepo.cli import cmd_release

from tests._helpers import _make_plan, _write_workspace_repo


class TestCmdRelease:
    """Tests for cmd_release()."""

    @patch("uv_release_monorepo.cli.build_plan")
    def test_release_exits_early_when_nothing_changed(
        self,
        mock_build_plan: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """cmd_release exits early if plan has no changed packages."""
        _write_workspace_repo(tmp_path, ["pkg-alpha"])
        monkeypatch.chdir(tmp_path)

        # Create the workflow file so cmd_release doesn't fail on missing workflow
        from uv_release_monorepo.cli import cmd_init

        cmd_init(argparse.Namespace(workflow_dir=".github/workflows"))

        mock_build_plan.return_value = (
            _make_plan(changed=[], unchanged=["pkg-alpha"]),
            [],
        )

        args = argparse.Namespace(
            rebuild_all=False,
            yes=False,
            workflow_dir=".github/workflows",
            python_version="3.12",
            skip=None,
            skip_to=None,
            reuse_run=None,
            reuse_release=False,
        )
        cmd_release(args)

        output = capsys.readouterr().out
        assert "Nothing changed" in output

    @patch("uv_release_monorepo.cli.build_plan")
    def test_release_prints_plan_json(
        self,
        mock_build_plan: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """cmd_release prints the plan as JSON and prompts before dispatching."""
        _write_workspace_repo(tmp_path, ["pkg-alpha"])
        monkeypatch.chdir(tmp_path)

        from uv_release_monorepo.cli import cmd_init

        cmd_init(argparse.Namespace(workflow_dir=".github/workflows"))

        plan = _make_plan(changed=["pkg-alpha"])
        mock_build_plan.return_value = plan, []

        # Simulate user declining the prompt
        monkeypatch.setattr("builtins.input", lambda _: "n")

        args = argparse.Namespace(
            rebuild_all=False,
            yes=False,
            workflow_dir=".github/workflows",
            python_version="3.12",
            skip=None,
            skip_to=None,
            reuse_run=None,
            reuse_release=False,
        )
        cmd_release(args)

        output = capsys.readouterr().out
        # Extract just the JSON block (starts at the first '{')
        json_part = output[output.index("{") :]
        parsed = json.loads(json_part)
        assert "changed" in parsed
        assert "pkg-alpha" in parsed["changed"]

    @patch("subprocess.run")
    @patch("uv_release_monorepo.cli.build_plan")
    def test_release_dispatches_with_yes_flag(
        self,
        mock_build_plan: MagicMock,
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
        mock_build_plan.return_value = plan, []

        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="[]")

        args = argparse.Namespace(
            rebuild_all=False,
            yes=True,
            workflow_dir=".github/workflows",
            python_version="3.12",
            skip=None,
            skip_to=None,
            reuse_run=None,
            reuse_release=False,
        )
        cmd_release(args)

        # Verify gh workflow run was called with -f plan=...
        calls = [c for c in mock_subprocess_run.call_args_list]
        trigger_call = calls[0][0][0]  # first positional arg of first call
        assert "gh" in trigger_call
        assert "workflow" in trigger_call
        assert "run" in trigger_call
        # Find -f plan= argument
        joined = " ".join(str(a) for a in trigger_call)
        assert "plan=" in joined

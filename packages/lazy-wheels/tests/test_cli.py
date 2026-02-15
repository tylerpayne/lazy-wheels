"""Tests for lazy_wheels.cli."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lazy_wheels.cli import cli, cmd_init, cmd_run


def _write_workspace_repo(root: Path, package_names: list[str]) -> None:
    (root / ".git").mkdir()
    (root / "pyproject.toml").write_text(
        '[tool.uv.workspace]\nmembers = ["packages/*"]\n'
    )
    for package_name in package_names:
        package_dir = root / "packages" / package_name
        package_dir.mkdir(parents=True)
        (package_dir / "pyproject.toml").write_text(
            f'[project]\nname = "{package_name}"\nversion = "1.0.0"\n'
        )


class TestInit:
    """Tests for init command."""

    def test_writes_default_release_workflow(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """init writes the default workflow template."""
        _write_workspace_repo(tmp_path, [])
        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(
            workflow_dir=".github/workflows",
            matrix=None,
        )
        cmd_init(args)

        workflow = tmp_path / ".github" / "workflows" / "release.yml"
        assert workflow.exists()
        assert "jobs:\n  release:" in workflow.read_text()

    def test_matrix_writes_split_jobs_workflow(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """init with matrix args creates matrix workflow with specified runners."""
        _write_workspace_repo(tmp_path, ["pkg-alpha", "pkg-beta"])
        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(
            workflow_dir=".github/workflows",
            matrix=[
                ["pkg-alpha", "ubuntu-latest"],
                ["pkg-beta", "ubuntu-latest", "ubuntu-24.04-arm"],
            ],
        )
        cmd_init(args)

        workflow = (tmp_path / ".github" / "workflows" / "release.yml").read_text()
        assert "jobs:\n  discover:" in workflow
        assert (
            "outputs:\n      changed: ${{ steps.discover.outputs.changed }}" in workflow
        )
        assert '- package: "pkg-beta"' in workflow
        assert 'runner: "ubuntu-24.04-arm"' in workflow


@patch("lazy_wheels.cli.run_pipeline")
def test_run_command_uses_workflow_steps_runner(mock_run_pipeline: MagicMock) -> None:
    """run command dispatches through workflow_steps.run_pipeline."""
    args = argparse.Namespace(release="r9", force_all=True)
    cmd_run(args)

    mock_run_pipeline.assert_called_once_with(release="r9", force_all=True)


def test_cli_parses_matrix_args() -> None:
    """CLI correctly parses -m arguments with nargs='+'."""
    with patch.object(
        sys,
        "argv",
        [
            "lazy-wheels",
            "init",
            "-m",
            "pkg-alpha",
            "ubuntu-latest",
            "-m",
            "pkg-beta",
            "ubuntu-latest",
            "macos-14",
        ],
    ):
        with patch("lazy_wheels.cli.cmd_init") as mock_init:
            cli()
            args = mock_init.call_args[0][0]
            assert args.matrix == [
                ["pkg-alpha", "ubuntu-latest"],
                ["pkg-beta", "ubuntu-latest", "macos-14"],
            ]

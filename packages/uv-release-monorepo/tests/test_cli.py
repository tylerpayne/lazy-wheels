"""Tests for uv_release_monorepo.cli."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from uv_release_monorepo.cli import (
    __version__,
    _discover_packages,
    _parse_existing_matrix,
    cli,
    cmd_init,
    cmd_release,
    cmd_run,
    cmd_status,
)


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


@patch("uv_release_monorepo.cli.run_pipeline")
def test_run_command_uses_workflow_steps_runner(mock_run_pipeline: MagicMock) -> None:
    """run command dispatches through workflow_steps.run_pipeline."""
    args = argparse.Namespace(
        release="r9", force_all=True, no_push=False, dry_run=False
    )
    cmd_run(args)

    mock_run_pipeline.assert_called_once_with(
        release="r9", force_all=True, push=True, dry_run=False
    )


@patch("uv_release_monorepo.cli.run_pipeline")
def test_run_command_no_push_flag(mock_run_pipeline: MagicMock) -> None:
    """run command passes push=False when --no-push is set."""
    args = argparse.Namespace(
        release=None, force_all=False, no_push=True, dry_run=False
    )
    cmd_run(args)

    mock_run_pipeline.assert_called_once_with(
        release=None, force_all=False, push=False, dry_run=False
    )


@patch("uv_release_monorepo.cli.run_pipeline")
def test_run_command_dry_run_flag(mock_run_pipeline: MagicMock) -> None:
    """run command passes dry_run=True when --dry-run is set."""
    args = argparse.Namespace(
        release=None, force_all=False, no_push=False, dry_run=True
    )
    cmd_run(args)

    mock_run_pipeline.assert_called_once_with(
        release=None, force_all=False, push=True, dry_run=True
    )


def test_cli_dry_run_is_valid_arg() -> None:
    """--dry-run is a recognized argument for the run subcommand."""
    with patch.object(sys, "argv", ["uvr", "run", "--dry-run"]):
        with patch("uv_release_monorepo.cli.cmd_run") as mock_run:
            cli()
            args = mock_run.call_args[0][0]
            assert args.dry_run is True


def test_init_workflow_has_uvr_version_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Generated workflow has uvr_version input (no baked-in version)."""
    _write_workspace_repo(tmp_path, [])
    monkeypatch.chdir(tmp_path)

    args = argparse.Namespace(workflow_dir=".github/workflows", matrix=None)
    cmd_init(args)

    workflow = (tmp_path / ".github" / "workflows" / "release.yml").read_text()
    assert "uvr_version" in workflow
    assert "uv-release-monorepo=={0}" in workflow
    assert "__UVR_VERSION__" not in workflow


def test_release_command_passes_uvr_version(monkeypatch: pytest.MonkeyPatch) -> None:
    """cmd_release passes the local uvr version to the workflow dispatch."""
    import subprocess

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        result = MagicMock()
        result.returncode = 0
        result.stdout = "[]"
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)

    args = argparse.Namespace(release=None, force_all=False)
    cmd_release(args)

    trigger_call = calls[0]
    assert f"uvr_version={__version__}" in " ".join(trigger_call)


def test_cli_parses_matrix_args() -> None:
    """CLI correctly parses -m arguments with nargs='+'."""
    with patch.object(
        sys,
        "argv",
        [
            "uvr",
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
        with patch("uv_release_monorepo.cli.cmd_init") as mock_init:
            cli()
            args = mock_init.call_args[0][0]
            assert args.matrix == [
                ["pkg-alpha", "ubuntu-latest"],
                ["pkg-beta", "ubuntu-latest", "macos-14"],
            ]


class TestInitAdditive:
    """Tests for additive init behavior."""

    def test_init_m_merges_with_existing_matrix(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Adding a new package preserves existing packages."""
        _write_workspace_repo(tmp_path, ["pkg-alpha", "pkg-beta"])
        monkeypatch.chdir(tmp_path)

        # First init: pkg-alpha
        cmd_init(
            argparse.Namespace(
                workflow_dir=".github/workflows",
                matrix=[["pkg-alpha", "ubuntu-latest"]],
            )
        )

        # Second init: pkg-beta (should keep pkg-alpha)
        cmd_init(
            argparse.Namespace(
                workflow_dir=".github/workflows",
                matrix=[["pkg-beta", "ubuntu-latest"]],
            )
        )

        workflow = (tmp_path / ".github" / "workflows" / "release.yml").read_text()
        assert '- package: "pkg-alpha"' in workflow
        assert '- package: "pkg-beta"' in workflow

    def test_init_m_replaces_runners_for_existing_package(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Re-specifying a package replaces its runner list."""
        _write_workspace_repo(tmp_path, ["pkg-alpha"])
        monkeypatch.chdir(tmp_path)

        # First init: ubuntu-latest
        cmd_init(
            argparse.Namespace(
                workflow_dir=".github/workflows",
                matrix=[["pkg-alpha", "ubuntu-latest"]],
            )
        )

        # Second init: replace with macos-14
        cmd_init(
            argparse.Namespace(
                workflow_dir=".github/workflows",
                matrix=[["pkg-alpha", "macos-14"]],
            )
        )

        workflow = (tmp_path / ".github" / "workflows" / "release.yml").read_text()
        assert 'runner: "macos-14"' in workflow
        assert 'runner: "ubuntu-latest"' not in workflow

    def test_init_no_m_preserves_existing_matrix(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Bare `uvr init` on a matrix workflow preserves matrix entries."""
        _write_workspace_repo(tmp_path, ["pkg-alpha"])
        monkeypatch.chdir(tmp_path)

        # First init with matrix
        cmd_init(
            argparse.Namespace(
                workflow_dir=".github/workflows",
                matrix=[["pkg-alpha", "ubuntu-latest", "macos-14"]],
            )
        )

        # Second init without -m
        cmd_init(
            argparse.Namespace(
                workflow_dir=".github/workflows",
                matrix=None,
            )
        )

        workflow = (tmp_path / ".github" / "workflows" / "release.yml").read_text()
        assert "jobs:\n  discover:" in workflow
        assert '- package: "pkg-alpha"' in workflow
        assert 'runner: "ubuntu-latest"' in workflow
        assert 'runner: "macos-14"' in workflow

    def test_init_m_upgrades_simple_to_matrix(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Adding -m to a simple workflow upgrades to matrix."""
        _write_workspace_repo(tmp_path, ["pkg-alpha"])
        monkeypatch.chdir(tmp_path)

        # First init: simple workflow
        cmd_init(
            argparse.Namespace(
                workflow_dir=".github/workflows",
                matrix=None,
            )
        )
        workflow = (tmp_path / ".github" / "workflows" / "release.yml").read_text()
        assert "jobs:\n  release:" in workflow

        # Second init: add matrix
        cmd_init(
            argparse.Namespace(
                workflow_dir=".github/workflows",
                matrix=[["pkg-alpha", "ubuntu-latest"]],
            )
        )
        workflow = (tmp_path / ".github" / "workflows" / "release.yml").read_text()
        assert "jobs:\n  discover:" in workflow
        assert '- package: "pkg-alpha"' in workflow


class TestParseExistingMatrix:
    """Tests for _parse_existing_matrix()."""

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        assert _parse_existing_matrix(tmp_path / "nope.yml") == {}

    def test_parses_generated_workflow(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_workspace_repo(tmp_path, ["pkg-a", "pkg-b"])
        monkeypatch.chdir(tmp_path)

        cmd_init(
            argparse.Namespace(
                workflow_dir=".github/workflows",
                matrix=[
                    ["pkg-a", "ubuntu-latest"],
                    ["pkg-b", "ubuntu-latest", "macos-14"],
                ],
            )
        )

        result = _parse_existing_matrix(
            tmp_path / ".github" / "workflows" / "release.yml"
        )
        assert result == {
            "pkg-a": ["ubuntu-latest"],
            "pkg-b": ["ubuntu-latest", "macos-14"],
        }


class TestStatus:
    """Tests for status command."""

    def test_status_shows_matrix(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_workspace_repo(tmp_path, ["pkg-alpha", "pkg-beta"])
        monkeypatch.chdir(tmp_path)

        cmd_init(
            argparse.Namespace(
                workflow_dir=".github/workflows",
                matrix=[
                    ["pkg-alpha", "ubuntu-latest"],
                    ["pkg-beta", "ubuntu-latest", "macos-14"],
                ],
            )
        )
        capsys.readouterr()  # clear init output

        cmd_status(argparse.Namespace(workflow_dir=".github/workflows"))
        output = capsys.readouterr().out

        assert "Build matrix:" in output
        assert "pkg-alpha" in output
        assert "pkg-beta" in output
        assert "ubuntu-latest" in output
        assert "macos-14" in output

    def test_status_no_workflow(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(tmp_path)

        cmd_status(argparse.Namespace(workflow_dir=".github/workflows"))
        output = capsys.readouterr().out

        assert "No release workflow found" in output
        assert "uvr init" in output

    def test_status_simple_workflow_shows_packages(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Simple workflow status discovers packages and shows them on ubuntu-latest."""
        _write_workspace_repo(tmp_path, ["pkg-alpha", "pkg-beta"])
        monkeypatch.chdir(tmp_path)

        cmd_init(argparse.Namespace(workflow_dir=".github/workflows", matrix=None))
        capsys.readouterr()

        cmd_status(argparse.Namespace(workflow_dir=".github/workflows"))
        output = capsys.readouterr().out

        assert "Build matrix:" in output
        assert "pkg-alpha" in output
        assert "pkg-beta" in output
        assert "ubuntu-latest" in output


class TestDiscoverPackages:
    """Tests for _discover_packages()."""

    def test_discovers_names_and_deps(self, tmp_path: Path) -> None:
        """Discovers packages and resolves internal dependencies."""
        _write_workspace_repo(tmp_path, ["pkg-alpha", "pkg-beta"])
        beta_toml = tmp_path / "packages" / "pkg-beta" / "pyproject.toml"
        beta_toml.write_text(
            '[project]\nname = "pkg-beta"\nversion = "1.0.0"\n'
            'dependencies = ["pkg-alpha>=1.0"]\n'
        )

        result = _discover_packages(root=tmp_path)

        assert "pkg-alpha" in result
        assert "pkg-beta" in result
        assert result["pkg-alpha"] == ("1.0.0", [])
        assert result["pkg-beta"] == ("1.0.0", ["pkg-alpha"])

    def test_discovers_packages_with_explicit_root(self, tmp_path: Path) -> None:
        """_discover_packages accepts an explicit root parameter."""
        _write_workspace_repo(tmp_path, ["pkg-x"])

        result = _discover_packages(root=tmp_path)

        assert "pkg-x" in result

    def test_status_shows_dependency_matrix(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Status command shows dependency matrix."""
        _write_workspace_repo(tmp_path, ["pkg-alpha", "pkg-beta"])
        beta_toml = tmp_path / "packages" / "pkg-beta" / "pyproject.toml"
        beta_toml.write_text(
            '[project]\nname = "pkg-beta"\nversion = "1.0.0"\n'
            'dependencies = ["pkg-alpha>=1.0"]\n'
        )
        monkeypatch.chdir(tmp_path)

        cmd_init(argparse.Namespace(workflow_dir=".github/workflows", matrix=None))
        capsys.readouterr()

        cmd_status(argparse.Namespace(workflow_dir=".github/workflows"))
        output = capsys.readouterr().out

        assert "Dependencies:" in output
        assert "pkg-alpha" in output
        assert "pkg-beta" in output

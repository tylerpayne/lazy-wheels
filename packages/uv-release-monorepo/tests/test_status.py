"""Tests for the status command and _discover_packages."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from uv_release_monorepo.cli import (
    _discover_packages,
    cmd_init,
    cmd_runners,
    cmd_status,
)

from tests._helpers import _runners_args, _write_workspace_repo


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

        # Set up matrix via cmd_runners
        cmd_runners(_runners_args(package="pkg-alpha", add_value="ubuntu-latest"))
        cmd_runners(_runners_args(package="pkg-beta", add_value="ubuntu-latest"))
        cmd_runners(_runners_args(package="pkg-beta", add_value="macos-14"))

        # Init workflow (needed for cmd_status to find release.yml)
        cmd_init(argparse.Namespace(workflow_dir=".github/workflows"))
        capsys.readouterr()  # clear output

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

        cmd_init(argparse.Namespace(workflow_dir=".github/workflows"))
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

        cmd_init(argparse.Namespace(workflow_dir=".github/workflows"))
        capsys.readouterr()

        cmd_status(argparse.Namespace(workflow_dir=".github/workflows"))
        output = capsys.readouterr().out

        assert "Dependencies:" in output
        assert "pkg-alpha" in output
        assert "pkg-beta" in output

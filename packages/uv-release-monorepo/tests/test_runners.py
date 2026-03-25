"""Tests for the runners command and _read_matrix."""

from __future__ import annotations

from pathlib import Path

import pytest

from uv_release_monorepo.cli import _read_matrix, cmd_runners

from tests._helpers import _runners_args, _write_workspace_repo


class TestCmdRunners:
    """Tests for cmd_runners()."""

    def test_show_all_empty(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """No matrix configured shows default message."""
        _write_workspace_repo(tmp_path, ["pkg-alpha"])
        monkeypatch.chdir(tmp_path)

        cmd_runners(_runners_args())
        output = capsys.readouterr().out
        assert "No runners configured" in output

    def test_add_runner(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Adds a runner for a package, verifiable via _read_matrix."""
        _write_workspace_repo(tmp_path, ["pkg-alpha"])
        monkeypatch.chdir(tmp_path)

        cmd_runners(_runners_args(package="pkg-alpha", add_value="ubuntu-latest"))

        result = _read_matrix(tmp_path)
        assert result["pkg-alpha"] == ["ubuntu-latest"]

    def test_add_duplicate_ignored(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Adding the same runner twice does not duplicate it."""
        _write_workspace_repo(tmp_path, ["pkg-alpha"])
        monkeypatch.chdir(tmp_path)

        cmd_runners(_runners_args(package="pkg-alpha", add_value="ubuntu-latest"))
        cmd_runners(_runners_args(package="pkg-alpha", add_value="ubuntu-latest"))

        result = _read_matrix(tmp_path)
        assert result["pkg-alpha"] == ["ubuntu-latest"]
        output = capsys.readouterr().out
        assert "already in runners" in output

    def test_remove_runner(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Removes a runner from a package."""
        _write_workspace_repo(tmp_path, ["pkg-alpha"])
        monkeypatch.chdir(tmp_path)

        cmd_runners(_runners_args(package="pkg-alpha", add_value="ubuntu-latest"))
        cmd_runners(_runners_args(package="pkg-alpha", add_value="macos-14"))
        cmd_runners(_runners_args(package="pkg-alpha", remove_value="ubuntu-latest"))

        result = _read_matrix(tmp_path)
        assert result["pkg-alpha"] == ["macos-14"]

    def test_remove_last_runner_clears_package(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Removing the only runner removes the package from the matrix."""
        _write_workspace_repo(tmp_path, ["pkg-alpha"])
        monkeypatch.chdir(tmp_path)

        cmd_runners(_runners_args(package="pkg-alpha", add_value="ubuntu-latest"))
        cmd_runners(_runners_args(package="pkg-alpha", remove_value="ubuntu-latest"))

        result = _read_matrix(tmp_path)
        assert "pkg-alpha" not in result

    def test_clear(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Clears all runners for a package."""
        _write_workspace_repo(tmp_path, ["pkg-alpha"])
        monkeypatch.chdir(tmp_path)

        cmd_runners(_runners_args(package="pkg-alpha", add_value="ubuntu-latest"))
        cmd_runners(_runners_args(package="pkg-alpha", add_value="macos-14"))
        cmd_runners(_runners_args(package="pkg-alpha", clear=True))

        result = _read_matrix(tmp_path)
        assert "pkg-alpha" not in result

    def test_read_single_package(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Reads runners for one package."""
        _write_workspace_repo(tmp_path, ["pkg-alpha"])
        monkeypatch.chdir(tmp_path)

        cmd_runners(_runners_args(package="pkg-alpha", add_value="ubuntu-latest"))
        cmd_runners(_runners_args(package="pkg-alpha", add_value="macos-14"))
        capsys.readouterr()  # clear add output

        cmd_runners(_runners_args(package="pkg-alpha"))
        output = capsys.readouterr().out
        assert "ubuntu-latest" in output
        assert "macos-14" in output


class TestReadMatrix:
    """Tests for _read_matrix()."""

    def test_returns_empty_when_no_matrix(self, tmp_path: Path) -> None:
        """Returns {} for a repo with no [tool.uvr.matrix]."""
        _write_workspace_repo(tmp_path, [])
        result = _read_matrix(tmp_path)
        assert result == {}

    def test_returns_empty_when_no_pyproject(self, tmp_path: Path) -> None:
        """Returns {} when pyproject.toml does not exist."""
        result = _read_matrix(tmp_path)
        assert result == {}

    def test_returns_matrix_after_cmd_runners(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns the matrix after cmd_runners has been used to set up runners."""
        _write_workspace_repo(tmp_path, ["pkg-a", "pkg-b"])
        monkeypatch.chdir(tmp_path)

        cmd_runners(_runners_args(package="pkg-a", add_value="ubuntu-latest"))
        cmd_runners(_runners_args(package="pkg-b", add_value="ubuntu-latest"))
        cmd_runners(_runners_args(package="pkg-b", add_value="macos-14"))

        result = _read_matrix(tmp_path)
        assert result == {
            "pkg-a": ["ubuntu-latest"],
            "pkg-b": ["ubuntu-latest", "macos-14"],
        }

"""Tests for the ``uvr workflow publish`` command and get_publish_config."""

from __future__ import annotations

from pathlib import Path

import pytest

from uv_release_monorepo.shared.utils.config import get_publish_config
from uv_release_monorepo.shared.utils.toml import read_pyproject
from uv_release_monorepo.cli import cmd_publish_config

from tests._helpers import _publish_args, _write_workspace_repo


class TestCmdPublishConfig:
    """Tests for cmd_publish_config()."""

    def test_show_empty(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """No publish config shows 'not configured'."""
        _write_workspace_repo(tmp_path, ["pkg-alpha"])
        monkeypatch.chdir(tmp_path)

        cmd_publish_config(_publish_args())
        output = capsys.readouterr().out
        assert "not configured" in output

    def test_set_index(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Sets the publish index."""
        _write_workspace_repo(tmp_path, ["pkg-alpha"])
        monkeypatch.chdir(tmp_path)

        cmd_publish_config(_publish_args(index="pypi"))

        doc = read_pyproject(tmp_path / "pyproject.toml")
        config = get_publish_config(doc)
        assert config["index"] == "pypi"

    def test_set_environment(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sets the GitHub Actions environment."""
        _write_workspace_repo(tmp_path, ["pkg-alpha"])
        monkeypatch.chdir(tmp_path)

        cmd_publish_config(_publish_args(environment="pypi"))

        doc = read_pyproject(tmp_path / "pyproject.toml")
        config = get_publish_config(doc)
        assert config["environment"] == "pypi"

    def test_set_trusted_publishing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sets the trusted publishing mode."""
        _write_workspace_repo(tmp_path, ["pkg-alpha"])
        monkeypatch.chdir(tmp_path)

        cmd_publish_config(_publish_args(trusted_publishing="always"))

        doc = read_pyproject(tmp_path / "pyproject.toml")
        config = get_publish_config(doc)
        assert config["trusted_publishing"] == "always"

    def test_exclude_packages(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Adds packages to the exclude list."""
        _write_workspace_repo(tmp_path, ["pkg-alpha", "pkg-beta"])
        monkeypatch.chdir(tmp_path)

        cmd_publish_config(_publish_args(exclude_packages=["pkg-alpha"]))

        doc = read_pyproject(tmp_path / "pyproject.toml")
        config = get_publish_config(doc)
        assert config["exclude"] == ["pkg-alpha"]

    def test_include_packages(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Adds packages to the include list."""
        _write_workspace_repo(tmp_path, ["pkg-alpha", "pkg-beta"])
        monkeypatch.chdir(tmp_path)

        cmd_publish_config(_publish_args(include_packages=["pkg-alpha"]))

        doc = read_pyproject(tmp_path / "pyproject.toml")
        config = get_publish_config(doc)
        assert config["include"] == ["pkg-alpha"]

    def test_remove_from_both_lists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--remove alone removes from both include and exclude."""
        _write_workspace_repo(tmp_path, ["pkg-alpha", "pkg-beta"])
        monkeypatch.chdir(tmp_path)

        # Add to exclude first
        cmd_publish_config(_publish_args(exclude_packages=["pkg-alpha", "pkg-beta"]))
        # Remove pkg-alpha from both
        cmd_publish_config(_publish_args(remove_packages=["pkg-alpha"]))

        doc = read_pyproject(tmp_path / "pyproject.toml")
        config = get_publish_config(doc)
        assert config["exclude"] == ["pkg-beta"]

    def test_remove_with_include(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--include combined with --remove adds and removes in one call."""
        _write_workspace_repo(tmp_path, ["pkg-alpha", "pkg-beta", "pkg-gamma"])
        monkeypatch.chdir(tmp_path)

        # Seed include list
        cmd_publish_config(_publish_args(include_packages=["pkg-alpha", "pkg-beta"]))
        # Add gamma, remove alpha
        cmd_publish_config(
            _publish_args(include_packages=["pkg-gamma"], remove_packages=["pkg-alpha"])
        )

        doc = read_pyproject(tmp_path / "pyproject.toml")
        config = get_publish_config(doc)
        assert "pkg-alpha" not in config["include"]
        assert "pkg-beta" in config["include"]
        assert "pkg-gamma" in config["include"]

    def test_clear(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--clear removes the entire publish config."""
        _write_workspace_repo(tmp_path, ["pkg-alpha"])
        monkeypatch.chdir(tmp_path)

        cmd_publish_config(_publish_args(index="pypi", environment="pypi"))
        cmd_publish_config(_publish_args(clear=True))

        doc = read_pyproject(tmp_path / "pyproject.toml")
        config = get_publish_config(doc)
        assert config["index"] == ""
        assert config["environment"] == ""

    def test_combined_flags(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--index and --exclude can be set in one call."""
        _write_workspace_repo(tmp_path, ["pkg-alpha", "pkg-beta"])
        monkeypatch.chdir(tmp_path)

        cmd_publish_config(_publish_args(index="pypi", exclude_packages=["pkg-alpha"]))

        doc = read_pyproject(tmp_path / "pyproject.toml")
        config = get_publish_config(doc)
        assert config["index"] == "pypi"
        assert config["exclude"] == ["pkg-alpha"]


class TestGetPublishConfig:
    """Tests for get_publish_config()."""

    def test_returns_defaults_when_no_section(self, tmp_path: Path) -> None:
        """Returns empty defaults when [tool.uvr.publish] is absent."""
        _write_workspace_repo(tmp_path, [])
        doc = read_pyproject(tmp_path / "pyproject.toml")
        config = get_publish_config(doc)
        assert config["index"] == ""
        assert config["environment"] == ""
        assert config["trusted_publishing"] == "automatic"
        assert config["include"] == []
        assert config["exclude"] == []

    def test_reads_all_fields(self, tmp_path: Path) -> None:
        """Reads all configured fields."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[tool.uv.workspace]\nmembers = ["packages/*"]\n'
            "\n[tool.uvr.publish]\n"
            'index = "testpypi"\n'
            'environment = "staging"\n'
            'trusted-publishing = "always"\n'
            'include = ["my-pkg"]\n'
            'exclude = ["test-pkg"]\n'
        )
        doc = read_pyproject(pyproject)
        config = get_publish_config(doc)
        assert config["index"] == "testpypi"
        assert config["environment"] == "staging"
        assert config["trusted_publishing"] == "always"
        assert config["include"] == ["my-pkg"]
        assert config["exclude"] == ["test-pkg"]

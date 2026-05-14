"""Tests for single-package workspace discovery.

A single-package layout is a pyproject.toml that is itself a package
(carries [project] + [build-system]) and has no [tool.uv.workspace]
block. uv supports this natively as the simplest form of "workspace",
and uv-release discovers the root as a single package at path ".".
"""

from __future__ import annotations

from pathlib import Path

import diny
import pytest
import tomlkit

from conftest import read_toml, run_cli


class TestSinglePackageDiscovery:
    def test_status_shows_root_package(
        self, single_package_workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with diny.provide():
            run_cli("status")
        out = capsys.readouterr().out
        assert "pkg-a" in out
        assert "0.1.0.dev0" in out
        assert "initial release" in out

    def test_workspace_packages_root_at_dot(
        self, single_package_workspace: Path
    ) -> None:
        from uv_release.dependencies.shared.workspace_packages import (
            WorkspacePackages,
        )

        with diny.provide():
            workspace = diny.resolve(WorkspacePackages)
        assert list(workspace.items.keys()) == ["pkg-a"]
        # path "." means the root pyproject IS the package; downstream code
        # uses this directly as a git pathspec and as the build cwd.
        assert workspace.items["pkg-a"].path == "."

    def test_version_bump_writes_root_pyproject(
        self, single_package_workspace: Path
    ) -> None:
        with diny.provide():
            run_cli("version", "--bump", "minor", "--no-commit", "--no-push")
        doc = read_toml(single_package_workspace / "pyproject.toml")
        assert doc["project"]["version"] == "0.2.0.dev0"

    def test_latest_defaults_to_sole_package(
        self, single_package_workspace: Path
    ) -> None:
        """`latest` need not be set when the workspace has one package.

        The fixture deliberately omits `[tool.uvr.config].latest`; the
        UvrConfig provider should fall back to the only package.
        """
        from uv_release.dependencies.config.uvr_config import UvrConfig

        with diny.provide():
            config = diny.resolve(UvrConfig)
        assert config.latest_package == "pkg-a"


class TestSinglePackageErrors:
    def test_both_project_and_workspace_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Reject a root that is both a package and a workspace root.

        That shape is ambiguous (the root would appear twice during
        discovery), so uvr raises rather than guessing.
        """
        (tmp_path / "pyproject.toml").write_text(
            tomlkit.dumps(
                {
                    "project": {"name": "pkg-a", "version": "0.1.0.dev0"},
                    "build-system": {
                        "requires": ["hatchling"],
                        "build-backend": "hatchling.build",
                    },
                    "tool": {
                        "uv": {"workspace": {"members": ["packages/*"]}},
                    },
                }
            )
        )
        monkeypatch.chdir(tmp_path)

        from uv_release.dependencies.shared.workspace_packages import (
            WorkspacePackages,
        )

        with pytest.raises(ValueError, match="both \\[project\\] and"):
            with diny.provide():
                diny.resolve(WorkspacePackages)

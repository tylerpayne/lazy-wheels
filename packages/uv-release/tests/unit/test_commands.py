"""Tests for PackagePyProjectDoc and commands that use it."""

from __future__ import annotations

from pathlib import Path

import pytest

from uv_release.commands import PinDepsCommand, SetVersionCommand, UpdateTomlCommand
from uv_release.types import (
    PackagePyProjectDoc,
    WorkspacePyProjectDoc,
)

from .conftest import make_package, make_version


# ---------------------------------------------------------------------------
# PackagePyProjectDoc
# ---------------------------------------------------------------------------


class TestPackagePyProjectDoc:
    """PackagePyProjectDoc wraps tomlkit and preserves comments."""

    def test_read_version(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "pyproject.toml").write_text(
            '[project]\nname = "pkg"\nversion = "1.0.0"\n'
        )
        doc = PackagePyProjectDoc.read("pkg/pyproject.toml")
        assert doc.version == "1.0.0"

    def test_set_version(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "pyproject.toml").write_text(
            '[project]\nname = "pkg"\nversion = "1.0.0"\n'
        )
        doc = PackagePyProjectDoc.read("pkg/pyproject.toml")
        doc.version = "2.0.0"
        doc.write("pkg/pyproject.toml")
        assert 'version = "2.0.0"' in (pkg / "pyproject.toml").read_text()

    def test_preserves_comments(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        original = '# This is my package\n[project]\nname = "pkg"\nversion = "1.0.0"\n'
        (pkg / "pyproject.toml").write_text(original)
        doc = PackagePyProjectDoc.read("pkg/pyproject.toml")
        doc.version = "2.0.0"
        doc.write("pkg/pyproject.toml")
        result = (pkg / "pyproject.toml").read_text()
        assert "# This is my package" in result
        assert 'version = "2.0.0"' in result

    def test_read_dependencies(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "pyproject.toml").write_text(
            '[project]\nname = "pkg"\nversion = "1.0.0"\n'
            'dependencies = ["alpha>=1.0.0", "requests"]\n'
        )
        doc = PackagePyProjectDoc.read("pkg/pyproject.toml")
        assert len(doc.dependencies) == 2

    def test_read_build_requires(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "pyproject.toml").write_text(
            '[project]\nname = "pkg"\nversion = "1.0.0"\n'
            '[build-system]\nrequires = ["setuptools"]\n'
        )
        doc = PackagePyProjectDoc.read("pkg/pyproject.toml")
        assert doc.build_requires == ["setuptools"]

    def test_read_name(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "pyproject.toml").write_text(
            '[project]\nname = "my-pkg"\nversion = "1.0.0"\n'
        )
        doc = PackagePyProjectDoc.read("pkg/pyproject.toml")
        assert doc.name == "my-pkg"


# ---------------------------------------------------------------------------
# SetVersionCommand
# ---------------------------------------------------------------------------


class TestSetVersionCommand:
    def test_sets_version(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        pkg_dir = tmp_path / "packages" / "alpha"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "pyproject.toml").write_text(
            '[project]\nname = "alpha"\nversion = "1.0.0.dev0"\n'
        )
        pkg = make_package("alpha")
        cmd = SetVersionCommand(label="set", package=pkg, version=make_version("1.0.0"))
        assert cmd.execute() == 0
        assert 'version = "1.0.0"' in (pkg_dir / "pyproject.toml").read_text()

    def test_preserves_comments(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        pkg_dir = tmp_path / "packages" / "alpha"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "pyproject.toml").write_text(
            '# My package\n[project]\nname = "alpha"\nversion = "1.0.0.dev0"\n'
        )
        pkg = make_package("alpha")
        SetVersionCommand(
            label="set", package=pkg, version=make_version("2.0.0")
        ).execute()
        text = (pkg_dir / "pyproject.toml").read_text()
        assert "# My package" in text
        assert 'version = "2.0.0"' in text


# ---------------------------------------------------------------------------
# PinDepsCommand
# ---------------------------------------------------------------------------


class TestPinDepsCommand:
    def test_pins_project_dependency(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        pkg_dir = tmp_path / "packages" / "beta"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "pyproject.toml").write_text(
            '[project]\nname = "beta"\nversion = "1.0.0"\n'
            'dependencies = ["alpha>=1.0.0,<2.0.0"]\n'
        )
        pkg = make_package("beta", version="1.0.0")
        alpha_pkg = make_package("alpha", version="2.0.0")
        cmd = PinDepsCommand(label="pin", package=pkg, pins={"alpha": alpha_pkg})
        assert cmd.execute() == 0
        assert ">=2.0.0" in (pkg_dir / "pyproject.toml").read_text()

    def test_ignores_non_pinned_deps(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        pkg_dir = tmp_path / "packages" / "beta"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "pyproject.toml").write_text(
            '[project]\nname = "beta"\nversion = "1.0.0"\n'
            'dependencies = ["requests>=2.0"]\n'
        )
        pkg = make_package("beta", version="1.0.0")
        alpha_pkg = make_package("alpha", version="2.0.0")
        PinDepsCommand(label="pin", package=pkg, pins={"alpha": alpha_pkg}).execute()
        assert "requests>=2.0" in (pkg_dir / "pyproject.toml").read_text()

    def test_preserves_comments(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        pkg_dir = tmp_path / "packages" / "beta"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "pyproject.toml").write_text(
            '# Beta package\n[project]\nname = "beta"\nversion = "1.0.0"\n'
            'dependencies = ["alpha>=1.0.0,<2.0.0"]\n'
        )
        pkg = make_package("beta", version="1.0.0")
        alpha_pkg = make_package("alpha", version="2.0.0")
        PinDepsCommand(label="pin", package=pkg, pins={"alpha": alpha_pkg}).execute()
        text = (pkg_dir / "pyproject.toml").read_text()
        assert "# Beta package" in text
        assert ">=2.0.0" in text


# ---------------------------------------------------------------------------
# UpdateTomlCommand
# ---------------------------------------------------------------------------


class TestUpdateTomlCommand:
    def test_sets_key(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        cmd = UpdateTomlCommand(label="set", key="workflow_version", value="1.0.0")
        assert cmd.execute() == 0
        assert 'workflow_version = "1.0.0"' in (tmp_path / "pyproject.toml").read_text()

    def test_missing_file_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        cmd = UpdateTomlCommand(label="fail", key="x", value="y")
        assert cmd.execute() == 1


# ---------------------------------------------------------------------------
# Sequential mutations
# ---------------------------------------------------------------------------


class TestSequentialMutations:
    def test_set_version_then_pin_deps(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        pkg_dir = tmp_path / "packages" / "beta"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "pyproject.toml").write_text(
            "# Important comment\n"
            '[project]\nname = "beta"\nversion = "1.0.0.dev0"\n'
            'dependencies = ["alpha>=1.0.0,<2.0.0"]\n'
        )
        pkg = make_package("beta")
        SetVersionCommand(
            label="set", package=pkg, version=make_version("1.0.0")
        ).execute()
        alpha_pkg = make_package("alpha", version="1.0.0")
        PinDepsCommand(label="pin", package=pkg, pins={"alpha": alpha_pkg}).execute()

        text = (pkg_dir / "pyproject.toml").read_text()
        assert 'version = "1.0.0"' in text
        assert ">=1.0.0" in text
        assert "# Important comment" in text


# ---------------------------------------------------------------------------
# WorkspacePyProjectDoc
# ---------------------------------------------------------------------------


class TestWorkspacePyProjectDoc:
    """WorkspacePyProjectDoc wraps tomlkit for root pyproject.toml."""

    def test_read_workspace_members(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pyproject.toml").write_text(
            '[tool.uv.workspace]\nmembers = ["packages/*"]\n'
        )
        doc = WorkspacePyProjectDoc.read()
        assert doc.workspace_members == ["packages/*"]

    def test_empty_workspace_members(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        doc = WorkspacePyProjectDoc.read()
        assert doc.workspace_members == []

    def test_set_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        doc = WorkspacePyProjectDoc.read()
        doc.set_config("workflow_version", "1.0.0")
        doc.write()
        text = (tmp_path / "pyproject.toml").read_text()
        assert 'workflow_version = "1.0.0"' in text

    def test_set_config_preserves_comments(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pyproject.toml").write_text(
            "# Workspace config\n[project]\nname = 'test'\n"
        )
        doc = WorkspacePyProjectDoc.read()
        doc.set_config("skill_version", "2.0.0")
        doc.write()
        text = (tmp_path / "pyproject.toml").read_text()
        assert "# Workspace config" in text
        assert 'skill_version = "2.0.0"' in text

    def test_set_config_updates_existing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pyproject.toml").write_text(
            '[tool.uvr.config]\nworkflow_version = "0.1.0"\n'
        )
        doc = WorkspacePyProjectDoc.read()
        doc.set_config("workflow_version", "2.0.0")
        doc.write()
        text = (tmp_path / "pyproject.toml").read_text()
        assert 'workflow_version = "2.0.0"' in text
        assert "0.1.0" not in text

    def test_read_custom_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        subdir = tmp_path / "sub"
        subdir.mkdir()
        (subdir / "pyproject.toml").write_text(
            '[tool.uv.workspace]\nmembers = ["pkgs/*"]\n'
        )
        doc = WorkspacePyProjectDoc.read("sub/pyproject.toml")
        assert doc.workspace_members == ["pkgs/*"]

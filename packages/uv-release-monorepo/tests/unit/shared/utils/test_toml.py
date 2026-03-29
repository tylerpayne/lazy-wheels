"""Tests for uv_release_monorepo.toml."""

from __future__ import annotations

from pathlib import Path

import tomlkit

from uv_release_monorepo.shared.utils.config import (
    get_hooks,
    get_matrix,
    get_workspace_member_globs,
    set_matrix,
)
from packaging.utils import canonicalize_name

from uv_release_monorepo.shared.utils.packages import get_dependencies
from uv_release_monorepo.shared.utils.toml import read_pyproject, write_pyproject


def _get_project_name(doc: tomlkit.TOMLDocument, fallback: str) -> str:
    return canonicalize_name(doc.get("project", {}).get("name", fallback))


def _get_project_version(doc: tomlkit.TOMLDocument) -> str:
    return doc.get("project", {}).get("version", "0.0.0")


class TestLoadSavePyproject:
    def test_load(self, tmp_pyproject: Path) -> None:
        doc = read_pyproject(tmp_pyproject)
        assert _get_project_name(doc, "") == "test-package"

    def test_save_preserves_content(self, tmp_pyproject: Path) -> None:
        doc = read_pyproject(tmp_pyproject)
        project = doc.get("project", {})
        project["version"] = "9.9.9"
        write_pyproject(tmp_pyproject, doc)

        reloaded = read_pyproject(tmp_pyproject)
        assert _get_project_version(reloaded) == "9.9.9"
        assert _get_project_name(reloaded, "") == "test-package"


class TestGetProjectName:
    def test_returns_name(self, sample_toml_doc: tomlkit.TOMLDocument) -> None:
        assert _get_project_name(sample_toml_doc, "fallback") == "my-package"

    def test_normalizes_name(self) -> None:
        doc = tomlkit.parse('[project]\nname = "My_Package"')
        assert _get_project_name(doc, "fallback") == "my-package"

    def test_returns_fallback_when_missing(self) -> None:
        doc = tomlkit.parse("[project]")
        assert _get_project_name(doc, "my-fallback") == "my-fallback"

    def test_returns_fallback_when_no_project(self) -> None:
        doc = tomlkit.parse("")
        assert _get_project_name(doc, "fallback") == "fallback"


class TestGetProjectVersion:
    def test_returns_version(self, sample_toml_doc: tomlkit.TOMLDocument) -> None:
        assert _get_project_version(sample_toml_doc) == "2.0.0"

    def test_returns_default_when_missing(self) -> None:
        doc = tomlkit.parse("[project]")
        assert _get_project_version(doc) == "0.0.0"


class TestGetDependencies:
    def test_gets_main_deps(self, sample_toml_doc: tomlkit.TOMLDocument) -> None:
        deps = get_dependencies(sample_toml_doc)
        assert "click>=8.0" in deps
        assert "pydantic>=2.0" in deps

    def test_gets_optional_deps(self, sample_toml_doc: tomlkit.TOMLDocument) -> None:
        deps = get_dependencies(sample_toml_doc)
        assert "pytest>=8.0" in deps
        assert "sphinx>=7.0" in deps

    def test_gets_dependency_groups(
        self, sample_toml_doc: tomlkit.TOMLDocument
    ) -> None:
        deps = get_dependencies(sample_toml_doc)
        assert "hypothesis>=6.0" in deps

    def test_gets_build_system_requires(self) -> None:
        doc = tomlkit.parse(
            '[build-system]\nrequires = ["hatchling", "my-tool>=1.0"]\n'
            "[project]\nname = 'foo'\ndependencies = ['click>=8.0']\n"
        )
        deps = get_dependencies(doc)
        assert "hatchling" in deps
        assert "my-tool>=1.0" in deps
        assert "click>=8.0" in deps

    def test_empty_when_no_deps(self) -> None:
        doc = tomlkit.parse("[project]\nname = 'foo'")
        assert get_dependencies(doc) == []


class TestGetWorkspaceMemberGlobs:
    def test_returns_members(self, sample_toml_doc: tomlkit.TOMLDocument) -> None:
        members = get_workspace_member_globs(sample_toml_doc)
        assert members == ["packages/*", "libs/*"]


class TestUvrHooks:
    def test_returns_empty_when_missing(self) -> None:
        doc = tomlkit.parse("[project]\nname = 'foo'\n")
        assert get_hooks(doc) == {}

    def test_string_value(self) -> None:
        doc = tomlkit.parse('[tool.uvr.hooks]\nfile = "uvr_hooks.py:MyHook"\n')
        assert get_hooks(doc) == {"file": "uvr_hooks.py:MyHook"}

    def test_bare_path(self) -> None:
        doc = tomlkit.parse('[tool.uvr.hooks]\nfile = "scripts/hooks.py"\n')
        assert get_hooks(doc) == {"file": "scripts/hooks.py"}


class TestUvrMatrix:
    def test_get_uvr_matrix_returns_empty_when_missing(self) -> None:
        """Returns {} when there is no [tool.uvr] section."""
        doc = tomlkit.parse("[project]\nname = 'foo'\n")
        assert get_matrix(doc) == {}

    def test_get_uvr_matrix_returns_matrix(self) -> None:
        """Parses a doc that has [tool.uvr.matrix]."""
        content = """\
[tool.uvr.matrix]
pkg-alpha = ["ubuntu-latest", "macos-14"]
pkg-beta = ["ubuntu-latest"]
"""
        doc = tomlkit.parse(content)
        result = get_matrix(doc)
        assert result == {
            "pkg-alpha": [["ubuntu-latest"], ["macos-14"]],
            "pkg-beta": [["ubuntu-latest"]],
        }

    def test_set_uvr_matrix_writes_matrix(self) -> None:
        """set_uvr_matrix then get_uvr_matrix round-trips the data."""
        doc = tomlkit.parse('[tool.uv.workspace]\nmembers = ["packages/*"]\n')
        matrix: dict[str, list[list[str]]] = {
            "pkg-beta": [["ubuntu-latest"], ["macos-14"]],
            "pkg-alpha": [["ubuntu-latest"]],
        }
        set_matrix(doc, matrix)
        result = get_matrix(doc)
        assert result == {
            "pkg-alpha": [["ubuntu-latest"]],
            "pkg-beta": [["ubuntu-latest"], ["macos-14"]],
        }

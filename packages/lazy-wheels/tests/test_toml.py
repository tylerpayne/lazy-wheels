"""Tests for lazy_wheels.toml."""

from __future__ import annotations

from pathlib import Path

import tomlkit

from lazy_wheels.toml import (
    get_all_dependency_strings,
    get_project_name,
    get_project_version,
    get_workspace_member_globs,
    load_pyproject,
    save_pyproject,
)


class TestLoadSavePyproject:
    def test_load(self, tmp_pyproject: Path) -> None:
        doc = load_pyproject(tmp_pyproject)
        assert get_project_name(doc, "") == "test-package"

    def test_save_preserves_content(self, tmp_pyproject: Path) -> None:
        doc = load_pyproject(tmp_pyproject)
        project = doc.get("project", {})
        project["version"] = "9.9.9"
        save_pyproject(tmp_pyproject, doc)

        reloaded = load_pyproject(tmp_pyproject)
        assert get_project_version(reloaded) == "9.9.9"
        assert get_project_name(reloaded, "") == "test-package"


class TestGetProjectName:
    def test_returns_name(self, sample_toml_doc: tomlkit.TOMLDocument) -> None:
        assert get_project_name(sample_toml_doc, "fallback") == "my-package"

    def test_normalizes_name(self) -> None:
        doc = tomlkit.parse('[project]\nname = "My_Package"')
        assert get_project_name(doc, "fallback") == "my-package"

    def test_returns_fallback_when_missing(self) -> None:
        doc = tomlkit.parse("[project]")
        assert get_project_name(doc, "my-fallback") == "my-fallback"

    def test_returns_fallback_when_no_project(self) -> None:
        doc = tomlkit.parse("")
        assert get_project_name(doc, "fallback") == "fallback"


class TestGetProjectVersion:
    def test_returns_version(self, sample_toml_doc: tomlkit.TOMLDocument) -> None:
        assert get_project_version(sample_toml_doc) == "2.0.0"

    def test_returns_default_when_missing(self) -> None:
        doc = tomlkit.parse("[project]")
        assert get_project_version(doc) == "0.0.0"


class TestGetAllDependencyStrings:
    def test_gets_main_deps(self, sample_toml_doc: tomlkit.TOMLDocument) -> None:
        deps = get_all_dependency_strings(sample_toml_doc)
        assert "click>=8.0" in deps
        assert "pydantic>=2.0" in deps

    def test_gets_optional_deps(self, sample_toml_doc: tomlkit.TOMLDocument) -> None:
        deps = get_all_dependency_strings(sample_toml_doc)
        assert "pytest>=8.0" in deps
        assert "sphinx>=7.0" in deps

    def test_gets_dependency_groups(
        self, sample_toml_doc: tomlkit.TOMLDocument
    ) -> None:
        deps = get_all_dependency_strings(sample_toml_doc)
        assert "hypothesis>=6.0" in deps

    def test_empty_when_no_deps(self) -> None:
        doc = tomlkit.parse("[project]\nname = 'foo'")
        assert get_all_dependency_strings(doc) == []


class TestGetWorkspaceMemberGlobs:
    def test_returns_members(self, sample_toml_doc: tomlkit.TOMLDocument) -> None:
        members = get_workspace_member_globs(sample_toml_doc)
        assert members == ["packages/*", "libs/*"]

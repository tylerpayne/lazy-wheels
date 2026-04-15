"""Tests for PackageBuilder — reads pyproject.toml into frozen Package."""

from __future__ import annotations

from pathlib import Path


from uv_release.parse.package import create_package
from uv_release.types import Package


def _write_pyproject(
    path: Path, name: str, version: str, deps: list[str] | None = None
) -> None:
    deps_str = ""
    if deps:
        dep_lines = ", ".join(f'"{d}"' for d in deps)
        deps_str = f"dependencies = [{dep_lines}]"
    (path / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "{version}"\n{deps_str}\n'
    )


class TestBuildPackage:
    def test_reads_name_version_path(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "packages" / "my-pkg"
        pkg_dir.mkdir(parents=True)
        _write_pyproject(pkg_dir, "my-pkg", "1.0.0")

        pkg = create_package(pkg_dir, workspace_members=frozenset())
        assert isinstance(pkg, Package)
        assert pkg.name == "my-pkg"
        assert pkg.version.raw == "1.0.0"

    def test_filters_deps_to_workspace_members(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "packages" / "app"
        pkg_dir.mkdir(parents=True)
        _write_pyproject(pkg_dir, "app", "1.0.0", deps=["lib", "requests", "other"])

        pkg = create_package(pkg_dir, workspace_members=frozenset({"lib", "other"}))
        assert set(pkg.deps) == {"lib", "other"}

    def test_no_deps(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "packages" / "leaf"
        pkg_dir.mkdir(parents=True)
        _write_pyproject(pkg_dir, "leaf", "2.0.0")

        pkg = create_package(pkg_dir, workspace_members=frozenset())
        assert pkg.deps == []

    def test_includes_build_system_requires(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "packages" / "app"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "pyproject.toml").write_text(
            '[project]\nname = "app"\nversion = "1.0.0"\n'
            'dependencies = ["lib"]\n'
            "[build-system]\n"
            'requires = ["hatchling", "build-helper"]\n'
        )

        pkg = create_package(
            pkg_dir, workspace_members=frozenset({"lib", "build-helper"})
        )
        assert "lib" in pkg.deps
        assert "build-helper" in pkg.deps
        assert "hatchling" not in pkg.deps  # not a workspace member

    def test_version_parsed_to_rich_object(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "packages" / "dev-pkg"
        pkg_dir.mkdir(parents=True)
        _write_pyproject(pkg_dir, "dev-pkg", "1.0.1a2.dev0")

        pkg = create_package(pkg_dir, workspace_members=frozenset())
        assert pkg.version.state.name == "DEV0_PRE"
        assert pkg.version.pre_kind == "a"

"""Integration tests for command execute methods using real git repos."""

from __future__ import annotations

from pathlib import Path

import pytest
import tomlkit

from uv_release.commands import (
    CreateTagCommand,
    PinDepsCommand,
    SetVersionCommand,
    ShellCommand,
)
from uv_release.types import Package
from uv_release.utils.git import GitRepo
from uv_release.types import Version


def _version(raw: str) -> Version:
    return Version.parse(raw)


def _package(workspace: Path, name: str, version: str = "1.0.0.dev0") -> Package:
    return Package(
        name=name,
        path=f"packages/{name}",
        version=_version(version),
    )


class TestSetVersionCommand:
    def test_writes_version_to_pyproject(self, workspace: Path) -> None:
        pkg = _package(workspace, "alpha")
        cmd = SetVersionCommand(
            label="set version", package=pkg, version=_version("2.0.0")
        )
        result = cmd.execute()
        assert result == 0

        doc = tomlkit.loads((workspace / "packages/alpha/pyproject.toml").read_text())
        assert doc["project"]["version"] == "2.0.0"  # type: ignore[index]

    def test_preserves_other_fields(self, workspace: Path) -> None:
        pkg = _package(workspace, "alpha")
        cmd = SetVersionCommand(
            label="set version", package=pkg, version=_version("2.0.0")
        )
        cmd.execute()

        doc = tomlkit.loads((workspace / "packages/alpha/pyproject.toml").read_text())
        assert doc["project"]["name"] == "alpha"  # type: ignore[index]


class TestPinDepsCommand:
    def test_pins_dependency_version(self, workspace: Path) -> None:
        pkg = _package(workspace, "beta")
        alpha = _package(workspace, "alpha")
        alpha_pinned = Package(
            name=alpha.name,
            path=alpha.path,
            version=_version("2.0.0"),
            dependencies=alpha.dependencies,
        )
        cmd = PinDepsCommand(
            label="pin deps", package=pkg, pins={"alpha": alpha_pinned}
        )
        result = cmd.execute()
        assert result == 0

        doc = tomlkit.loads((workspace / "packages/beta/pyproject.toml").read_text())
        deps = doc["project"]["dependencies"]  # type: ignore[index]
        alpha_dep = [d for d in deps if "alpha" in str(d)]  # type: ignore[union-attr]
        assert len(alpha_dep) == 1
        assert ">=2.0.0" in str(alpha_dep[0])


class TestCreateTagCommand:
    def test_creates_tag(self, workspace: Path) -> None:
        cmd = CreateTagCommand(label="tag", tag_name="test/v1.0.0")
        result = cmd.execute()
        assert result == 0

        repo = GitRepo()
        assert repo.find_tag("test/v1.0.0") is not None


class TestBuildCommand:
    def test_builds_package(self, workspace: Path) -> None:
        from uv_release.commands import BuildCommand

        (workspace / "dist").mkdir(exist_ok=True)
        pkg = _package(workspace, "alpha")
        cmd = BuildCommand(label="build alpha", package=pkg, find_links=[])
        result = cmd.execute()
        assert result == 0

        wheels = list((workspace / "dist").glob("alpha-*.whl"))
        assert len(wheels) >= 1


class TestBuildCommandRunnerFilter:
    def test_matching_runner_builds(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from uv_release.commands import BuildCommand

        (workspace / "dist").mkdir(exist_ok=True)
        pkg = _package(workspace, "alpha")
        cmd = BuildCommand(
            label="build",
            package=pkg,
            runners=[["ubuntu-latest"]],
            find_links=[],
        )
        monkeypatch.setenv("UVR_RUNNER", '["ubuntu-latest"]')
        result = cmd.execute()
        assert result == 0
        assert len(list((workspace / "dist").glob("alpha-*.whl"))) >= 1

    def test_non_matching_runner_skips(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from uv_release.commands import BuildCommand

        (workspace / "dist").mkdir(exist_ok=True)
        pkg = _package(workspace, "alpha")
        cmd = BuildCommand(
            label="build",
            package=pkg,
            runners=[["macos-latest"]],
            find_links=[],
        )
        monkeypatch.setenv("UVR_RUNNER", '["ubuntu-latest"]')
        result = cmd.execute()
        assert result == 0
        # No wheel built because runner didn't match
        assert len(list((workspace / "dist").glob("alpha-*.whl"))) == 0

    def test_no_env_var_builds_anyway(self, workspace: Path) -> None:
        from uv_release.commands import BuildCommand

        (workspace / "dist").mkdir(exist_ok=True)
        pkg = _package(workspace, "alpha")
        cmd = BuildCommand(
            label="build",
            package=pkg,
            runners=[["ubuntu-latest"]],
            find_links=[],
        )
        # No UVR_RUNNER set — should build regardless
        result = cmd.execute()
        assert result == 0
        assert len(list((workspace / "dist").glob("alpha-*.whl"))) >= 1


class TestShellCommand:
    def test_success(self, workspace: Path) -> None:
        cmd = ShellCommand(label="echo", args=["true"])
        assert cmd.execute() == 0

    def test_failure(self, workspace: Path) -> None:
        cmd = ShellCommand(label="fail", args=["false"])
        assert cmd.execute() != 0

    def test_mkdir(self, workspace: Path) -> None:
        cmd = ShellCommand(label="mkdir", args=["mkdir", "-p", "dist", "deps"])
        assert cmd.execute() == 0
        assert (workspace / "dist").is_dir()
        assert (workspace / "deps").is_dir()

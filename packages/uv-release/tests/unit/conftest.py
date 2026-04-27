"""Shared test factories for unit tests."""

from __future__ import annotations

from pathlib import Path

from uv_release.states.uvr_state import UvrState
from uv_release.states.workspace import Workspace
from uv_release.types import (
    Change,
    Config,
    Package,
    Publishing,
    Tag,
    Version,
)


def make_version(raw: str) -> Version:
    return Version.parse(raw)


def make_package(
    name: str, version: str = "1.0.0.dev0", dependencies: list[str] | None = None
) -> Package:
    return Package(
        name=name,
        path=f"packages/{name}",
        version=make_version(version),
        dependencies=dependencies or [],
    )


def make_workspace(packages: dict[str, Package] | None = None) -> Workspace:
    return Workspace(root=Path("."), packages=packages or {})


def make_uvr_state(
    *,
    latest_package: str = "",
    python_version: str = "3.12",
    runners: dict[str, list[list[str]]] | None = None,
    publishing: Publishing | None = None,
) -> UvrState:
    return UvrState(
        config=Config(
            uvr_version="0.1.0",
            latest_package=latest_package,
            python_version=python_version,
        ),
        runners=runners or {},
        publishing=publishing or Publishing(),
        uvr_version="0.1.0",
    )


def make_changes_for(
    packages: dict[str, Package], *, commit_log: str = ""
) -> list[Change]:
    """Build a list of Changes for each package."""
    return [
        Change(
            package=pkg,
            baseline=Tag(
                package_name=name,
                raw=f"{name}/v{pkg.version.raw}-base",
                version=pkg.version,
                is_baseline=True,
                commit="abc123",
            ),
            commit_log=commit_log or f"fixed {name}",
            reason="files changed",
        )
        for name, pkg in packages.items()
    ]


class FakeGitRepo:
    """Minimal fake for GitRepo that satisfies Changes.parse."""

    def __init__(
        self,
        *,
        head: str = "head_sha",
        changed_paths: set[str] | None = None,
    ) -> None:
        self._head = head
        self._changed_paths = changed_paths or set()

    def head_commit(self) -> str:
        return self._head

    def path_changed(self, from_commit: str, to_commit: str, path: str) -> bool:
        return path in self._changed_paths

    def commit_log(self, from_commit: str, to_commit: str, path: str) -> str:
        return "abc1234 some commit"

    def diff_stats(self, from_commit: str, to_commit: str, path: str) -> str:
        return "1 file changed"

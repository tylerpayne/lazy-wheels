"""Tests for Changes.parse with fake GitRepo."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


from uv_release.states.changes import Changes
from uv_release.states.workspace import Workspace
from uv_release.types import (
    Package,
    PlanParams,
    Tag,
    Version,
)


def _v(raw: str) -> Version:
    return Version.parse(raw)


def _package(
    name: str, version: str = "1.0.0.dev0", dependencies: list[str] | None = None
) -> Package:
    return Package(
        name=name,
        path=f"packages/{name}",
        version=_v(version),
        dependencies=dependencies or [],
    )


def _workspace(packages: dict[str, Package]) -> Workspace:
    return Workspace(root=Path("."), packages=packages)


def _baseline_tag(name: str, version: str) -> Tag:
    v = _v(version)
    return Tag(
        package_name=name,
        raw=Tag.baseline_tag_name(name, v),
        version=v,
        is_baseline=True,
        commit="baseline_sha",
    )


class _FakeGitRepo:
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


# ---------------------------------------------------------------------------
# Initial release (no baseline)
# ---------------------------------------------------------------------------


class TestInitialRelease:
    """Package with no baseline detected as initial release."""

    def test_no_baseline_is_initial_release(self) -> None:
        pkg = _package("mypkg")
        ws = _workspace({"mypkg": pkg})
        repo = _FakeGitRepo()

        with patch("uv_release.states.changes._find_baseline_tag", return_value=None):
            result = Changes.parse(
                workspace=ws,
                params=PlanParams(),
                git_repo=repo,  # type: ignore[arg-type]
            )

        assert len(result.items) == 1
        assert result.items[0].package.name == "mypkg"
        assert result.items[0].baseline is None
        assert result.items[0].reason == "initial release"
        assert result.items[0].commit_log == "initial release"


# ---------------------------------------------------------------------------
# all_packages
# ---------------------------------------------------------------------------


class TestAllPackages:
    """all_packages forces all packages dirty."""

    def test_all_packages_includes_unchanged(self) -> None:
        pkg_a = _package("a")
        pkg_b = _package("b")
        ws = _workspace({"a": pkg_a, "b": pkg_b})
        baseline_a = _baseline_tag("a", "1.0.0.dev0")
        baseline_b = _baseline_tag("b", "1.0.0.dev0")
        repo = _FakeGitRepo(changed_paths=set())

        def find_baseline(name: str, version: Version, repo_arg: object) -> Tag | None:
            return {"a": baseline_a, "b": baseline_b}.get(name)

        with patch(
            "uv_release.states.changes._find_baseline_tag",
            side_effect=find_baseline,
        ):
            result = Changes.parse(
                workspace=ws,
                params=PlanParams(all_packages=True),
                git_repo=repo,  # type: ignore[arg-type]
            )

        names = {c.package.name for c in result.items}
        assert names == {"a", "b"}
        reasons = {c.reason for c in result.items}
        assert "all packages" in reasons


# ---------------------------------------------------------------------------
# packages (specific packages)
# ---------------------------------------------------------------------------


class TestSelectedPackages:
    """packages selects specific packages."""

    def test_packages_selects_specific_package(self) -> None:
        pkg_a = _package("a")
        pkg_b = _package("b")
        ws = _workspace({"a": pkg_a, "b": pkg_b})
        baseline_a = _baseline_tag("a", "1.0.0.dev0")
        baseline_b = _baseline_tag("b", "1.0.0.dev0")
        repo = _FakeGitRepo(changed_paths=set())

        def find_baseline(name: str, version: Version, repo_arg: object) -> Tag | None:
            return {"a": baseline_a, "b": baseline_b}.get(name)

        with patch(
            "uv_release.states.changes._find_baseline_tag",
            side_effect=find_baseline,
        ):
            result = Changes.parse(
                workspace=ws,
                params=PlanParams(packages=frozenset({"a"})),
                git_repo=repo,  # type: ignore[arg-type]
            )

        names = {c.package.name for c in result.items}
        assert "a" in names
        forced = [c for c in result.items if c.package.name == "a"]
        assert forced[0].reason == "selected"


# ---------------------------------------------------------------------------
# packages filter
# ---------------------------------------------------------------------------


class TestPackagesFilter:
    """packages filters results to specified packages and their deps."""

    def test_restrict_filters_results(self) -> None:
        pkg_a = _package("a")
        pkg_b = _package("b")
        ws = _workspace({"a": pkg_a, "b": pkg_b})
        repo = _FakeGitRepo(changed_paths={"packages/a", "packages/b"})

        def find_baseline(name: str, version: Version, repo_arg: object) -> Tag | None:
            return _baseline_tag(name, "1.0.0.dev0")

        with patch(
            "uv_release.states.changes._find_baseline_tag",
            side_effect=find_baseline,
        ):
            result = Changes.parse(
                workspace=ws,
                params=PlanParams(packages=frozenset({"a"})),
                git_repo=repo,  # type: ignore[arg-type]
            )

        names = {c.package.name for c in result.items}
        assert names == {"a"}


# ---------------------------------------------------------------------------
# Dependency propagation
# ---------------------------------------------------------------------------


class TestDependencyPropagation:
    """If A is dirty and B depends on A, B becomes dirty."""

    def test_dependent_becomes_dirty(self) -> None:
        pkg_a = _package("a")
        pkg_b = _package("b", dependencies=["a"])
        ws = _workspace({"a": pkg_a, "b": pkg_b})
        baseline_a = _baseline_tag("a", "1.0.0.dev0")
        baseline_b = _baseline_tag("b", "1.0.0.dev0")
        repo = _FakeGitRepo(changed_paths={"packages/a"})

        def find_baseline(name: str, version: Version, repo_arg: object) -> Tag | None:
            return {"a": baseline_a, "b": baseline_b}.get(name)

        with patch(
            "uv_release.states.changes._find_baseline_tag",
            side_effect=find_baseline,
        ):
            result = Changes.parse(
                workspace=ws,
                params=PlanParams(),
                git_repo=repo,  # type: ignore[arg-type]
            )

        names = {c.package.name for c in result.items}
        assert "a" in names
        assert "b" in names
        b_change = [c for c in result.items if c.package.name == "b"][0]
        assert b_change.reason == "dependency changed"

    def test_independent_not_propagated(self) -> None:
        pkg_a = _package("a")
        pkg_b = _package("b")
        ws = _workspace({"a": pkg_a, "b": pkg_b})
        baseline_a = _baseline_tag("a", "1.0.0.dev0")
        baseline_b = _baseline_tag("b", "1.0.0.dev0")
        repo = _FakeGitRepo(changed_paths={"packages/a"})

        def find_baseline(name: str, version: Version, repo_arg: object) -> Tag | None:
            return {"a": baseline_a, "b": baseline_b}.get(name)

        with patch(
            "uv_release.states.changes._find_baseline_tag",
            side_effect=find_baseline,
        ):
            result = Changes.parse(
                workspace=ws,
                params=PlanParams(),
                git_repo=repo,  # type: ignore[arg-type]
            )

        names = {c.package.name for c in result.items}
        assert "a" in names
        assert "b" not in names

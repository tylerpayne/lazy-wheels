"""Tests for parse_changes with fake GitRepo."""

from __future__ import annotations

from unittest.mock import patch


from uv_release.states.changes import parse_changes
from uv_release.types import (
    Config,
    Package,
    Publishing,
    Tag,
    Version,
    Workspace,
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
    return Workspace(
        packages=packages,
        config=Config(uvr_version="0.1.0"),
        runners={},
        publishing=Publishing(),
    )


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
    """Minimal fake for GitRepo that satisfies parse_changes."""

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

        with (
            patch("uv_release.states.changes.GitRepo", return_value=repo),
            patch("uv_release.states.changes.find_baseline_tag", return_value=None),
        ):
            changes = parse_changes(ws)

        assert len(changes) == 1
        assert changes[0].package.name == "mypkg"
        assert changes[0].baseline is None
        assert changes[0].reason == "initial release"
        assert changes[0].commit_log == "initial release"


# ---------------------------------------------------------------------------
# rebuild_all
# ---------------------------------------------------------------------------


class TestRebuildAll:
    """rebuild_all forces all packages dirty."""

    def test_rebuild_all_includes_unchanged(self) -> None:
        pkg_a = _package("a")
        pkg_b = _package("b")
        ws = _workspace({"a": pkg_a, "b": pkg_b})
        baseline_a = _baseline_tag("a", "1.0.0.dev0")
        baseline_b = _baseline_tag("b", "1.0.0.dev0")
        repo = _FakeGitRepo(changed_paths=set())

        def find_baseline(name: str, version: Version, repo_arg: object) -> Tag | None:
            return {"a": baseline_a, "b": baseline_b}.get(name)

        with (
            patch("uv_release.states.changes.GitRepo", return_value=repo),
            patch(
                "uv_release.states.changes.find_baseline_tag",
                side_effect=find_baseline,
            ),
        ):
            changes = parse_changes(ws, rebuild_all=True)

        names = {c.package.name for c in changes}
        assert names == {"a", "b"}
        reasons = {c.reason for c in changes}
        assert "rebuild all" in reasons


# ---------------------------------------------------------------------------
# rebuild (specific packages)
# ---------------------------------------------------------------------------


class TestRebuildSpecific:
    """rebuild forces specific packages dirty."""

    def test_rebuild_forces_specific_package(self) -> None:
        pkg_a = _package("a")
        pkg_b = _package("b")
        ws = _workspace({"a": pkg_a, "b": pkg_b})
        baseline_a = _baseline_tag("a", "1.0.0.dev0")
        baseline_b = _baseline_tag("b", "1.0.0.dev0")
        repo = _FakeGitRepo(changed_paths=set())

        def find_baseline(name: str, version: Version, repo_arg: object) -> Tag | None:
            return {"a": baseline_a, "b": baseline_b}.get(name)

        with (
            patch("uv_release.states.changes.GitRepo", return_value=repo),
            patch(
                "uv_release.states.changes.find_baseline_tag",
                side_effect=find_baseline,
            ),
        ):
            changes = parse_changes(ws, rebuild=frozenset({"a"}))

        names = {c.package.name for c in changes}
        assert "a" in names
        forced = [c for c in changes if c.package.name == "a"]
        assert forced[0].reason == "forced rebuild"


# ---------------------------------------------------------------------------
# restrict_packages
# ---------------------------------------------------------------------------


class TestRestrictPackages:
    """restrict_packages filters results to specified packages and their deps."""

    def test_restrict_filters_results(self) -> None:
        pkg_a = _package("a")
        pkg_b = _package("b")
        ws = _workspace({"a": pkg_a, "b": pkg_b})
        repo = _FakeGitRepo(changed_paths={"packages/a", "packages/b"})

        def find_baseline(name: str, version: Version, repo_arg: object) -> Tag | None:
            return _baseline_tag(name, "1.0.0.dev0")

        with (
            patch("uv_release.states.changes.GitRepo", return_value=repo),
            patch(
                "uv_release.states.changes.find_baseline_tag",
                side_effect=find_baseline,
            ),
        ):
            changes = parse_changes(ws, restrict_packages=frozenset({"a"}))

        names = {c.package.name for c in changes}
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

        with (
            patch("uv_release.states.changes.GitRepo", return_value=repo),
            patch(
                "uv_release.states.changes.find_baseline_tag",
                side_effect=find_baseline,
            ),
        ):
            changes = parse_changes(ws)

        names = {c.package.name for c in changes}
        assert "a" in names
        assert "b" in names
        b_change = [c for c in changes if c.package.name == "b"][0]
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

        with (
            patch("uv_release.states.changes.GitRepo", return_value=repo),
            patch(
                "uv_release.states.changes.find_baseline_tag",
                side_effect=find_baseline,
            ),
        ):
            changes = parse_changes(ws)

        names = {c.package.name for c in changes}
        assert "a" in names
        assert "b" not in names

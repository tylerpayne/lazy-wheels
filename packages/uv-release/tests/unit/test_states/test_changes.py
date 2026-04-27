"""Tests for Changes.parse with fake GitRepo."""

from __future__ import annotations

from unittest.mock import patch


from uv_release.states.changes import parse_changes
from uv_release.types import (
    PlanParams,
    Tag,
    Version,
)

from ..conftest import FakeGitRepo, make_package, make_version, make_workspace


def _baseline_tag(name: str, version: str) -> Tag:
    v = make_version(version)
    return Tag(
        package_name=name,
        raw=Tag.baseline_tag_name(name, v),
        version=v,
        is_baseline=True,
        commit="baseline_sha",
    )


# ---------------------------------------------------------------------------
# Initial release (no baseline)
# ---------------------------------------------------------------------------


class TestInitialRelease:
    """Package with no baseline detected as initial release."""

    def test_no_baseline_is_initial_release(self) -> None:
        pkg = make_package("mypkg")
        ws = make_workspace({"mypkg": pkg})
        repo = FakeGitRepo()

        with patch("uv_release.states.changes._find_baseline_tag", return_value=None):
            result = parse_changes(
                workspace=ws,
                params=PlanParams(),
                git_repo=repo,
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
        pkg_a = make_package("a")
        pkg_b = make_package("b")
        ws = make_workspace({"a": pkg_a, "b": pkg_b})
        baseline_a = _baseline_tag("a", "1.0.0.dev0")
        baseline_b = _baseline_tag("b", "1.0.0.dev0")
        repo = FakeGitRepo(changed_paths=set())

        def find_baseline(name: str, version: Version, repo_arg: object) -> Tag | None:
            return {"a": baseline_a, "b": baseline_b}.get(name)

        with patch(
            "uv_release.states.changes._find_baseline_tag",
            side_effect=find_baseline,
        ):
            result = parse_changes(
                workspace=ws,
                params=PlanParams(all_packages=True),
                git_repo=repo,
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
        pkg_a = make_package("a")
        pkg_b = make_package("b")
        ws = make_workspace({"a": pkg_a, "b": pkg_b})
        baseline_a = _baseline_tag("a", "1.0.0.dev0")
        baseline_b = _baseline_tag("b", "1.0.0.dev0")
        repo = FakeGitRepo(changed_paths=set())

        def find_baseline(name: str, version: Version, repo_arg: object) -> Tag | None:
            return {"a": baseline_a, "b": baseline_b}.get(name)

        with patch(
            "uv_release.states.changes._find_baseline_tag",
            side_effect=find_baseline,
        ):
            result = parse_changes(
                workspace=ws,
                params=PlanParams(packages=frozenset({"a"})),
                git_repo=repo,
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
        pkg_a = make_package("a")
        pkg_b = make_package("b")
        ws = make_workspace({"a": pkg_a, "b": pkg_b})
        repo = FakeGitRepo(changed_paths={"packages/a", "packages/b"})

        def find_baseline(name: str, version: Version, repo_arg: object) -> Tag | None:
            return _baseline_tag(name, "1.0.0.dev0")

        with patch(
            "uv_release.states.changes._find_baseline_tag",
            side_effect=find_baseline,
        ):
            result = parse_changes(
                workspace=ws,
                params=PlanParams(packages=frozenset({"a"})),
                git_repo=repo,
            )

        names = {c.package.name for c in result.items}
        assert names == {"a"}


# ---------------------------------------------------------------------------
# Dependency propagation
# ---------------------------------------------------------------------------


class TestDependencyPropagation:
    """If A is dirty and B depends on A, B becomes dirty."""

    def test_dependent_becomes_dirty(self) -> None:
        pkg_a = make_package("a")
        pkg_b = make_package("b", dependencies=["a"])
        ws = make_workspace({"a": pkg_a, "b": pkg_b})
        baseline_a = _baseline_tag("a", "1.0.0.dev0")
        baseline_b = _baseline_tag("b", "1.0.0.dev0")
        repo = FakeGitRepo(changed_paths={"packages/a"})

        def find_baseline(name: str, version: Version, repo_arg: object) -> Tag | None:
            return {"a": baseline_a, "b": baseline_b}.get(name)

        with patch(
            "uv_release.states.changes._find_baseline_tag",
            side_effect=find_baseline,
        ):
            result = parse_changes(
                workspace=ws,
                params=PlanParams(),
                git_repo=repo,
            )

        names = {c.package.name for c in result.items}
        assert "a" in names
        assert "b" in names
        b_change = [c for c in result.items if c.package.name == "b"][0]
        assert b_change.reason == "dependency changed"

    def test_independent_not_propagated(self) -> None:
        pkg_a = make_package("a")
        pkg_b = make_package("b")
        ws = make_workspace({"a": pkg_a, "b": pkg_b})
        baseline_a = _baseline_tag("a", "1.0.0.dev0")
        baseline_b = _baseline_tag("b", "1.0.0.dev0")
        repo = FakeGitRepo(changed_paths={"packages/a"})

        def find_baseline(name: str, version: Version, repo_arg: object) -> Tag | None:
            return {"a": baseline_a, "b": baseline_b}.get(name)

        with patch(
            "uv_release.states.changes._find_baseline_tag",
            side_effect=find_baseline,
        ):
            result = parse_changes(
                workspace=ws,
                params=PlanParams(),
                git_repo=repo,
            )

        names = {c.package.name for c in result.items}
        assert "a" in names
        assert "b" not in names

"""Tests for dependency propagation of dirtiness."""

from __future__ import annotations

from uv_release.detect.propagation import propagate_dirtiness
from uv_release.types import Package, Version


def _pkg(
    name: str, deps: list[str] | None = None, version: str = "1.0.0.dev0"
) -> Package:
    return Package(
        name=name,
        path=f"packages/{name}",
        version=Version.parse(version),
        deps=deps or [],
    )


class TestPropagateDirtiness:
    """BFS propagation through workspace dependency graph."""

    def test_dependent_becomes_dirty_when_dependency_is_dirty(self) -> None:
        """A depends on B, B dirty -> A also dirty."""
        packages = {
            "a": _pkg("a", deps=["b"]),
            "b": _pkg("b"),
        }
        result = propagate_dirtiness({"b"}, packages)
        assert result == {"a", "b"}

    def test_dependent_stays_clean_when_dependency_is_clean(self) -> None:
        """A depends on B, B clean -> A stays clean."""
        packages = {
            "a": _pkg("a", deps=["b"]),
            "b": _pkg("b"),
        }
        result = propagate_dirtiness(set(), packages)
        assert result == set()

    def test_diamond_propagation(self) -> None:
        """Diamond: D->B->A, D->C->A, A dirty -> all dirty."""
        packages = {
            "a": _pkg("a"),
            "b": _pkg("b", deps=["a"]),
            "c": _pkg("c", deps=["a"]),
            "d": _pkg("d", deps=["b", "c"]),
        }
        result = propagate_dirtiness({"a"}, packages)
        assert result == {"a", "b", "c", "d"}

    def test_post_release_packages_do_not_propagate(self) -> None:
        """Post-release packages are dirty themselves but do not propagate to dependents."""
        packages = {
            "a": _pkg("a", version="1.0.0.post0"),
            "b": _pkg("b", deps=["a"]),
        }
        result = propagate_dirtiness({"a"}, packages)
        assert result == {"a"}

    def test_no_deps_means_no_propagation(self) -> None:
        """Independent packages: only the originally dirty one stays dirty."""
        packages = {
            "a": _pkg("a"),
            "b": _pkg("b"),
            "c": _pkg("c"),
        }
        result = propagate_dirtiness({"a"}, packages)
        assert result == {"a"}

    def test_transitive_propagation(self) -> None:
        """A->B->C, C dirty -> B and A also dirty (transitive)."""
        packages = {
            "a": _pkg("a", deps=["b"]),
            "b": _pkg("b", deps=["c"]),
            "c": _pkg("c"),
        }
        result = propagate_dirtiness({"c"}, packages)
        assert result == {"a", "b", "c"}

    def test_dirty_name_not_in_packages(self) -> None:
        """A dirty name that isn't in the packages dict is silently skipped."""
        packages = {"a": _pkg("a")}
        result = propagate_dirtiness({"nonexistent", "a"}, packages)
        assert "nonexistent" in result  # stays dirty
        assert "a" in result

    def test_empty_packages(self) -> None:
        """Empty packages dict returns empty set."""
        result = propagate_dirtiness(set(), {})
        assert result == set()

    def test_multiple_dirty_roots(self) -> None:
        """Multiple dirty roots propagate independently."""
        packages = {
            "a": _pkg("a"),
            "b": _pkg("b"),
            "c": _pkg("c", deps=["a"]),
            "d": _pkg("d", deps=["b"]),
        }
        result = propagate_dirtiness({"a", "b"}, packages)
        assert result == {"a", "b", "c", "d"}

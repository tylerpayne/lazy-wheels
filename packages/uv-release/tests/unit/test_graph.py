"""Tests for topological layer assignment."""

from __future__ import annotations

import pytest

from uv_release.utils.graph import compute_ancestors, topo_layers, topo_sort
from uv_release.types import Package, Version


def _pkg(name: str, dependencies: list[str] | None = None) -> Package:
    return Package(
        name=name,
        path=f"packages/{name}",
        version=Version.parse("1.0.0"),
        dependencies=dependencies or [],
    )


class TestTopoLayers:
    def test_diamond_deps(self) -> None:
        """A→B→D, A→C→D produces 3 layers."""
        pkgs = {
            "a": _pkg("a"),
            "b": _pkg("b", dependencies=["a"]),
            "c": _pkg("c", dependencies=["a"]),
            "d": _pkg("d", dependencies=["b", "c"]),
        }
        layers = topo_layers(pkgs)
        assert layers["a"] == 0
        assert layers["b"] == 1
        assert layers["c"] == 1
        assert layers["d"] == 2

    def test_independent_packages(self) -> None:
        """Independent packages all land in layer 0."""
        pkgs = {
            "a": _pkg("a"),
            "b": _pkg("b"),
            "c": _pkg("c"),
        }
        layers = topo_layers(pkgs)
        assert layers == {"a": 0, "b": 0, "c": 0}

    def test_linear_chain(self) -> None:
        """A→B→C produces 3 layers."""
        pkgs = {
            "a": _pkg("a"),
            "b": _pkg("b", dependencies=["a"]),
            "c": _pkg("c", dependencies=["b"]),
        }
        layers = topo_layers(pkgs)
        assert layers["a"] == 0
        assert layers["b"] == 1
        assert layers["c"] == 2

    def test_cycle_raises(self) -> None:
        """Cycle detection raises RuntimeError."""
        pkgs = {
            "a": _pkg("a", dependencies=["b"]),
            "b": _pkg("b", dependencies=["a"]),
        }
        with pytest.raises(RuntimeError):
            topo_layers(pkgs)

    def test_single_package(self) -> None:
        """Single package is layer 0."""
        pkgs = {"a": _pkg("a")}
        assert topo_layers(pkgs) == {"a": 0}

    def test_empty_input(self) -> None:
        """Empty input returns empty output."""
        assert topo_layers({}) == {}


class TestTopoSort:
    def test_empty_input(self) -> None:
        assert topo_sort({}) == []

    def test_cycle_raises(self) -> None:
        with pytest.raises(RuntimeError, match="cycle"):
            topo_sort({"a": ["b"], "b": ["a"]})


class TestComputeAncestors:
    """Tests for compute_ancestors (strict ancestor set via BFS)."""

    def test_linear_chain(self) -> None:
        dag = {
            "validate": [],
            "build": ["validate"],
            "release": ["build"],
            "publish": ["release"],
            "bump": ["publish"],
        }
        assert compute_ancestors(dag, "release") == {"validate", "build"}

    def test_custom_job_in_chain(self) -> None:
        dag = {
            "validate": [],
            "checks": ["validate"],
            "build": ["validate", "checks"],
            "release": ["build"],
        }
        assert compute_ancestors(dag, "build") == {"validate", "checks"}

    def test_root_node_has_no_ancestors(self) -> None:
        dag = {"validate": [], "build": ["validate"]}
        assert compute_ancestors(dag, "validate") == set()

    def test_target_not_in_dag_raises(self) -> None:
        dag = {"validate": [], "build": ["validate"]}
        with pytest.raises(KeyError):
            compute_ancestors(dag, "nonexistent")

    def test_diamond_dag(self) -> None:
        dag = {
            "validate": [],
            "build": ["validate"],
            "scan": ["validate"],
            "release": ["build", "scan"],
        }
        assert compute_ancestors(dag, "release") == {"validate", "build", "scan"}

    def test_parallel_branch_not_included(self) -> None:
        """A job on a parallel branch is not an ancestor of the target."""
        dag = {
            "validate": [],
            "build": ["validate"],
            "scan": ["build"],
            "release": ["build"],
            "publish": ["release"],
        }
        assert compute_ancestors(dag, "release") == {"validate", "build"}
        assert "scan" not in compute_ancestors(dag, "release")

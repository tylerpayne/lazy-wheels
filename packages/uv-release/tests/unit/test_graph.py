"""Tests for topological layer assignment."""

from __future__ import annotations

import pytest

from uv_release.utils.graph import topo_layers, topo_sort
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

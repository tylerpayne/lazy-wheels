"""Tests for uv_release_monorepo.graph."""

from __future__ import annotations

import pytest

from uv_release_monorepo.shared.graph import topo_layers, topo_sort
from uv_release_monorepo.shared.models import PackageInfo


class TestTopoSort:
    def test_no_deps(self) -> None:
        packages = {
            "a": PackageInfo(path="a", version="1.0.0"),
            "b": PackageInfo(path="b", version="1.0.0"),
            "c": PackageInfo(path="c", version="1.0.0"),
        }
        result = topo_sort(packages)
        assert set(result) == {"a", "b", "c"}
        assert result == ["a", "b", "c"]  # alphabetical when no deps

    def test_linear_deps(self) -> None:
        packages = {
            "a": PackageInfo(path="a", version="1.0.0", deps=["b"]),
            "b": PackageInfo(path="b", version="1.0.0", deps=["c"]),
            "c": PackageInfo(path="c", version="1.0.0"),
        }
        result = topo_sort(packages)
        assert result.index("c") < result.index("b")
        assert result.index("b") < result.index("a")

    def test_diamond_deps(self) -> None:
        packages = {
            "top": PackageInfo(path="top", version="1.0.0", deps=["left", "right"]),
            "left": PackageInfo(path="left", version="1.0.0", deps=["bottom"]),
            "right": PackageInfo(path="right", version="1.0.0", deps=["bottom"]),
            "bottom": PackageInfo(path="bottom", version="1.0.0"),
        }
        result = topo_sort(packages)
        assert result.index("bottom") < result.index("left")
        assert result.index("bottom") < result.index("right")
        assert result.index("left") < result.index("top")
        assert result.index("right") < result.index("top")

    def test_single_package(self) -> None:
        packages = {"only": PackageInfo(path="only", version="1.0.0")}
        assert topo_sort(packages) == ["only"]

    def test_empty_packages(self) -> None:
        assert topo_sort({}) == []

    def test_cycle_raises(self) -> None:
        packages = {
            "a": PackageInfo(path="a", version="1.0.0", deps=["b"]),
            "b": PackageInfo(path="b", version="1.0.0", deps=["a"]),
        }
        with pytest.raises(RuntimeError, match="cycle"):
            topo_sort(packages)

    def test_three_way_cycle_raises(self) -> None:
        packages = {
            "a": PackageInfo(path="a", version="1.0.0", deps=["b"]),
            "b": PackageInfo(path="b", version="1.0.0", deps=["c"]),
            "c": PackageInfo(path="c", version="1.0.0", deps=["a"]),
        }
        with pytest.raises(RuntimeError, match="cycle"):
            topo_sort(packages)

    def test_external_deps_ignored(self) -> None:
        """Dependencies outside the packages dict are ignored.

        This happens when sorting only changed packages - they may depend on
        unchanged packages that aren't in the dict.
        """
        packages = {
            "a": PackageInfo(path="a", version="1.0.0", deps=["external"]),
            "b": PackageInfo(path="b", version="1.0.0", deps=["a"]),
        }
        # Should not raise KeyError for "external"
        result = topo_sort(packages)
        assert result.index("a") < result.index("b")


class TestTopoLayers:
    def test_no_deps(self) -> None:
        packages = {
            "a": PackageInfo(path="a", version="1.0.0"),
            "b": PackageInfo(path="b", version="1.0.0"),
            "c": PackageInfo(path="c", version="1.0.0"),
        }
        layers = topo_layers(packages)
        assert layers == {"a": 0, "b": 0, "c": 0}

    def test_linear_chain(self) -> None:
        packages = {
            "a": PackageInfo(path="a", version="1.0.0", deps=["b"]),
            "b": PackageInfo(path="b", version="1.0.0", deps=["c"]),
            "c": PackageInfo(path="c", version="1.0.0"),
        }
        layers = topo_layers(packages)
        assert layers == {"c": 0, "b": 1, "a": 2}

    def test_diamond_deps(self) -> None:
        packages = {
            "top": PackageInfo(path="top", version="1.0.0", deps=["left", "right"]),
            "left": PackageInfo(path="left", version="1.0.0", deps=["bottom"]),
            "right": PackageInfo(path="right", version="1.0.0", deps=["bottom"]),
            "bottom": PackageInfo(path="bottom", version="1.0.0"),
        }
        layers = topo_layers(packages)
        assert layers["bottom"] == 0
        assert layers["left"] == 1
        assert layers["right"] == 1
        assert layers["top"] == 2

    def test_external_deps_ignored(self) -> None:
        packages = {
            "a": PackageInfo(path="a", version="1.0.0", deps=["external"]),
            "b": PackageInfo(path="b", version="1.0.0", deps=["a"]),
        }
        layers = topo_layers(packages)
        assert layers == {"a": 0, "b": 1}

    def test_single_package(self) -> None:
        assert topo_layers({"x": PackageInfo(path="x", version="1.0.0")}) == {"x": 0}

    def test_empty(self) -> None:
        assert topo_layers({}) == {}

    def test_cycle_raises(self) -> None:
        packages = {
            "a": PackageInfo(path="a", version="1.0.0", deps=["b"]),
            "b": PackageInfo(path="b", version="1.0.0", deps=["a"]),
        }
        with pytest.raises(RuntimeError, match="cycle"):
            topo_layers(packages)

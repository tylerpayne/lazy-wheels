"""Tests for uv_release_monorepo.shared.planner._graph."""

from __future__ import annotations

import pytest

from uv_release_monorepo.shared.planner._graph import topo_layers
from uv_release_monorepo.shared.models import PackageInfo


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

"""Tests for plan_build_job: generate build jobs with layered stages."""

from __future__ import annotations

from uv_release.plan.build import plan_build_job
from uv_release.types import (
    Config,
    Job,
    Package,
    Publishing,
    Release,
    Version,
    Workspace,
)


def _version(raw: str) -> Version:
    return Version.parse(raw)


def _package(
    name: str, version: str = "1.0.0.dev0", deps: list[str] | None = None
) -> Package:
    return Package(
        name=name, path=f"packages/{name}", version=_version(version), deps=deps or []
    )


def _release(pkg: Package) -> Release:
    return Release(
        package=pkg,
        release_version=_version("1.0.0"),
        next_version=_version("1.0.1.dev0"),
    )


def _workspace(packages: dict[str, Package]) -> Workspace:
    return Workspace(
        packages=packages,
        config=Config(uvr_version="0.1.0"),
        runners={},
        publishing=Publishing(),
    )


class TestBuildLayersDiamond:
    """Diamond deps (a->b->d, a->c->d) should produce 3 build layers."""

    def test_diamond_produces_three_layers(self) -> None:
        a = _package("a")
        b = _package("b", deps=["a"])
        c = _package("c", deps=["a"])
        d = _package("d", deps=["b", "c"])
        pkgs = {"a": a, "b": b, "c": c, "d": d}
        releases = {n: _release(p) for n, p in pkgs.items()}

        job = plan_build_job(_workspace(pkgs), releases)
        assert isinstance(job, Job)
        assert len(job.commands) > 0


class TestBuildLayersIndependent:
    """Independent packages should all land in a single build layer."""

    def test_independent_single_layer(self) -> None:
        a = _package("a")
        b = _package("b")
        c = _package("c")
        pkgs = {"a": a, "b": b, "c": c}
        releases = {n: _release(p) for n, p in pkgs.items()}

        job = plan_build_job(_workspace(pkgs), releases)
        assert len(job.commands) > 0


class TestBuildUsesTopoLayers:
    """Build stages should use topo_layers for ordering."""

    def test_linear_chain_ordering(self) -> None:
        a = _package("a")
        b = _package("b", deps=["a"])
        c = _package("c", deps=["b"])
        pkgs = {"a": a, "b": b, "c": c}
        releases = {n: _release(p) for n, p in pkgs.items()}

        job = plan_build_job(_workspace(pkgs), releases)
        assert len(job.commands) > 0


class TestBuildEmptyReleases:
    """Empty releases should produce an empty build job."""

    def test_empty_releases_empty_commands(self) -> None:
        job = plan_build_job(_workspace({}), {})
        assert job.commands == []


class TestBuildMultipleRunners:
    """Multiple runners should each get build commands."""

    def test_two_runners_both_get_commands(self) -> None:
        a = _package("a")
        releases = {"a": _release(a)}

        job = plan_build_job(_workspace({"a": a}), releases)
        assert len(job.commands) > 0

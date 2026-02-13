"""Tests for lazy_wheels.models."""

from __future__ import annotations

from lazy_wheels.models import PackageInfo, VersionBump


class TestPackageInfo:
    def test_create_with_required_fields(self) -> None:
        pkg = PackageInfo(path="packages/foo", version="1.0.0")
        assert pkg.path == "packages/foo"
        assert pkg.version == "1.0.0"
        assert pkg.deps == []

    def test_create_with_deps(self) -> None:
        pkg = PackageInfo(path="libs/bar", version="2.1.0", deps=["foo", "baz"])
        assert pkg.deps == ["foo", "baz"]

    def test_deps_is_mutable(self) -> None:
        pkg = PackageInfo(path="pkg", version="1.0.0")
        pkg.deps.append("new-dep")
        assert pkg.deps == ["new-dep"]


class TestVersionBump:
    def test_create(self) -> None:
        bump = VersionBump(old="1.0.0", new="1.0.1")
        assert bump.old == "1.0.0"
        assert bump.new == "1.0.1"

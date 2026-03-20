"""Tests for uv_release_monorepo.models."""

from __future__ import annotations

from uv_release_monorepo.models import (
    MatrixEntry,
    PackageInfo,
    ReleasePlan,
    VersionBump,
)


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


class TestMatrixEntry:
    def test_create(self) -> None:
        entry = MatrixEntry(package="pkg-alpha", runner="ubuntu-latest")
        assert entry.package == "pkg-alpha"
        assert entry.runner == "ubuntu-latest"


class TestReleasePlan:
    def _make_plan(self) -> ReleasePlan:
        alpha = PackageInfo(path="packages/alpha", version="0.1.5", deps=[])
        beta = PackageInfo(path="packages/beta", version="0.2.0", deps=["pkg-alpha"])
        return ReleasePlan(
            uvr_version="0.3.0",
            force_all=False,
            changed={"pkg-alpha": alpha},
            unchanged={"pkg-beta": beta},
            release_tags={
                "pkg-alpha": "pkg-alpha/v0.1.4",
                "pkg-beta": "pkg-beta/v0.1.9",
            },
            matrix=[MatrixEntry(package="pkg-alpha", runner="ubuntu-latest")],
        )

    def test_schema_version_defaults_to_2(self) -> None:
        plan = self._make_plan()
        assert plan.schema_version == 2

    def test_round_trip_json(self) -> None:
        plan = self._make_plan()
        restored = ReleasePlan.model_validate_json(plan.model_dump_json())
        assert restored.uvr_version == plan.uvr_version
        assert restored.changed["pkg-alpha"].version == "0.1.5"
        assert restored.unchanged["pkg-beta"].version == "0.2.0"
        assert restored.matrix[0].package == "pkg-alpha"
        assert restored.matrix[0].runner == "ubuntu-latest"

    def test_matrix_shape_matches_gha_include(self) -> None:
        """matrix entries serialize as {package, runner} dicts for GHA fromJSON."""
        plan = self._make_plan()
        data = plan.model_dump()
        assert data["matrix"] == [{"package": "pkg-alpha", "runner": "ubuntu-latest"}]

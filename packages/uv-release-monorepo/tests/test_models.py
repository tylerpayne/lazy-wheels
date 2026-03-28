"""Tests for uv_release_monorepo.models."""

from __future__ import annotations

from uv_release_monorepo.shared.models import (
    ChangedPackage,
    PackageInfo,
    ReleasePlan,
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


class TestReleasePlan:
    def _make_plan(self) -> ReleasePlan:
        alpha = ChangedPackage(
            path="packages/alpha",
            version="0.1.5",
            deps=[],
            current_version="0.1.5.dev0",
            release_version="0.1.5",
            next_version="0.1.6.dev0",
            runners=[["ubuntu-latest"]],
        )
        beta = PackageInfo(path="packages/beta", version="0.2.0", deps=["pkg-alpha"])
        return ReleasePlan(
            uvr_version="0.3.0",
            rebuild_all=False,
            changed={"pkg-alpha": alpha},
            unchanged={"pkg-beta": beta},
        )

    def test_schema_version_defaults_to_9(self) -> None:
        plan = self._make_plan()
        assert plan.schema_version == 9

    def test_extra_keys_survive_round_trip(self) -> None:
        plan = self._make_plan()
        data = plan.model_dump()
        data["deploy_env"] = "staging"
        data["custom_flags"] = {"notify": True}

        restored = ReleasePlan.model_validate(data)
        assert restored.model_extra is not None
        assert restored.model_extra["deploy_env"] == "staging"

        # JSON round-trip
        json_str = restored.model_dump_json()
        final = ReleasePlan.model_validate_json(json_str)
        assert final.model_extra is not None
        assert final.model_extra["deploy_env"] == "staging"
        assert final.model_extra["custom_flags"] == {"notify": True}

    def test_round_trip_json(self) -> None:
        plan = self._make_plan()
        restored = ReleasePlan.model_validate_json(plan.model_dump_json())
        assert restored.uvr_version == plan.uvr_version
        assert restored.changed["pkg-alpha"].version == "0.1.5"
        assert restored.unchanged["pkg-beta"].version == "0.2.0"

    def test_build_matrix_shape(self) -> None:
        """build_matrix serializes as list of runner label sets."""
        plan = self._make_plan()
        data = plan.model_dump()
        assert data["build_matrix"] == [["ubuntu-latest"]]

    def test_release_matrix_shape(self) -> None:
        """release_matrix serializes as list of dicts for GHA fromJSON."""
        plan = self._make_plan()
        data = plan.model_dump()
        assert len(data["release_matrix"]) == 1
        entry = data["release_matrix"][0]
        assert entry["package"] == "pkg-alpha"
        assert entry["tag"] == "pkg-alpha/v0.1.5"

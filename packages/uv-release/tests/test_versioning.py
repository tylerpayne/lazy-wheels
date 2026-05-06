"""Tests for version computation: release versions, next versions, bumps, pins."""

from __future__ import annotations

import pytest

from uv_release.types.bump_kind import BumpKind
from uv_release.types.dependency import Dependency
from uv_release.types.package import Package
from uv_release.types.version import Version
from uv_release.utils.versioning import (
    compute_bumped_version,
    compute_dependency_pins,
    compute_next_version,
    compute_release_version,
)

_d = Dependency.parse


class TestComputeReleaseVersion:
    def test_dev_release_from_dev(self) -> None:
        assert (
            compute_release_version(Version.parse("1.0.0.dev3"), dev_release=True).raw
            == "1.0.0.dev3"
        )

    def test_dev_release_from_stable_errors(self) -> None:
        with pytest.raises(ValueError, match="Cannot do a dev release"):
            compute_release_version(Version.parse("1.0.0"), dev_release=True)

    def test_stable_release_strips_dev(self) -> None:
        assert compute_release_version(Version.parse("1.0.0.dev3")).raw == "1.0.0"

    def test_stable_release_from_stable_is_noop(self) -> None:
        assert compute_release_version(Version.parse("1.0.0")).raw == "1.0.0"

    def test_pre_dev_strips_dev(self) -> None:
        assert compute_release_version(Version.parse("1.0.0a2.dev0")).raw == "1.0.0a2"


class TestComputeNextVersion:
    def test_dev_release_increments_dev(self) -> None:
        assert (
            compute_next_version(Version.parse("1.0.0.dev3"), dev_release=True).raw
            == "1.0.0.dev4"
        )

    def test_dev_release_from_stable_errors(self) -> None:
        with pytest.raises(ValueError, match="Cannot compute next dev"):
            compute_next_version(Version.parse("1.0.0"), dev_release=True)

    def test_stable_advances_patch(self) -> None:
        assert compute_next_version(Version.parse("1.2.3")).raw == "1.2.4.dev0"

    def test_pre_release_advances_pre(self) -> None:
        assert compute_next_version(Version.parse("1.0.0a2")).raw == "1.0.0a3.dev0"

    def test_post_release_advances_post(self) -> None:
        assert (
            compute_next_version(Version.parse("1.0.0.post1")).raw == "1.0.0.post2.dev0"
        )

    def test_rc_advances_rc(self) -> None:
        assert compute_next_version(Version.parse("1.0.0rc0")).raw == "1.0.0rc1.dev0"

    def test_beta_advances_beta(self) -> None:
        assert compute_next_version(Version.parse("2.0.0b5")).raw == "2.0.0b6.dev0"


class TestComputeBumpedVersion:
    # --- Major/Minor/Patch ---
    def test_major(self) -> None:
        assert (
            compute_bumped_version(Version.parse("1.2.3"), BumpKind.MAJOR).raw
            == "2.0.0.dev0"
        )

    def test_minor(self) -> None:
        assert (
            compute_bumped_version(Version.parse("1.2.3"), BumpKind.MINOR).raw
            == "1.3.0.dev0"
        )

    def test_patch(self) -> None:
        assert (
            compute_bumped_version(Version.parse("1.2.3"), BumpKind.PATCH).raw
            == "1.2.4.dev0"
        )

    # --- Stable ---
    def test_stable_strips_dev(self) -> None:
        assert (
            compute_bumped_version(Version.parse("1.0.0.dev5"), BumpKind.STABLE).raw
            == "1.0.0"
        )

    def test_stable_strips_pre(self) -> None:
        assert (
            compute_bumped_version(Version.parse("1.0.0a3"), BumpKind.STABLE).raw
            == "1.0.0"
        )

    def test_stable_keeps_post(self) -> None:
        assert (
            compute_bumped_version(Version.parse("1.0.0.post2"), BumpKind.STABLE).raw
            == "1.0.0.post2"
        )

    # --- Dev ---
    def test_dev_increment(self) -> None:
        assert (
            compute_bumped_version(Version.parse("1.0.0.dev3"), BumpKind.DEV).raw
            == "1.0.0.dev4"
        )

    def test_dev_from_stable(self) -> None:
        assert (
            compute_bumped_version(Version.parse("1.0.0"), BumpKind.DEV).raw
            == "1.0.0.dev0"
        )

    # --- Post ---
    def test_post_from_stable(self) -> None:
        assert (
            compute_bumped_version(Version.parse("1.0.0"), BumpKind.POST).raw
            == "1.0.0.post0.dev0"
        )

    def test_post_increment(self) -> None:
        assert (
            compute_bumped_version(Version.parse("1.0.0.post2"), BumpKind.POST).raw
            == "1.0.0.post3.dev0"
        )

    def test_post_from_pre_errors(self) -> None:
        with pytest.raises(ValueError, match="Cannot bump post from pre-release"):
            compute_bumped_version(Version.parse("1.0.0a1"), BumpKind.POST)

    def test_post_from_dev_errors(self) -> None:
        with pytest.raises(ValueError, match="Cannot bump post from dev"):
            compute_bumped_version(Version.parse("1.0.0.dev0"), BumpKind.POST)

    # --- Auto: increment last section ---
    def test_auto_dev(self) -> None:
        v = compute_bumped_version(Version.parse("1.0.0.dev3"), BumpKind.AUTO)
        assert v.raw == "1.0.0.dev4"

    def test_auto_pre_dev(self) -> None:
        v = compute_bumped_version(Version.parse("1.0.0a2.dev0"), BumpKind.AUTO)
        assert v.raw == "1.0.0a2.dev1"

    def test_auto_alpha(self) -> None:
        v = compute_bumped_version(Version.parse("1.0.0a2"), BumpKind.AUTO)
        assert v.raw == "1.0.0a3"

    def test_auto_beta(self) -> None:
        v = compute_bumped_version(Version.parse("1.0.0b1"), BumpKind.AUTO)
        assert v.raw == "1.0.0b2"

    def test_auto_rc(self) -> None:
        v = compute_bumped_version(Version.parse("1.0.0rc2"), BumpKind.AUTO)
        assert v.raw == "1.0.0rc3"

    def test_auto_post(self) -> None:
        v = compute_bumped_version(Version.parse("1.0.0.post1"), BumpKind.AUTO)
        assert v.raw == "1.0.0.post2"

    def test_auto_stable(self) -> None:
        v = compute_bumped_version(Version.parse("1.0.0"), BumpKind.AUTO)
        assert v.raw == "1.0.1"

    def test_auto_post_dev(self) -> None:
        v = compute_bumped_version(Version.parse("1.0.0.post1.dev3"), BumpKind.AUTO)
        assert v.raw == "1.0.0.post1.dev4"


class TestComputeDependencyPins:
    def test_pins_internal_dep(self) -> None:
        versions = {"pkg-a": Version.parse("2.0.0")}
        packages = {
            "pkg-a": Package(
                name="pkg-a", path="packages/pkg-a", version=Version.parse("2.0.0")
            ),
            "pkg-b": Package(
                name="pkg-b",
                path="packages/pkg-b",
                version=Version.parse("1.0.0"),
                dependencies=[_d("pkg-a")],
            ),
        }
        pins = compute_dependency_pins(versions, packages)
        assert len(pins) == 1
        assert pins[0].package_path == "packages/pkg-b"
        assert "pkg-a>=2.0.0" in pins[0].pins["pkg-a"]

    def test_dev_versions_not_pinned(self) -> None:
        """Dev versions are skipped because they are not installable from PyPI."""
        versions = {"pkg-a": Version.parse("2.0.0.dev0")}
        packages = {
            "pkg-a": Package(
                name="pkg-a", path="packages/pkg-a", version=Version.parse("2.0.0.dev0")
            ),
            "pkg-b": Package(
                name="pkg-b",
                path="packages/pkg-b",
                version=Version.parse("1.0.0"),
                dependencies=[_d("pkg-a")],
            ),
        }
        pins = compute_dependency_pins(versions, packages)
        assert len(pins) == 0

    def test_no_pins_for_external_deps(self) -> None:
        versions = {"pkg-a": Version.parse("2.0.0")}
        packages = {
            "pkg-a": Package(
                name="pkg-a", path="packages/pkg-a", version=Version.parse("2.0.0")
            ),
            "pkg-b": Package(
                name="pkg-b",
                path="packages/pkg-b",
                version=Version.parse("1.0.0"),
                dependencies=[_d("requests")],
            ),
        }
        pins = compute_dependency_pins(versions, packages)
        assert len(pins) == 0

    def test_no_pins_when_dep_not_bumped(self) -> None:
        versions = {"pkg-a": Version.parse("2.0.0")}
        packages = {
            "pkg-a": Package(
                name="pkg-a", path="packages/pkg-a", version=Version.parse("2.0.0")
            ),
            "pkg-b": Package(
                name="pkg-b",
                path="packages/pkg-b",
                version=Version.parse("1.0.0"),
                dependencies=[_d("pkg-c")],
            ),
        }
        pins = compute_dependency_pins(versions, packages)
        assert len(pins) == 0

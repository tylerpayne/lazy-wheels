"""Tests for versioning computations in uv_release.intents.versioning."""

from __future__ import annotations

import pytest

from uv_release.intents.shared.versioning import (
    compute_bumped_version,
    compute_next_version,
    compute_release_version,
)
from uv_release.types import BumpType

from ..conftest import make_version


# ---------------------------------------------------------------------------
# Resolve matrix (compute_release_version + compute_next_version)
# ---------------------------------------------------------------------------

# fmt: off
_RESOLVE_MATRIX: list[tuple[str, bool, str, str]] = [
    ("1.0.1",              False, "1.0.1",       "1.0.2.dev0"),
    ("1.0.1.dev0",         False, "1.0.1",       "1.0.2.dev0"),
    ("1.0.1.dev3",         False, "1.0.1",       "1.0.2.dev0"),
    ("1.0.1a0",            False, "1.0.1a0",     "1.0.1a1.dev0"),
    ("1.0.1a0.dev0",       False, "1.0.1a0",     "1.0.1a1.dev0"),
    ("1.0.1a0.dev3",       False, "1.0.1a0",     "1.0.1a1.dev0"),
    ("1.0.1a2",            False, "1.0.1a2",     "1.0.1a3.dev0"),
    ("1.0.1a2.dev0",       False, "1.0.1a2",     "1.0.1a3.dev0"),
    ("1.0.1a2.dev3",       False, "1.0.1a2",     "1.0.1a3.dev0"),
    ("1.0.1b0",            False, "1.0.1b0",     "1.0.1b1.dev0"),
    ("1.0.1b0.dev0",       False, "1.0.1b0",     "1.0.1b1.dev0"),
    ("1.0.1b0.dev3",       False, "1.0.1b0",     "1.0.1b1.dev0"),
    ("1.0.1b2",            False, "1.0.1b2",     "1.0.1b3.dev0"),
    ("1.0.1b2.dev0",       False, "1.0.1b2",     "1.0.1b3.dev0"),
    ("1.0.1b2.dev3",       False, "1.0.1b2",     "1.0.1b3.dev0"),
    ("1.0.1rc0",           False, "1.0.1rc0",    "1.0.1rc1.dev0"),
    ("1.0.1rc0.dev0",      False, "1.0.1rc0",    "1.0.1rc1.dev0"),
    ("1.0.1rc0.dev3",      False, "1.0.1rc0",    "1.0.1rc1.dev0"),
    ("1.0.1rc2",           False, "1.0.1rc2",    "1.0.1rc3.dev0"),
    ("1.0.1rc2.dev0",      False, "1.0.1rc2",    "1.0.1rc3.dev0"),
    ("1.0.1rc2.dev3",      False, "1.0.1rc2",    "1.0.1rc3.dev0"),
    ("1.0.1.post0",        False, "1.0.1.post0", "1.0.1.post1.dev0"),
    ("1.0.1.post0.dev0",   False, "1.0.1.post0", "1.0.1.post1.dev0"),
    ("1.0.1.post0.dev3",   False, "1.0.1.post0", "1.0.1.post1.dev0"),
    ("1.0.1.post2",        False, "1.0.1.post2", "1.0.1.post3.dev0"),
    ("1.0.1.post2.dev0",   False, "1.0.1.post2", "1.0.1.post3.dev0"),
    ("1.0.1.post2.dev3",   False, "1.0.1.post2", "1.0.1.post3.dev0"),
    ("1.0.1.dev0",         True,  "1.0.1.dev0",       "1.0.1.dev1"),
    ("1.0.1.dev3",         True,  "1.0.1.dev3",       "1.0.1.dev4"),
    ("1.0.1a0.dev0",       True,  "1.0.1a0.dev0",     "1.0.1a0.dev1"),
    ("1.0.1a0.dev3",       True,  "1.0.1a0.dev3",     "1.0.1a0.dev4"),
    ("1.0.1a2.dev0",       True,  "1.0.1a2.dev0",     "1.0.1a2.dev1"),
    ("1.0.1a2.dev3",       True,  "1.0.1a2.dev3",     "1.0.1a2.dev4"),
    ("1.0.1b0.dev0",       True,  "1.0.1b0.dev0",     "1.0.1b0.dev1"),
    ("1.0.1b0.dev3",       True,  "1.0.1b0.dev3",     "1.0.1b0.dev4"),
    ("1.0.1b2.dev0",       True,  "1.0.1b2.dev0",     "1.0.1b2.dev1"),
    ("1.0.1b2.dev3",       True,  "1.0.1b2.dev3",     "1.0.1b2.dev4"),
    ("1.0.1rc0.dev0",      True,  "1.0.1rc0.dev0",    "1.0.1rc0.dev1"),
    ("1.0.1rc0.dev3",      True,  "1.0.1rc0.dev3",    "1.0.1rc0.dev4"),
    ("1.0.1rc2.dev0",      True,  "1.0.1rc2.dev0",    "1.0.1rc2.dev1"),
    ("1.0.1rc2.dev3",      True,  "1.0.1rc2.dev3",    "1.0.1rc2.dev4"),
    ("1.0.1.post0.dev0",   True,  "1.0.1.post0.dev0", "1.0.1.post0.dev1"),
    ("1.0.1.post0.dev3",   True,  "1.0.1.post0.dev3", "1.0.1.post0.dev4"),
    ("1.0.1.post2.dev0",   True,  "1.0.1.post2.dev0", "1.0.1.post2.dev1"),
    ("1.0.1.post2.dev3",   True,  "1.0.1.post2.dev3", "1.0.1.post2.dev4"),
]
# fmt: on

_DEV_RELEASE_INVALID: list[str] = [
    "1.0.1",
    "1.0.1a0",
    "1.0.1a2",
    "1.0.1b0",
    "1.0.1b2",
    "1.0.1rc0",
    "1.0.1rc2",
    "1.0.1.post0",
    "1.0.1.post2",
]

_BUMP_VALID: list[tuple[str, BumpType, str]] = [
    ("1.0.1.dev0", BumpType.MAJOR, "2.0.0.dev0"),
    ("1.0.1.dev0", BumpType.MINOR, "1.1.0.dev0"),
    ("1.0.1.dev0", BumpType.PATCH, "1.0.2.dev0"),
    ("1.0.1.dev0", BumpType.ALPHA, "1.0.1a0.dev0"),
    ("1.0.1.dev0", BumpType.BETA, "1.0.1b0.dev0"),
    ("1.0.1.dev0", BumpType.RC, "1.0.1rc0.dev0"),
    ("1.0.1.dev0", BumpType.DEV, "1.0.1.dev1"),
    ("1.0.1", BumpType.DEV, "1.0.1.dev0"),
    ("1.0.1.dev0", BumpType.STABLE, "1.0.1"),
    ("1.0.1a0.dev0", BumpType.MAJOR, "2.0.0.dev0"),
    ("1.0.1a0.dev0", BumpType.MINOR, "1.1.0.dev0"),
    ("1.0.1a0.dev0", BumpType.PATCH, "1.0.2.dev0"),
    ("1.0.1a0.dev0", BumpType.ALPHA, "1.0.1a1.dev0"),
    ("1.0.1a0.dev0", BumpType.BETA, "1.0.1b0.dev0"),
    ("1.0.1a0.dev0", BumpType.RC, "1.0.1rc0.dev0"),
    ("1.0.1a0.dev0", BumpType.DEV, "1.0.1a0.dev1"),
    ("1.0.1a0.dev0", BumpType.STABLE, "1.0.1"),
    ("1.0.1b0.dev0", BumpType.BETA, "1.0.1b1.dev0"),
    ("1.0.1b0.dev0", BumpType.RC, "1.0.1rc0.dev0"),
    ("1.0.1b0.dev0", BumpType.STABLE, "1.0.1"),
    ("1.0.1rc0.dev0", BumpType.RC, "1.0.1rc1.dev0"),
    ("1.0.1rc0.dev0", BumpType.STABLE, "1.0.1"),
    ("1.0.1", BumpType.MAJOR, "2.0.0.dev0"),
    ("1.0.1", BumpType.MINOR, "1.1.0.dev0"),
    ("1.0.1", BumpType.PATCH, "1.0.2.dev0"),
    ("1.0.1", BumpType.POST, "1.0.1.post0.dev0"),
    ("1.0.1.post0.dev0", BumpType.POST, "1.0.1.post1.dev0"),
    ("1.0.1.post0.dev0", BumpType.DEV, "1.0.1.post0.dev1"),
    ("1.0.1.post0.dev0", BumpType.STABLE, "1.0.1.post0"),
]

_BUMP_INVALID: list[tuple[str, BumpType]] = [
    ("1.0.1.post0.dev0", BumpType.ALPHA),
    ("1.0.1.post0.dev0", BumpType.BETA),
    ("1.0.1.post0.dev0", BumpType.RC),
    ("1.0.1b0.dev0", BumpType.ALPHA),
    ("1.0.1rc0.dev0", BumpType.ALPHA),
    ("1.0.1rc0.dev0", BumpType.BETA),
    ("1.0.1a2.dev0", BumpType.POST),
    ("1.0.1.dev0", BumpType.POST),
]


# ---------------------------------------------------------------------------
# compute_release_version
# ---------------------------------------------------------------------------


class TestComputeReleaseVersion:
    """compute_release_version strips dev or returns as-is for dev releases."""

    @pytest.mark.parametrize(
        ("raw", "dev_release", "expected_release", "_next"),
        _RESOLVE_MATRIX,
        ids=[f"{r[0]}-dev={r[1]}" for r in _RESOLVE_MATRIX],
    )
    def test_release_version(
        self, raw: str, dev_release: bool, expected_release: str, _next: str
    ) -> None:
        version = make_version(raw)
        result = compute_release_version(version, dev_release=dev_release)
        assert result.raw == expected_release

    @pytest.mark.parametrize("raw", _DEV_RELEASE_INVALID)
    def test_dev_release_non_dev_raises(self, raw: str) -> None:
        version = make_version(raw)
        with pytest.raises(ValueError, match="Cannot do a dev release"):
            compute_release_version(version, dev_release=True)


# ---------------------------------------------------------------------------
# compute_next_version
# ---------------------------------------------------------------------------


class TestComputeNextVersion:
    """compute_next_version computes the post-release dev version."""

    @pytest.mark.parametrize(
        ("raw", "dev_release", "_release", "expected_next"),
        _RESOLVE_MATRIX,
        ids=[f"{r[0]}-dev={r[1]}" for r in _RESOLVE_MATRIX],
    )
    def test_next_version(
        self, raw: str, dev_release: bool, _release: str, expected_next: str
    ) -> None:
        version = make_version(raw)
        result = compute_next_version(version, dev_release=dev_release)
        assert result.raw == expected_next

    @pytest.mark.parametrize("raw", _DEV_RELEASE_INVALID)
    def test_dev_release_non_dev_raises(self, raw: str) -> None:
        version = make_version(raw)
        with pytest.raises(ValueError, match="Cannot compute next dev version"):
            compute_next_version(version, dev_release=True)


# ---------------------------------------------------------------------------
# compute_bumped_version
# ---------------------------------------------------------------------------


class TestComputeBumpedVersion:
    """compute_bumped_version applies bump transitions."""

    @pytest.mark.parametrize(
        ("raw", "bump_type", "expected"),
        _BUMP_VALID,
        ids=[f"{b[0]}-{b[1].value}" for b in _BUMP_VALID],
    )
    def test_valid_bump(self, raw: str, bump_type: BumpType, expected: str) -> None:
        version = make_version(raw)
        result = compute_bumped_version(version, bump_type)
        assert result.raw == expected

    @pytest.mark.parametrize(
        ("raw", "bump_type"),
        _BUMP_INVALID,
        ids=[f"{b[0]}-{b[1].value}" for b in _BUMP_INVALID],
    )
    def test_invalid_bump_raises(self, raw: str, bump_type: BumpType) -> None:
        version = make_version(raw)
        with pytest.raises(ValueError):
            compute_bumped_version(version, bump_type)

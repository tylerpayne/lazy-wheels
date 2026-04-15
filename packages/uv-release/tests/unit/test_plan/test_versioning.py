"""Tests for plan/versioning: compute_release_version, compute_next_version, compute_bumped_version."""

from __future__ import annotations

import pytest

from uv_release.plan.versioning import (
    compute_bumped_version,
    compute_next_version,
    compute_release_version,
)
from uv_release.types import BumpType, Version


# ---------------------------------------------------------------------------
# resolve_versions: 27 versions × 2 modes = 54 cells
# ---------------------------------------------------------------------------

# fmt: off
_RESOLVE_MATRIX: list[tuple[str, bool, str, str]] = [
    # (version, dev_release, expected_release, expected_next)

    # ── default mode (strip dev, release what's underneath) ──

    # stable base
    ("1.0.1",              False, "1.0.1",       "1.0.2.dev0"),
    ("1.0.1.dev0",         False, "1.0.1",       "1.0.2.dev0"),
    ("1.0.1.dev3",         False, "1.0.1",       "1.0.2.dev0"),
    # alpha
    ("1.0.1a0",            False, "1.0.1a0",     "1.0.1a1.dev0"),
    ("1.0.1a0.dev0",       False, "1.0.1a0",     "1.0.1a1.dev0"),
    ("1.0.1a0.dev3",       False, "1.0.1a0",     "1.0.1a1.dev0"),
    ("1.0.1a2",            False, "1.0.1a2",     "1.0.1a3.dev0"),
    ("1.0.1a2.dev0",       False, "1.0.1a2",     "1.0.1a3.dev0"),
    ("1.0.1a2.dev3",       False, "1.0.1a2",     "1.0.1a3.dev0"),
    # beta
    ("1.0.1b0",            False, "1.0.1b0",     "1.0.1b1.dev0"),
    ("1.0.1b0.dev0",       False, "1.0.1b0",     "1.0.1b1.dev0"),
    ("1.0.1b0.dev3",       False, "1.0.1b0",     "1.0.1b1.dev0"),
    ("1.0.1b2",            False, "1.0.1b2",     "1.0.1b3.dev0"),
    ("1.0.1b2.dev0",       False, "1.0.1b2",     "1.0.1b3.dev0"),
    ("1.0.1b2.dev3",       False, "1.0.1b2",     "1.0.1b3.dev0"),
    # rc
    ("1.0.1rc0",           False, "1.0.1rc0",    "1.0.1rc1.dev0"),
    ("1.0.1rc0.dev0",      False, "1.0.1rc0",    "1.0.1rc1.dev0"),
    ("1.0.1rc0.dev3",      False, "1.0.1rc0",    "1.0.1rc1.dev0"),
    ("1.0.1rc2",           False, "1.0.1rc2",    "1.0.1rc3.dev0"),
    ("1.0.1rc2.dev0",      False, "1.0.1rc2",    "1.0.1rc3.dev0"),
    ("1.0.1rc2.dev3",      False, "1.0.1rc2",    "1.0.1rc3.dev0"),
    # post
    ("1.0.1.post0",        False, "1.0.1.post0", "1.0.1.post1.dev0"),
    ("1.0.1.post0.dev0",   False, "1.0.1.post0", "1.0.1.post1.dev0"),
    ("1.0.1.post0.dev3",   False, "1.0.1.post0", "1.0.1.post1.dev0"),
    ("1.0.1.post2",        False, "1.0.1.post2", "1.0.1.post3.dev0"),
    ("1.0.1.post2.dev0",   False, "1.0.1.post2", "1.0.1.post3.dev0"),
    ("1.0.1.post2.dev3",   False, "1.0.1.post2", "1.0.1.post3.dev0"),

    # ── dev mode (publish .devN as-is, only valid for dev versions) ──

    # stable base
    ("1.0.1.dev0",         True,  "1.0.1.dev0",       "1.0.1.dev1"),
    ("1.0.1.dev3",         True,  "1.0.1.dev3",       "1.0.1.dev4"),
    # alpha
    ("1.0.1a0.dev0",       True,  "1.0.1a0.dev0",     "1.0.1a0.dev1"),
    ("1.0.1a0.dev3",       True,  "1.0.1a0.dev3",     "1.0.1a0.dev4"),
    ("1.0.1a2.dev0",       True,  "1.0.1a2.dev0",     "1.0.1a2.dev1"),
    ("1.0.1a2.dev3",       True,  "1.0.1a2.dev3",     "1.0.1a2.dev4"),
    # beta
    ("1.0.1b0.dev0",       True,  "1.0.1b0.dev0",     "1.0.1b0.dev1"),
    ("1.0.1b0.dev3",       True,  "1.0.1b0.dev3",     "1.0.1b0.dev4"),
    ("1.0.1b2.dev0",       True,  "1.0.1b2.dev0",     "1.0.1b2.dev1"),
    ("1.0.1b2.dev3",       True,  "1.0.1b2.dev3",     "1.0.1b2.dev4"),
    # rc
    ("1.0.1rc0.dev0",      True,  "1.0.1rc0.dev0",    "1.0.1rc0.dev1"),
    ("1.0.1rc0.dev3",      True,  "1.0.1rc0.dev3",    "1.0.1rc0.dev4"),
    ("1.0.1rc2.dev0",      True,  "1.0.1rc2.dev0",    "1.0.1rc2.dev1"),
    ("1.0.1rc2.dev3",      True,  "1.0.1rc2.dev3",    "1.0.1rc2.dev4"),
    # post
    ("1.0.1.post0.dev0",   True,  "1.0.1.post0.dev0", "1.0.1.post0.dev1"),
    ("1.0.1.post0.dev3",   True,  "1.0.1.post0.dev3", "1.0.1.post0.dev4"),
    ("1.0.1.post2.dev0",   True,  "1.0.1.post2.dev0", "1.0.1.post2.dev1"),
    ("1.0.1.post2.dev3",   True,  "1.0.1.post2.dev3", "1.0.1.post2.dev4"),
]
# fmt: on

assert len(_RESOLVE_MATRIX) == 45, f"Expected 45 cells, got {len(_RESOLVE_MATRIX)}"


@pytest.mark.parametrize(
    "version,dev_release,expected_release,expected_next",
    _RESOLVE_MATRIX,
    ids=[f"{v}+{'dev' if d else 'default'}" for v, d, _, _ in _RESOLVE_MATRIX],
)
def test_resolve_versions(
    version: str,
    dev_release: bool,
    expected_release: str,
    expected_next: str,
) -> None:
    v = Version.parse(version)
    release_v = compute_release_version(v, dev_release=dev_release)
    next_v = compute_next_version(v, dev_release=dev_release)
    assert isinstance(release_v, Version)
    assert isinstance(next_v, Version)
    assert release_v.raw == expected_release
    assert next_v.raw == expected_next


# ---------------------------------------------------------------------------
# dev release from non-dev version raises
# ---------------------------------------------------------------------------

# fmt: off
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
# fmt: on


@pytest.mark.parametrize("version", _DEV_RELEASE_INVALID)
def test_dev_release_from_non_dev_raises(version: str) -> None:
    v = Version.parse(version)
    with pytest.raises(ValueError):
        compute_release_version(v, dev_release=True)
    with pytest.raises(ValueError):
        compute_next_version(v, dev_release=True)


# ---------------------------------------------------------------------------
# compute_bumped_version: 27 versions × 9 BumpTypes (valid transitions only)
# ---------------------------------------------------------------------------

# fmt: off
_BUMP_VALID: list[tuple[str, BumpType, str]] = [
    # (version, bump_type, expected_result)

    # From stable dev0
    ("1.0.1.dev0", BumpType.MAJOR, "2.0.0.dev0"),
    ("1.0.1.dev0", BumpType.MINOR, "1.1.0.dev0"),
    ("1.0.1.dev0", BumpType.PATCH, "1.0.2.dev0"),
    ("1.0.1.dev0", BumpType.ALPHA, "1.0.1a0.dev0"),
    ("1.0.1.dev0", BumpType.BETA,  "1.0.1b0.dev0"),
    ("1.0.1.dev0", BumpType.RC,    "1.0.1rc0.dev0"),
    ("1.0.1.dev0", BumpType.DEV,   "1.0.1.dev1"),
    ("1.0.1",      BumpType.DEV,   "1.0.1.dev0"),    # non-dev enters dev track
    ("1.0.1.dev0", BumpType.STABLE, "1.0.1"),

    # From alpha dev0
    ("1.0.1a0.dev0", BumpType.MAJOR, "2.0.0.dev0"),
    ("1.0.1a0.dev0", BumpType.MINOR, "1.1.0.dev0"),
    ("1.0.1a0.dev0", BumpType.PATCH, "1.0.2.dev0"),
    ("1.0.1a0.dev0", BumpType.ALPHA, "1.0.1a1.dev0"),
    ("1.0.1a0.dev0", BumpType.BETA,  "1.0.1b0.dev0"),
    ("1.0.1a0.dev0", BumpType.RC,    "1.0.1rc0.dev0"),
    ("1.0.1a0.dev0", BumpType.DEV,   "1.0.1a0.dev1"),
    ("1.0.1a0.dev0", BumpType.STABLE, "1.0.1"),

    # From beta dev0
    ("1.0.1b0.dev0", BumpType.BETA,  "1.0.1b1.dev0"),
    ("1.0.1b0.dev0", BumpType.RC,    "1.0.1rc0.dev0"),
    ("1.0.1b0.dev0", BumpType.STABLE, "1.0.1"),

    # From rc dev0
    ("1.0.1rc0.dev0", BumpType.RC,    "1.0.1rc1.dev0"),
    ("1.0.1rc0.dev0", BumpType.STABLE, "1.0.1"),

    # From clean stable
    ("1.0.1", BumpType.MAJOR, "2.0.0.dev0"),
    ("1.0.1", BumpType.MINOR, "1.1.0.dev0"),
    ("1.0.1", BumpType.PATCH, "1.0.2.dev0"),
    ("1.0.1", BumpType.POST,  "1.0.1.post0.dev0"),

    # From post dev0
    ("1.0.1.post0.dev0", BumpType.POST, "1.0.1.post1.dev0"),
    ("1.0.1.post0.dev0", BumpType.DEV,  "1.0.1.post0.dev1"),
    ("1.0.1.post0.dev0", BumpType.STABLE, "1.0.1.post0"),
]
# fmt: on


@pytest.mark.parametrize(
    "version,bump_type,expected",
    _BUMP_VALID,
    ids=[f"{v}+{bt.name}" for v, bt, _ in _BUMP_VALID],
)
def test_compute_bumped_version_valid(
    version: str, bump_type: BumpType, expected: str
) -> None:
    v = Version.parse(version)
    result = compute_bumped_version(v, bump_type)
    assert isinstance(result, Version)
    assert result.raw == expected


# Invalid bump transitions
# fmt: off
_BUMP_INVALID: list[tuple[str, BumpType]] = [
    ("1.0.1.post0.dev0", BumpType.ALPHA),   # post → alpha invalid
    ("1.0.1.post0.dev0", BumpType.BETA),    # post → beta invalid
    ("1.0.1.post0.dev0", BumpType.RC),      # post → rc invalid
    ("1.0.1b0.dev0",     BumpType.ALPHA),   # beta → alpha invalid (backwards)
    ("1.0.1rc0.dev0",    BumpType.ALPHA),   # rc → alpha invalid
    ("1.0.1rc0.dev0",    BumpType.BETA),    # rc → beta invalid
    ("1.0.1a2.dev0",     BumpType.POST),    # pre-release → post invalid
    ("1.0.1.dev0",       BumpType.POST),    # dev → post invalid
]
# fmt: on


@pytest.mark.parametrize(
    "version,bump_type",
    _BUMP_INVALID,
    ids=[f"{v}+{bt.name}" for v, bt in _BUMP_INVALID],
)
def test_compute_bumped_version_invalid_raises(
    version: str, bump_type: BumpType
) -> None:
    v = Version.parse(version)
    with pytest.raises(ValueError):
        compute_bumped_version(v, bump_type)

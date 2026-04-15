"""Tests for VERSION string parsing (same matrix as test_types but focused on parsing module)."""

from __future__ import annotations

import pytest

from uv_release.types import Version, VersionState


# The 27 canonical version strings covering all 11 states
# fmt: off
_VERSIONS: list[tuple[str, VersionState]] = [
    ("1.0.1",              VersionState.CLEAN_STABLE),
    ("1.0.1.dev0",         VersionState.DEV0_STABLE),
    ("1.0.1.dev3",         VersionState.DEVK_STABLE),
    ("1.0.1a0",            VersionState.CLEAN_PRE0),
    ("1.0.1a2",            VersionState.CLEAN_PREN),
    ("1.0.1a0.dev0",       VersionState.DEV0_PRE),
    ("1.0.1a2.dev0",       VersionState.DEV0_PRE),
    ("1.0.1a0.dev3",       VersionState.DEVK_PRE),
    ("1.0.1b0",            VersionState.CLEAN_PRE0),
    ("1.0.1b2",            VersionState.CLEAN_PREN),
    ("1.0.1b0.dev0",       VersionState.DEV0_PRE),
    ("1.0.1b0.dev3",       VersionState.DEVK_PRE),
    ("1.0.1rc0",           VersionState.CLEAN_PRE0),
    ("1.0.1rc1",           VersionState.CLEAN_PREN),
    ("1.0.1rc0.dev0",      VersionState.DEV0_PRE),
    ("1.0.1rc0.dev3",      VersionState.DEVK_PRE),
    ("1.0.1.post0",        VersionState.CLEAN_POST0),
    ("1.0.1.post2",        VersionState.CLEAN_POSTM),
    ("1.0.1.post0.dev0",   VersionState.DEV0_POST),
    ("1.0.1.post0.dev3",   VersionState.DEVK_POST),
    ("1.0.1.post2.dev0",   VersionState.DEV0_POST),
    ("1.0.1.post2.dev3",   VersionState.DEVK_POST),
    ("0.0.0",              VersionState.CLEAN_STABLE),
    ("0.0.0.dev0",         VersionState.DEV0_STABLE),
    ("10.20.30",           VersionState.CLEAN_STABLE),
    ("10.20.30a5.dev0",    VersionState.DEV0_PRE),
    ("10.20.30.post1.dev2", VersionState.DEVK_POST),
]
# fmt: on


@pytest.mark.parametrize(
    "raw,expected_state",
    _VERSIONS,
    ids=[raw for raw, _ in _VERSIONS],
)
def test_round_trip(raw: str, expected_state: VersionState) -> None:
    v = Version.parse(raw)
    assert v.raw == raw
    assert v.state == expected_state


@pytest.mark.parametrize(
    "raw,expected_state",
    _VERSIONS,
    ids=[raw for raw, _ in _VERSIONS],
)
def test_base_strips_suffixes(raw: str, expected_state: VersionState) -> None:
    v = Version.parse(raw)
    # base should never contain dev, pre, or post suffixes
    assert "dev" not in v.base
    assert "post" not in v.base
    assert "a" not in v.base or v.base.count("a") == 0  # edge: "a" not in X.Y.Z
    assert v.base.count(".") == 2  # always X.Y.Z

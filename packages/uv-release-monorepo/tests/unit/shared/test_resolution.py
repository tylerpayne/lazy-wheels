"""Tests for the release resolution state machine.

Exhaustive parametrized coverage of every (VersionState, ReleaseMode) pair:
- classify_version: 12 states
- resolve_release default mode: 27 versions x (baseline, release, next)
- resolve_release --dev mode: 18 dev versions + 9 clean versions (error)
- tag conflicts, version conflicts, skip behavior, baseline fallbacks
"""

from __future__ import annotations

import pytest

from uv_release_monorepo.shared.resolution import (
    ReleaseConflictError,
    ReleaseInvalidError,
    VersionState,
    classify_version,
    resolve_release,
)


PKG = "pkg"


class _FakeRepo:
    """Minimal repo mock that responds to reference lookups."""

    def __init__(self, tags: set[str]) -> None:
        self._tags = tags
        self.references = self
        self._refs = [f"refs/tags/{t}" for t in tags]

    def get(self, ref: str) -> object | None:
        return object() if ref in {f"refs/tags/{t}" for t in self._tags} else None

    def listall_references(self) -> list[str]:
        return self._refs


def _repo(*tags: str) -> _FakeRepo:
    return _FakeRepo(set(tags))


# ===================================================================
# classify_version
# ===================================================================


_CLASSIFY_CASES: list[tuple[str, VersionState]] = [
    ("1.2.3", VersionState.CLEAN_STABLE),
    ("1.2.3.dev0", VersionState.DEV0_STABLE),
    ("1.2.3.dev3", VersionState.DEVK_STABLE),
    ("1.2.3a0", VersionState.CLEAN_PRE0),
    ("1.2.3b0", VersionState.CLEAN_PRE0),
    ("1.2.3rc0", VersionState.CLEAN_PRE0),
    ("1.2.3a2", VersionState.CLEAN_PREN),
    ("1.2.3b1", VersionState.CLEAN_PREN),
    ("1.2.3rc3", VersionState.CLEAN_PREN),
    ("1.2.3a0.dev0", VersionState.DEV0_PRE),
    ("1.2.3a2.dev0", VersionState.DEV0_PRE),
    ("1.2.3a0.dev3", VersionState.DEVK_PRE),
    ("1.2.3a2.dev3", VersionState.DEVK_PRE),
    ("1.2.3.post0", VersionState.CLEAN_POST0),
    ("1.2.3.post2", VersionState.CLEAN_POSTM),
    ("1.2.3.post0.dev0", VersionState.DEV0_POST),
    ("1.2.3.post2.dev0", VersionState.DEV0_POST),
    ("1.2.3.post0.dev3", VersionState.DEVK_POST),
    ("1.2.3.post2.dev3", VersionState.DEVK_POST),
]


class TestClassifyVersion:
    @pytest.mark.parametrize(
        "version,expected",
        _CLASSIFY_CASES,
        ids=[f"{v}->{s.name}" for v, s in _CLASSIFY_CASES],
    )
    def test_classify(self, version: str, expected: VersionState) -> None:
        assert classify_version(version) == expected


# ===================================================================
# Release matrix: version x mode -> (state, baseline, release, next)
#
# Every valid (version, dev_release) pair with static expected values.
# No version logic in the test.
# ===================================================================


# fmt: off
_RELEASE_MATRIX: list[tuple[str, bool, str, str]] = [
    # ── uvr release (default) ──
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

    # ── uvr release --dev (dev versions only) ──
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


class TestReleaseMatrix:
    """27 versions x default + 18 versions x --dev = 45 valid cells."""

    @pytest.mark.parametrize(
        "version,dev_release,expected_release,expected_next",
        _RELEASE_MATRIX,
        ids=[f"{v}+{'dev' if d else 'default'}" for v, d, _, _ in _RELEASE_MATRIX],
    )
    def test_release_and_next_version(
        self,
        version: str,
        dev_release: bool,
        expected_release: str,
        expected_next: str,
    ) -> None:
        r = resolve_release(version, PKG, _repo(), dev_release=dev_release)
        assert r.release_version == expected_release
        assert r.next_version == expected_next


# ===================================================================
# Baseline resolution
# ===================================================================


# (version, dev_release, tags_in_repo, expected_baseline)
# fmt: off
_BASELINE_CASES: list[tuple[str, bool, list[str], str | None]] = [
    # ── default mode: every version form ──
    # stable
    ("1.2.3",              False, [f"{PKG}/v1.2.2"],                 f"{PKG}/v1.2.2"),
    ("1.2.3.dev0",         False, [],                                f"{PKG}/v1.2.3.dev0-base"),
    ("1.2.3.dev3",         False, [],                                f"{PKG}/v1.2.3.dev0-base"),
    # alpha
    ("1.2.3a0",            False, [f"{PKG}/v1.2.2"],                 f"{PKG}/v1.2.2"),
    ("1.2.3a0.dev0",       False, [f"{PKG}/v1.2.3a0.dev0-base"],     f"{PKG}/v1.2.3a0.dev0-base"),
    ("1.2.3a0.dev3",       False, [f"{PKG}/v1.2.3a0.dev0-base"],     f"{PKG}/v1.2.3a0.dev0-base"),
    ("1.2.3a2",            False, [f"{PKG}/v1.2.3a1"],               f"{PKG}/v1.2.3a1"),
    ("1.2.3a2.dev0",       False, [f"{PKG}/v1.2.3a2.dev0-base"],     f"{PKG}/v1.2.3a2.dev0-base"),
    ("1.2.3a2.dev3",       False, [f"{PKG}/v1.2.3a2.dev0-base"],     f"{PKG}/v1.2.3a2.dev0-base"),
    # beta
    ("1.2.3b0",            False, [f"{PKG}/v1.2.2"],                 f"{PKG}/v1.2.2"),
    ("1.2.3b0.dev0",       False, [f"{PKG}/v1.2.3b0.dev0-base"],     f"{PKG}/v1.2.3b0.dev0-base"),
    ("1.2.3b0.dev3",       False, [f"{PKG}/v1.2.3b0.dev0-base"],     f"{PKG}/v1.2.3b0.dev0-base"),
    ("1.2.3b2",            False, [f"{PKG}/v1.2.3b1"],               f"{PKG}/v1.2.3b1"),
    ("1.2.3b2.dev0",       False, [f"{PKG}/v1.2.3b2.dev0-base"],     f"{PKG}/v1.2.3b2.dev0-base"),
    ("1.2.3b2.dev3",       False, [f"{PKG}/v1.2.3b2.dev0-base"],     f"{PKG}/v1.2.3b2.dev0-base"),
    # rc
    ("1.2.3rc0",           False, [f"{PKG}/v1.2.2"],                 f"{PKG}/v1.2.2"),
    ("1.2.3rc0.dev0",      False, [f"{PKG}/v1.2.3rc0.dev0-base"],    f"{PKG}/v1.2.3rc0.dev0-base"),
    ("1.2.3rc0.dev3",      False, [f"{PKG}/v1.2.3rc0.dev0-base"],    f"{PKG}/v1.2.3rc0.dev0-base"),
    ("1.2.3rc2",           False, [f"{PKG}/v1.2.3rc1"],              f"{PKG}/v1.2.3rc1"),
    ("1.2.3rc2.dev0",      False, [f"{PKG}/v1.2.3rc2.dev0-base"],    f"{PKG}/v1.2.3rc2.dev0-base"),
    ("1.2.3rc2.dev3",      False, [f"{PKG}/v1.2.3rc2.dev0-base"],    f"{PKG}/v1.2.3rc2.dev0-base"),
    # post
    ("1.2.3.post0",        False, [f"{PKG}/v1.2.3"],                 f"{PKG}/v1.2.3"),
    ("1.2.3.post0.dev0",   False, [],                                f"{PKG}/v1.2.3.post0.dev0-base"),
    ("1.2.3.post0.dev3",   False, [],                                f"{PKG}/v1.2.3.post0.dev0-base"),
    ("1.2.3.post2",        False, [f"{PKG}/v1.2.3.post1"],           f"{PKG}/v1.2.3.post1"),
    ("1.2.3.post2.dev0",   False, [],                                f"{PKG}/v1.2.3.post2.dev0-base"),
    ("1.2.3.post2.dev3",   False, [],                                f"{PKG}/v1.2.3.post2.dev0-base"),

    # ── --dev mode: every dev version form (own -base, no rewind) ──
    ("1.2.3.dev0",         True,  [],                                f"{PKG}/v1.2.3.dev0-base"),
    ("1.2.3.dev3",         True,  [],                                f"{PKG}/v1.2.3.dev3-base"),
    ("1.2.3a0.dev0",       True,  [],                                f"{PKG}/v1.2.3a0.dev0-base"),
    ("1.2.3a0.dev3",       True,  [],                                f"{PKG}/v1.2.3a0.dev3-base"),
    ("1.2.3a2.dev0",       True,  [],                                f"{PKG}/v1.2.3a2.dev0-base"),
    ("1.2.3a2.dev3",       True,  [],                                f"{PKG}/v1.2.3a2.dev3-base"),
    ("1.2.3b0.dev0",       True,  [],                                f"{PKG}/v1.2.3b0.dev0-base"),
    ("1.2.3b0.dev3",       True,  [],                                f"{PKG}/v1.2.3b0.dev3-base"),
    ("1.2.3b2.dev0",       True,  [],                                f"{PKG}/v1.2.3b2.dev0-base"),
    ("1.2.3b2.dev3",       True,  [],                                f"{PKG}/v1.2.3b2.dev3-base"),
    ("1.2.3rc0.dev0",      True,  [],                                f"{PKG}/v1.2.3rc0.dev0-base"),
    ("1.2.3rc0.dev3",      True,  [],                                f"{PKG}/v1.2.3rc0.dev3-base"),
    ("1.2.3rc2.dev0",      True,  [],                                f"{PKG}/v1.2.3rc2.dev0-base"),
    ("1.2.3rc2.dev3",      True,  [],                                f"{PKG}/v1.2.3rc2.dev3-base"),
    ("1.2.3.post0.dev0",   True,  [],                                f"{PKG}/v1.2.3.post0.dev0-base"),
    ("1.2.3.post0.dev3",   True,  [],                                f"{PKG}/v1.2.3.post0.dev3-base"),
    ("1.2.3.post2.dev0",   True,  [],                                f"{PKG}/v1.2.3.post2.dev0-base"),
    ("1.2.3.post2.dev3",   True,  [],                                f"{PKG}/v1.2.3.post2.dev3-base"),
]
# fmt: on


class TestBaselineResolution:
    @pytest.mark.parametrize(
        "version,dev_release,tags,expected_baseline",
        _BASELINE_CASES,
        ids=[
            f"{v}+{'dev' if d else 'default'}->{b or 'None'}"
            for v, d, _, b in _BASELINE_CASES
        ],
    )
    def test_baseline(
        self,
        version: str,
        dev_release: bool,
        tags: list[str],
        expected_baseline: str | None,
    ) -> None:
        r = resolve_release(version, PKG, _repo(*tags), dev_release=dev_release)
        assert r.baseline_tag == expected_baseline


# ===================================================================
# --dev from clean version (ReleaseInvalidError, NOT ReleaseConflictError)
# ===================================================================


_DEV_INVALID: list[str] = [
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


class TestDevFromCleanInvalid:
    @pytest.mark.parametrize("version", _DEV_INVALID)
    def test_raises_invalid_not_conflict(self, version: str) -> None:
        with pytest.raises(ReleaseInvalidError, match="--dev") as exc_info:
            resolve_release(version, PKG, _repo(), dev_release=True)
        assert not isinstance(exc_info.value, ReleaseConflictError)


# ===================================================================
# Tag conflicts
# ===================================================================


class TestTagConflicts:
    def test_release_tag_from_dev(self) -> None:
        """dev0 targeting already-released version."""
        with pytest.raises(ReleaseConflictError, match="already released"):
            resolve_release("1.2.3.dev0", PKG, _repo(f"{PKG}/v1.2.3"))

    def test_release_tag_from_clean(self) -> None:
        """Clean version whose release tag already exists."""
        with pytest.raises(ReleaseConflictError, match="Tag"):
            resolve_release("1.2.3", PKG, _repo(f"{PKG}/v1.2.2", f"{PKG}/v1.2.3"))

    def test_baseline_tag_conflict(self) -> None:
        with pytest.raises(ReleaseConflictError, match="Tag"):
            resolve_release("1.2.3.dev0", PKG, _repo(f"{PKG}/v1.2.4.dev0-base"))

    def test_skip_release_suppresses_release_tag_check(self) -> None:
        """Recovery mode: release tag exists, skip={uvr-release} allows it."""
        r = resolve_release(
            "1.2.3",
            PKG,
            _repo(f"{PKG}/v1.2.2", f"{PKG}/v1.2.3"),
            skip=frozenset({"uvr-release"}),
        )
        assert r.release_version == "1.2.3"

    def test_skip_release_still_checks_baseline_tag(self) -> None:
        with pytest.raises(ReleaseConflictError, match="Tag"):
            resolve_release(
                "1.2.3",
                PKG,
                _repo(f"{PKG}/v1.2.2", f"{PKG}/v1.2.4.dev0-base"),
                skip=frozenset({"uvr-release"}),
            )


# ===================================================================
# Version conflicts (dev targeting already-released)
# ===================================================================


class TestVersionConflicts:
    def test_stable_dev(self) -> None:
        with pytest.raises(ReleaseConflictError, match="already released"):
            resolve_release("1.2.3.dev0", PKG, _repo(f"{PKG}/v1.2.3"))

    def test_pre_dev(self) -> None:
        with pytest.raises(ReleaseConflictError, match="already released"):
            resolve_release("1.2.3a1.dev0", PKG, _repo(f"{PKG}/v1.2.3a1"))

    def test_post_dev(self) -> None:
        with pytest.raises(ReleaseConflictError, match="already released"):
            resolve_release("1.2.3.post0.dev0", PKG, _repo(f"{PKG}/v1.2.3.post0"))

    def test_clean_version_not_checked(self) -> None:
        """Clean versions are the release itself, no conflict possible."""
        r = resolve_release("1.2.3", PKG, _repo(f"{PKG}/v1.2.2"))
        assert r.release_version == "1.2.3"


# ===================================================================
# State field
# ===================================================================


class TestStateField:
    @pytest.mark.parametrize(
        "version,dev_release,expected_state",
        [
            ("1.2.3", False, VersionState.CLEAN_STABLE),
            ("1.2.3.dev0", False, VersionState.DEV0_STABLE),
            ("1.2.3.dev3", False, VersionState.DEVK_STABLE),
            ("1.2.3a0", False, VersionState.CLEAN_PRE0),
            ("1.2.3a2.dev0", False, VersionState.DEV0_PRE),
            ("1.2.3.post0", False, VersionState.CLEAN_POST0),
            ("1.2.3.post2.dev3", False, VersionState.DEVK_POST),
            ("1.2.3.dev0", True, VersionState.DEV0_STABLE),
            ("1.2.3a1.dev0", True, VersionState.DEV0_PRE),
            ("1.2.3.post2.dev0", True, VersionState.DEV0_POST),
        ],
    )
    def test_state_on_resolution(
        self,
        version: str,
        dev_release: bool,
        expected_state: VersionState,
    ) -> None:
        r = resolve_release(version, PKG, _repo(), dev_release=dev_release)
        assert r.state == expected_state

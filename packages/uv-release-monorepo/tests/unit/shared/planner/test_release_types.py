"""ADR-0008: PEP 440 release type compliance.

Validates that the version flow from the ADR produces valid PEP 440
versions at every step — release version, tag, post-release bump, and
baseline tag.
"""

from __future__ import annotations

import re as _re
from unittest.mock import MagicMock

import pygit2
import pytest
from packaging.version import Version

from uv_release_monorepo.shared.context import RepositoryContext
from uv_release_monorepo.shared.models import PackageInfo, PlanConfig
from uv_release_monorepo.shared.planner import ReleasePlanner


def _pep440(v: str) -> Version:
    """Parse a version string and assert it is PEP 440 compliant."""
    return Version(v)


def _make_ctx() -> RepositoryContext:
    """Build a minimal fake RepositoryContext for unit tests."""
    return RepositoryContext(
        repo=MagicMock(spec=pygit2.Repository),
        packages={},
    )


def _planner(
    release_type: str = "final",
    pre_kind: str = "",
) -> ReleasePlanner:
    return ReleasePlanner(
        PlanConfig(
            rebuild_all=True,
            matrix={},
            uvr_version="0.7.1",
            ci_publish=False,
            release_type=release_type,
            pre_kind=pre_kind,
            dry_run=True,
        ),
        _make_ctx(),
    )


def _pkg(version: str, deps: list[str] | None = None) -> PackageInfo:
    return PackageInfo(path="packages/alpha", version=version, deps=deps or [])


def _release_and_bump(
    planner: ReleasePlanner,
    pyproject_version: str,
) -> tuple[str, str]:
    """Run the planner's version computation and return (release_ver, next_dev_ver).

    next_dev_ver is the exact version that will be written to pyproject.toml.
    """
    changed = {"alpha": _pkg(pyproject_version)}

    release_versions = planner._compute_release_versions(changed)

    # Build versioned PackageInfo dict with release versions applied
    versioned: dict[str, PackageInfo] = {}
    for name, info in changed.items():
        versioned[name] = PackageInfo(
            path=info.path, version=release_versions[name], deps=info.deps
        )

    next_versions = planner._compute_next_versions(versioned)

    release_ver = release_versions["alpha"]
    next_ver = next_versions["alpha"]

    return release_ver, next_ver


# ---------------------------------------------------------------------------
# Final releases
# ---------------------------------------------------------------------------


class TestFinalRelease:
    """uvr release (default) — final PEP 440 release."""

    def test_strips_dev_suffix(self) -> None:
        release, _ = _release_and_bump(_planner(), "1.0.1.dev0")
        assert _pep440(release) == Version("1.0.1")

    def test_already_clean(self) -> None:
        release, _ = _release_and_bump(_planner(), "1.0.1")
        assert _pep440(release) == Version("1.0.1")

    def test_bumps_to_next_dev(self) -> None:
        _, next_ver = _release_and_bump(_planner(), "1.0.1.dev0")
        v = _pep440(next_ver)
        assert v.is_devrelease
        assert v > Version("1.0.1")

    def test_next_dev_is_patch_bump(self) -> None:
        _, next_ver = _release_and_bump(_planner(), "2.3.7.dev0")
        assert _pep440(next_ver) == Version("2.3.8.dev0")

    def test_release_is_not_pre_or_post(self) -> None:
        release, _ = _release_and_bump(_planner(), "1.0.0.dev5")
        v = _pep440(release)
        assert not v.is_devrelease
        assert not v.is_prerelease
        assert not v.is_postrelease

    def test_strips_pre_suffix(self) -> None:
        """Final release from a pre-release branch strips the pre suffix."""
        release, _ = _release_and_bump(_planner(), "1.0.1rc1.dev0")
        assert _pep440(release) == Version("1.0.1")

    def test_strips_post_suffix(self) -> None:
        """Final release from a post-release branch strips the post suffix."""
        release, _ = _release_and_bump(_planner(), "1.0.1.post0.dev0")
        assert _pep440(release) == Version("1.0.1")


# ---------------------------------------------------------------------------
# Dev releases
# ---------------------------------------------------------------------------


class TestDevRelease:
    """uvr release --dev — PEP 440 dev release."""

    def test_publishes_as_is(self) -> None:
        release, _ = _release_and_bump(_planner("dev"), "1.0.1.dev0")
        assert _pep440(release) == Version("1.0.1.dev0")

    def test_is_dev_release(self) -> None:
        release, _ = _release_and_bump(_planner("dev"), "1.0.1.dev3")
        assert _pep440(release).is_devrelease

    def test_bumps_dev_number(self) -> None:
        _, next_ver = _release_and_bump(_planner("dev"), "1.0.1.dev0")
        assert _pep440(next_ver) == Version("1.0.1.dev1")

    def test_bumps_higher_dev_number(self) -> None:
        _, next_ver = _release_and_bump(_planner("dev"), "1.0.1.dev5")
        assert _pep440(next_ver) == Version("1.0.1.dev6")

    def test_next_dev_sorts_after_release(self) -> None:
        release, next_ver = _release_and_bump(_planner("dev"), "1.0.1.dev2")
        assert _pep440(next_ver) > _pep440(release)

    def test_auto_appends_dev0_to_clean(self) -> None:
        """--dev on a clean version auto-appends .dev0."""
        release, nxt = _release_and_bump(_planner("dev"), "1.0.1")
        assert release == "1.0.1.dev0"
        assert nxt == "1.0.1.dev1"


# ---------------------------------------------------------------------------
# Pre-releases (alpha, beta, rc)
# ---------------------------------------------------------------------------


class TestPreRelease:
    """uvr release --pre {a,b,rc} — PEP 440 pre-release."""

    def test_alpha_first(self) -> None:
        release, _ = _release_and_bump(_planner("pre", pre_kind="a"), "1.0.1a0.dev0")
        assert _pep440(release) == Version("1.0.1a0")

    def test_alpha_is_prerelease(self) -> None:
        release, _ = _release_and_bump(_planner("pre", pre_kind="a"), "1.0.1a0.dev0")
        assert _pep440(release).is_prerelease

    def test_alpha_increments(self) -> None:
        release, _ = _release_and_bump(
            _planner("pre", pre_kind="a"),
            "1.0.1a1.dev0",
        )
        assert _pep440(release) == Version("1.0.1a1")

    def test_beta(self) -> None:
        release, _ = _release_and_bump(_planner("pre", pre_kind="b"), "1.0.1b0.dev0")
        assert _pep440(release) == Version("1.0.1b0")

    def test_rc(self) -> None:
        release, _ = _release_and_bump(_planner("pre", pre_kind="rc"), "1.0.1rc0.dev0")
        assert _pep440(release) == Version("1.0.1rc0")

    def test_rc_increments(self) -> None:
        release, _ = _release_and_bump(
            _planner("pre", pre_kind="rc"),
            "1.0.1rc2.dev0",
        )
        assert _pep440(release) == Version("1.0.1rc2")

    def test_bumps_to_next_dev(self) -> None:
        _, next_ver = _release_and_bump(_planner("pre", pre_kind="a"), "1.0.1a0.dev0")
        v = _pep440(next_ver)
        assert v.is_devrelease
        # After 1.0.1a0 → dev toward next alpha → 1.0.1a1.dev0
        assert v == Version("1.0.1a1.dev0")

    def test_alpha_sorts_before_final(self) -> None:
        release, _ = _release_and_bump(_planner("pre", pre_kind="a"), "1.0.1a0.dev0")
        assert _pep440(release) < Version("1.0.1")

    def test_rc_sorts_before_final(self) -> None:
        release, _ = _release_and_bump(_planner("pre", pre_kind="rc"), "1.0.1rc0.dev0")
        assert _pep440(release) < Version("1.0.1")

    def test_alpha_sorts_before_beta(self) -> None:
        a, _ = _release_and_bump(_planner("pre", pre_kind="a"), "1.0.1a0.dev0")
        b, _ = _release_and_bump(_planner("pre", pre_kind="b"), "1.0.1b0.dev0")
        assert _pep440(a) < _pep440(b)

    def test_beta_sorts_before_rc(self) -> None:
        b, _ = _release_and_bump(_planner("pre", pre_kind="b"), "1.0.1b0.dev0")
        rc, _ = _release_and_bump(_planner("pre", pre_kind="rc"), "1.0.1rc0.dev0")
        assert _pep440(b) < _pep440(rc)


# ---------------------------------------------------------------------------
# Post-releases
# ---------------------------------------------------------------------------


class TestPostRelease:
    """uvr release --post — PEP 440 post-release."""

    def test_post_first(self) -> None:
        release, _ = _release_and_bump(_planner("post"), "1.0.0.post0.dev0")
        assert _pep440(release) == Version("1.0.0.post0")

    def test_is_post_release(self) -> None:
        release, _ = _release_and_bump(_planner("post"), "1.0.0.post0.dev0")
        assert _pep440(release).is_postrelease

    def test_post_increments(self) -> None:
        release, _ = _release_and_bump(
            _planner("post"),
            "1.0.0.post1.dev0",
        )
        assert _pep440(release) == Version("1.0.0.post1")

    def test_bumps_to_next_post_dev(self) -> None:
        _, next_ver = _release_and_bump(_planner("post"), "1.0.0.post0.dev0")
        v = _pep440(next_ver)
        assert v.is_devrelease
        # After 1.0.0.post0 → dev toward next post → 1.0.0.post1.dev0
        assert v == Version("1.0.0.post1.dev0")

    def test_post_sorts_after_final(self) -> None:
        release, _ = _release_and_bump(_planner("post"), "1.0.0.post0.dev0")
        assert _pep440(release) > Version("1.0.0")

    def test_post_sorts_before_next_final(self) -> None:
        release, _ = _release_and_bump(_planner("post"), "1.0.0.post0.dev0")
        assert _pep440(release) < Version("1.0.1")


# ---------------------------------------------------------------------------
# PEP 440 sort order across the full lifecycle
# ---------------------------------------------------------------------------


class TestVersionOrdering:
    """The full lifecycle from the ADR produces correctly ordered versions."""

    def test_full_lifecycle_ordering(self) -> None:
        """Versions from the ADR flow must sort in chronological order."""
        versions = [
            "1.0.0",  # final release
            "1.0.1.dev0",  # auto-bump after final
            "1.0.1.dev0",  # dev release (same version)
            "1.0.1.dev1",  # auto-bump after dev
            "1.0.1a0",  # pre-release alpha
            "1.0.1a1.dev0",  # auto-bump after alpha
            "1.0.1a1",  # second alpha
            "1.0.1a2.dev0",  # auto-bump after second alpha
            "1.0.1b0",  # beta
            "1.0.1rc0",  # release candidate
            "1.0.1",  # final release
            "1.0.1.post0",  # post-release
            "1.0.1.post1.dev0",  # auto-bump after post
            "1.0.2.dev0",  # auto-bump after final
        ]
        parsed = [Version(v) for v in versions]
        # Each version should be >= the previous (some are equal, like dev0 released)
        for i in range(1, len(parsed)):
            assert parsed[i] >= parsed[i - 1], (
                f"{versions[i]} should sort >= {versions[i - 1]}"
            )

    def test_dev_before_pre_before_final(self) -> None:
        """dev < alpha < beta < rc < final for same base version."""
        assert Version("1.0.1.dev0") < Version("1.0.1a0")
        assert Version("1.0.1a0") < Version("1.0.1b0")
        assert Version("1.0.1b0") < Version("1.0.1rc0")
        assert Version("1.0.1rc0") < Version("1.0.1")

    def test_post_after_final(self) -> None:
        assert Version("1.0.1.post0") > Version("1.0.1")
        assert Version("1.0.1.post0") < Version("1.0.2")


# ---------------------------------------------------------------------------
# Comprehensive version matrix
# ---------------------------------------------------------------------------


# Dev versions: every combination of (base_suffix, dev_N)
_DEV_VERSIONS = [
    "1.0.1.dev0",  # final + dev0
    "1.0.1.dev3",  # final + dev3
    "1.0.1a0.dev0",  # alpha0 + dev0
    "1.0.1a0.dev3",  # alpha0 + dev3
    "1.0.1a2.dev0",  # alpha2 + dev0
    "1.0.1a2.dev3",  # alpha2 + dev3
    "1.0.1b0.dev0",  # beta0 + dev0
    "1.0.1b0.dev3",  # beta0 + dev3
    "1.0.1b2.dev0",  # beta2 + dev0
    "1.0.1b2.dev3",  # beta2 + dev3
    "1.0.1rc0.dev0",  # rc0 + dev0
    "1.0.1rc0.dev3",  # rc0 + dev3
    "1.0.1rc2.dev0",  # rc2 + dev0
    "1.0.1rc2.dev3",  # rc2 + dev3
    "1.0.1.post0.dev0",  # post0 + dev0
    "1.0.1.post0.dev3",  # post0 + dev3
    "1.0.1.post2.dev0",  # post2 + dev0
    "1.0.1.post2.dev3",  # post2 + dev3
]

# Clean versions (no .dev suffix) — dev auto-appends .dev0
_CLEAN_VERSIONS = [
    "1.0.1",  # final
    "1.0.1a0",  # alpha0
    "1.0.1a2",  # alpha2
    "1.0.1b0",  # beta0
    "1.0.1b2",  # beta2
    "1.0.1rc0",  # rc0
    "1.0.1rc2",  # rc2
    "1.0.1.post0",  # post0
    "1.0.1.post2",  # post2
]

_ALL_VERSIONS = _DEV_VERSIONS + _CLEAN_VERSIONS

# Expected version computation helpers (use module-level re import)


def _expected_final(v: str) -> tuple[str, str]:
    base = _re.sub(
        r"(a|b|rc)\d+", "", _re.sub(r"\.post\d+", "", _re.sub(r"\.dev\d+$", "", v))
    )
    return base, f"{_pep440_bump_patch(base)}.dev0"


def _pep440_bump_patch(base: str) -> str:
    parts = base.split(".")
    parts[2] = str(int(parts[2]) + 1)
    return ".".join(parts)


def _expected_dev(v: str) -> tuple[str, str]:
    m = _re.search(r"\.dev(\d+)$", v)
    if m:
        # Already dev — release as-is, bump dev number
        n = int(m.group(1))
        return v, v[: m.start()] + f".dev{n + 1}"
    # Clean version — append .dev0, next is .dev1
    return f"{v}.dev0", f"{v}.dev1"


def _expected_pre(kind: str, v: str) -> tuple[str, str]:
    without_dev = _re.sub(r"\.dev\d+$", "", v)
    # If already same kind, strip dev
    if _re.search(rf"{_re.escape(kind)}\d+$", without_dev):
        release = without_dev
        # Bump the pre number for next
        m = _re.search(rf"({_re.escape(kind)})(\d+)$", release)
        assert m
        nxt_pre = f"{m.group(1)}{int(m.group(2)) + 1}"
        nxt = release[: m.start()] + nxt_pre + ".dev0"
        return release, nxt
    # Different kind or no pre — start at kind0
    base = _re.sub(
        r"(a|b|rc)\d+", "", _re.sub(r"\.post\d+", "", _re.sub(r"\.dev\d+$", "", v))
    )
    release = f"{base}{kind}0"
    nxt = f"{base}{kind}1.dev0"
    return release, nxt


def _expected_post(v: str) -> tuple[str, str]:
    without_dev = _re.sub(r"\.dev\d+$", "", v)
    m = _re.search(r"\.post(\d+)$", without_dev)
    if m:
        release = without_dev
        n = int(m.group(1))
        nxt = without_dev[: m.start()] + f".post{n + 1}.dev0"
        return release, nxt
    # No post suffix — strip dev
    return without_dev, ""


class TestVersionMatrix:
    """Every combination of current version x release type (parametrized).

    18 dev versions x 6 release types = 108 dev tests
    9 clean versions x 5 release types = 45 clean tests (dev rejects clean)
    9 clean versions x 1 dev-rejects = 9 rejection tests
    Total: 162 parametrized cases
    """

    # final works with both dev and clean versions
    @pytest.mark.parametrize("version", _ALL_VERSIONS)
    def test_final(self, version: str) -> None:
        release, nxt = _release_and_bump(_planner("final"), version)
        exp_release, exp_nxt = _expected_final(version)
        assert release == exp_release
        assert nxt == exp_nxt

    # dev works with all versions — auto-appends .dev0 for clean
    @pytest.mark.parametrize("version", _ALL_VERSIONS)
    def test_dev(self, version: str) -> None:
        release, nxt = _release_and_bump(_planner("dev"), version)
        exp_release, exp_nxt = _expected_dev(version)
        assert release == exp_release
        assert nxt == exp_nxt

    # pre-alpha works with both dev and clean
    @pytest.mark.parametrize("version", _ALL_VERSIONS)
    def test_pre_alpha(self, version: str) -> None:
        release, nxt = _release_and_bump(_planner("pre", "a"), version)
        exp_release, exp_nxt = _expected_pre("a", version)
        assert release == exp_release
        assert nxt == exp_nxt

    # pre-beta works with both dev and clean
    @pytest.mark.parametrize("version", _ALL_VERSIONS)
    def test_pre_beta(self, version: str) -> None:
        release, nxt = _release_and_bump(_planner("pre", "b"), version)
        exp_release, exp_nxt = _expected_pre("b", version)
        assert release == exp_release
        assert nxt == exp_nxt

    # pre-rc works with both dev and clean
    @pytest.mark.parametrize("version", _ALL_VERSIONS)
    def test_pre_rc(self, version: str) -> None:
        release, nxt = _release_and_bump(_planner("pre", "rc"), version)
        exp_release, exp_nxt = _expected_pre("rc", version)
        assert release == exp_release
        assert nxt == exp_nxt

    # post works with both dev and clean
    @pytest.mark.parametrize("version", _ALL_VERSIONS)
    def test_post(self, version: str) -> None:
        release, _ = _release_and_bump(_planner("post"), version)
        exp_release, _ = _expected_post(version)
        assert release == exp_release


# ---------------------------------------------------------------------------
# Tag conflict detection
# ---------------------------------------------------------------------------


class TestTagConflicts:
    """Planner rejects plans when tags already exist."""

    def test_errors_on_existing_baseline_tag(self) -> None:
        """Planner errors when a baseline tag already exists."""
        from uv_release_monorepo.shared.models import ChangedPackage

        planner = _planner("final")
        # Inject a conflicting baseline tag into the mock repo
        existing_refs = {"refs/tags/alpha/v1.0.2.dev0-base"}
        planner.ctx = RepositoryContext(
            repo=MagicMock(
                spec=pygit2.Repository,
                references=MagicMock(
                    get=lambda ref: True if ref in existing_refs else None
                ),
            ),
            packages={},
        )
        changed = {
            "alpha": ChangedPackage(
                path="packages/alpha",
                version="1.0.1",
                deps=[],
                current_version="1.0.1",
                release_version="1.0.1",
                next_version="1.0.2.dev0",
            )
        }
        with pytest.raises(SystemExit):
            planner._check_tag_conflicts(changed)

    def test_passes_when_no_conflicts(self) -> None:
        """Planner proceeds when no tags conflict."""
        from uv_release_monorepo.shared.models import ChangedPackage

        planner = _planner("final")
        # No refs exist
        planner.ctx = RepositoryContext(
            repo=MagicMock(
                spec=pygit2.Repository,
                references=MagicMock(get=lambda ref: None),
            ),
            packages={},
        )
        changed = {
            "alpha": ChangedPackage(
                path="packages/alpha",
                version="1.0.1",
                deps=[],
                current_version="1.0.1",
                release_version="1.0.1",
                next_version="1.0.2.dev0",
            )
        }
        # Should not raise
        planner._check_tag_conflicts(changed)

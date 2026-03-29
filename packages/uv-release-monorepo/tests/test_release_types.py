"""ADR-0008: PEP 440 release type compliance.

Validates that the version flow from the ADR produces valid PEP 440
versions at every step — release version, tag, post-release bump, and
baseline tag.
"""

from __future__ import annotations

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
        git_tags=set(),
        packages={},
        baselines={},
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
    *,
    existing_tags: str = "",
) -> tuple[str, str]:
    """Run the planner's version computation and return (release_ver, next_dev_ver).

    next_dev_ver is the exact version that will be written to pyproject.toml.
    """
    changed = {"alpha": _pkg(pyproject_version)}

    tag_lines = existing_tags.splitlines() if existing_tags else []
    release_versions = planner._compute_release_versions(changed, tag_lines)

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

    def test_rejects_clean_version(self) -> None:
        """--dev on a non-.dev version errors with instructions."""
        planner = _planner("dev")
        changed = {"alpha": _pkg("1.0.1")}
        with pytest.raises(SystemExit):
            planner._compute_release_versions(changed, [])


# ---------------------------------------------------------------------------
# Pre-releases (alpha, beta, rc)
# ---------------------------------------------------------------------------


class TestPreRelease:
    """uvr release --pre {a,b,rc} — PEP 440 pre-release."""

    def test_alpha_first(self) -> None:
        release, _ = _release_and_bump(_planner("pre", pre_kind="a"), "1.0.1.dev2")
        assert _pep440(release) == Version("1.0.1a0")

    def test_alpha_is_prerelease(self) -> None:
        release, _ = _release_and_bump(_planner("pre", pre_kind="a"), "1.0.1.dev0")
        assert _pep440(release).is_prerelease

    def test_alpha_increments_from_tags(self) -> None:
        release, _ = _release_and_bump(
            _planner("pre", pre_kind="a"),
            "1.0.1.dev3",
            existing_tags="alpha/v1.0.1a0",
        )
        assert _pep440(release) == Version("1.0.1a1")

    def test_beta(self) -> None:
        release, _ = _release_and_bump(_planner("pre", pre_kind="b"), "1.0.1.dev0")
        assert _pep440(release) == Version("1.0.1b0")

    def test_rc(self) -> None:
        release, _ = _release_and_bump(_planner("pre", pre_kind="rc"), "1.0.1.dev0")
        assert _pep440(release) == Version("1.0.1rc0")

    def test_rc_increments(self) -> None:
        release, _ = _release_and_bump(
            _planner("pre", pre_kind="rc"),
            "1.0.1.dev5",
            existing_tags="alpha/v1.0.1rc0\nalpha/v1.0.1rc1",
        )
        assert _pep440(release) == Version("1.0.1rc2")

    def test_bumps_to_next_dev(self) -> None:
        _, next_ver = _release_and_bump(_planner("pre", pre_kind="a"), "1.0.1.dev2")
        v = _pep440(next_ver)
        assert v.is_devrelease
        # After 1.0.1a0 → dev toward next alpha → 1.0.1a1.dev0
        assert v == Version("1.0.1a1.dev0")

    def test_alpha_sorts_before_final(self) -> None:
        release, _ = _release_and_bump(_planner("pre", pre_kind="a"), "1.0.1.dev0")
        assert _pep440(release) < Version("1.0.1")

    def test_rc_sorts_before_final(self) -> None:
        release, _ = _release_and_bump(_planner("pre", pre_kind="rc"), "1.0.1.dev0")
        assert _pep440(release) < Version("1.0.1")

    def test_alpha_sorts_before_beta(self) -> None:
        a, _ = _release_and_bump(_planner("pre", pre_kind="a"), "1.0.1.dev0")
        b, _ = _release_and_bump(_planner("pre", pre_kind="b"), "1.0.1.dev0")
        assert _pep440(a) < _pep440(b)

    def test_beta_sorts_before_rc(self) -> None:
        b, _ = _release_and_bump(_planner("pre", pre_kind="b"), "1.0.1.dev0")
        rc, _ = _release_and_bump(_planner("pre", pre_kind="rc"), "1.0.1.dev0")
        assert _pep440(b) < _pep440(rc)


# ---------------------------------------------------------------------------
# Post-releases
# ---------------------------------------------------------------------------


class TestPostRelease:
    """uvr release --post — PEP 440 post-release."""

    def test_post_first(self) -> None:
        release, _ = _release_and_bump(_planner("post"), "1.0.0")
        assert _pep440(release) == Version("1.0.0.post0")

    def test_is_post_release(self) -> None:
        release, _ = _release_and_bump(_planner("post"), "1.0.0")
        assert _pep440(release).is_postrelease

    def test_post_increments(self) -> None:
        release, _ = _release_and_bump(
            _planner("post"),
            "1.0.0",
            existing_tags="alpha/v1.0.0.post0",
        )
        assert _pep440(release) == Version("1.0.0.post1")

    def test_bumps_to_next_post_dev(self) -> None:
        _, next_ver = _release_and_bump(_planner("post"), "1.0.0")
        v = _pep440(next_ver)
        assert v.is_devrelease
        # After 1.0.0.post0 → dev toward next post → 1.0.0.post1.dev0
        assert v == Version("1.0.0.post1.dev0")

    def test_post_sorts_after_final(self) -> None:
        release, _ = _release_and_bump(_planner("post"), "1.0.0")
        assert _pep440(release) > Version("1.0.0")

    def test_post_sorts_before_next_final(self) -> None:
        release, _ = _release_and_bump(_planner("post"), "1.0.0")
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
# Tag conflict detection
# ---------------------------------------------------------------------------


class TestTagConflicts:
    """Planner rejects plans when tags already exist."""

    @pytest.fixture
    def _mock_github(self) -> None:  # type: ignore[return]
        from unittest.mock import patch

        with patch(
            "uv_release_monorepo.shared.git.remote.check_release_exists",
            return_value=False,
        ):
            yield

    def test_errors_on_existing_baseline_tag(self, _mock_github: None) -> None:
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
            git_tags=set(),
            packages={},
            baselines={},
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

    def test_passes_when_no_conflicts(self, _mock_github: None) -> None:
        """Planner proceeds when no tags conflict."""
        from uv_release_monorepo.shared.models import ChangedPackage

        planner = _planner("final")
        # No refs exist
        planner.ctx = RepositoryContext(
            repo=MagicMock(
                spec=pygit2.Repository,
                references=MagicMock(get=lambda ref: None),
            ),
            git_tags=set(),
            packages={},
            baselines={},
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

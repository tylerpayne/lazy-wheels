"""Tests for find_baseline_tag with mock GitRepo."""

from __future__ import annotations


from uv_release.states.changes import _find_baseline_tag as find_baseline_tag
from uv_release.types import Version, VersionState


class _FakeGitRepo:
    """Minimal fake for GitRepo that satisfies find_baseline_tag."""

    def __init__(self, tags: dict[str, str]) -> None:
        self._tags = tags

    def find_tag(self, tag_name: str) -> str | None:
        return self._tags.get(tag_name)

    def list_tags(self, prefix: str) -> list[str]:
        return [name for name in self._tags if name.startswith(prefix)]


def _v(raw: str) -> Version:
    return Version.parse(raw)


# ---------------------------------------------------------------------------
# DEV0_STABLE: looks for baseline tag, falls back to previous release
# ---------------------------------------------------------------------------


class TestDev0StableBaseline:
    """DEV0_STABLE version finds its baseline tag."""

    def test_finds_baseline_tag(self) -> None:
        version = _v("1.0.1.dev0")
        assert version.state == VersionState.DEV0_STABLE
        repo = _FakeGitRepo({"mypkg/v1.0.1.dev0-base": "abc123"})
        tag = find_baseline_tag("mypkg", version, repo)  # type: ignore[arg-type]
        assert tag is not None
        assert tag.is_baseline is True
        assert tag.commit == "abc123"
        assert tag.raw == "mypkg/v1.0.1.dev0-base"

    def test_falls_back_to_previous_release(self) -> None:
        version = _v("1.0.1.dev0")
        repo = _FakeGitRepo({"mypkg/v1.0.0": "prev123"})
        tag = find_baseline_tag("mypkg", version, repo)  # type: ignore[arg-type]
        assert tag is not None
        assert tag.is_baseline is False
        assert tag.commit == "prev123"
        assert tag.version.raw == "1.0.0"

    def test_no_tags_returns_none(self) -> None:
        version = _v("1.0.1.dev0")
        repo = _FakeGitRepo({})
        tag = find_baseline_tag("mypkg", version, repo)  # type: ignore[arg-type]
        assert tag is None


# ---------------------------------------------------------------------------
# DEVK_STABLE: looks for dev0 baseline, falls back to previous release
# ---------------------------------------------------------------------------


class TestDevkStableBaseline:
    """DEVK_STABLE version finds dev0 baseline tag."""

    def test_finds_dev0_baseline(self) -> None:
        version = _v("1.0.1.dev3")
        assert version.state == VersionState.DEVK_STABLE
        repo = _FakeGitRepo({"mypkg/v1.0.1.dev0-base": "abc123"})
        tag = find_baseline_tag("mypkg", version, repo)  # type: ignore[arg-type]
        assert tag is not None
        assert tag.is_baseline is True
        assert tag.commit == "abc123"
        assert tag.raw == "mypkg/v1.0.1.dev0-base"

    def test_falls_back_to_previous_release(self) -> None:
        version = _v("1.0.1.dev3")
        repo = _FakeGitRepo({"mypkg/v1.0.0": "prev123"})
        tag = find_baseline_tag("mypkg", version, repo)  # type: ignore[arg-type]
        assert tag is not None
        assert tag.is_baseline is False
        assert tag.version.raw == "1.0.0"

    def test_no_tags_returns_none(self) -> None:
        version = _v("1.0.1.dev3")
        repo = _FakeGitRepo({})
        tag = find_baseline_tag("mypkg", version, repo)  # type: ignore[arg-type]
        assert tag is None


# ---------------------------------------------------------------------------
# CLEAN_STABLE: finds previous release
# ---------------------------------------------------------------------------


class TestCleanStableBaseline:
    """CLEAN_STABLE version finds previous release."""

    def test_finds_previous_release(self) -> None:
        version = _v("1.0.1")
        assert version.state == VersionState.CLEAN_STABLE
        repo = _FakeGitRepo({"mypkg/v1.0.0": "prev123"})
        tag = find_baseline_tag("mypkg", version, repo)  # type: ignore[arg-type]
        assert tag is not None
        assert tag.is_baseline is False
        assert tag.version.raw == "1.0.0"

    def test_no_previous_returns_none(self) -> None:
        version = _v("1.0.0")
        assert version.state == VersionState.CLEAN_STABLE
        repo = _FakeGitRepo({})
        tag = find_baseline_tag("mypkg", version, repo)  # type: ignore[arg-type]
        assert tag is None

    def test_skips_baseline_tags_in_candidates(self) -> None:
        version = _v("1.0.1")
        repo = _FakeGitRepo(
            {
                "mypkg/v1.0.0-base": "base123",
                "mypkg/v0.9.0": "old123",
            }
        )
        tag = find_baseline_tag("mypkg", version, repo)  # type: ignore[arg-type]
        assert tag is not None
        assert tag.version.raw == "0.9.0"


# ---------------------------------------------------------------------------
# CLEAN_POST0: finds base release tag
# ---------------------------------------------------------------------------


class TestCleanPost0Baseline:
    """CLEAN_POST0 version finds base release tag."""

    def test_finds_base_release(self) -> None:
        version = _v("1.0.1.post0")
        assert version.state == VersionState.CLEAN_POST0
        repo = _FakeGitRepo({"mypkg/v1.0.1": "base123"})
        tag = find_baseline_tag("mypkg", version, repo)  # type: ignore[arg-type]
        assert tag is not None
        assert tag.is_baseline is False
        assert tag.commit == "base123"
        assert tag.version.raw == "1.0.1"

    def test_no_base_release_returns_none(self) -> None:
        version = _v("1.0.1.post0")
        repo = _FakeGitRepo({})
        tag = find_baseline_tag("mypkg", version, repo)  # type: ignore[arg-type]
        assert tag is None


# ---------------------------------------------------------------------------
# DEV0_PRE: looks for baseline tag
# ---------------------------------------------------------------------------


class TestDev0PreBaseline:
    """DEV0_PRE version finds its baseline tag."""

    def test_finds_baseline_tag(self) -> None:
        version = _v("1.0.1a0.dev0")
        assert version.state == VersionState.DEV0_PRE
        repo = _FakeGitRepo({"mypkg/v1.0.1a0.dev0-base": "abc123"})
        tag = find_baseline_tag("mypkg", version, repo)  # type: ignore[arg-type]
        assert tag is not None
        assert tag.is_baseline is True

    def test_falls_back_to_previous_release(self) -> None:
        version = _v("1.0.1a0.dev0")
        repo = _FakeGitRepo({"mypkg/v1.0.0": "prev123"})
        tag = find_baseline_tag("mypkg", version, repo)  # type: ignore[arg-type]
        assert tag is not None
        assert tag.is_baseline is False


# ---------------------------------------------------------------------------
# DEV0_POST: looks for baseline tag
# ---------------------------------------------------------------------------


class TestDev0PostBaseline:
    """DEV0_POST version finds its baseline tag."""

    def test_finds_baseline_tag(self) -> None:
        version = _v("1.0.1.post0.dev0")
        assert version.state == VersionState.DEV0_POST
        repo = _FakeGitRepo({"mypkg/v1.0.1.post0.dev0-base": "abc123"})
        tag = find_baseline_tag("mypkg", version, repo)  # type: ignore[arg-type]
        assert tag is not None
        assert tag.is_baseline is True


# ---------------------------------------------------------------------------
# Picks highest previous release when multiple exist
# ---------------------------------------------------------------------------


class TestPreviousReleaseOrdering:
    """find_baseline_tag picks the highest version below current."""

    def test_picks_highest(self) -> None:
        version = _v("2.0.0.dev0")
        repo = _FakeGitRepo(
            {
                "mypkg/v0.9.0": "old1",
                "mypkg/v1.0.0": "old2",
                "mypkg/v1.5.0": "old3",
            }
        )
        tag = find_baseline_tag("mypkg", version, repo)  # type: ignore[arg-type]
        assert tag is not None
        assert tag.version.raw == "1.5.0"

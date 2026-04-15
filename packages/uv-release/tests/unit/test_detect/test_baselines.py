"""Tests for detect/baselines: find_baseline_tag."""

from __future__ import annotations

from typing import Any

from uv_release.detect.baselines import find_baseline_tag
from uv_release.types import Version


class _FakeGitRepo:
    """Minimal mock implementing the GitRepo interface for testing."""

    def __init__(self, tags: dict[str, str]) -> None:
        self._tags = tags

    def find_tag(self, tag_name: str) -> str | None:
        return self._tags.get(tag_name)

    def list_tags(self, prefix: str) -> list[str]:
        return [name for name in self._tags if name.startswith(prefix)]


def _repo(**tags: str) -> Any:
    return _FakeGitRepo(tags)


class TestFindBaselineTag:
    PKG_NAME = "pkg"

    def test_dev0_stable_looks_for_base_tag(self) -> None:
        """1.0.1.dev0 -> looks for pkg/v1.0.1.dev0-base."""
        repo = _repo(**{"pkg/v1.0.1.dev0-base": "aaa"})
        pkg_version = Version.parse("1.0.1.dev0")
        tag = find_baseline_tag(self.PKG_NAME, pkg_version, repo)
        assert tag is not None
        assert tag.is_baseline is True
        assert tag.commit == "aaa"
        assert "1.0.1.dev0-base" in tag.raw

    def test_devk_stable_looks_for_dev0_base(self) -> None:
        """1.0.1.dev3 -> looks for pkg/v1.0.1.dev0-base (rewinds to dev0)."""
        repo = _repo(**{"pkg/v1.0.1.dev0-base": "bbb"})
        tag = find_baseline_tag(self.PKG_NAME, Version.parse("1.0.1.dev3"), repo)
        assert tag is not None
        assert tag.is_baseline is True
        assert tag.commit == "bbb"

    def test_clean_stable_looks_for_previous_release(self) -> None:
        """1.0.1 (clean) -> looks for previous release tag below 1.0.1."""
        repo = _repo(**{"pkg/v1.0.0": "ccc"})
        tag = find_baseline_tag(self.PKG_NAME, Version.parse("1.0.1"), repo)
        assert tag is not None
        assert tag.is_baseline is False
        assert tag.commit == "ccc"

    def test_dev0_pre_looks_for_base_tag(self) -> None:
        """1.0.1a2.dev0 -> looks for pkg/v1.0.1a2.dev0-base."""
        repo = _repo(**{"pkg/v1.0.1a2.dev0-base": "ddd"})
        tag = find_baseline_tag(self.PKG_NAME, Version.parse("1.0.1a2.dev0"), repo)
        assert tag is not None
        assert tag.is_baseline is True

    def test_dev0_pre_falls_back_to_previous_release(self) -> None:
        """1.0.1a0.dev0 with no base tag -> falls back to previous release."""
        repo = _repo(**{"pkg/v1.0.0": "eee"})
        tag = find_baseline_tag(self.PKG_NAME, Version.parse("1.0.1a0.dev0"), repo)
        assert tag is not None
        assert tag.commit == "eee"

    def test_clean_pre_looks_for_previous_release(self) -> None:
        """1.0.1a2 (clean pre) -> previous release tag."""
        repo = _repo(**{"pkg/v1.0.1a1": "fff"})
        tag = find_baseline_tag(self.PKG_NAME, Version.parse("1.0.1a2"), repo)
        assert tag is not None
        assert tag.commit == "fff"

    def test_dev0_post_looks_for_base_tag(self) -> None:
        """1.0.1.post0.dev0 -> looks for pkg/v1.0.1.post0.dev0-base."""
        repo = _repo(**{"pkg/v1.0.1.post0.dev0-base": "ggg"})
        tag = find_baseline_tag(self.PKG_NAME, Version.parse("1.0.1.post0.dev0"), repo)
        assert tag is not None
        assert tag.is_baseline is True

    def test_clean_post_looks_for_base_release(self) -> None:
        """1.0.1.post0 (clean) -> looks for pkg/v1.0.1."""
        repo = _repo(**{"pkg/v1.0.1": "hhh"})
        tag = find_baseline_tag(self.PKG_NAME, Version.parse("1.0.1.post0"), repo)
        assert tag is not None
        assert tag.commit == "hhh"

    def test_first_release_returns_none(self) -> None:
        """No tags exist -> None (first release)."""
        repo = _repo()
        tag = find_baseline_tag(self.PKG_NAME, Version.parse("0.1.0.dev0"), repo)
        assert tag is None

    def test_missing_tag_returns_none(self) -> None:
        """Expected tag doesn't exist -> None."""
        repo = _repo()
        tag = find_baseline_tag(self.PKG_NAME, Version.parse("1.0.1.dev0"), repo)
        assert tag is None

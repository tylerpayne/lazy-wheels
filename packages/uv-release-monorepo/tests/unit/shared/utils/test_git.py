"""Tests for git utilities."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from uv_release_monorepo.shared.models import PackageInfo
from uv_release_monorepo.shared.utils.git import generate_release_notes


class TestGenerateReleaseNotes:
    """Tests for generate_release_notes()."""

    @patch("uv_release_monorepo.shared.utils.git.commit_log")
    def test_with_baseline_and_commits(self, mock_log: MagicMock) -> None:
        """Includes commit log when baseline tag exists."""
        mock_log.return_value = ["abc1234 fix: something", "def5678 feat: another"]
        info = PackageInfo(path="packages/a", version="1.0.0", deps=[])

        result = generate_release_notes("pkg-a", info, "pkg-a/v0.9.0")

        assert "**Released:** pkg-a 1.0.0" in result
        assert "**Commits since last release (0.9.0):**" in result
        assert "- abc1234 fix: something" in result
        assert "- def5678 feat: another" in result

    @patch("uv_release_monorepo.shared.utils.git.commit_log")
    def test_without_baseline(self, mock_log: MagicMock) -> None:
        """No commit log when no baseline tag."""
        info = PackageInfo(path="packages/a", version="1.0.0", deps=[])

        result = generate_release_notes("pkg-a", info, None)

        assert result == "**Released:** pkg-a 1.0.0"
        mock_log.assert_not_called()

    @patch("uv_release_monorepo.shared.utils.git.commit_log")
    def test_with_baseline_no_commits(self, mock_log: MagicMock) -> None:
        """No commit section when git log returns empty."""
        mock_log.return_value = []
        info = PackageInfo(path="packages/a", version="1.0.0", deps=[])

        result = generate_release_notes("pkg-a", info, "pkg-a/v0.9.0")

        assert "**Released:** pkg-a 1.0.0" in result
        assert "Commits" not in result

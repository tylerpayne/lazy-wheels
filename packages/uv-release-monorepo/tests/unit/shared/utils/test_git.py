"""Tests for git utilities."""

from __future__ import annotations

from uv_release_monorepo.shared.models import PackageInfo
from uv_release_monorepo.shared.utils.git import generate_release_notes


class TestGenerateReleaseNotes:
    """Tests for generate_release_notes()."""

    def test_header_only(self) -> None:
        """Returns just the release header."""
        info = PackageInfo(path="packages/a", version="1.0.0", deps=[])
        result = generate_release_notes("pkg-a", info)
        assert result == "**Released:** pkg-a 1.0.0"

    def test_pre_release_version(self) -> None:
        """Works with pre-release versions."""
        info = PackageInfo(path="packages/a", version="1.0.0b2", deps=[])
        result = generate_release_notes("pkg-a", info)
        assert result == "**Released:** pkg-a 1.0.0b2"

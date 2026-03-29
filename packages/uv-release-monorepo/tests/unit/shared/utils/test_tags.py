"""Tests for tag discovery utilities."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from uv_release_monorepo.shared.models import PackageInfo
from uv_release_monorepo.shared.utils.tags import find_baseline_tags, find_release_tags


class TestFindReleaseTags:
    """Tests for find_release_tags()."""

    @pytest.fixture
    def sample_packages(self) -> dict[str, PackageInfo]:
        """Create sample packages for testing."""
        return {
            "pkg-a": PackageInfo(path="packages/a", version="1.0.1.dev0", deps=[]),
            "pkg-b": PackageInfo(path="packages/b", version="1.0.1.dev0", deps=[]),
        }

    @patch("uv_release_monorepo.shared.utils.tags.print_step")
    def test_returns_per_package_releases(
        self,
        _mock_step: MagicMock,
        sample_packages: dict[str, PackageInfo],
    ) -> None:
        """Returns the most recent release for each package."""
        gh_releases = {"pkg-a/v1.0.0", "pkg-a/v0.9.0", "pkg-b/v1.0.0"}

        result = find_release_tags(sample_packages, gh_releases)

        assert result == {"pkg-a": "pkg-a/v1.0.0", "pkg-b": "pkg-b/v1.0.0"}

    @patch("uv_release_monorepo.shared.utils.tags.print_step")
    def test_returns_none_for_new_packages(
        self,
        _mock_step: MagicMock,
        sample_packages: dict[str, PackageInfo],
    ) -> None:
        """Returns None for packages with no releases."""
        gh_releases = {"pkg-a/v1.0.0"}

        result = find_release_tags(sample_packages, gh_releases)

        assert result == {"pkg-a": "pkg-a/v1.0.0", "pkg-b": None}

    @patch("uv_release_monorepo.shared.utils.tags.print_step")
    def test_all_new_packages(
        self,
        _mock_step: MagicMock,
        sample_packages: dict[str, PackageInfo],
    ) -> None:
        """When no releases exist, all return None."""
        result = find_release_tags(sample_packages, set())

        assert result == {"pkg-a": None, "pkg-b": None}

    @patch("uv_release_monorepo.shared.utils.tags.print_step")
    def test_excludes_future_versions(
        self,
        _mock_step: MagicMock,
    ) -> None:
        """Releases with versions >= current base are excluded."""
        packages = {
            "pkg-a": PackageInfo(path="packages/a", version="1.0.1.dev0", deps=[]),
        }
        gh_releases = {"pkg-a/v1.0.1", "pkg-a/v1.0.0"}

        result = find_release_tags(packages, gh_releases)

        # v1.0.1 is >= current base 1.0.1, so only v1.0.0 matches
        assert result == {"pkg-a": "pkg-a/v1.0.0"}


class TestGetBaselineTags:
    """Tests for find_baseline_tags()."""

    @pytest.fixture
    def sample_packages(self) -> dict[str, PackageInfo]:
        """Create sample packages for testing."""
        return {
            "pkg-a": PackageInfo(path="packages/a", version="1.0.1", deps=[]),
            "pkg-b": PackageInfo(path="packages/b", version="1.0.1", deps=[]),
        }

    @patch("uv_release_monorepo.shared.utils.tags.print_step")
    def test_returns_base_tags(
        self,
        _mock_step: MagicMock,
        sample_packages: dict[str, PackageInfo],
    ) -> None:
        """Returns the -base tag derived from pyproject.toml version."""
        all_tags = {"pkg-a/v1.0.1-base", "pkg-b/v1.0.1-base"}

        result = find_baseline_tags(sample_packages, all_tags=all_tags)

        assert result == {
            "pkg-a": "pkg-a/v1.0.1-base",
            "pkg-b": "pkg-b/v1.0.1-base",
        }

    @patch("uv_release_monorepo.shared.utils.tags.print_step")
    def test_returns_none_when_no_base_tag(
        self,
        _mock_step: MagicMock,
        sample_packages: dict[str, PackageInfo],
    ) -> None:
        """Returns None when no -base tag exists for a package."""
        all_tags = {"pkg-b/v1.0.1-base"}

        result = find_baseline_tags(sample_packages, all_tags=all_tags)

        assert result == {
            "pkg-a": None,
            "pkg-b": "pkg-b/v1.0.1-base",
        }

    @patch("uv_release_monorepo.shared.utils.tags.print_step")
    def test_returns_none_for_new_packages(
        self,
        _mock_step: MagicMock,
        sample_packages: dict[str, PackageInfo],
    ) -> None:
        """Returns None for packages with no tags at all."""
        result = find_baseline_tags(sample_packages, all_tags=set())

        assert result == {"pkg-a": None, "pkg-b": None}

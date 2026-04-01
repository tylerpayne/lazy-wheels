"""Tests for change detection utilities."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from uv_release_monorepo.shared.models import PackageInfo
from uv_release_monorepo.shared.utils.changes import detect_changes

_MOD = "uv_release_monorepo.shared.utils.changes"


def _mock_repo() -> MagicMock:
    """Create a mock repo with a HEAD commit.

    references.get returns None by default so that release-tag lookups
    in detect_changes don't falsely match.
    """
    repo = MagicMock()
    repo.revparse_single.return_value = MagicMock()  # HEAD commit
    repo.references.get.return_value = None
    return repo


class TestDetectChanges:
    """Tests for detect_changes()."""

    @pytest.fixture
    def sample_packages(self) -> dict[str, PackageInfo]:
        """Create a sample package set for testing."""
        return {
            "pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[]),
            "pkg-b": PackageInfo(path="packages/b", version="1.0.0", deps=["pkg-a"]),
            "pkg-c": PackageInfo(path="packages/c", version="1.0.0", deps=["pkg-b"]),
        }

    @pytest.fixture
    def all_tags(self) -> dict[str, str | None]:
        """All packages have a tag."""
        return {
            "pkg-a": "pkg-a/v1.0.0",
            "pkg-b": "pkg-b/v1.0.0",
            "pkg-c": "pkg-c/v1.0.0",
        }

    @pytest.fixture
    def no_tags(self) -> dict[str, str | None]:
        """No packages have tags (first release)."""
        return {"pkg-a": None, "pkg-b": None, "pkg-c": None}

    @patch(f"{_MOD}.path_changed")
    @patch(f"{_MOD}._resolve_tag")
    @patch(f"{_MOD}.print_step")
    def test_first_release_all_changed(
        self,
        _step: MagicMock,
        _resolve: MagicMock,
        _changed: MagicMock,
        sample_packages: dict[str, PackageInfo],
        no_tags: dict[str, None],
    ) -> None:
        """On first release (no tags), all packages are marked changed."""
        changed = detect_changes(
            sample_packages, baselines=no_tags, rebuild_all=False, repo=_mock_repo()
        )
        assert set(changed) == {"pkg-a", "pkg-b", "pkg-c"}

    @patch(f"{_MOD}.path_changed")
    @patch(f"{_MOD}._resolve_tag")
    @patch(f"{_MOD}.print_step")
    def test_rebuild_all_marks_everything_dirty(
        self,
        _step: MagicMock,
        _resolve: MagicMock,
        _changed: MagicMock,
        sample_packages: dict[str, PackageInfo],
        all_tags: dict[str, str],
    ) -> None:
        """rebuild_all=True marks all packages as changed regardless of git diff."""
        changed = detect_changes(
            sample_packages, baselines=all_tags, rebuild_all=True, repo=_mock_repo()
        )
        assert set(changed) == {"pkg-a", "pkg-b", "pkg-c"}

    @patch(f"{_MOD}.path_changed")
    @patch(f"{_MOD}._resolve_tag", return_value=MagicMock())
    @patch(f"{_MOD}.print_step")
    def test_single_package_changed(
        self,
        _step: MagicMock,
        _resolve: MagicMock,
        mock_changed: MagicMock,
        sample_packages: dict[str, PackageInfo],
        all_tags: dict[str, str],
    ) -> None:
        """When only one leaf package changes, only it is rebuilt."""

        def path_changed(_repo, _old, _new, path):
            return path == "packages/c"

        mock_changed.side_effect = path_changed

        changed = detect_changes(
            sample_packages, baselines=all_tags, rebuild_all=False, repo=_mock_repo()
        )
        assert set(changed) == {"pkg-c"}

    @patch(f"{_MOD}.path_changed")
    @patch(f"{_MOD}._resolve_tag", return_value=MagicMock())
    @patch(f"{_MOD}.print_step")
    def test_dependency_change_propagates(
        self,
        _step: MagicMock,
        _resolve: MagicMock,
        mock_changed: MagicMock,
        sample_packages: dict[str, PackageInfo],
        all_tags: dict[str, str],
    ) -> None:
        """When a dependency changes, its dependents are also marked dirty."""

        def path_changed(_repo, _old, _new, path):
            return path == "packages/a"

        mock_changed.side_effect = path_changed

        changed = detect_changes(
            sample_packages, baselines=all_tags, rebuild_all=False, repo=_mock_repo()
        )
        assert set(changed) == {"pkg-a", "pkg-b", "pkg-c"}

    @patch(f"{_MOD}.path_changed")
    @patch(f"{_MOD}._resolve_tag", return_value=MagicMock())
    @patch(f"{_MOD}.print_step")
    def test_middle_package_change_propagates_to_dependents(
        self,
        _step: MagicMock,
        _resolve: MagicMock,
        mock_changed: MagicMock,
        sample_packages: dict[str, PackageInfo],
        all_tags: dict[str, str],
    ) -> None:
        """When a middle package changes, only it and its dependents are dirty."""

        def path_changed(_repo, _old, _new, path):
            return path == "packages/b"

        mock_changed.side_effect = path_changed

        changed = detect_changes(
            sample_packages, baselines=all_tags, rebuild_all=False, repo=_mock_repo()
        )
        assert set(changed) == {"pkg-b", "pkg-c"}

    @patch(f"{_MOD}.path_changed", return_value=False)
    @patch(f"{_MOD}._resolve_tag", return_value=MagicMock())
    @patch(f"{_MOD}.print_step")
    def test_root_pyproject_change_does_not_mark_packages_dirty(
        self,
        _step: MagicMock,
        _resolve: MagicMock,
        _changed: MagicMock,
        sample_packages: dict[str, PackageInfo],
        all_tags: dict[str, str],
    ) -> None:
        """Root pyproject.toml changes alone don't trigger package rebuilds."""
        changed = detect_changes(
            sample_packages, baselines=all_tags, rebuild_all=False, repo=_mock_repo()
        )
        assert changed == []

    @patch(f"{_MOD}.path_changed", return_value=False)
    @patch(f"{_MOD}._resolve_tag", return_value=MagicMock())
    @patch(f"{_MOD}.print_step")
    def test_no_changes_returns_empty(
        self,
        _step: MagicMock,
        _resolve: MagicMock,
        _changed: MagicMock,
        sample_packages: dict[str, PackageInfo],
        all_tags: dict[str, str],
    ) -> None:
        """When nothing changed, returns empty changed list."""
        changed = detect_changes(
            sample_packages, baselines=all_tags, rebuild_all=False, repo=_mock_repo()
        )
        assert changed == []


class TestDetectChangesDiamondDeps:
    """Test detect_changes with diamond dependency pattern."""

    @pytest.fixture
    def diamond_packages(self) -> dict[str, PackageInfo]:
        """Diamond: top depends on left and right, both depend on bottom."""
        return {
            "bottom": PackageInfo(path="packages/bottom", version="1.0.0", deps=[]),
            "left": PackageInfo(path="packages/left", version="1.0.0", deps=["bottom"]),
            "right": PackageInfo(
                path="packages/right", version="1.0.0", deps=["bottom"]
            ),
            "top": PackageInfo(
                path="packages/top", version="1.0.0", deps=["left", "right"]
            ),
        }

    @pytest.fixture
    def diamond_tags(self) -> dict[str, str | None]:
        """All diamond packages have tags."""
        return {
            "bottom": "bottom/v1.0.0",
            "left": "left/v1.0.0",
            "right": "right/v1.0.0",
            "top": "top/v1.0.0",
        }

    @patch(f"{_MOD}.path_changed")
    @patch(f"{_MOD}._resolve_tag", return_value=MagicMock())
    @patch(f"{_MOD}.print_step")
    def test_bottom_change_propagates_to_all(
        self,
        _step: MagicMock,
        _resolve: MagicMock,
        mock_changed: MagicMock,
        diamond_packages: dict[str, PackageInfo],
        diamond_tags: dict[str, str],
    ) -> None:
        """Changing bottom affects all packages in diamond."""
        mock_changed.side_effect = lambda _r, _o, _n, p: p == "packages/bottom"
        changed = detect_changes(
            diamond_packages,
            baselines=diamond_tags,
            rebuild_all=False,
            repo=_mock_repo(),
        )
        assert set(changed) == {"bottom", "left", "right", "top"}

    @patch(f"{_MOD}.path_changed")
    @patch(f"{_MOD}._resolve_tag", return_value=MagicMock())
    @patch(f"{_MOD}.print_step")
    def test_left_change_propagates_to_top_only(
        self,
        _step: MagicMock,
        _resolve: MagicMock,
        mock_changed: MagicMock,
        diamond_packages: dict[str, PackageInfo],
        diamond_tags: dict[str, str],
    ) -> None:
        """Changing left affects only left and top."""
        mock_changed.side_effect = lambda _r, _o, _n, p: p == "packages/left"
        changed = detect_changes(
            diamond_packages,
            baselines=diamond_tags,
            rebuild_all=False,
            repo=_mock_repo(),
        )
        assert set(changed) == {"left", "top"}

    @patch(f"{_MOD}.path_changed")
    @patch(f"{_MOD}._resolve_tag", return_value=MagicMock())
    @patch(f"{_MOD}.print_step")
    def test_top_change_only_affects_top(
        self,
        _step: MagicMock,
        _resolve: MagicMock,
        mock_changed: MagicMock,
        diamond_packages: dict[str, PackageInfo],
        diamond_tags: dict[str, str],
    ) -> None:
        """Changing top affects only top (no dependents)."""
        mock_changed.side_effect = lambda _r, _o, _n, p: p == "packages/top"
        changed = detect_changes(
            diamond_packages,
            baselines=diamond_tags,
            rebuild_all=False,
            repo=_mock_repo(),
        )
        assert set(changed) == {"top"}

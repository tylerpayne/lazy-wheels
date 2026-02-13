"""Tests for lazy_wheels.pipeline."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lazy_wheels.models import PackageInfo
from lazy_wheels.pipeline import (
    detect_changes,
    fetch_unchanged_wheels,
    find_last_tag,
    run_release,
)


class TestFindLastTag:
    """Tests for find_last_tag()."""

    @patch("lazy_wheels.pipeline.git")
    @patch("lazy_wheels.pipeline.step")
    def test_returns_most_recent_tag(
        self, mock_step: MagicMock, mock_git: MagicMock
    ) -> None:
        """When tags exist, returns the first (most recent) one."""
        mock_git.return_value = (
            "v2024.01.15-abc123\nv2024.01.14-def456\nv2024.01.13-ghi789"
        )

        result = find_last_tag()

        assert result == "v2024.01.15-abc123"
        mock_git.assert_called_once_with(
            "tag", "--list", "v*", "--sort=-v:refname", check=False
        )

    @patch("lazy_wheels.pipeline.git")
    @patch("lazy_wheels.pipeline.step")
    def test_returns_none_when_no_tags(
        self, mock_step: MagicMock, mock_git: MagicMock
    ) -> None:
        """When no tags exist, returns None."""
        mock_git.return_value = ""

        result = find_last_tag()

        assert result is None

    @patch("lazy_wheels.pipeline.git")
    @patch("lazy_wheels.pipeline.step")
    def test_returns_single_tag(
        self, mock_step: MagicMock, mock_git: MagicMock
    ) -> None:
        """When only one tag exists, returns it."""
        mock_git.return_value = "v2024.01.15-abc123"

        result = find_last_tag()

        assert result == "v2024.01.15-abc123"


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
    def topo_order(self) -> list[str]:
        """Topological order for sample packages."""
        return ["pkg-a", "pkg-b", "pkg-c"]

    @patch("lazy_wheels.pipeline.git")
    @patch("lazy_wheels.pipeline.step")
    def test_first_release_all_changed(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        sample_packages: dict[str, PackageInfo],
        topo_order: list[str],
    ) -> None:
        """On first release (no last_tag), all packages are marked changed."""
        mock_git.return_value = (
            "packages/a/src.py\npackages/b/src.py\npackages/c/src.py"
        )

        changed, unchanged = detect_changes(
            sample_packages, topo_order, last_tag=None, force_all=False
        )

        assert set(changed) == {"pkg-a", "pkg-b", "pkg-c"}
        assert unchanged == []

    @patch("lazy_wheels.pipeline.git")
    @patch("lazy_wheels.pipeline.step")
    def test_force_all_marks_everything_dirty(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        sample_packages: dict[str, PackageInfo],
        topo_order: list[str],
    ) -> None:
        """force_all=True marks all packages as changed regardless of git diff."""
        mock_git.return_value = ""  # No actual changes

        changed, unchanged = detect_changes(
            sample_packages, topo_order, last_tag="v1.0.0", force_all=True
        )

        assert set(changed) == {"pkg-a", "pkg-b", "pkg-c"}
        assert unchanged == []

    @patch("lazy_wheels.pipeline.git")
    @patch("lazy_wheels.pipeline.step")
    def test_single_package_changed(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        sample_packages: dict[str, PackageInfo],
        topo_order: list[str],
    ) -> None:
        """When only one leaf package changes, only it is rebuilt."""
        mock_git.return_value = "packages/c/src.py"

        changed, unchanged = detect_changes(
            sample_packages, topo_order, last_tag="v1.0.0", force_all=False
        )

        assert changed == ["pkg-c"]
        assert unchanged == ["pkg-a", "pkg-b"]

    @patch("lazy_wheels.pipeline.git")
    @patch("lazy_wheels.pipeline.step")
    def test_dependency_change_propagates(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        sample_packages: dict[str, PackageInfo],
        topo_order: list[str],
    ) -> None:
        """When a dependency changes, its dependents are also marked dirty."""
        mock_git.return_value = "packages/a/src.py"  # Only pkg-a changed

        changed, unchanged = detect_changes(
            sample_packages, topo_order, last_tag="v1.0.0", force_all=False
        )

        # pkg-a changed directly, pkg-b and pkg-c are dirty because they depend on it
        assert changed == ["pkg-a", "pkg-b", "pkg-c"]
        assert unchanged == []

    @patch("lazy_wheels.pipeline.git")
    @patch("lazy_wheels.pipeline.step")
    def test_middle_package_change_propagates_to_dependents(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        sample_packages: dict[str, PackageInfo],
        topo_order: list[str],
    ) -> None:
        """When a middle package changes, only it and its dependents are dirty."""
        mock_git.return_value = "packages/b/src.py"  # Only pkg-b changed

        changed, unchanged = detect_changes(
            sample_packages, topo_order, last_tag="v1.0.0", force_all=False
        )

        # pkg-b changed, pkg-c depends on it, pkg-a is unaffected
        assert changed == ["pkg-b", "pkg-c"]
        assert unchanged == ["pkg-a"]

    @patch("lazy_wheels.pipeline.git")
    @patch("lazy_wheels.pipeline.step")
    def test_root_pyproject_change_marks_all_dirty(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        sample_packages: dict[str, PackageInfo],
        topo_order: list[str],
    ) -> None:
        """When root pyproject.toml changes, all packages are marked dirty."""
        mock_git.return_value = "pyproject.toml"

        changed, unchanged = detect_changes(
            sample_packages, topo_order, last_tag="v1.0.0", force_all=False
        )

        assert set(changed) == {"pkg-a", "pkg-b", "pkg-c"}
        assert unchanged == []

    @patch("lazy_wheels.pipeline.git")
    @patch("lazy_wheels.pipeline.step")
    def test_uv_lock_change_marks_all_dirty(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        sample_packages: dict[str, PackageInfo],
        topo_order: list[str],
    ) -> None:
        """When uv.lock changes, all packages are marked dirty."""
        mock_git.return_value = "uv.lock"

        changed, unchanged = detect_changes(
            sample_packages, topo_order, last_tag="v1.0.0", force_all=False
        )

        assert set(changed) == {"pkg-a", "pkg-b", "pkg-c"}
        assert unchanged == []

    @patch("lazy_wheels.pipeline.git")
    @patch("lazy_wheels.pipeline.step")
    def test_no_changes_returns_empty(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        sample_packages: dict[str, PackageInfo],
        topo_order: list[str],
    ) -> None:
        """When nothing changed, returns empty changed list."""
        mock_git.return_value = "unrelated/file.txt"  # Change outside packages

        changed, unchanged = detect_changes(
            sample_packages, topo_order, last_tag="v1.0.0", force_all=False
        )

        assert changed == []
        assert unchanged == ["pkg-a", "pkg-b", "pkg-c"]

    @patch("lazy_wheels.pipeline.git")
    @patch("lazy_wheels.pipeline.step")
    def test_preserves_topo_order(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        sample_packages: dict[str, PackageInfo],
        topo_order: list[str],
    ) -> None:
        """Changed packages are returned in topological order."""
        # Change pkg-c and pkg-a (not in topo order)
        mock_git.return_value = "packages/c/src.py\npackages/a/src.py"

        changed, unchanged = detect_changes(
            sample_packages, topo_order, last_tag="v1.0.0", force_all=False
        )

        # Should be in topo order: a, then b (propagated), then c
        assert changed == ["pkg-a", "pkg-b", "pkg-c"]


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
    def diamond_order(self) -> list[str]:
        return ["bottom", "left", "right", "top"]

    @patch("lazy_wheels.pipeline.git")
    @patch("lazy_wheels.pipeline.step")
    def test_bottom_change_propagates_to_all(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        diamond_packages: dict[str, PackageInfo],
        diamond_order: list[str],
    ) -> None:
        """Changing bottom affects all packages in diamond."""
        mock_git.return_value = "packages/bottom/src.py"

        changed, unchanged = detect_changes(
            diamond_packages, diamond_order, last_tag="v1.0.0", force_all=False
        )

        assert set(changed) == {"bottom", "left", "right", "top"}
        assert unchanged == []

    @patch("lazy_wheels.pipeline.git")
    @patch("lazy_wheels.pipeline.step")
    def test_left_change_propagates_to_top_only(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        diamond_packages: dict[str, PackageInfo],
        diamond_order: list[str],
    ) -> None:
        """Changing left affects only left and top."""
        mock_git.return_value = "packages/left/src.py"

        changed, unchanged = detect_changes(
            diamond_packages, diamond_order, last_tag="v1.0.0", force_all=False
        )

        assert set(changed) == {"left", "top"}
        assert set(unchanged) == {"bottom", "right"}

    @patch("lazy_wheels.pipeline.git")
    @patch("lazy_wheels.pipeline.step")
    def test_top_change_only_affects_top(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        diamond_packages: dict[str, PackageInfo],
        diamond_order: list[str],
    ) -> None:
        """Changing top affects only top (no dependents)."""
        mock_git.return_value = "packages/top/src.py"

        changed, unchanged = detect_changes(
            diamond_packages, diamond_order, last_tag="v1.0.0", force_all=False
        )

        assert changed == ["top"]
        assert set(unchanged) == {"bottom", "left", "right"}


class TestFetchUnchangedWheels:
    """Tests for fetch_unchanged_wheels()."""

    @patch("lazy_wheels.pipeline.run")
    @patch("lazy_wheels.pipeline.step")
    @patch("lazy_wheels.pipeline.Path")
    def test_copies_matching_wheels(
        self,
        mock_path_cls: MagicMock,
        mock_step: MagicMock,
        mock_run: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Wheels that exist in prev release are copied to dist/."""
        # Setup tmp directories
        tmp_wheels = tmp_path / "prev-wheels"
        tmp_wheels.mkdir()
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()

        # Create a wheel file in tmp
        wheel_file = tmp_wheels / "pkg_a-1.0.0-py3-none-any.whl"
        wheel_file.write_text("fake wheel content")

        # Mock Path to return our tmp directories
        mock_path_cls.side_effect = lambda p: (
            tmp_wheels
            if p == "/tmp/prev-wheels"
            else dist_dir
            if p == "dist"
            else Path(p)
        )

        fetch_unchanged_wheels(["pkg-a"], "v1.0.0")

        # Verify gh release download was called
        mock_run.assert_called_once()
        assert "download" in mock_run.call_args[0]

    @patch("lazy_wheels.pipeline.run")
    @patch("lazy_wheels.pipeline.step")
    def test_missing_wheel_not_copied(
        self,
        mock_step: MagicMock,
        mock_run: MagicMock,
        tmp_path: Path,
    ) -> None:
        """If a wheel doesn't exist in prev release, it's silently skipped."""
        # Create real dist directory
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()

        # Patch Path to use real tmp_path for /tmp/prev-wheels
        tmp_wheels = tmp_path / "prev-wheels"
        tmp_wheels.mkdir()
        # Note: we do NOT create pkg_a wheel - it's missing

        with patch("lazy_wheels.pipeline.Path") as mock_path_cls:
            mock_path_cls.side_effect = lambda p: (
                tmp_wheels
                if p == "/tmp/prev-wheels"
                else dist_dir
                if p == "dist"
                else Path(p)
            )

            fetch_unchanged_wheels(["pkg-a"], "v1.0.0")

        # dist should be empty - no wheel was copied
        assert list(dist_dir.glob("*.whl")) == []

    @patch("lazy_wheels.pipeline.run")
    @patch("lazy_wheels.pipeline.step")
    def test_skips_when_no_last_tag(
        self,
        mock_step: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        """When last_tag is None, does nothing."""
        fetch_unchanged_wheels(["pkg-a"], None)

        mock_run.assert_not_called()
        mock_step.assert_not_called()

    @patch("lazy_wheels.pipeline.run")
    @patch("lazy_wheels.pipeline.step")
    def test_skips_when_no_unchanged(
        self,
        mock_step: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        """When unchanged list is empty, does nothing."""
        fetch_unchanged_wheels([], "v1.0.0")

        mock_run.assert_not_called()
        mock_step.assert_not_called()


class TestRunRelease:
    """Integration test for the full release pipeline."""

    @patch("lazy_wheels.pipeline.publish_release")
    @patch("lazy_wheels.pipeline.commit_bumps")
    @patch("lazy_wheels.pipeline.bump_versions")
    @patch("lazy_wheels.pipeline.create_tag")
    @patch("lazy_wheels.pipeline.build_packages")
    @patch("lazy_wheels.pipeline.fetch_unchanged_wheels")
    @patch("lazy_wheels.pipeline.detect_changes")
    @patch("lazy_wheels.pipeline.find_last_tag")
    @patch("lazy_wheels.pipeline.discover_packages")
    @patch("lazy_wheels.pipeline.Path")
    def test_golden_path_partial_rebuild(
        self,
        mock_path: MagicMock,
        mock_discover: MagicMock,
        mock_find_tag: MagicMock,
        mock_detect: MagicMock,
        mock_fetch: MagicMock,
        mock_build: MagicMock,
        mock_create_tag: MagicMock,
        mock_bump: MagicMock,
        mock_commit: MagicMock,
        mock_publish: MagicMock,
    ) -> None:
        """Test golden path: pkg-a unchanged, pkg-b and pkg-c rebuilt."""
        # Setup: 3 packages where pkg-b changed, pkg-c depends on pkg-b
        packages = {
            "pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[]),
            "pkg-b": PackageInfo(path="packages/b", version="1.0.0", deps=["pkg-a"]),
            "pkg-c": PackageInfo(path="packages/c", version="1.0.0", deps=["pkg-b"]),
        }
        topo_order = ["pkg-a", "pkg-b", "pkg-c"]

        # Mock return values
        mock_path.return_value.mkdir = MagicMock()
        mock_discover.return_value = (packages, topo_order)
        mock_find_tag.return_value = "v2024.01.01-abc123"
        # pkg-b changed directly, pkg-c is dirty because it depends on pkg-b
        mock_detect.return_value = (["pkg-b", "pkg-c"], ["pkg-a"])
        mock_create_tag.return_value = "v2024.01.02-def456"
        mock_bump.return_value = {
            "pkg-b": MagicMock(old="1.0.0", new="1.0.1"),
            "pkg-c": MagicMock(old="1.0.0", new="1.0.1"),
        }

        # Execute
        run_release()

        # Verify discover was called
        mock_discover.assert_called_once()

        # Verify detect_changes received correct args
        mock_detect.assert_called_once_with(
            packages, topo_order, "v2024.01.01-abc123", False
        )

        # Verify fetch_unchanged_wheels called for pkg-a only
        mock_fetch.assert_called_once_with(["pkg-a"], "v2024.01.01-abc123")

        # Verify build_packages called with only changed packages
        mock_build.assert_called_once_with(packages, ["pkg-b", "pkg-c"])

        # Verify bump_versions called with only changed packages
        mock_bump.assert_called_once_with(packages, ["pkg-b", "pkg-c"])

        # Verify commit and publish were called
        mock_commit.assert_called_once()
        mock_publish.assert_called_once()

    @patch("lazy_wheels.pipeline.publish_release")
    @patch("lazy_wheels.pipeline.commit_bumps")
    @patch("lazy_wheels.pipeline.bump_versions")
    @patch("lazy_wheels.pipeline.create_tag")
    @patch("lazy_wheels.pipeline.build_packages")
    @patch("lazy_wheels.pipeline.fetch_unchanged_wheels")
    @patch("lazy_wheels.pipeline.detect_changes")
    @patch("lazy_wheels.pipeline.find_last_tag")
    @patch("lazy_wheels.pipeline.discover_packages")
    @patch("lazy_wheels.pipeline.Path")
    def test_no_changes_exits_early(
        self,
        mock_path: MagicMock,
        mock_discover: MagicMock,
        mock_find_tag: MagicMock,
        mock_detect: MagicMock,
        mock_fetch: MagicMock,
        mock_build: MagicMock,
        mock_create_tag: MagicMock,
        mock_bump: MagicMock,
        mock_commit: MagicMock,
        mock_publish: MagicMock,
    ) -> None:
        """When nothing changed, pipeline exits early without building."""
        packages = {"pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[])}

        mock_path.return_value.mkdir = MagicMock()
        mock_discover.return_value = (packages, ["pkg-a"])
        mock_find_tag.return_value = "v2024.01.01-abc123"
        mock_detect.return_value = ([], ["pkg-a"])  # Nothing changed

        # Execute
        run_release()

        # Verify build/bump/publish were NOT called
        mock_build.assert_not_called()
        mock_bump.assert_not_called()
        mock_publish.assert_not_called()

"""Tests for lazy_wheels.pipeline."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lazy_wheels.models import PackageInfo
from lazy_wheels.pipeline import (
    check_for_existing_wheels,
    detect_changes,
    fetch_unchanged_wheels,
    find_last_tags,
    find_next_release_tag,
    get_existing_wheels,
    run_release,
    tag_changed_packages,
)


class TestFindLastTags:
    """Tests for find_last_tags()."""

    @pytest.fixture
    def sample_packages(self) -> dict[str, PackageInfo]:
        """Create sample packages for testing."""
        return {
            "pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[]),
            "pkg-b": PackageInfo(path="packages/b", version="1.0.0", deps=[]),
        }

    @patch("lazy_wheels.pipeline.git")
    @patch("lazy_wheels.pipeline.step")
    def test_returns_per_package_tags(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        sample_packages: dict[str, PackageInfo],
    ) -> None:
        """Returns the most recent tag for each package."""
        mock_git.side_effect = [
            "pkg-a/v1.0.0\npkg-a/v0.9.0",  # Tags for pkg-a
            "pkg-b/v2.0.0",  # Tags for pkg-b
        ]

        result = find_last_tags(sample_packages)

        assert result == {"pkg-a": "pkg-a/v1.0.0", "pkg-b": "pkg-b/v2.0.0"}

    @patch("lazy_wheels.pipeline.git")
    @patch("lazy_wheels.pipeline.step")
    def test_returns_none_for_new_packages(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        sample_packages: dict[str, PackageInfo],
    ) -> None:
        """Returns None for packages with no tags."""
        mock_git.side_effect = [
            "pkg-a/v1.0.0",  # pkg-a has a tag
            "",  # pkg-b has no tags
        ]

        result = find_last_tags(sample_packages)

        assert result == {"pkg-a": "pkg-a/v1.0.0", "pkg-b": None}

    @patch("lazy_wheels.pipeline.git")
    @patch("lazy_wheels.pipeline.step")
    def test_all_new_packages(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        sample_packages: dict[str, PackageInfo],
    ) -> None:
        """When no packages have tags, all return None."""
        mock_git.return_value = ""

        result = find_last_tags(sample_packages)

        assert result == {"pkg-a": None, "pkg-b": None}


class TestFindNextReleaseTag:
    """Tests for find_next_release_tag()."""

    @patch("lazy_wheels.pipeline.git")
    def test_first_release(self, mock_git: MagicMock) -> None:
        """When no releases exist, returns r1."""
        mock_git.return_value = ""

        result = find_next_release_tag()

        assert result == "r1"

    @patch("lazy_wheels.pipeline.git")
    def test_increments_from_last(self, mock_git: MagicMock) -> None:
        """Returns one more than the highest existing release."""
        mock_git.return_value = "r5\nr4\nr3"

        result = find_next_release_tag()

        assert result == "r6"

    @patch("lazy_wheels.pipeline.git")
    def test_handles_single_release(self, mock_git: MagicMock) -> None:
        """Works with a single existing release."""
        mock_git.return_value = "r1"

        result = find_next_release_tag()

        assert result == "r2"


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

    @patch("lazy_wheels.pipeline.git")
    @patch("lazy_wheels.pipeline.step")
    def test_first_release_all_changed(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        sample_packages: dict[str, PackageInfo],
        no_tags: dict[str, None],
    ) -> None:
        """On first release (no tags), all packages are marked changed."""
        # No git diff called when tags are None

        changed = detect_changes(sample_packages, last_tags=no_tags, force_all=False)

        assert set(changed) == {"pkg-a", "pkg-b", "pkg-c"}

    @patch("lazy_wheels.pipeline.git")
    @patch("lazy_wheels.pipeline.step")
    def test_force_all_marks_everything_dirty(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        sample_packages: dict[str, PackageInfo],
        all_tags: dict[str, str],
    ) -> None:
        """force_all=True marks all packages as changed regardless of git diff."""
        changed = detect_changes(sample_packages, last_tags=all_tags, force_all=True)

        assert set(changed) == {"pkg-a", "pkg-b", "pkg-c"}

    @patch("lazy_wheels.pipeline.git")
    @patch("lazy_wheels.pipeline.step")
    def test_single_package_changed(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        sample_packages: dict[str, PackageInfo],
        all_tags: dict[str, str],
    ) -> None:
        """When only one leaf package changes, only it is rebuilt."""
        # Each package calls git diff against its own tag
        mock_git.side_effect = [
            "",  # pkg-a: no changes
            "",  # pkg-b: no changes
            "packages/c/src.py",  # pkg-c: changed
        ]

        changed = detect_changes(sample_packages, last_tags=all_tags, force_all=False)

        assert set(changed) == {"pkg-c"}

    @patch("lazy_wheels.pipeline.git")
    @patch("lazy_wheels.pipeline.step")
    def test_dependency_change_propagates(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        sample_packages: dict[str, PackageInfo],
        all_tags: dict[str, str],
    ) -> None:
        """When a dependency changes, its dependents are also marked dirty."""
        mock_git.side_effect = [
            "packages/a/src.py",  # pkg-a: changed
            "",  # pkg-b: no direct changes
            "",  # pkg-c: no direct changes
        ]

        changed = detect_changes(sample_packages, last_tags=all_tags, force_all=False)

        # pkg-a changed directly, pkg-b and pkg-c are dirty because they depend on it
        assert set(changed) == {"pkg-a", "pkg-b", "pkg-c"}

    @patch("lazy_wheels.pipeline.git")
    @patch("lazy_wheels.pipeline.step")
    def test_middle_package_change_propagates_to_dependents(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        sample_packages: dict[str, PackageInfo],
        all_tags: dict[str, str],
    ) -> None:
        """When a middle package changes, only it and its dependents are dirty."""
        mock_git.side_effect = [
            "",  # pkg-a: no changes
            "packages/b/src.py",  # pkg-b: changed
            "",  # pkg-c: no direct changes
        ]

        changed = detect_changes(sample_packages, last_tags=all_tags, force_all=False)

        # pkg-b changed, pkg-c depends on it, pkg-a is unaffected
        assert set(changed) == {"pkg-b", "pkg-c"}

    @patch("lazy_wheels.pipeline.git")
    @patch("lazy_wheels.pipeline.step")
    def test_root_pyproject_change_marks_package_dirty(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        sample_packages: dict[str, PackageInfo],
        all_tags: dict[str, str],
    ) -> None:
        """When root pyproject.toml changes since a package's tag, it's marked dirty."""
        mock_git.side_effect = [
            "pyproject.toml",  # pkg-a: root config changed
            "pyproject.toml",  # pkg-b: root config changed
            "pyproject.toml",  # pkg-c: root config changed
        ]

        changed = detect_changes(sample_packages, last_tags=all_tags, force_all=False)

        assert set(changed) == {"pkg-a", "pkg-b", "pkg-c"}

    @patch("lazy_wheels.pipeline.git")
    @patch("lazy_wheels.pipeline.step")
    def test_uv_lock_change_marks_package_dirty(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        sample_packages: dict[str, PackageInfo],
        all_tags: dict[str, str],
    ) -> None:
        """When uv.lock changes since a package's tag, it's marked dirty."""
        mock_git.side_effect = [
            "uv.lock",  # pkg-a: lock file changed
            "uv.lock",  # pkg-b: lock file changed
            "uv.lock",  # pkg-c: lock file changed
        ]

        changed = detect_changes(sample_packages, last_tags=all_tags, force_all=False)

        assert set(changed) == {"pkg-a", "pkg-b", "pkg-c"}

    @patch("lazy_wheels.pipeline.git")
    @patch("lazy_wheels.pipeline.step")
    def test_no_changes_returns_empty(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        sample_packages: dict[str, PackageInfo],
        all_tags: dict[str, str],
    ) -> None:
        """When nothing changed, returns empty changed list."""
        mock_git.side_effect = [
            "unrelated/file.txt",  # pkg-a: unrelated change
            "unrelated/file.txt",  # pkg-b: unrelated change
            "unrelated/file.txt",  # pkg-c: unrelated change
        ]

        changed = detect_changes(sample_packages, last_tags=all_tags, force_all=False)

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

    @patch("lazy_wheels.pipeline.git")
    @patch("lazy_wheels.pipeline.step")
    def test_bottom_change_propagates_to_all(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        diamond_packages: dict[str, PackageInfo],
        diamond_tags: dict[str, str],
    ) -> None:
        """Changing bottom affects all packages in diamond."""
        mock_git.side_effect = [
            "packages/bottom/src.py",  # bottom: changed
            "",  # left: no direct changes
            "",  # right: no direct changes
            "",  # top: no direct changes
        ]

        changed = detect_changes(
            diamond_packages, last_tags=diamond_tags, force_all=False
        )

        assert set(changed) == {"bottom", "left", "right", "top"}

    @patch("lazy_wheels.pipeline.git")
    @patch("lazy_wheels.pipeline.step")
    def test_left_change_propagates_to_top_only(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        diamond_packages: dict[str, PackageInfo],
        diamond_tags: dict[str, str],
    ) -> None:
        """Changing left affects only left and top."""
        mock_git.side_effect = [
            "",  # bottom: no changes
            "packages/left/src.py",  # left: changed
            "",  # right: no changes
            "",  # top: no direct changes
        ]

        changed = detect_changes(
            diamond_packages, last_tags=diamond_tags, force_all=False
        )

        assert set(changed) == {"left", "top"}

    @patch("lazy_wheels.pipeline.git")
    @patch("lazy_wheels.pipeline.step")
    def test_top_change_only_affects_top(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        diamond_packages: dict[str, PackageInfo],
        diamond_tags: dict[str, str],
    ) -> None:
        """Changing top affects only top (no dependents)."""
        mock_git.side_effect = [
            "",  # bottom: no changes
            "",  # left: no changes
            "",  # right: no changes
            "packages/top/src.py",  # top: changed
        ]

        changed = detect_changes(
            diamond_packages, last_tags=diamond_tags, force_all=False
        )

        assert set(changed) == {"top"}


class TestFetchUnchangedWheels:
    """Tests for fetch_unchanged_wheels()."""

    @patch("lazy_wheels.pipeline.run")
    @patch("lazy_wheels.pipeline.gh")
    @patch("lazy_wheels.pipeline.step")
    @patch("lazy_wheels.pipeline.Path")
    def test_copies_matching_wheels(
        self,
        mock_path_cls: MagicMock,
        mock_step: MagicMock,
        mock_gh: MagicMock,
        mock_run: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Wheels that exist in releases are copied to dist/."""
        # Setup tmp directories
        tmp_wheels = tmp_path / "prev-wheels"
        tmp_wheels.mkdir()
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()

        # Create a wheel file in tmp
        wheel_file = tmp_wheels / "pkg_a-1.0.0-py3-none-any.whl"
        wheel_file.write_text("fake wheel content")

        # Mock gh to return a release
        mock_gh.return_value = '[{"tagName": "v2024.01.01-abc123"}]'

        # Mock Path to return our tmp directories
        mock_path_cls.side_effect = lambda p: (
            tmp_wheels
            if p == "/tmp/prev-wheels"
            else dist_dir
            if p == "dist"
            else Path(p)
        )

        unchanged = {"pkg-a": PackageInfo(path="packages/a", version="1.0.1", deps=[])}
        last_tags = {"pkg-a": "pkg-a/v1.0.0"}  # Released version
        fetch_unchanged_wheels(unchanged, last_tags)

        # Verify gh release download was called
        mock_run.assert_called()
        assert "download" in mock_run.call_args[0]

    @patch("lazy_wheels.pipeline.run")
    @patch("lazy_wheels.pipeline.gh")
    @patch("lazy_wheels.pipeline.step")
    def test_missing_wheel_not_copied(
        self,
        mock_step: MagicMock,
        mock_gh: MagicMock,
        mock_run: MagicMock,
        tmp_path: Path,
    ) -> None:
        """If a wheel doesn't exist in releases, it's reported as missing."""
        # Create real dist directory
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()

        # Patch Path to use real tmp_path for /tmp/prev-wheels
        tmp_wheels = tmp_path / "prev-wheels"
        tmp_wheels.mkdir()
        # Note: we do NOT create pkg_a wheel - it's missing

        # Mock gh to return a release
        mock_gh.return_value = '[{"tagName": "v2024.01.01-abc123"}]'

        with patch("lazy_wheels.pipeline.Path") as mock_path_cls:
            mock_path_cls.side_effect = lambda p: (
                tmp_wheels
                if p == "/tmp/prev-wheels"
                else dist_dir
                if p == "dist"
                else Path(p)
            )

            unchanged = {
                "pkg-a": PackageInfo(path="packages/a", version="1.0.1", deps=[])
            }
            last_tags = {"pkg-a": "pkg-a/v1.0.0"}
            fetch_unchanged_wheels(unchanged, last_tags)

        # dist should be empty - no wheel was copied
        assert list(dist_dir.glob("*.whl")) == []

    @patch("lazy_wheels.pipeline.gh")
    @patch("lazy_wheels.pipeline.step")
    def test_skips_when_no_unchanged(
        self,
        mock_step: MagicMock,
        mock_gh: MagicMock,
    ) -> None:
        """When unchanged dict is empty, does nothing."""
        fetch_unchanged_wheels({}, {})

        mock_gh.assert_not_called()
        mock_step.assert_not_called()


class TestRunRelease:
    """Integration test for the full release pipeline."""

    @patch("lazy_wheels.pipeline.git")
    @patch("lazy_wheels.pipeline.publish_release")
    @patch("lazy_wheels.pipeline.commit_bumps")
    @patch("lazy_wheels.pipeline.bump_versions")
    @patch("lazy_wheels.pipeline.tag_changed_packages")
    @patch("lazy_wheels.pipeline.build_packages")
    @patch("lazy_wheels.pipeline.fetch_unchanged_wheels")
    @patch("lazy_wheels.pipeline.check_for_existing_wheels")
    @patch("lazy_wheels.pipeline.detect_changes")
    @patch("lazy_wheels.pipeline.find_last_tags")
    @patch("lazy_wheels.pipeline.find_next_release_tag")
    @patch("lazy_wheels.pipeline.discover_packages")
    @patch("lazy_wheels.pipeline.Path")
    def test_golden_path_partial_rebuild(
        self,
        mock_path: MagicMock,
        mock_discover: MagicMock,
        mock_find_next_tag: MagicMock,
        mock_find_tags: MagicMock,
        mock_detect: MagicMock,
        mock_check_existing: MagicMock,
        mock_fetch: MagicMock,
        mock_build: MagicMock,
        mock_create_pkg_tags: MagicMock,
        mock_bump: MagicMock,
        mock_commit: MagicMock,
        mock_publish: MagicMock,
        mock_git: MagicMock,
    ) -> None:
        """Test golden path: pkg-a unchanged, pkg-b and pkg-c rebuilt."""
        # Setup: 3 packages where pkg-b changed, pkg-c depends on pkg-b
        packages = {
            "pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[]),
            "pkg-b": PackageInfo(path="packages/b", version="1.0.0", deps=["pkg-a"]),
            "pkg-c": PackageInfo(path="packages/c", version="1.0.0", deps=["pkg-b"]),
        }
        last_tags = {
            "pkg-a": "pkg-a/v1.0.0",
            "pkg-b": "pkg-b/v1.0.0",
            "pkg-c": "pkg-c/v1.0.0",
        }

        # Mock return values
        mock_path.return_value.mkdir = MagicMock()
        mock_discover.return_value = packages
        mock_find_tags.return_value = last_tags
        mock_find_next_tag.return_value = "r1"
        # pkg-b changed directly, pkg-c is dirty because it depends on pkg-b
        mock_detect.return_value = ["pkg-b", "pkg-c"]
        mock_bump.return_value = {
            "pkg-b": MagicMock(old="1.0.0", new="1.0.1"),
            "pkg-c": MagicMock(old="1.0.0", new="1.0.1"),
        }

        # Execute
        run_release()

        # Verify discover was called
        mock_discover.assert_called_once()

        # Verify detect_changes received correct args
        mock_detect.assert_called_once_with(packages, last_tags, False)

        # Verify check_for_existing_wheels was called with changed dict
        mock_check_existing.assert_called_once()

        # Verify fetch_unchanged_wheels called with unchanged dict
        mock_fetch.assert_called_once()

        # Verify build_packages called with changed dict
        mock_build.assert_called_once()

        # Verify tag_changed_packages was called with changed dict
        mock_create_pkg_tags.assert_called_once()

        # Verify bump_versions called with changed and unchanged dicts
        mock_bump.assert_called_once()

        # Verify commit and publish were called
        mock_commit.assert_called_once()
        mock_publish.assert_called_once()

    @patch("lazy_wheels.pipeline.fatal")
    @patch("lazy_wheels.pipeline.bump_versions")
    @patch("lazy_wheels.pipeline.build_packages")
    @patch("lazy_wheels.pipeline.fetch_unchanged_wheels")
    @patch("lazy_wheels.pipeline.detect_changes")
    @patch("lazy_wheels.pipeline.find_last_tags")
    @patch("lazy_wheels.pipeline.discover_packages")
    @patch("lazy_wheels.pipeline.Path")
    def test_no_changes_exits_early(
        self,
        mock_path: MagicMock,
        mock_discover: MagicMock,
        mock_find_tags: MagicMock,
        mock_detect: MagicMock,
        mock_fetch: MagicMock,
        mock_build: MagicMock,
        mock_bump: MagicMock,
        mock_fatal: MagicMock,
    ) -> None:
        """When nothing changed, pipeline calls fatal."""
        packages = {"pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[])}
        last_tags = {"pkg-a": "pkg-a/v1.0.0"}

        mock_path.return_value.mkdir = MagicMock()
        mock_discover.return_value = packages
        mock_find_tags.return_value = last_tags
        mock_detect.return_value = []  # Nothing changed
        # Make fatal actually stop execution
        mock_fatal.side_effect = SystemExit(1)

        # Execute - should raise SystemExit
        with pytest.raises(SystemExit):
            run_release()

        # Verify fatal was called for no changes
        mock_fatal.assert_called_once()
        assert "Nothing changed" in mock_fatal.call_args[0][0]

        # Verify build/bump were NOT called
        mock_build.assert_not_called()
        mock_bump.assert_not_called()


class TestGetExistingWheels:
    """Tests for get_existing_wheels()."""

    @patch("lazy_wheels.pipeline.gh")
    def test_no_releases_returns_empty_set(
        self,
        mock_gh: MagicMock,
    ) -> None:
        """When gh release list fails, returns empty set."""
        mock_gh.return_value = ""

        result = get_existing_wheels()

        assert result == set()

    @patch("lazy_wheels.pipeline.gh")
    def test_parses_wheel_assets(
        self,
        mock_gh: MagicMock,
    ) -> None:
        """Successfully parses wheel assets from releases."""
        # First call: gh release list, Second call: gh release view
        mock_gh.side_effect = [
            '[{"tagName": "v2024.01.01-abc123"}]',
            '{"assets": [{"name": "pkg_a-1.0.0-py3-none-any.whl"}, {"name": "notes.txt"}]}',
        ]

        result = get_existing_wheels()

        assert result == {"pkg_a-1.0.0-py3-none-any.whl"}

    @patch("lazy_wheels.pipeline.gh")
    def test_aggregates_wheels_from_multiple_releases(
        self,
        mock_gh: MagicMock,
    ) -> None:
        """Collects wheels from all releases."""
        mock_gh.side_effect = [
            '[{"tagName": "v1"}, {"tagName": "v2"}]',
            '{"assets": [{"name": "pkg_a-1.0.0-py3-none-any.whl"}]}',
            '{"assets": [{"name": "pkg_b-2.0.0-py3-none-any.whl"}]}',
        ]

        result = get_existing_wheels()

        assert result == {
            "pkg_a-1.0.0-py3-none-any.whl",
            "pkg_b-2.0.0-py3-none-any.whl",
        }


class TestCreatePackageTags:
    """Tests for create_package_tags()."""

    @pytest.fixture
    def sample_packages(self) -> dict[str, PackageInfo]:
        """Create sample packages for testing."""
        return {
            "pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[]),
            "pkg-b": PackageInfo(path="packages/b", version="2.0.0", deps=[]),
        }

    @patch("lazy_wheels.pipeline.git")
    @patch("lazy_wheels.pipeline.step")
    def test_creates_tags_for_changed_packages(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        sample_packages: dict[str, PackageInfo],
    ) -> None:
        """Creates a tag for each changed package."""
        tag_changed_packages(sample_packages)

        # Verify tags were created (2 tag calls, no push - push happens later)
        assert mock_git.call_count == 2
        mock_git.assert_any_call("tag", "pkg-a/v1.0.0")
        mock_git.assert_any_call("tag", "pkg-b/v2.0.0")

    @patch("lazy_wheels.pipeline.git")
    @patch("lazy_wheels.pipeline.step")
    def test_no_tags_when_no_changes(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
    ) -> None:
        """No tags created when no packages changed."""
        tag_changed_packages({})

        # Only step was called, no git operations
        mock_git.assert_not_called()


class TestCheckForDuplicateVersions:
    """Tests for check_for_duplicate_versions()."""

    @pytest.fixture
    def sample_packages(self) -> dict[str, PackageInfo]:
        """Create sample packages for testing."""
        return {
            "pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[]),
            "pkg-b": PackageInfo(path="packages/b", version="2.0.0", deps=[]),
        }

    @patch("lazy_wheels.pipeline.get_existing_wheels")
    @patch("lazy_wheels.pipeline.step")
    def test_no_existing_releases(
        self,
        mock_step: MagicMock,
        mock_get_wheels: MagicMock,
        sample_packages: dict[str, PackageInfo],
    ) -> None:
        """When no releases exist, check passes."""
        mock_get_wheels.return_value = set()

        # Should not raise
        check_for_existing_wheels(sample_packages)

    @patch("lazy_wheels.pipeline.fatal")
    @patch("lazy_wheels.pipeline.get_existing_wheels")
    @patch("lazy_wheels.pipeline.step")
    def test_duplicate_version_found(
        self,
        mock_step: MagicMock,
        mock_get_wheels: MagicMock,
        mock_fatal: MagicMock,
    ) -> None:
        """When a duplicate version exists, fatal is called."""
        mock_get_wheels.return_value = {
            "pkg_a-1.0.0-py3-none-any.whl",
            "other_pkg-3.0.0-py3-none-any.whl",
        }

        changed = {"pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[])}
        check_for_existing_wheels(changed)

        mock_fatal.assert_called_once()
        assert "pkg-a 1.0.0" in mock_fatal.call_args[0][0]

    @patch("lazy_wheels.pipeline.fatal")
    @patch("lazy_wheels.pipeline.get_existing_wheels")
    @patch("lazy_wheels.pipeline.step")
    def test_no_duplicate_different_versions(
        self,
        mock_step: MagicMock,
        mock_get_wheels: MagicMock,
        mock_fatal: MagicMock,
    ) -> None:
        """When versions differ, check passes."""
        mock_get_wheels.return_value = {
            "pkg_a-0.9.0-py3-none-any.whl",  # Different version
        }

        changed = {"pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[])}
        check_for_existing_wheels(changed)

        mock_fatal.assert_not_called()

    @patch("lazy_wheels.pipeline.fatal")
    @patch("lazy_wheels.pipeline.get_existing_wheels")
    @patch("lazy_wheels.pipeline.step")
    def test_multiple_duplicates_found(
        self,
        mock_step: MagicMock,
        mock_get_wheels: MagicMock,
        mock_fatal: MagicMock,
        sample_packages: dict[str, PackageInfo],
    ) -> None:
        """When multiple duplicates exist, all are reported."""
        mock_get_wheels.return_value = {
            "pkg_a-1.0.0-py3-none-any.whl",
            "pkg_b-2.0.0-py3-none-any.whl",
        }

        check_for_existing_wheels(sample_packages)

        mock_fatal.assert_called_once()
        error_msg = mock_fatal.call_args[0][0]
        assert "pkg-a 1.0.0" in error_msg
        assert "pkg-b 2.0.0" in error_msg

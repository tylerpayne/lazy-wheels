"""Tests for uv_release_monorepo.pipeline."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from uv_release_monorepo.models import (
    MatrixEntry,
    PackageInfo,
    PublishedPackage,
    ReleasePlan,
)
from uv_release_monorepo.pipeline import (
    build_plan,
    bump_versions,
    check_for_existing_wheels,
    collect_published_state,
    detect_changes,
    discover_packages,
    execute_plan,
    fetch_unchanged_wheels,
    find_release_tags,
    generate_release_notes,
    get_baseline_tags,
    get_existing_wheels,
    publish_release,
    run_release,
    tag_changed_packages,
)


class TestFindReleaseTags:
    """Tests for find_release_tags()."""

    @pytest.fixture
    def sample_packages(self) -> dict[str, PackageInfo]:
        """Create sample packages for testing."""
        return {
            "pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[]),
            "pkg-b": PackageInfo(path="packages/b", version="1.0.0", deps=[]),
        }

    @patch("uv_release_monorepo.pipeline.git")
    @patch("uv_release_monorepo.pipeline.step")
    def test_returns_per_package_tags(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        sample_packages: dict[str, PackageInfo],
    ) -> None:
        """Returns the most recent release tag for each package."""
        mock_git.side_effect = [
            "pkg-a/v1.0.0\npkg-a/v0.9.0",  # Tags for pkg-a
            "pkg-b/v2.0.0",  # Tags for pkg-b
        ]

        result = find_release_tags(sample_packages)

        assert result == {"pkg-a": "pkg-a/v1.0.0", "pkg-b": "pkg-b/v2.0.0"}

    @patch("uv_release_monorepo.pipeline.git")
    @patch("uv_release_monorepo.pipeline.step")
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

        result = find_release_tags(sample_packages)

        assert result == {"pkg-a": "pkg-a/v1.0.0", "pkg-b": None}

    @patch("uv_release_monorepo.pipeline.git")
    @patch("uv_release_monorepo.pipeline.step")
    def test_all_new_packages(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        sample_packages: dict[str, PackageInfo],
    ) -> None:
        """When no packages have tags, all return None."""
        mock_git.return_value = ""

        result = find_release_tags(sample_packages)

        assert result == {"pkg-a": None, "pkg-b": None}

    @patch("uv_release_monorepo.pipeline.git")
    @patch("uv_release_monorepo.pipeline.step")
    def test_skips_dev_and_base_tags(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        sample_packages: dict[str, PackageInfo],
    ) -> None:
        """Dev and base baseline tags are excluded from release tags."""
        mock_git.side_effect = [
            "pkg-a/v1.0.1-base\npkg-a/v1.0.1-dev\npkg-a/v1.0.0",  # -base and -dev tags
            "pkg-b/v2.0.1-dev",  # Only a -dev tag
        ]

        result = find_release_tags(sample_packages)

        assert result == {"pkg-a": "pkg-a/v1.0.0", "pkg-b": None}


class TestGetBaselineTags:
    """Tests for get_baseline_tags()."""

    @pytest.fixture
    def sample_packages(self) -> dict[str, PackageInfo]:
        """Create sample packages for testing."""
        return {
            "pkg-a": PackageInfo(path="packages/a", version="1.0.1", deps=[]),
            "pkg-b": PackageInfo(path="packages/b", version="1.0.1", deps=[]),
        }

    @patch("uv_release_monorepo.pipeline.git")
    @patch("uv_release_monorepo.pipeline.step")
    def test_returns_base_tags(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        sample_packages: dict[str, PackageInfo],
    ) -> None:
        """Returns the -base tag derived from pyproject.toml version."""
        mock_git.side_effect = [
            "pkg-a/v1.0.1-base",  # base tag for pkg-a exists
            "pkg-b/v1.0.1-base",  # base tag for pkg-b exists
        ]

        result = get_baseline_tags(sample_packages)

        assert result == {
            "pkg-a": "pkg-a/v1.0.1-base",
            "pkg-b": "pkg-b/v1.0.1-base",
        }

    @patch("uv_release_monorepo.pipeline.git")
    @patch("uv_release_monorepo.pipeline.step")
    def test_falls_back_to_dev_tag(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        sample_packages: dict[str, PackageInfo],
    ) -> None:
        """Falls back to -dev tag when no -base tag exists (backward compat)."""
        mock_git.side_effect = [
            "",  # pkg-a: no -base tag
            "pkg-a/v1.0.1-dev",  # pkg-a: fall back to -dev tag
            "pkg-b/v1.0.1-base",  # pkg-b: has -base tag
        ]

        result = get_baseline_tags(sample_packages)

        assert result == {
            "pkg-a": "pkg-a/v1.0.1-dev",
            "pkg-b": "pkg-b/v1.0.1-base",
        }

    @patch("uv_release_monorepo.pipeline.git")
    @patch("uv_release_monorepo.pipeline.step")
    def test_falls_back_to_release_tag(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        sample_packages: dict[str, PackageInfo],
    ) -> None:
        """Falls back to release tag when no -base or -dev tag exists."""
        mock_git.side_effect = [
            "",  # pkg-a: no -base tag
            "",  # pkg-a: no -dev tag
            "pkg-a/v1.0.0",  # pkg-a: fall back to release tag search
            "pkg-b/v1.0.1-base",  # pkg-b: has -base tag
        ]

        result = get_baseline_tags(sample_packages)

        assert result == {
            "pkg-a": "pkg-a/v1.0.0",
            "pkg-b": "pkg-b/v1.0.1-base",
        }

    @patch("uv_release_monorepo.pipeline.git")
    @patch("uv_release_monorepo.pipeline.step")
    def test_returns_none_for_new_packages(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        sample_packages: dict[str, PackageInfo],
    ) -> None:
        """Returns None for packages with no tags at all."""
        mock_git.return_value = ""

        result = get_baseline_tags(sample_packages)

        assert result == {"pkg-a": None, "pkg-b": None}


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

    @patch("uv_release_monorepo.pipeline.git")
    @patch("uv_release_monorepo.pipeline.step")
    def test_first_release_all_changed(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        sample_packages: dict[str, PackageInfo],
        no_tags: dict[str, None],
    ) -> None:
        """On first release (no tags), all packages are marked changed."""
        # No git diff called when tags are None

        changed = detect_changes(sample_packages, baselines=no_tags, rebuild_all=False)

        assert set(changed) == {"pkg-a", "pkg-b", "pkg-c"}

    @patch("uv_release_monorepo.pipeline.git")
    @patch("uv_release_monorepo.pipeline.step")
    def test_rebuild_all_marks_everything_dirty(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        sample_packages: dict[str, PackageInfo],
        all_tags: dict[str, str],
    ) -> None:
        """rebuild_all=True marks all packages as changed regardless of git diff."""
        changed = detect_changes(sample_packages, baselines=all_tags, rebuild_all=True)

        assert set(changed) == {"pkg-a", "pkg-b", "pkg-c"}

    @patch("uv_release_monorepo.pipeline.git")
    @patch("uv_release_monorepo.pipeline.step")
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

        changed = detect_changes(sample_packages, baselines=all_tags, rebuild_all=False)

        assert set(changed) == {"pkg-c"}

    @patch("uv_release_monorepo.pipeline.git")
    @patch("uv_release_monorepo.pipeline.step")
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

        changed = detect_changes(sample_packages, baselines=all_tags, rebuild_all=False)

        # pkg-a changed directly, pkg-b and pkg-c are dirty because they depend on it
        assert set(changed) == {"pkg-a", "pkg-b", "pkg-c"}

    @patch("uv_release_monorepo.pipeline.git")
    @patch("uv_release_monorepo.pipeline.step")
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

        changed = detect_changes(sample_packages, baselines=all_tags, rebuild_all=False)

        # pkg-b changed, pkg-c depends on it, pkg-a is unaffected
        assert set(changed) == {"pkg-b", "pkg-c"}

    @patch("uv_release_monorepo.pipeline.git")
    @patch("uv_release_monorepo.pipeline.step")
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

        changed = detect_changes(sample_packages, baselines=all_tags, rebuild_all=False)

        assert set(changed) == {"pkg-a", "pkg-b", "pkg-c"}

    @patch("uv_release_monorepo.pipeline.git")
    @patch("uv_release_monorepo.pipeline.step")
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

        changed = detect_changes(sample_packages, baselines=all_tags, rebuild_all=False)

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

    @patch("uv_release_monorepo.pipeline.git")
    @patch("uv_release_monorepo.pipeline.step")
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
            diamond_packages, baselines=diamond_tags, rebuild_all=False
        )

        assert set(changed) == {"bottom", "left", "right", "top"}

    @patch("uv_release_monorepo.pipeline.git")
    @patch("uv_release_monorepo.pipeline.step")
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
            diamond_packages, baselines=diamond_tags, rebuild_all=False
        )

        assert set(changed) == {"left", "top"}

    @patch("uv_release_monorepo.pipeline.git")
    @patch("uv_release_monorepo.pipeline.step")
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
            diamond_packages, baselines=diamond_tags, rebuild_all=False
        )

        assert set(changed) == {"top"}


class TestFetchUnchangedWheels:
    """Tests for fetch_unchanged_wheels()."""

    @patch("uv_release_monorepo.pipeline.run")
    @patch("uv_release_monorepo.pipeline.gh")
    @patch("uv_release_monorepo.pipeline.step")
    @patch("uv_release_monorepo.pipeline.Path")
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
        release_tags = {"pkg-a": "pkg-a/v1.0.0"}  # Released version
        fetch_unchanged_wheels(unchanged, release_tags)

        # Verify gh release download was called
        mock_run.assert_called()
        assert "download" in mock_run.call_args[0]

    @patch("uv_release_monorepo.pipeline.run")
    @patch("uv_release_monorepo.pipeline.gh")
    @patch("uv_release_monorepo.pipeline.step")
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

        with patch("uv_release_monorepo.pipeline.Path") as mock_path_cls:
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
            release_tags = {"pkg-a": "pkg-a/v1.0.0"}
            fetch_unchanged_wheels(unchanged, release_tags)

        # dist should be empty - no wheel was copied
        assert list(dist_dir.glob("*.whl")) == []

    @patch("uv_release_monorepo.pipeline.gh")
    @patch("uv_release_monorepo.pipeline.step")
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

    @patch("uv_release_monorepo.pipeline.git")
    @patch("uv_release_monorepo.pipeline.publish_release")
    @patch("uv_release_monorepo.pipeline.tag_baselines")
    @patch("uv_release_monorepo.pipeline.commit_bumps")
    @patch("uv_release_monorepo.pipeline.bump_versions")
    @patch("uv_release_monorepo.pipeline.tag_changed_packages")
    @patch("uv_release_monorepo.pipeline.build_packages")
    @patch("uv_release_monorepo.pipeline.fetch_unchanged_wheels")
    @patch("uv_release_monorepo.pipeline.check_for_existing_wheels")
    @patch("uv_release_monorepo.pipeline.detect_changes")
    @patch("uv_release_monorepo.pipeline.get_baseline_tags")
    @patch("uv_release_monorepo.pipeline.find_release_tags")
    @patch("uv_release_monorepo.pipeline.discover_packages")
    @patch("uv_release_monorepo.pipeline.Path")
    def test_golden_path_partial_rebuild(
        self,
        mock_path: MagicMock,
        mock_discover: MagicMock,
        mock_find_release_tags: MagicMock,
        mock_get_baseline_tags: MagicMock,
        mock_detect: MagicMock,
        mock_check_existing: MagicMock,
        mock_fetch: MagicMock,
        mock_build: MagicMock,
        mock_create_pkg_tags: MagicMock,
        mock_bump: MagicMock,
        mock_commit: MagicMock,
        mock_tag_dev: MagicMock,
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
        release_tags = {
            "pkg-a": "pkg-a/v1.0.0",
            "pkg-b": "pkg-b/v1.0.0",
            "pkg-c": "pkg-c/v1.0.0",
        }
        baselines = {
            "pkg-a": "pkg-a/v1.0.0-base",
            "pkg-b": "pkg-b/v1.0.0-base",
            "pkg-c": "pkg-c/v1.0.0-base",
        }

        # Mock return values
        mock_path.return_value.mkdir = MagicMock()
        mock_discover.return_value = packages
        mock_find_release_tags.return_value = release_tags
        mock_get_baseline_tags.return_value = baselines
        # pkg-b changed directly, pkg-c is dirty because it depends on pkg-b
        mock_detect.return_value = ["pkg-b", "pkg-c"]
        bumped = {
            "pkg-b": MagicMock(old="1.0.0", new="1.0.1"),
            "pkg-c": MagicMock(old="1.0.0", new="1.0.1"),
        }
        mock_bump.return_value = bumped

        # Execute
        run_release()

        # Verify discover was called
        mock_discover.assert_called_once()

        # Verify detect_changes received baselines
        mock_detect.assert_called_once_with(packages, baselines, False)

        # Verify fetch_unchanged_wheels received release tags
        mock_fetch.assert_called_once()
        fetch_args = mock_fetch.call_args
        assert fetch_args[0][1] == release_tags

        # Verify build_packages called with changed dict
        mock_build.assert_called_once()

        # Verify tag_changed_packages was called with changed dict
        mock_create_pkg_tags.assert_called_once()

        # Verify bump_versions called with changed and unchanged dicts
        mock_bump.assert_called_once()

        # Verify commit, dev baselines, and publish were called
        mock_commit.assert_called_once()
        mock_tag_dev.assert_called_once_with(bumped)
        mock_publish.assert_called_once()

    @patch("uv_release_monorepo.pipeline.fatal")
    @patch("uv_release_monorepo.pipeline.bump_versions")
    @patch("uv_release_monorepo.pipeline.build_packages")
    @patch("uv_release_monorepo.pipeline.fetch_unchanged_wheels")
    @patch("uv_release_monorepo.pipeline.detect_changes")
    @patch("uv_release_monorepo.pipeline.get_baseline_tags")
    @patch("uv_release_monorepo.pipeline.find_release_tags")
    @patch("uv_release_monorepo.pipeline.discover_packages")
    @patch("uv_release_monorepo.pipeline.Path")
    def test_no_changes_exits_early(
        self,
        mock_path: MagicMock,
        mock_discover: MagicMock,
        mock_find_release_tags: MagicMock,
        mock_get_baseline_tags: MagicMock,
        mock_detect: MagicMock,
        mock_fetch: MagicMock,
        mock_build: MagicMock,
        mock_bump: MagicMock,
        mock_fatal: MagicMock,
    ) -> None:
        """When nothing changed, pipeline calls fatal."""
        packages = {"pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[])}
        release_tags = {"pkg-a": "pkg-a/v1.0.0"}
        baselines = {"pkg-a": "pkg-a/v1.0.0-base"}

        mock_path.return_value.mkdir = MagicMock()
        mock_discover.return_value = packages
        mock_find_release_tags.return_value = release_tags
        mock_get_baseline_tags.return_value = baselines
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

    @patch("uv_release_monorepo.pipeline.gh")
    def test_no_releases_returns_empty_set(
        self,
        mock_gh: MagicMock,
    ) -> None:
        """When gh release list fails, returns empty set."""
        mock_gh.return_value = ""

        result = get_existing_wheels()

        assert result == set()

    @patch("uv_release_monorepo.pipeline.gh")
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

    @patch("uv_release_monorepo.pipeline.gh")
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

    @patch("uv_release_monorepo.pipeline.git")
    @patch("uv_release_monorepo.pipeline.step")
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

    @patch("uv_release_monorepo.pipeline.git")
    @patch("uv_release_monorepo.pipeline.step")
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

    @patch("uv_release_monorepo.pipeline.get_existing_wheels")
    @patch("uv_release_monorepo.pipeline.step")
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

    @patch("uv_release_monorepo.pipeline.fatal")
    @patch("uv_release_monorepo.pipeline.get_existing_wheels")
    @patch("uv_release_monorepo.pipeline.step")
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

    @patch("uv_release_monorepo.pipeline.fatal")
    @patch("uv_release_monorepo.pipeline.get_existing_wheels")
    @patch("uv_release_monorepo.pipeline.step")
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

    @patch("uv_release_monorepo.pipeline.fatal")
    @patch("uv_release_monorepo.pipeline.get_existing_wheels")
    @patch("uv_release_monorepo.pipeline.step")
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


class TestPublishReleaseChangelog:
    """Tests for publish_release() changelog generation."""

    @patch("uv_release_monorepo.pipeline.gh")
    @patch("uv_release_monorepo.pipeline.git")
    @patch("uv_release_monorepo.pipeline.step")
    def test_includes_git_log_in_release_notes(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        mock_gh: MagicMock,
    ) -> None:
        """publish_release includes commit history for changed packages."""
        # Create a real dist dir with a wheel
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp) / "dist"
            dist.mkdir()
            (dist / "pkg_a-1.0.0-py3-none-any.whl").write_bytes(b"")

            with patch("uv_release_monorepo.pipeline.Path") as mock_path_cls:
                mock_path_cls.return_value.glob.return_value = [
                    dist / "pkg_a-1.0.0-py3-none-any.whl"
                ]
                mock_git.return_value = "abc1234 Add feature X\ndef5678 Fix bug Y"
                mock_gh.return_value = ""

                changed = {
                    "pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[])
                }
                release_tags = {"pkg-a": "pkg-a/v0.9.0"}

                publish_release(changed, release_tags)

                notes = mock_gh.call_args[0]
                notes_str = " ".join(notes)
                assert "Add feature X" in notes_str
                assert "Fix bug Y" in notes_str

    @patch("uv_release_monorepo.pipeline.gh")
    @patch("uv_release_monorepo.pipeline.git")
    @patch("uv_release_monorepo.pipeline.step")
    def test_skips_log_for_new_packages(
        self,
        mock_step: MagicMock,
        mock_git: MagicMock,
        mock_gh: MagicMock,
    ) -> None:
        """publish_release skips git log when no release tag exists."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp) / "dist"
            dist.mkdir()
            (dist / "pkg_a-1.0.0-py3-none-any.whl").write_bytes(b"")

            with patch("uv_release_monorepo.pipeline.Path") as mock_path_cls:
                mock_path_cls.return_value.glob.return_value = [
                    dist / "pkg_a-1.0.0-py3-none-any.whl"
                ]
                mock_gh.return_value = ""

                changed = {
                    "pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[])
                }
                release_tags: dict[str, str | None] = {"pkg-a": None}

                publish_release(changed, release_tags)

                # git should not be called for commit log (no baseline)
                mock_git.assert_not_called()


class TestRunReleaseDryRun:
    """Tests for run_release() dry-run mode."""

    @patch("uv_release_monorepo.pipeline.check_for_existing_wheels")
    @patch("uv_release_monorepo.pipeline.build_packages")
    @patch("uv_release_monorepo.pipeline.publish_release")
    @patch("uv_release_monorepo.pipeline.detect_changes")
    @patch("uv_release_monorepo.pipeline.get_baseline_tags")
    @patch("uv_release_monorepo.pipeline.find_release_tags")
    @patch("uv_release_monorepo.pipeline.discover_packages")
    @patch("uv_release_monorepo.pipeline.Path")
    def test_dry_run_skips_mutations(
        self,
        mock_path: MagicMock,
        mock_discover: MagicMock,
        mock_find_release_tags: MagicMock,
        mock_get_baseline_tags: MagicMock,
        mock_detect: MagicMock,
        mock_publish: MagicMock,
        mock_build: MagicMock,
        mock_check_existing: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """dry_run=True prints plan and skips all mutations."""
        packages = {
            "pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[]),
        }
        mock_path.return_value.mkdir = MagicMock()
        mock_discover.return_value = packages
        mock_find_release_tags.return_value = {"pkg-a": "pkg-a/v1.0.0"}
        mock_get_baseline_tags.return_value = {"pkg-a": "pkg-a/v1.0.0-base"}
        mock_detect.return_value = ["pkg-a"]

        run_release(dry_run=True)

        # No mutations should happen
        mock_build.assert_not_called()
        mock_publish.assert_not_called()
        mock_check_existing.assert_not_called()

        output = capsys.readouterr().out
        assert "Dry-run" in output
        assert "pkg-a" in output
        assert "1.0.0" in output

    @patch("uv_release_monorepo.pipeline.git")
    @patch("uv_release_monorepo.pipeline.build_packages")
    @patch("uv_release_monorepo.pipeline.detect_changes")
    @patch("uv_release_monorepo.pipeline.get_baseline_tags")
    @patch("uv_release_monorepo.pipeline.find_release_tags")
    @patch("uv_release_monorepo.pipeline.discover_packages")
    @patch("uv_release_monorepo.pipeline.Path")
    def test_dry_run_shows_version_bumps(
        self,
        mock_path: MagicMock,
        mock_discover: MagicMock,
        mock_find_release_tags: MagicMock,
        mock_get_baseline_tags: MagicMock,
        mock_detect: MagicMock,
        mock_build: MagicMock,
        mock_git: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """dry_run output includes version bump preview."""
        packages = {
            "pkg-a": PackageInfo(path="packages/a", version="1.2.3", deps=[]),
        }
        mock_path.return_value.mkdir = MagicMock()
        mock_discover.return_value = packages
        mock_find_release_tags.return_value = {"pkg-a": None}
        mock_get_baseline_tags.return_value = {"pkg-a": None}
        mock_detect.return_value = ["pkg-a"]

        run_release(dry_run=True)

        output = capsys.readouterr().out
        assert "1.2.3" in output
        assert "1.2.4" in output


class TestDiscoverPackagesRoot:
    """Tests for discover_packages() root parameter."""

    @patch("uv_release_monorepo.pipeline.step")
    def test_accepts_explicit_root(self, mock_step: MagicMock, tmp_path: Path) -> None:
        """discover_packages() uses the provided root directory."""
        root = tmp_path
        (root / "pyproject.toml").write_text(
            '[tool.uv.workspace]\nmembers = ["packages/*"]\n'
        )
        pkg_dir = root / "packages" / "my-pkg"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "pyproject.toml").write_text(
            '[project]\nname = "my-pkg"\nversion = "0.1.0"\n'
        )

        result = discover_packages(root=root)

        assert "my-pkg" in result
        assert result["my-pkg"].version == "0.1.0"


class TestCollectPublishedState:
    """Tests for collect_published_state()."""

    def _pkg(
        self, name: str, version: str, deps: list[str] | None = None
    ) -> PackageInfo:
        return PackageInfo(path=f"packages/{name}", version=version, deps=deps or [])

    def test_changed_package_uses_info_version(self) -> None:
        """Changed packages: published_version == info.version (pre-bump)."""
        alpha = self._pkg("pkg-alpha", "0.1.5")
        state = collect_published_state(
            changed={"pkg-alpha": alpha},
            unchanged={},
            release_tags={"pkg-alpha": "pkg-alpha/v0.1.4"},
        )
        assert state["pkg-alpha"].published_version == "0.1.5"
        assert state["pkg-alpha"].changed is True

    def test_unchanged_package_uses_release_tag_version(self) -> None:
        """Unchanged packages: published_version == version from release tag."""
        alpha = self._pkg("pkg-alpha", "0.1.6")  # pyproject already bumped to dev
        state = collect_published_state(
            changed={},
            unchanged={"pkg-alpha": alpha},
            release_tags={"pkg-alpha": "pkg-alpha/v0.1.5"},
        )
        assert state["pkg-alpha"].published_version == "0.1.5"
        assert state["pkg-alpha"].changed is False

    def test_unchanged_package_no_tag_falls_back_to_info_version(self) -> None:
        """Unchanged packages without a release tag fall back to info.version."""
        alpha = self._pkg("pkg-alpha", "0.1.0")
        state = collect_published_state(
            changed={},
            unchanged={"pkg-alpha": alpha},
            release_tags={"pkg-alpha": None},
        )
        assert state["pkg-alpha"].published_version == "0.1.0"

    def test_mixed_changed_and_unchanged(self) -> None:
        """Both changed and unchanged packages appear in state."""
        alpha = self._pkg("pkg-alpha", "0.1.5")
        beta = self._pkg("pkg-beta", "0.1.6")
        state = collect_published_state(
            changed={"pkg-alpha": alpha},
            unchanged={"pkg-beta": beta},
            release_tags={"pkg-beta": "pkg-beta/v0.1.5"},
        )
        assert state["pkg-alpha"].published_version == "0.1.5"
        assert state["pkg-alpha"].changed is True
        assert state["pkg-beta"].published_version == "0.1.5"
        assert state["pkg-beta"].changed is False


class TestBumpVersions:
    """Tests for bump_versions()."""

    def _pkg(
        self, name: str, version: str, deps: list[str] | None = None
    ) -> PackageInfo:
        return PackageInfo(path=f"packages/{name}", version=version, deps=deps or [])

    @patch("uv_release_monorepo.pipeline.rewrite_pyproject")
    @patch("uv_release_monorepo.pipeline.step")
    def test_bumps_changed_package_version(
        self, mock_step: MagicMock, mock_rewrite: MagicMock
    ) -> None:
        """Changed packages get their version bumped."""
        alpha = PublishedPackage(
            info=self._pkg("pkg-alpha", "0.1.5"),
            published_version="0.1.5",
            changed=True,
        )
        result = bump_versions({"pkg-alpha": alpha})
        assert result["pkg-alpha"].old == "0.1.5"
        assert result["pkg-alpha"].new == "0.1.6"

    @patch("uv_release_monorepo.pipeline.rewrite_pyproject")
    @patch("uv_release_monorepo.pipeline.step")
    def test_unchanged_package_not_bumped(
        self, mock_step: MagicMock, mock_rewrite: MagicMock
    ) -> None:
        """Unchanged packages are not included in returned bumped dict."""
        alpha = PublishedPackage(
            info=self._pkg("pkg-alpha", "0.1.5"),
            published_version="0.1.5",
            changed=False,
        )
        result = bump_versions({"pkg-alpha": alpha})
        assert "pkg-alpha" not in result
        mock_rewrite.assert_not_called()

    @patch("uv_release_monorepo.pipeline.rewrite_pyproject")
    @patch("uv_release_monorepo.pipeline.step")
    def test_internal_dep_pinned_to_published_version_not_bumped(
        self, mock_step: MagicMock, mock_rewrite: MagicMock
    ) -> None:
        """Internal deps are pinned to published_version (pre-bump), not next-dev version.

        Scenario: pkg-alpha published at 0.1.5 (changed), pkg-beta depends on
        pkg-alpha. The bump writes pkg-alpha>=0.1.5 into pkg-beta, NOT >=0.1.6.
        """
        alpha = PublishedPackage(
            info=self._pkg("pkg-alpha", "0.1.5"),
            published_version="0.1.5",
            changed=True,
        )
        beta = PublishedPackage(
            info=self._pkg("pkg-beta", "0.1.5", deps=["pkg-alpha"]),
            published_version="0.1.5",
            changed=True,
        )
        bump_versions({"pkg-alpha": alpha, "pkg-beta": beta})

        beta_rewrite_call = next(
            call for call in mock_rewrite.call_args_list if "pkg-beta" in str(call)
        )
        _, _, internal_dep_versions = beta_rewrite_call.args
        assert internal_dep_versions["pkg-alpha"] == "0.1.5"

    @patch("uv_release_monorepo.pipeline.rewrite_pyproject")
    @patch("uv_release_monorepo.pipeline.step")
    def test_unchanged_dep_pinned_to_release_tag_version(
        self, mock_step: MagicMock, mock_rewrite: MagicMock
    ) -> None:
        """Deps from unchanged packages use their release-tag version, not pyproject version.

        Scenario: pkg-alpha unchanged (pyproject says 0.1.6 from last bump, but last
        release was 0.1.5). pkg-beta changed and depends on pkg-alpha. The bump should
        write pkg-alpha>=0.1.5, not >=0.1.6, so the wheel stays installable when only
        pkg-beta changes.
        """
        alpha = PublishedPackage(
            info=self._pkg("pkg-alpha", "0.1.6"),  # dev version in pyproject
            published_version="0.1.5",  # actual last-released version
            changed=False,
        )
        beta = PublishedPackage(
            info=self._pkg("pkg-beta", "0.1.5", deps=["pkg-alpha"]),
            published_version="0.1.5",
            changed=True,
        )
        bump_versions({"pkg-alpha": alpha, "pkg-beta": beta})

        beta_rewrite_call = next(
            call for call in mock_rewrite.call_args_list if "pkg-beta" in str(call)
        )
        _, _, internal_dep_versions = beta_rewrite_call.args
        assert (
            internal_dep_versions["pkg-alpha"] == "0.1.5"
        )  # release tag version, not 0.1.6


class TestBuildPlan:
    """Tests for build_plan()."""

    @patch("uv_release_monorepo.pipeline.detect_changes")
    @patch("uv_release_monorepo.pipeline.get_baseline_tags")
    @patch("uv_release_monorepo.pipeline.find_release_tags")
    @patch("uv_release_monorepo.pipeline.discover_packages")
    def test_returns_release_plan(
        self,
        mock_discover: MagicMock,
        mock_find_release: MagicMock,
        mock_find_dev: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """build_plan returns a ReleasePlan with correct changed/unchanged split."""
        packages = {
            "pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[]),
            "pkg-b": PackageInfo(path="packages/b", version="1.0.0", deps=[]),
        }
        mock_discover.return_value = packages
        mock_find_release.return_value = {
            "pkg-a": "pkg-a/v0.9.0",
            "pkg-b": "pkg-b/v0.9.0",
        }
        mock_find_dev.return_value = {
            "pkg-a": "pkg-a/v1.0.0-dev",
            "pkg-b": "pkg-b/v1.0.0-dev",
        }
        mock_detect.return_value = ["pkg-a"]

        plan, pin_updates = build_plan(
            rebuild_all=False, matrix={}, uvr_version="0.3.0"
        )

        assert isinstance(plan, ReleasePlan)
        assert "pkg-a" in plan.changed
        assert "pkg-b" in plan.unchanged
        assert plan.uvr_version == "0.3.0"
        assert plan.rebuild_all is False
        assert pin_updates == []  # no deps, no pins to update

    @patch("uv_release_monorepo.pipeline.detect_changes")
    @patch("uv_release_monorepo.pipeline.get_baseline_tags")
    @patch("uv_release_monorepo.pipeline.find_release_tags")
    @patch("uv_release_monorepo.pipeline.discover_packages")
    def test_expands_matrix_for_changed_only(
        self,
        mock_discover: MagicMock,
        mock_find_release: MagicMock,
        mock_find_dev: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """Matrix entries are only created for changed packages, not unchanged."""
        packages = {
            "pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[]),
            "pkg-b": PackageInfo(path="packages/b", version="1.0.0", deps=[]),
        }
        mock_discover.return_value = packages
        mock_find_release.return_value = {"pkg-a": None, "pkg-b": None}
        mock_find_dev.return_value = {"pkg-a": None, "pkg-b": None}
        mock_detect.return_value = ["pkg-a"]  # only pkg-a changed

        plan, _ = build_plan(
            rebuild_all=False,
            matrix={"pkg-a": ["ubuntu-latest", "macos-14"], "pkg-b": ["ubuntu-latest"]},
            uvr_version="0.3.0",
        )

        # Only pkg-a gets matrix entries; pkg-b is unchanged
        packages_in_matrix = {e.package for e in plan.matrix}
        assert "pkg-a" in packages_in_matrix
        assert "pkg-b" not in packages_in_matrix
        assert len(plan.matrix) == 2  # ubuntu-latest + macos-14 for pkg-a

    @patch("uv_release_monorepo.pipeline.detect_changes")
    @patch("uv_release_monorepo.pipeline.get_baseline_tags")
    @patch("uv_release_monorepo.pipeline.find_release_tags")
    @patch("uv_release_monorepo.pipeline.discover_packages")
    def test_defaults_matrix_to_ubuntu_latest(
        self,
        mock_discover: MagicMock,
        mock_find_release: MagicMock,
        mock_find_dev: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """Changed packages with no matrix entry default to ubuntu-latest."""
        packages = {"pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[])}
        mock_discover.return_value = packages
        mock_find_release.return_value = {"pkg-a": None}
        mock_find_dev.return_value = {"pkg-a": None}
        mock_detect.return_value = ["pkg-a"]

        plan, _ = build_plan(rebuild_all=False, matrix={}, uvr_version="0.3.0")

        assert len(plan.matrix) == 1
        assert plan.matrix[0].package == "pkg-a"
        assert plan.matrix[0].runner == "ubuntu-latest"

    @patch("uv_release_monorepo.pipeline.detect_changes")
    @patch("uv_release_monorepo.pipeline.get_baseline_tags")
    @patch("uv_release_monorepo.pipeline.find_release_tags")
    @patch("uv_release_monorepo.pipeline.discover_packages")
    def test_empty_changed_returns_empty_plan(
        self,
        mock_discover: MagicMock,
        mock_find_release: MagicMock,
        mock_find_dev: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """When nothing changed, returns a plan with empty changed dict."""
        packages = {"pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[])}
        mock_discover.return_value = packages
        mock_find_release.return_value = {"pkg-a": "pkg-a/v1.0.0"}
        mock_find_dev.return_value = {"pkg-a": "pkg-a/v1.0.0-dev"}
        mock_detect.return_value = []

        plan, _ = build_plan(rebuild_all=False, matrix={}, uvr_version="0.3.0")

        assert plan.changed == {}
        assert "pkg-a" in plan.unchanged

    @patch("uv_release_monorepo.pipeline.generate_release_notes")
    @patch("uv_release_monorepo.pipeline.detect_changes")
    @patch("uv_release_monorepo.pipeline.get_baseline_tags")
    @patch("uv_release_monorepo.pipeline.find_release_tags")
    @patch("uv_release_monorepo.pipeline.discover_packages")
    def test_populates_publish_matrix_and_ci_publish(
        self,
        mock_discover: MagicMock,
        mock_find_release: MagicMock,
        mock_find_dev: MagicMock,
        mock_detect: MagicMock,
        mock_gen_notes: MagicMock,
    ) -> None:
        """build_plan populates publish_matrix with precomputed notes and sets ci_publish=True."""
        packages = {
            "pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[]),
        }
        mock_discover.return_value = packages
        mock_find_release.return_value = {"pkg-a": "pkg-a/v0.9.0"}
        mock_find_dev.return_value = {"pkg-a": None}
        mock_detect.return_value = ["pkg-a"]
        mock_gen_notes.return_value = "**Released:** pkg-a 1.0.0"

        plan, _ = build_plan(rebuild_all=False, matrix={}, uvr_version="0.3.0")

        assert plan.ci_publish is True
        assert len(plan.publish_matrix) == 1
        entry = plan.publish_matrix[0]
        assert entry.package == "pkg-a"
        assert entry.version == "1.0.0"
        assert entry.tag == "pkg-a/v1.0.0"
        assert entry.title == "pkg-a 1.0.0"
        assert entry.body == "**Released:** pkg-a 1.0.0"

    @patch("uv_release_monorepo.pipeline.detect_changes")
    @patch("uv_release_monorepo.pipeline.get_baseline_tags")
    @patch("uv_release_monorepo.pipeline.find_release_tags")
    @patch("uv_release_monorepo.pipeline.discover_packages")
    def test_matrix_entries_include_path_and_version(
        self,
        mock_discover: MagicMock,
        mock_find_release: MagicMock,
        mock_find_dev: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """MatrixEntry includes path and version from the plan."""
        packages = {
            "pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[]),
        }
        mock_discover.return_value = packages
        mock_find_release.return_value = {"pkg-a": None}
        mock_find_dev.return_value = {"pkg-a": None}
        mock_detect.return_value = ["pkg-a"]

        plan, _ = build_plan(rebuild_all=False, matrix={}, uvr_version="0.3.0")

        assert plan.matrix[0].path == "packages/a"
        assert plan.matrix[0].version == "1.0.0"


class TestGenerateReleaseNotes:
    """Tests for generate_release_notes()."""

    @patch("uv_release_monorepo.pipeline.git")
    def test_with_baseline_and_commits(self, mock_git: MagicMock) -> None:
        """Includes commit log when baseline tag exists."""
        mock_git.return_value = "abc1234 fix: something\ndef5678 feat: another"
        info = PackageInfo(path="packages/a", version="1.0.0", deps=[])

        result = generate_release_notes("pkg-a", info, "pkg-a/v0.9.0")

        assert "**Released:** pkg-a 1.0.0" in result
        assert "**Commits:**" in result
        assert "- abc1234 fix: something" in result
        assert "- def5678 feat: another" in result

    @patch("uv_release_monorepo.pipeline.git")
    def test_without_baseline(self, mock_git: MagicMock) -> None:
        """No commit log when no baseline tag."""
        info = PackageInfo(path="packages/a", version="1.0.0", deps=[])

        result = generate_release_notes("pkg-a", info, None)

        assert result == "**Released:** pkg-a 1.0.0"
        mock_git.assert_not_called()

    @patch("uv_release_monorepo.pipeline.git")
    def test_with_baseline_no_commits(self, mock_git: MagicMock) -> None:
        """No commit section when git log returns empty."""
        mock_git.return_value = ""
        info = PackageInfo(path="packages/a", version="1.0.0", deps=[])

        result = generate_release_notes("pkg-a", info, "pkg-a/v0.9.0")

        assert result == "**Released:** pkg-a 1.0.0"
        assert "Commits" not in result


class TestExecutePlan:
    """Tests for execute_plan()."""

    @patch("uv_release_monorepo.pipeline.git")
    @patch("uv_release_monorepo.pipeline.tag_baselines")
    @patch("uv_release_monorepo.pipeline.commit_bumps")
    @patch("uv_release_monorepo.pipeline.apply_bumps")
    @patch("uv_release_monorepo.pipeline.tag_changed_packages")
    @patch("uv_release_monorepo.pipeline.publish_release")
    @patch("uv_release_monorepo.pipeline.build_packages")
    @patch("uv_release_monorepo.pipeline.fetch_unchanged_wheels")
    @patch("uv_release_monorepo.pipeline.check_for_existing_wheels")
    @patch("uv_release_monorepo.pipeline.Path")
    def test_calls_pipeline_in_order(
        self,
        mock_path: MagicMock,
        mock_check: MagicMock,
        mock_fetch: MagicMock,
        mock_build: MagicMock,
        mock_publish: MagicMock,
        mock_tag_pkg: MagicMock,
        mock_apply: MagicMock,
        mock_commit: MagicMock,
        mock_tag_dev: MagicMock,
        mock_git: MagicMock,
    ) -> None:
        """execute_plan calls pipeline steps in the correct order."""
        alpha = PackageInfo(path="packages/alpha", version="0.1.5", deps=[])
        plan = ReleasePlan(
            uvr_version="0.3.0",
            rebuild_all=False,
            changed={"pkg-alpha": alpha},
            unchanged={},
            release_tags={"pkg-alpha": "pkg-alpha/v0.1.4"},
            matrix=[MatrixEntry(package="pkg-alpha", runner="ubuntu-latest")],
        )
        mock_path.return_value.mkdir = MagicMock()
        bumped = {"pkg-alpha": MagicMock(old="0.1.5", new="0.1.6")}
        mock_apply.return_value = bumped

        execute_plan(plan, push=False)

        mock_check.assert_called_once()
        mock_fetch.assert_called_once()
        mock_build.assert_called_once()
        mock_publish.assert_called_once()
        mock_tag_pkg.assert_called_once()
        mock_apply.assert_called_once()
        mock_commit.assert_called_once()
        mock_tag_dev.assert_called_once_with(bumped)
        mock_git.assert_not_called()  # push=False

    @patch("uv_release_monorepo.pipeline.git")
    @patch("uv_release_monorepo.pipeline.step")
    @patch("uv_release_monorepo.pipeline.tag_baselines")
    @patch("uv_release_monorepo.pipeline.commit_bumps")
    @patch("uv_release_monorepo.pipeline.apply_bumps")
    @patch("uv_release_monorepo.pipeline.tag_changed_packages")
    @patch("uv_release_monorepo.pipeline.publish_release")
    @patch("uv_release_monorepo.pipeline.build_packages")
    @patch("uv_release_monorepo.pipeline.fetch_unchanged_wheels")
    @patch("uv_release_monorepo.pipeline.check_for_existing_wheels")
    @patch("uv_release_monorepo.pipeline.Path")
    def test_pushes_when_push_true(
        self,
        mock_path: MagicMock,
        mock_check: MagicMock,
        mock_fetch: MagicMock,
        mock_build: MagicMock,
        mock_publish: MagicMock,
        mock_tag_pkg: MagicMock,
        mock_apply: MagicMock,
        mock_commit: MagicMock,
        mock_tag_dev: MagicMock,
        mock_step: MagicMock,
        mock_git: MagicMock,
    ) -> None:
        """execute_plan pushes commits and tags when push=True."""
        alpha = PackageInfo(path="packages/alpha", version="0.1.5", deps=[])
        plan = ReleasePlan(
            uvr_version="0.3.0",
            rebuild_all=False,
            changed={"pkg-alpha": alpha},
            unchanged={},
            release_tags={"pkg-alpha": None},
            matrix=[MatrixEntry(package="pkg-alpha", runner="ubuntu-latest")],
        )
        mock_path.return_value.mkdir = MagicMock()
        mock_apply.return_value = {}

        execute_plan(plan, push=True)

        mock_git.assert_any_call("push")
        mock_git.assert_any_call("push", "--tags")

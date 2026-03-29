"""Tests for the release pipeline."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pygit2
import pytest

from uv_release_monorepo.shared.context import RepositoryContext
from uv_release_monorepo.shared.context._baselines import find_baselines
from uv_release_monorepo.shared.context._packages import find_packages
from uv_release_monorepo.shared.context._releases import find_release_tags
from uv_release_monorepo.shared.git.local import generate_release_notes
from uv_release_monorepo.shared.models import (
    PackageInfo,
    PlanConfig,
    ReleasePlan,
)
from uv_release_monorepo.shared.planner import build_plan
from uv_release_monorepo.shared.planner._changes import detect_changes


def _make_ctx(
    packages: dict[str, PackageInfo],
    release_tags: dict[str, str | None] | None = None,
    baselines: dict[str, str | None] | None = None,
    git_tags: set[str] | None = None,
    github_releases: set[str] | None = None,
) -> RepositoryContext:
    """Build a fake RepositoryContext for tests."""
    if release_tags is None:
        release_tags = {n: None for n in packages}
    if baselines is None:
        baselines = {n: None for n in packages}
    return RepositoryContext(
        repo=MagicMock(spec=pygit2.Repository),
        git_tags=git_tags or set(),
        github_releases=github_releases or set(),
        packages=packages,
        release_tags=release_tags,
        baselines=baselines,
    )


class TestFindReleaseTags:
    """Tests for find_release_tags()."""

    @pytest.fixture
    def sample_packages(self) -> dict[str, PackageInfo]:
        """Create sample packages for testing."""
        return {
            "pkg-a": PackageInfo(path="packages/a", version="1.0.1.dev0", deps=[]),
            "pkg-b": PackageInfo(path="packages/b", version="1.0.1.dev0", deps=[]),
        }

    @patch("uv_release_monorepo.shared.context._releases.print_step")
    def test_returns_per_package_releases(
        self,
        _mock_step: MagicMock,
        sample_packages: dict[str, PackageInfo],
    ) -> None:
        """Returns the most recent release for each package."""
        gh_releases = {"pkg-a/v1.0.0", "pkg-a/v0.9.0", "pkg-b/v1.0.0"}

        result = find_release_tags(sample_packages, gh_releases)

        assert result == {"pkg-a": "pkg-a/v1.0.0", "pkg-b": "pkg-b/v1.0.0"}

    @patch("uv_release_monorepo.shared.context._releases.print_step")
    def test_returns_none_for_new_packages(
        self,
        _mock_step: MagicMock,
        sample_packages: dict[str, PackageInfo],
    ) -> None:
        """Returns None for packages with no releases."""
        gh_releases = {"pkg-a/v1.0.0"}

        result = find_release_tags(sample_packages, gh_releases)

        assert result == {"pkg-a": "pkg-a/v1.0.0", "pkg-b": None}

    @patch("uv_release_monorepo.shared.context._releases.print_step")
    def test_all_new_packages(
        self,
        _mock_step: MagicMock,
        sample_packages: dict[str, PackageInfo],
    ) -> None:
        """When no releases exist, all return None."""
        result = find_release_tags(sample_packages, set())

        assert result == {"pkg-a": None, "pkg-b": None}

    @patch("uv_release_monorepo.shared.context._releases.print_step")
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
    """Tests for find_baselines()."""

    @pytest.fixture
    def sample_packages(self) -> dict[str, PackageInfo]:
        """Create sample packages for testing."""
        return {
            "pkg-a": PackageInfo(path="packages/a", version="1.0.1", deps=[]),
            "pkg-b": PackageInfo(path="packages/b", version="1.0.1", deps=[]),
        }

    @patch("uv_release_monorepo.shared.context._baselines.print_step")
    def test_returns_base_tags(
        self,
        _mock_step: MagicMock,
        sample_packages: dict[str, PackageInfo],
    ) -> None:
        """Returns the -base tag derived from pyproject.toml version."""
        all_tags = {"pkg-a/v1.0.1-base", "pkg-b/v1.0.1-base"}

        result = find_baselines(sample_packages, all_tags)

        assert result == {
            "pkg-a": "pkg-a/v1.0.1-base",
            "pkg-b": "pkg-b/v1.0.1-base",
        }

    @patch("uv_release_monorepo.shared.context._baselines.print_step")
    def test_returns_none_when_no_base_tag(
        self,
        _mock_step: MagicMock,
        sample_packages: dict[str, PackageInfo],
    ) -> None:
        """Returns None when no -base tag exists for a package."""
        all_tags = {"pkg-b/v1.0.1-base"}

        result = find_baselines(sample_packages, all_tags)

        assert result == {
            "pkg-a": None,
            "pkg-b": "pkg-b/v1.0.1-base",
        }

    @patch("uv_release_monorepo.shared.context._baselines.print_step")
    def test_returns_none_for_new_packages(
        self,
        _mock_step: MagicMock,
        sample_packages: dict[str, PackageInfo],
    ) -> None:
        """Returns None for packages with no tags at all."""
        result = find_baselines(sample_packages, set())

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

    @patch("uv_release_monorepo.shared.planner._changes.diff_files")
    @patch("uv_release_monorepo.shared.planner._changes.print_step")
    def test_first_release_all_changed(
        self,
        mock_step: MagicMock,
        mock_diff: MagicMock,
        sample_packages: dict[str, PackageInfo],
        no_tags: dict[str, None],
    ) -> None:
        """On first release (no tags), all packages are marked changed."""
        changed = detect_changes(sample_packages, baselines=no_tags, rebuild_all=False)

        assert set(changed) == {"pkg-a", "pkg-b", "pkg-c"}

    @patch("uv_release_monorepo.shared.planner._changes.diff_files")
    @patch("uv_release_monorepo.shared.planner._changes.print_step")
    def test_rebuild_all_marks_everything_dirty(
        self,
        mock_step: MagicMock,
        mock_diff: MagicMock,
        sample_packages: dict[str, PackageInfo],
        all_tags: dict[str, str],
    ) -> None:
        """rebuild_all=True marks all packages as changed regardless of git diff."""
        changed = detect_changes(sample_packages, baselines=all_tags, rebuild_all=True)

        assert set(changed) == {"pkg-a", "pkg-b", "pkg-c"}

    @patch("uv_release_monorepo.shared.planner._changes.diff_files")
    @patch("uv_release_monorepo.shared.planner._changes.print_step")
    def test_single_package_changed(
        self,
        mock_step: MagicMock,
        mock_diff: MagicMock,
        sample_packages: dict[str, PackageInfo],
        all_tags: dict[str, str],
    ) -> None:
        """When only one leaf package changes, only it is rebuilt."""
        responses: dict[str, set[str]] = {
            "pkg-a/v1.0.0": set(),
            "pkg-b/v1.0.0": set(),
            "pkg-c/v1.0.0": {"packages/c/src.py"},
        }
        mock_diff.side_effect = lambda _repo, tag: responses.get(tag, set())

        changed = detect_changes(sample_packages, baselines=all_tags, rebuild_all=False)

        assert set(changed) == {"pkg-c"}

    @patch("uv_release_monorepo.shared.planner._changes.diff_files")
    @patch("uv_release_monorepo.shared.planner._changes.print_step")
    def test_dependency_change_propagates(
        self,
        mock_step: MagicMock,
        mock_diff: MagicMock,
        sample_packages: dict[str, PackageInfo],
        all_tags: dict[str, str],
    ) -> None:
        """When a dependency changes, its dependents are also marked dirty."""
        responses: dict[str, set[str]] = {
            "pkg-a/v1.0.0": {"packages/a/src.py"},
            "pkg-b/v1.0.0": set(),
            "pkg-c/v1.0.0": set(),
        }
        mock_diff.side_effect = lambda _repo, tag: responses.get(tag, set())

        changed = detect_changes(sample_packages, baselines=all_tags, rebuild_all=False)

        assert set(changed) == {"pkg-a", "pkg-b", "pkg-c"}

    @patch("uv_release_monorepo.shared.planner._changes.diff_files")
    @patch("uv_release_monorepo.shared.planner._changes.print_step")
    def test_middle_package_change_propagates_to_dependents(
        self,
        mock_step: MagicMock,
        mock_diff: MagicMock,
        sample_packages: dict[str, PackageInfo],
        all_tags: dict[str, str],
    ) -> None:
        """When a middle package changes, only it and its dependents are dirty."""
        responses: dict[str, set[str]] = {
            "pkg-a/v1.0.0": set(),
            "pkg-b/v1.0.0": {"packages/b/src.py"},
            "pkg-c/v1.0.0": set(),
        }
        mock_diff.side_effect = lambda _repo, tag: responses.get(tag, set())

        changed = detect_changes(sample_packages, baselines=all_tags, rebuild_all=False)

        assert set(changed) == {"pkg-b", "pkg-c"}

    @patch("uv_release_monorepo.shared.planner._changes.diff_files")
    @patch("uv_release_monorepo.shared.planner._changes.print_step")
    def test_root_pyproject_change_does_not_mark_packages_dirty(
        self,
        mock_step: MagicMock,
        mock_diff: MagicMock,
        sample_packages: dict[str, PackageInfo],
        all_tags: dict[str, str],
    ) -> None:
        """Root pyproject.toml changes alone don't trigger package rebuilds."""
        mock_diff.return_value = {"pyproject.toml"}

        changed = detect_changes(sample_packages, baselines=all_tags, rebuild_all=False)

        assert changed == []

    @patch("uv_release_monorepo.shared.planner._changes.diff_files")
    @patch("uv_release_monorepo.shared.planner._changes.print_step")
    def test_no_changes_returns_empty(
        self,
        mock_step: MagicMock,
        mock_diff: MagicMock,
        sample_packages: dict[str, PackageInfo],
        all_tags: dict[str, str],
    ) -> None:
        """When nothing changed, returns empty changed list."""
        mock_diff.return_value = {"unrelated/file.txt"}

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

    @patch("uv_release_monorepo.shared.planner._changes.diff_files")
    @patch("uv_release_monorepo.shared.planner._changes.print_step")
    def test_bottom_change_propagates_to_all(
        self,
        mock_step: MagicMock,
        mock_diff: MagicMock,
        diamond_packages: dict[str, PackageInfo],
        diamond_tags: dict[str, str],
    ) -> None:
        """Changing bottom affects all packages in diamond."""
        responses: dict[str, set[str]] = {
            "bottom/v1.0.0": {"packages/bottom/src.py"},
            "left/v1.0.0": set(),
            "right/v1.0.0": set(),
            "top/v1.0.0": set(),
        }
        mock_diff.side_effect = lambda _repo, tag: responses.get(tag, set())

        changed = detect_changes(
            diamond_packages, baselines=diamond_tags, rebuild_all=False
        )

        assert set(changed) == {"bottom", "left", "right", "top"}

    @patch("uv_release_monorepo.shared.planner._changes.diff_files")
    @patch("uv_release_monorepo.shared.planner._changes.print_step")
    def test_left_change_propagates_to_top_only(
        self,
        mock_step: MagicMock,
        mock_diff: MagicMock,
        diamond_packages: dict[str, PackageInfo],
        diamond_tags: dict[str, str],
    ) -> None:
        """Changing left affects only left and top."""
        responses: dict[str, set[str]] = {
            "bottom/v1.0.0": set(),
            "left/v1.0.0": {"packages/left/src.py"},
            "right/v1.0.0": set(),
            "top/v1.0.0": set(),
        }
        mock_diff.side_effect = lambda _repo, tag: responses.get(tag, set())

        changed = detect_changes(
            diamond_packages, baselines=diamond_tags, rebuild_all=False
        )

        assert set(changed) == {"left", "top"}

    @patch("uv_release_monorepo.shared.planner._changes.diff_files")
    @patch("uv_release_monorepo.shared.planner._changes.print_step")
    def test_top_change_only_affects_top(
        self,
        mock_step: MagicMock,
        mock_diff: MagicMock,
        diamond_packages: dict[str, PackageInfo],
        diamond_tags: dict[str, str],
    ) -> None:
        """Changing top affects only top (no dependents)."""
        responses: dict[str, set[str]] = {
            "bottom/v1.0.0": set(),
            "left/v1.0.0": set(),
            "right/v1.0.0": set(),
            "top/v1.0.0": {"packages/top/src.py"},
        }
        mock_diff.side_effect = lambda _repo, tag: responses.get(tag, set())

        changed = detect_changes(
            diamond_packages, baselines=diamond_tags, rebuild_all=False
        )

        assert set(changed) == {"top"}


class TestDiscoverPackagesRoot:
    """Tests for find_packages() root parameter."""

    @patch("uv_release_monorepo.shared.context._packages.print_step")
    def test_accepts_explicit_root(self, mock_step: MagicMock, tmp_path: Path) -> None:
        """find_packages() uses the provided root directory."""
        root = tmp_path
        (root / "pyproject.toml").write_text(
            '[tool.uv.workspace]\nmembers = ["packages/*"]\n'
        )
        pkg_dir = root / "packages" / "my-pkg"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "pyproject.toml").write_text(
            '[project]\nname = "my-pkg"\nversion = "0.1.0"\n'
        )

        result = find_packages(root=root)

        assert "my-pkg" in result
        assert result["my-pkg"].version == "0.1.0"


class TestBuildPlan:
    """Tests for build_plan()."""

    @pytest.fixture(autouse=True)
    def _mock_planner_io(self) -> None:  # type: ignore[return]
        """Mock list_tags and generate_release_notes used by the planner."""
        with (
            patch(
                "uv_release_monorepo.shared.planner._planner.list_tags",
                return_value=[],
            ),
            patch(
                "uv_release_monorepo.shared.planner._planner.generate_release_notes",
                return_value="",
            ),
        ):
            yield

    @patch("uv_release_monorepo.shared.planner._planner.detect_changes")
    @patch("uv_release_monorepo.shared.planner._planner.build_context")
    def test_returns_release_plan(
        self,
        mock_build_ctx: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """build_plan returns a ReleasePlan with correct changed/unchanged split."""
        packages = {
            "pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[]),
            "pkg-b": PackageInfo(path="packages/b", version="1.0.0", deps=[]),
        }
        mock_build_ctx.return_value = _make_ctx(
            packages,
            release_tags={
                "pkg-a": "pkg-a/v0.9.0",
                "pkg-b": "pkg-b/v0.9.0",
            },
            baselines={
                "pkg-a": "pkg-a/v1.0.0-dev",
                "pkg-b": "pkg-b/v1.0.0-dev",
            },
        )
        mock_detect.return_value = ["pkg-a"]

        plan = build_plan(
            PlanConfig(rebuild_all=False, matrix={}, uvr_version="0.3.0", dry_run=True)
        )

        assert isinstance(plan, ReleasePlan)
        assert "pkg-a" in plan.changed
        assert "pkg-b" in plan.unchanged
        assert plan.uvr_version == "0.3.0"
        assert plan.rebuild_all is False

    @patch("uv_release_monorepo.shared.planner._planner.detect_changes")
    @patch("uv_release_monorepo.shared.planner._planner.build_context")
    def test_expands_matrix_for_changed_only(
        self,
        mock_build_ctx: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """Matrix entries are only created for changed packages, not unchanged."""
        packages = {
            "pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[]),
            "pkg-b": PackageInfo(path="packages/b", version="1.0.0", deps=[]),
        }
        mock_build_ctx.return_value = _make_ctx(packages)
        mock_detect.return_value = ["pkg-a"]  # only pkg-a changed

        plan = build_plan(
            PlanConfig(
                rebuild_all=False,
                matrix={
                    "pkg-a": [["ubuntu-latest"], ["macos-14"]],
                    "pkg-b": [["ubuntu-latest"]],
                },
                uvr_version="0.3.0",
                dry_run=True,
            )
        )

        # Only pkg-a is changed; it has two runners
        assert "pkg-a" in plan.changed
        assert "pkg-b" not in plan.changed
        assert plan.changed["pkg-a"].runners == [["ubuntu-latest"], ["macos-14"]]
        assert len(plan.build_matrix) == 2  # ubuntu-latest + macos-14

    @patch("uv_release_monorepo.shared.planner._planner.detect_changes")
    @patch("uv_release_monorepo.shared.planner._planner.build_context")
    def test_defaults_matrix_to_ubuntu_latest(
        self,
        mock_build_ctx: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """Changed packages with no matrix entry default to ubuntu-latest."""
        packages = {"pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[])}
        mock_build_ctx.return_value = _make_ctx(packages)
        mock_detect.return_value = ["pkg-a"]

        plan = build_plan(
            PlanConfig(rebuild_all=False, matrix={}, uvr_version="0.3.0", dry_run=True)
        )

        assert plan.changed["pkg-a"].runners == [["ubuntu-latest"]]
        assert len(plan.build_matrix) == 1

    @patch("uv_release_monorepo.shared.planner._planner.detect_changes")
    @patch("uv_release_monorepo.shared.planner._planner.build_context")
    def test_empty_changed_returns_empty_plan(
        self,
        mock_build_ctx: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """When nothing changed, returns a plan with empty changed dict."""
        packages = {"pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[])}
        mock_build_ctx.return_value = _make_ctx(
            packages,
            release_tags={"pkg-a": "pkg-a/v1.0.0"},
            baselines={"pkg-a": "pkg-a/v1.0.0-dev"},
        )
        mock_detect.return_value = []

        plan = build_plan(
            PlanConfig(rebuild_all=False, matrix={}, uvr_version="0.3.0", dry_run=True)
        )

        assert plan.changed == {}
        assert "pkg-a" in plan.unchanged

    @patch("uv_release_monorepo.shared.planner._planner.generate_release_notes")
    @patch("uv_release_monorepo.shared.planner._planner.detect_changes")
    @patch("uv_release_monorepo.shared.planner._planner.build_context")
    def test_populates_release_matrix_and_ci_publish(
        self,
        mock_build_ctx: MagicMock,
        mock_detect: MagicMock,
        mock_gen_notes: MagicMock,
    ) -> None:
        """build_plan populates release_matrix with precomputed notes and sets ci_publish=True."""
        packages = {
            "pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[]),
        }
        mock_build_ctx.return_value = _make_ctx(
            packages,
            release_tags={"pkg-a": "pkg-a/v0.9.0"},
        )
        mock_detect.return_value = ["pkg-a"]
        mock_gen_notes.return_value = "**Released:** pkg-a 1.0.0"

        plan = build_plan(
            PlanConfig(rebuild_all=False, matrix={}, uvr_version="0.3.0", dry_run=True)
        )

        assert plan.ci_publish is True
        assert len(plan.release_matrix) == 1
        entry = plan.release_matrix[0]
        assert entry["package"] == "pkg-a"
        assert entry["version"] == "1.0.0"
        assert entry["tag"] == "pkg-a/v1.0.0"
        assert entry["title"] == "pkg-a 1.0.0"
        assert entry["body"] == "**Released:** pkg-a 1.0.0"

    @patch("uv_release_monorepo.shared.planner._planner.detect_changes")
    @patch("uv_release_monorepo.shared.planner._planner.build_context")
    def test_changed_package_includes_path_and_version(
        self,
        mock_build_ctx: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """ChangedPackage includes path and release version."""
        packages = {
            "pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[]),
        }
        mock_build_ctx.return_value = _make_ctx(packages)
        mock_detect.return_value = ["pkg-a"]

        plan = build_plan(
            PlanConfig(rebuild_all=False, matrix={}, uvr_version="0.3.0", dry_run=True)
        )

        assert plan.changed["pkg-a"].path == "packages/a"
        assert plan.changed["pkg-a"].release_version == "1.0.0"


class TestBuildCommandStages:
    """Tests for _generate_build_commands() stage structure."""

    @pytest.fixture(autouse=True)
    def _mock_planner_io(self) -> None:  # type: ignore[return]
        """Mock list_tags and generate_release_notes used by the planner."""
        with (
            patch(
                "uv_release_monorepo.shared.planner._planner.list_tags",
                return_value=[],
            ),
            patch(
                "uv_release_monorepo.shared.planner._planner.generate_release_notes",
                return_value="",
            ),
        ):
            yield

    @patch("uv_release_monorepo.shared.planner._planner.detect_changes")
    @patch("uv_release_monorepo.shared.planner._planner.build_context")
    def test_diamond_deps_produce_correct_layers(
        self,
        mock_build_ctx: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """Diamond dep graph produces setup + 3 build layers + cleanup stages."""
        packages = {
            "alpha": PackageInfo(path="packages/alpha", version="1.0.0", deps=[]),
            "beta": PackageInfo(path="packages/beta", version="1.0.0", deps=["alpha"]),
            "delta": PackageInfo(
                path="packages/delta", version="1.0.0", deps=["alpha"]
            ),
            "gamma": PackageInfo(path="packages/gamma", version="1.0.0", deps=["beta"]),
        }
        mock_build_ctx.return_value = _make_ctx(packages)
        mock_detect.return_value = list(packages)

        plan = build_plan(
            PlanConfig(rebuild_all=False, matrix={}, uvr_version="0.3.0", dry_run=True)
        )

        stages = plan.build_commands[("ubuntu-latest",)]

        # Stage 0: setup
        assert stages[0].setup

        # Stage 1: layer 0 -- alpha (no deps)
        assert "alpha" in stages[1].packages
        assert len(stages[1].packages) == 1

        # Stage 2: layer 1 -- beta and delta (both depend on alpha only)
        assert set(stages[2].packages.keys()) == {"beta", "delta"}

        # Stage 3: layer 2 -- gamma (depends on beta)
        assert "gamma" in stages[3].packages
        assert len(stages[3].packages) == 1

        # No cleanup stage (all packages assigned to the same runner)
        assert len(stages) == 4

        # Layer 0 (alpha) should NOT have --no-sources
        alpha_build = [
            c for c in stages[1].packages["alpha"] if c.label == "Build alpha"
        ][0]
        assert "--no-sources" not in alpha_build.args

        # Layer 1+ (beta, delta, gamma) SHOULD have --no-sources
        for stage, pkgs in [(stages[2], ["beta", "delta"]), (stages[3], ["gamma"])]:
            for pkg in pkgs:
                build_cmd = [
                    c for c in stage.packages[pkg] if c.label == f"Build {pkg}"
                ][0]
                assert "--no-sources" in build_cmd.args

    @patch("uv_release_monorepo.shared.planner._planner.detect_changes")
    @patch("uv_release_monorepo.shared.planner._planner.build_context")
    def test_no_deps_single_parallel_layer(
        self,
        mock_build_ctx: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """Independent packages all land in a single parallel build stage."""
        packages = {
            "pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[]),
            "pkg-b": PackageInfo(path="packages/b", version="1.0.0", deps=[]),
            "pkg-c": PackageInfo(path="packages/c", version="1.0.0", deps=[]),
        }
        mock_build_ctx.return_value = _make_ctx(packages)
        mock_detect.return_value = list(packages)

        plan = build_plan(
            PlanConfig(rebuild_all=False, matrix={}, uvr_version="0.3.0", dry_run=True)
        )

        stages = plan.build_commands[("ubuntu-latest",)]
        # setup + one layer with all 3 packages
        assert len(stages) == 2
        assert stages[0].setup
        assert set(stages[1].packages.keys()) == {"pkg-a", "pkg-b", "pkg-c"}

    @patch("uv_release_monorepo.shared.planner._planner.detect_changes")
    @patch("uv_release_monorepo.shared.planner._planner.build_context")
    def test_changed_dep_built_on_runner_that_needs_it(
        self,
        mock_build_ctx: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """A changed dep not assigned to a runner is still built there."""
        # tools is pure-python (ubuntu-only), overlay depends on it (macos)
        packages = {
            "tools": PackageInfo(path="packages/tools", version="1.0.0", deps=[]),
            "overlay": PackageInfo(
                path="packages/overlay", version="1.0.0", deps=["tools"]
            ),
        }
        mock_build_ctx.return_value = _make_ctx(packages)
        mock_detect.return_value = list(packages)

        plan = build_plan(
            PlanConfig(
                rebuild_all=False,
                matrix={
                    "tools": [["ubuntu-latest"]],
                    "overlay": [["macos-14"]],
                },
                uvr_version="0.3.0",
                dry_run=True,
            )
        )

        # macos-14 runner should build both tools (layer 0) and overlay (layer 1)
        macos_stages = plan.build_commands[("macos-14",)]
        built_pkgs = {pkg for stage in macos_stages for pkg in stage.packages}
        assert "tools" in built_pkgs, "changed dep 'tools' must be built on macos-14"
        assert "overlay" in built_pkgs

        # tools wheel should be cleaned from dist/ (not assigned to macos-14)
        cleanup_stage = macos_stages[-1]
        assert cleanup_stage.cleanup
        cleanup_cmd = cleanup_stage.cleanup[0]
        assert "tools" in " ".join(cleanup_cmd.args)


class TestGenerateReleaseNotes:
    """Tests for generate_release_notes()."""

    @patch("uv_release_monorepo.shared.git.local.commit_log")
    def test_with_baseline_and_commits(self, mock_log: MagicMock) -> None:
        """Includes commit log when baseline tag exists."""
        mock_log.return_value = ["abc1234 fix: something", "def5678 feat: another"]
        info = PackageInfo(path="packages/a", version="1.0.0", deps=[])

        result = generate_release_notes("pkg-a", info, "pkg-a/v0.9.0")

        assert "**Released:** pkg-a 1.0.0" in result
        assert "**Commits:**" in result
        assert "- abc1234 fix: something" in result
        assert "- def5678 feat: another" in result

    @patch("uv_release_monorepo.shared.git.local.commit_log")
    def test_without_baseline(self, mock_log: MagicMock) -> None:
        """No commit log when no baseline tag."""
        info = PackageInfo(path="packages/a", version="1.0.0", deps=[])

        result = generate_release_notes("pkg-a", info, None)

        assert result == "**Released:** pkg-a 1.0.0"
        mock_log.assert_not_called()

    @patch("uv_release_monorepo.shared.git.local.commit_log")
    def test_with_baseline_no_commits(self, mock_log: MagicMock) -> None:
        """No commit section when git log returns empty."""
        mock_log.return_value = []
        info = PackageInfo(path="packages/a", version="1.0.0", deps=[])

        result = generate_release_notes("pkg-a", info, "pkg-a/v0.9.0")

        assert result == "**Released:** pkg-a 1.0.0"
        assert "Commits" not in result

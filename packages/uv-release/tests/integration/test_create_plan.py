"""Integration tests for create_plan using real git repos and real disk I/O."""

from __future__ import annotations

from pathlib import Path

import pytest

from uv_release.commands import DownloadWheelsCommand, SetVersionCommand, ShellCommand
from uv_release.plan.planner import create_plan
from uv_release.types import BumpType, CommandGroup, PlanParams

from .conftest import _git, add_baseline_tags, modify_file


def _params(**overrides: object) -> PlanParams:
    """Default params: dev_release=True, require_clean_worktree=False."""
    defaults = {"dev_release": True, "require_clean_worktree": False}
    defaults.update(overrides)
    return PlanParams(**defaults)  # type: ignore[arg-type]


class TestFirstRelease:
    """No baseline tags. Every package is detected as changed."""

    def test_both_packages_in_releases(self, workspace: Path) -> None:
        plan = create_plan(_params())
        assert "alpha" in plan.releases
        assert "beta" in plan.releases

    def test_changes_have_no_baseline(self, workspace: Path) -> None:
        plan = create_plan(_params())
        assert plan.changes["alpha"].baseline is None
        assert plan.changes["beta"].baseline is None

    def test_reason_is_initial_release(self, workspace: Path) -> None:
        plan = create_plan(_params())
        assert plan.changes["alpha"].reason == "initial release"
        assert plan.changes["beta"].reason == "initial release"


class TestChangedSinceBaseline:
    """Baseline tags exist, then a file is modified."""

    def test_direct_change_detected(self, workspace: Path) -> None:
        add_baseline_tags(workspace)
        modify_file(workspace, "packages/alpha/new.txt")
        plan = create_plan(_params())
        assert "alpha" in plan.releases
        assert plan.changes["alpha"].reason == "files changed"

    def test_dependency_propagation(self, workspace: Path) -> None:
        add_baseline_tags(workspace)
        modify_file(workspace, "packages/alpha/new.txt")
        plan = create_plan(_params())
        assert "beta" in plan.releases
        assert plan.changes["beta"].reason == "dependency changed"

    def test_commit_log_populated(self, workspace: Path) -> None:
        add_baseline_tags(workspace)
        modify_file(workspace, "packages/alpha/new.txt")
        plan = create_plan(_params())
        assert "modify" in plan.changes["alpha"].commit_log

    def test_diff_stats_populated(self, workspace: Path) -> None:
        add_baseline_tags(workspace)
        modify_file(workspace, "packages/alpha/new.txt")
        plan = create_plan(_params())
        assert plan.changes["alpha"].diff_stats is not None

    def test_baseline_has_commit(self, workspace: Path) -> None:
        add_baseline_tags(workspace)
        modify_file(workspace, "packages/alpha/new.txt")
        plan = create_plan(_params())
        assert plan.changes["alpha"].baseline is not None
        assert len(plan.changes["alpha"].baseline.commit) == 40


class TestUnchangedSinceBaseline:
    """Baseline tags exist, no modifications."""

    def test_no_releases(self, workspace: Path) -> None:
        add_baseline_tags(workspace)
        plan = create_plan(_params())
        assert plan.releases == {}

    def test_no_changes(self, workspace: Path) -> None:
        add_baseline_tags(workspace)
        plan = create_plan(_params())
        assert plan.changes == {}


class TestRebuildAll:
    """rebuild_all=True forces all packages dirty."""

    def test_all_packages_released(self, workspace: Path) -> None:
        add_baseline_tags(workspace)
        plan = create_plan(_params(rebuild_all=True))
        assert "alpha" in plan.releases
        assert "beta" in plan.releases

    def test_reason_is_rebuild_all(self, workspace: Path) -> None:
        add_baseline_tags(workspace)
        plan = create_plan(_params(rebuild_all=True))
        assert plan.changes["alpha"].reason == "rebuild all"


class TestSkipJobFiltering:
    """skip param controls which jobs have commands."""

    def test_status_mode_skips_all_but_validate(self, workspace: Path) -> None:
        plan = create_plan(
            _params(skip=frozenset({"build", "release", "publish", "bump"}))
        )
        assert plan.releases  # still has releases
        assert plan.workflow.jobs["uvr-build"].commands == []
        assert plan.workflow.jobs["uvr-release"].commands == []
        assert plan.workflow.jobs["uvr-publish"].commands == []
        assert plan.workflow.jobs["uvr-bump"].commands == []

    def test_all_five_jobs_exist(self, workspace: Path) -> None:
        plan = create_plan(
            _params(skip=frozenset({"build", "release", "publish", "bump"}))
        )
        assert len(plan.workflow.jobs) == 5


class TestVersionFixCommands:
    """Version fix commands in validate job for local non-dev releases."""

    def test_local_dev_packages_get_command_group(self, workspace: Path) -> None:
        plan = create_plan(_params(dev_release=False, target="local"))
        validate_cmds = plan.workflow.jobs["uvr-validate"].commands
        assert len(validate_cmds) == 1
        assert isinstance(validate_cmds[0], CommandGroup)
        assert validate_cmds[0].needs_user_confirmation is True

    def test_command_group_contains_set_version(self, workspace: Path) -> None:
        plan = create_plan(_params(dev_release=False, target="local"))
        group = plan.workflow.jobs["uvr-validate"].commands[0]
        assert isinstance(group, CommandGroup)
        set_cmds = [c for c in group.commands if isinstance(c, SetVersionCommand)]
        assert len(set_cmds) >= 1
        assert set_cmds[0].version.raw == "1.0.0"

    def test_command_group_contains_git_commit(self, workspace: Path) -> None:
        plan = create_plan(_params(dev_release=False, target="local"))
        group = plan.workflow.jobs["uvr-validate"].commands[0]
        assert isinstance(group, CommandGroup)
        shell_cmds = [c for c in group.commands if isinstance(c, ShellCommand)]
        commit_cmds = [c for c in shell_cmds if "commit" in c.args]
        assert len(commit_cmds) == 1

    def test_no_version_fix_for_dev_release(self, workspace: Path) -> None:
        plan = create_plan(_params(dev_release=True, target="local"))
        validate_cmds = plan.workflow.jobs["uvr-validate"].commands
        assert len(validate_cmds) == 0

    def test_ci_target_gets_raw_commands(self, workspace: Path) -> None:
        plan = create_plan(_params(dev_release=False, target="ci"))
        validate_cmds = plan.workflow.jobs["uvr-validate"].commands
        assert len(validate_cmds) > 0
        assert not isinstance(validate_cmds[0], CommandGroup)


class TestBumpTypeRouting:
    """bump_type controls next_version computation."""

    def test_minor_bump(self, workspace: Path) -> None:
        plan = create_plan(_params(bump_type=BumpType.MINOR))
        assert plan.releases["alpha"].next_version.raw == "1.1.0.dev0"

    def test_major_bump(self, workspace: Path) -> None:
        plan = create_plan(_params(bump_type=BumpType.MAJOR))
        assert plan.releases["alpha"].next_version.raw == "2.0.0.dev0"

    def test_default_dev_bump(self, workspace: Path) -> None:
        plan = create_plan(_params())
        # DEV default: compute_next_version for 1.0.0.dev0 -> 1.0.0.dev1
        assert plan.releases["alpha"].next_version.raw == "1.0.0.dev1"


class TestDirtyWorktree:
    """require_clean_worktree guards."""

    def test_dirty_worktree_exits(self, workspace: Path) -> None:
        (workspace / "dirty.txt").write_text("uncommitted")
        with pytest.raises(SystemExit):
            create_plan(PlanParams())

    def test_dirty_worktree_allowed_with_flag(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (workspace / "dirty.txt").write_text("uncommitted")
        plan = create_plan(_params())  # require_clean_worktree=False
        assert plan is not None
        captured = capsys.readouterr()
        assert "WARNING" in captured.err


class TestTargetPropagation:
    """target on PlanParams propagates to Plan."""

    def test_local_default(self, workspace: Path) -> None:
        plan = create_plan(_params())
        assert plan.target == "local"

    def test_ci_target(self, workspace: Path) -> None:
        plan = create_plan(_params(target="ci"))
        assert plan.target == "ci"


class TestRestrictPackages:
    """restrict_packages filters output to specified packages and their deps."""

    def test_restrict_to_beta_includes_alpha_dep(self, workspace: Path) -> None:
        plan = create_plan(_params(restrict_packages=frozenset({"beta"})))
        assert "beta" in plan.releases
        assert "alpha" in plan.releases  # transitive dep


class TestUnchangedDepDownload:
    """When only some packages change, unchanged deps get download commands."""

    def test_build_job_has_download_for_unchanged(self, workspace: Path) -> None:
        # Set alpha to a clean released version with a release tag
        alpha_pyproject = workspace / "packages" / "alpha" / "pyproject.toml"
        alpha_pyproject.write_text(
            "[project]\n"
            'name = "alpha"\n'
            'version = "1.0.0"\n'
            "dependencies = []\n\n"
            "[build-system]\n"
            'requires = ["hatchling"]\n'
            'build-backend = "hatchling.build"\n'
        )
        _git(workspace, "add", "-A")
        _git(workspace, "commit", "-m", "release alpha 1.0.0")
        # Previous release tag so baseline detection finds it
        _git(workspace, "tag", "alpha/v0.9.0")
        _git(workspace, "tag", "alpha/v1.0.0")

        # Tag beta baseline, then modify it
        _git(workspace, "tag", "beta/v1.0.0.dev0-base")
        modify_file(workspace, "packages/beta/beta/__init__.py", "# changed\n")

        plan = create_plan(_params(restrict_packages=frozenset({"beta"})))
        assert "beta" in plan.releases
        assert "alpha" not in plan.releases

        build_cmds = plan.workflow.jobs["uvr-build"].commands
        dl_cmds = [c for c in build_cmds if isinstance(c, DownloadWheelsCommand)]
        assert len(dl_cmds) == 1
        assert dl_cmds[0].release_tags["alpha"] == "alpha/v1.0.0"


class TestWorkspaceIncludeExclude:
    """Config include/exclude filters packages."""

    def test_exclude_filters_package(self, workspace: Path) -> None:
        # Add [tool.uvr.config] exclude to root pyproject
        root_pyproject = workspace / "pyproject.toml"
        root_pyproject.write_text(
            '[project]\nname = "workspace"\nversion = "0.0.0"\n\n'
            "[tool.uv.workspace]\n"
            'members = ["packages/*"]\n\n'
            "[tool.uvr.config]\n"
            'exclude = ["alpha"]\n'
        )
        _git(workspace, "add", "-A")
        _git(workspace, "commit", "-m", "exclude alpha")

        plan = create_plan(_params())
        assert "alpha" not in plan.releases
        assert "alpha" not in plan.workspace.packages
        assert "beta" in plan.workspace.packages


class TestWorkspaceWithEmptyDirs:
    """Workspace dirs that lack pyproject.toml are silently skipped."""

    def test_dir_without_pyproject_is_ignored(self, workspace: Path) -> None:
        orphan_dir = workspace / "packages" / "orphan"
        orphan_dir.mkdir()
        (orphan_dir / "README.md").write_text("no pyproject here")
        _git(workspace, "add", "-A")
        _git(workspace, "commit", "-m", "add orphan dir")

        plan = create_plan(_params())
        assert "orphan" not in plan.workspace.packages
        assert "alpha" in plan.workspace.packages


class TestWorkspaceIncludeFilter:
    """Config include filters which packages are part of the workspace."""

    def test_include_restricts_workspace(self, workspace: Path) -> None:
        root_pyproject = workspace / "pyproject.toml"
        root_pyproject.write_text(
            '[project]\nname = "workspace"\nversion = "0.0.0"\n\n'
            "[tool.uv.workspace]\n"
            'members = ["packages/*"]\n\n'
            "[tool.uvr.config]\n"
            'include = ["alpha"]\n'
        )
        _git(workspace, "add", "-A")
        _git(workspace, "commit", "-m", "add include filter")

        plan = create_plan(_params())
        assert "alpha" in plan.workspace.packages
        assert "beta" not in plan.workspace.packages


class TestExternalDependency:
    """A package dep that references a non-workspace package is handled gracefully."""

    def test_dep_not_in_workspace(self, workspace: Path) -> None:
        # beta depends on "requests" which is not a workspace member
        beta_pyproject = workspace / "packages" / "beta" / "pyproject.toml"
        beta_pyproject.write_text(
            "[project]\n"
            'name = "beta"\n'
            'version = "1.0.0.dev0"\n'
            'dependencies = ["alpha", "requests"]\n\n'
            "[build-system]\n"
            'requires = ["hatchling"]\n'
            'build-backend = "hatchling.build"\n'
        )
        _git(workspace, "add", "-A")
        _git(workspace, "commit", "-m", "add external dep")

        plan = create_plan(_params())
        # Should not crash; "requests" is filtered out during parsing
        assert "beta" in plan.releases


class TestHooksIntegration:
    """Hooks are loaded and called through the pipeline."""

    def test_hooks_modify_params(self, workspace: Path) -> None:
        # Write a hooks file that sets rebuild_all=True
        hooks_file = workspace / "uvr_hooks.py"
        hooks_file.write_text(
            "from uv_release.types import Hooks as _Base, PlanParams\n"
            "from dataclasses import replace\n\n"
            "class Hooks(_Base):\n"
            "    def pre_plan(self, params: PlanParams) -> PlanParams:\n"
            "        return replace(params, rebuild_all=True)\n"
        )
        _git(workspace, "add", "-A")
        _git(workspace, "commit", "-m", "add hooks")

        # Baseline both packages so they're normally unchanged
        add_baseline_tags(workspace)

        plan = create_plan(_params())
        # Hook forced rebuild_all, so both packages should be in releases
        assert "alpha" in plan.releases
        assert "beta" in plan.releases


class TestUpgradeTemplates:
    """upgrade/templates.py store_base and load_base."""

    def test_store_and_load_base(self, workspace: Path) -> None:
        from uv_release.upgrade.templates import load_base, store_base

        uvr_dir = workspace / ".uvr"
        stored = store_base("content", "release.yml", uvr_dir=uvr_dir)
        assert stored.exists()
        assert stored.read_text() == "content"

        loaded = load_base("release.yml", uvr_dir=uvr_dir)
        assert loaded == stored

    def test_store_base_defaults_to_cwd(self, workspace: Path) -> None:
        from uv_release.upgrade.templates import store_base

        stored = store_base("content", "release.yml")
        assert stored.exists()
        assert ".uvr/bases/release.yml" in str(stored)

    def test_load_base_defaults_to_cwd(self, workspace: Path) -> None:
        from uv_release.upgrade.templates import load_base, store_base

        store_base("content", "test.yml")
        loaded = load_base("test.yml")
        assert loaded.exists()


class TestThreeWayMerge:
    """upgrade/merge.py three_way_merge edge cases."""

    def test_no_base_with_different_content_has_conflicts(
        self, workspace: Path
    ) -> None:
        from uv_release.upgrade.merge import three_way_merge

        current = workspace / "current.yml"
        base = workspace / "nonexistent_base.yml"  # does not exist
        template = workspace / "template.yml"
        current.write_text("user content\n")
        template.write_text("template content\n")

        result = three_way_merge(current, base, template)
        assert result.has_conflicts is True

    def test_no_base_same_content_no_conflicts(self, workspace: Path) -> None:
        from uv_release.upgrade.merge import three_way_merge

        current = workspace / "current.yml"
        base = workspace / "nonexistent_base.yml"
        template = workspace / "template.yml"
        current.write_text("same content\n")
        template.write_text("same content\n")

        result = three_way_merge(current, base, template)
        assert result.has_conflicts is False

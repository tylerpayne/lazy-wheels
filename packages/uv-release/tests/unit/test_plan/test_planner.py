"""Tests for _assemble_plan: the pure plan assembly logic."""

from __future__ import annotations

from uv_release.commands import SetVersionCommand, PinDepsCommand, ShellCommand
from uv_release.plan.planner import _create_plan
from uv_release.types import (
    BumpType,
    Change,
    CommandGroup,
    Config,
    Package,
    Plan,
    PlanParams,
    Publishing,
    Release,
    Tag,
    Version,
    Workspace,
)


def _version(raw: str) -> Version:
    return Version.parse(raw)


def _package(
    name: str, version: str = "1.0.0.dev0", deps: list[str] | None = None
) -> Package:
    return Package(
        name=name, path=f"packages/{name}", version=_version(version), deps=deps or []
    )


def _tag(name: str, version: str, *, baseline: bool = True) -> Tag:
    return Tag(
        package_name=name,
        raw=f"{name}/v{version}-base",
        version=_version(version),
        is_baseline=baseline,
        commit="abc123",
    )


def _workspace(
    packages: dict[str, Package],
    *,
    latest_package: str = "",
) -> Workspace:
    return Workspace(
        packages=packages,
        config=Config(uvr_version="0.1.0", latest_package=latest_package),
        runners={"ubuntu-latest": [["python", "-m", "build"]]},
        publishing=Publishing(),
    )


class TestPlanReleasesNoChanges:
    """No changes should produce a Plan with empty releases and an empty workflow."""

    def test_empty_changes_empty_releases(self) -> None:
        ws = _workspace({"a": _package("a")})
        plan = _create_plan(ws, changes=[], params=PlanParams())
        assert isinstance(plan, Plan)
        assert plan.releases == {}

    def test_empty_changes_empty_workflow_jobs(self) -> None:
        ws = _workspace({"a": _package("a")})
        plan = _create_plan(ws, changes=[], params=PlanParams())
        assert plan.workflow.jobs == {}


class TestPlanReleasesOneChange:
    """One changed package should produce a Release with correct versions."""

    def test_one_change_produces_one_release(self) -> None:
        pkg = _package("a", version="1.0.0.dev0")
        ws = _workspace({"a": pkg})
        change = Change(package=pkg, baseline=_tag("a", "1.0.0.dev0"))
        plan = _create_plan(ws, changes=[change], params=PlanParams())
        assert "a" in plan.releases
        assert isinstance(plan.releases["a"], Release)

    def test_release_version_strips_dev(self) -> None:
        pkg = _package("a", version="1.0.0.dev0")
        ws = _workspace({"a": pkg})
        change = Change(package=pkg, baseline=_tag("a", "1.0.0.dev0"))
        plan = _create_plan(ws, changes=[change], params=PlanParams())
        release = plan.releases["a"]
        assert release.release_version.raw == "1.0.0"

    def test_next_version_is_dev0(self) -> None:
        pkg = _package("a", version="1.0.0.dev0")
        ws = _workspace({"a": pkg})
        change = Change(package=pkg, baseline=_tag("a", "1.0.0.dev0"))
        plan = _create_plan(ws, changes=[change], params=PlanParams())
        release = plan.releases["a"]
        assert release.next_version.raw == "1.0.1.dev0"

    def test_dev_release_mode(self) -> None:
        pkg = _package("a", version="1.0.0.dev0")
        ws = _workspace({"a": pkg})
        change = Change(package=pkg, baseline=_tag("a", "1.0.0.dev0"))
        plan = _create_plan(ws, changes=[change], params=PlanParams(dev_release=True))
        release = plan.releases["a"]
        assert release.release_version.raw == "1.0.0.dev0"
        assert release.next_version.raw == "1.0.0.dev1"


class TestMakeLatest:
    """make_latest should be True for the workspace config's latest_package."""

    def test_latest_package_flag(self) -> None:
        pkg_a = _package("a", version="1.0.0.dev0")
        pkg_b = _package("b", version="2.0.0.dev0")
        ws = _workspace({"a": pkg_a, "b": pkg_b}, latest_package="a")
        changes = [
            Change(package=pkg_a, baseline=_tag("a", "1.0.0.dev0")),
            Change(package=pkg_b, baseline=_tag("b", "2.0.0.dev0")),
        ]
        plan = _create_plan(ws, changes=changes, params=PlanParams())
        assert plan.releases["a"].make_latest is True
        assert plan.releases["b"].make_latest is False

    def test_no_latest_package_all_false(self) -> None:
        pkg = _package("a", version="1.0.0.dev0")
        ws = _workspace({"a": pkg}, latest_package="")
        change = Change(package=pkg, baseline=_tag("a", "1.0.0.dev0"))
        plan = _create_plan(ws, changes=[change], params=PlanParams())
        assert plan.releases["a"].make_latest is False


class TestReleaseNotes:
    """Release notes come from PlanParams override or change.commit_log."""

    def test_notes_from_commit_log(self) -> None:
        pkg = _package("a", version="1.0.0.dev0")
        ws = _workspace({"a": pkg})
        change = Change(
            package=pkg, baseline=_tag("a", "1.0.0.dev0"), commit_log="fixed a bug"
        )
        plan = _create_plan(ws, changes=[change], params=PlanParams())
        assert plan.releases["a"].release_notes == "fixed a bug"

    def test_notes_from_params_override(self) -> None:
        pkg = _package("a", version="1.0.0.dev0")
        ws = _workspace({"a": pkg})
        change = Change(
            package=pkg, baseline=_tag("a", "1.0.0.dev0"), commit_log="old log"
        )
        plan = _create_plan(
            ws,
            changes=[change],
            params=PlanParams(release_notes={"a": "custom notes"}),
        )
        assert plan.releases["a"].release_notes == "custom notes"


class TestPlanWorkflowStructure:
    """When there are releases, the workflow should have jobs."""

    def test_workflow_has_jobs_when_releases_exist(self) -> None:
        pkg = _package("a", version="1.0.0.dev0")
        ws = _workspace({"a": pkg})
        change = Change(package=pkg, baseline=_tag("a", "1.0.0.dev0"))
        plan = _create_plan(ws, changes=[change], params=PlanParams())
        assert len(plan.workflow.jobs) == 5

    def test_plan_holds_workspace(self) -> None:
        pkg = _package("a", version="1.0.0.dev0")
        ws = _workspace({"a": pkg})
        change = Change(package=pkg, baseline=_tag("a", "1.0.0.dev0"))
        plan = _create_plan(ws, changes=[change], params=PlanParams())
        assert plan.workspace is ws


class TestSkipJobFiltering:
    """skip param controls which jobs get populated with commands."""

    def test_skip_build_produces_empty_build_job(self) -> None:
        pkg = _package("a", version="1.0.0.dev0")
        ws = _workspace({"a": pkg})
        change = Change(package=pkg, baseline=_tag("a", "1.0.0.dev0"))
        plan = _create_plan(
            ws, changes=[change], params=PlanParams(skip=frozenset({"build"}))
        )
        assert plan.workflow.jobs["uvr-build"].commands == []

    def test_skip_release_produces_empty_release_job(self) -> None:
        pkg = _package("a", version="1.0.0.dev0")
        ws = _workspace({"a": pkg})
        change = Change(package=pkg, baseline=_tag("a", "1.0.0.dev0"))
        plan = _create_plan(
            ws, changes=[change], params=PlanParams(skip=frozenset({"release"}))
        )
        assert plan.workflow.jobs["uvr-release"].commands == []

    def test_skip_publish_produces_empty_publish_job(self) -> None:
        pkg = _package("a", version="1.0.0.dev0")
        ws = _workspace({"a": pkg})
        change = Change(package=pkg, baseline=_tag("a", "1.0.0.dev0"))
        plan = _create_plan(
            ws, changes=[change], params=PlanParams(skip=frozenset({"publish"}))
        )
        assert plan.workflow.jobs["uvr-publish"].commands == []

    def test_skip_bump_produces_empty_bump_job(self) -> None:
        pkg = _package("a", version="1.0.0.dev0")
        ws = _workspace({"a": pkg})
        change = Change(package=pkg, baseline=_tag("a", "1.0.0.dev0"))
        plan = _create_plan(
            ws, changes=[change], params=PlanParams(skip=frozenset({"bump"}))
        )
        assert plan.workflow.jobs["uvr-bump"].commands == []

    def test_skip_multiple_jobs(self) -> None:
        """Status mode: skip everything except validate."""
        pkg = _package("a", version="1.0.0.dev0")
        ws = _workspace({"a": pkg})
        change = Change(package=pkg, baseline=_tag("a", "1.0.0.dev0"))
        plan = _create_plan(
            ws,
            changes=[change],
            params=PlanParams(skip=frozenset({"build", "release", "publish", "bump"})),
        )
        assert plan.workflow.jobs["uvr-build"].commands == []
        assert plan.workflow.jobs["uvr-release"].commands == []
        assert plan.workflow.jobs["uvr-publish"].commands == []
        assert plan.workflow.jobs["uvr-bump"].commands == []

    def test_unskipped_jobs_still_have_commands(self) -> None:
        pkg = _package("a", version="1.0.0.dev0")
        ws = _workspace({"a": pkg})
        change = Change(package=pkg, baseline=_tag("a", "1.0.0.dev0"))
        plan = _create_plan(
            ws,
            changes=[change],
            params=PlanParams(skip=frozenset({"release", "publish"})),
        )
        # build and bump should still have commands
        assert len(plan.workflow.jobs["uvr-build"].commands) > 0
        assert len(plan.workflow.jobs["uvr-bump"].commands) > 0

    def test_workflow_structure_preserved_with_skips(self) -> None:
        """Even with skips, all 5 jobs exist in the workflow."""
        pkg = _package("a", version="1.0.0.dev0")
        ws = _workspace({"a": pkg})
        change = Change(package=pkg, baseline=_tag("a", "1.0.0.dev0"))
        plan = _create_plan(
            ws,
            changes=[change],
            params=PlanParams(skip=frozenset({"build", "release", "publish", "bump"})),
        )
        assert len(plan.workflow.jobs) == 5


class TestBumpTypeNextVersion:
    """bump_type controls how next_version is computed."""

    def test_default_dev_uses_compute_next_version(self) -> None:
        """BumpType.DEV (default) uses compute_next_version: 1.0.0.dev0 -> 1.0.1.dev0."""
        pkg = _package("a", version="1.0.0.dev0")
        ws = _workspace({"a": pkg})
        change = Change(package=pkg, baseline=_tag("a", "1.0.0.dev0"))
        plan = _create_plan(ws, changes=[change], params=PlanParams())
        assert plan.releases["a"].next_version.raw == "1.0.1.dev0"

    def test_minor_bump_type(self) -> None:
        """BumpType.MINOR: 1.0.0.dev0 -> 1.1.0.dev0."""
        pkg = _package("a", version="1.0.0.dev0")
        ws = _workspace({"a": pkg})
        change = Change(package=pkg, baseline=_tag("a", "1.0.0.dev0"))
        plan = _create_plan(
            ws, changes=[change], params=PlanParams(bump_type=BumpType.MINOR)
        )
        assert plan.releases["a"].next_version.raw == "1.1.0.dev0"

    def test_major_bump_type(self) -> None:
        """BumpType.MAJOR: 1.0.0.dev0 -> 2.0.0.dev0."""
        pkg = _package("a", version="1.0.0.dev0")
        ws = _workspace({"a": pkg})
        change = Change(package=pkg, baseline=_tag("a", "1.0.0.dev0"))
        plan = _create_plan(
            ws, changes=[change], params=PlanParams(bump_type=BumpType.MAJOR)
        )
        assert plan.releases["a"].next_version.raw == "2.0.0.dev0"

    def test_patch_bump_type(self) -> None:
        """BumpType.PATCH: 1.0.0.dev0 -> 1.0.1.dev0."""
        pkg = _package("a", version="1.0.0.dev0")
        ws = _workspace({"a": pkg})
        change = Change(package=pkg, baseline=_tag("a", "1.0.0.dev0"))
        plan = _create_plan(
            ws, changes=[change], params=PlanParams(bump_type=BumpType.PATCH)
        )
        assert plan.releases["a"].next_version.raw == "1.0.1.dev0"

    def test_bump_type_does_not_affect_release_version(self) -> None:
        """release_version is always from compute_release_version, not bump_type."""
        pkg = _package("a", version="1.0.0.dev0")
        ws = _workspace({"a": pkg})
        change = Change(package=pkg, baseline=_tag("a", "1.0.0.dev0"))
        plan = _create_plan(
            ws, changes=[change], params=PlanParams(bump_type=BumpType.MINOR)
        )
        # release_version should still be 1.0.0 (dev stripped)
        assert plan.releases["a"].release_version.raw == "1.0.0"


class TestTargetPropagation:
    """target on PlanParams propagates to Plan."""

    def test_target_defaults_to_local(self) -> None:
        pkg = _package("a", version="1.0.0.dev0")
        ws = _workspace({"a": pkg})
        change = Change(package=pkg, baseline=_tag("a", "1.0.0.dev0"))
        plan = _create_plan(ws, changes=[change], params=PlanParams())
        assert plan.target == "local"

    def test_target_ci_propagates(self) -> None:
        pkg = _package("a", version="1.0.0.dev0")
        ws = _workspace({"a": pkg})
        change = Change(package=pkg, baseline=_tag("a", "1.0.0.dev0"))
        plan = _create_plan(ws, changes=[change], params=PlanParams(target="ci"))
        assert plan.target == "ci"


class TestVersionFixCommands:
    """When version != release_version and target=local, validate job gets a CommandGroup."""

    def test_dev_package_local_gets_version_fix_group(self) -> None:
        """Dev package with target=local: validate job has a CommandGroup."""
        pkg = _package("a", version="1.0.0.dev0")
        ws = _workspace({"a": pkg})
        change = Change(package=pkg, baseline=_tag("a", "1.0.0.dev0"))
        plan = _create_plan(ws, changes=[change], params=PlanParams(target="local"))
        validate_cmds = plan.workflow.jobs["uvr-validate"].commands
        assert len(validate_cmds) == 1
        assert isinstance(validate_cmds[0], CommandGroup)

    def test_version_fix_group_has_set_version(self) -> None:
        """The CommandGroup contains a SetVersionCommand."""
        pkg = _package("a", version="1.0.0.dev0")
        ws = _workspace({"a": pkg})
        change = Change(package=pkg, baseline=_tag("a", "1.0.0.dev0"))
        plan = _create_plan(ws, changes=[change], params=PlanParams(target="local"))
        group = plan.workflow.jobs["uvr-validate"].commands[0]
        assert isinstance(group, CommandGroup)
        set_cmds = [c for c in group.commands if isinstance(c, SetVersionCommand)]
        assert len(set_cmds) == 1
        assert set_cmds[0].version.raw == "1.0.0"

    def test_version_fix_group_has_needs_user_confirmation(self) -> None:
        """The CommandGroup has needs_user_confirmation=True."""
        pkg = _package("a", version="1.0.0.dev0")
        ws = _workspace({"a": pkg})
        change = Change(package=pkg, baseline=_tag("a", "1.0.0.dev0"))
        plan = _create_plan(ws, changes=[change], params=PlanParams(target="local"))
        group = plan.workflow.jobs["uvr-validate"].commands[0]
        assert group.needs_user_confirmation is True

    def test_version_fix_group_includes_git_commit(self) -> None:
        """The CommandGroup contains a git commit ShellCommand."""
        pkg = _package("a", version="1.0.0.dev0")
        ws = _workspace({"a": pkg})
        change = Change(package=pkg, baseline=_tag("a", "1.0.0.dev0"))
        plan = _create_plan(ws, changes=[change], params=PlanParams(target="local"))
        group = plan.workflow.jobs["uvr-validate"].commands[0]
        assert isinstance(group, CommandGroup)
        shell_cmds = [c for c in group.commands if isinstance(c, ShellCommand)]
        commit_cmds = [c for c in shell_cmds if "commit" in c.args]
        assert len(commit_cmds) == 1

    def test_version_fix_group_includes_pin_deps(self) -> None:
        """The CommandGroup includes PinDepsCommand when packages have internal deps."""
        alpha = _package("a", version="1.0.0.dev0")
        beta = _package("b", version="1.0.0.dev0", deps=["a"])
        ws = _workspace({"a": alpha, "b": beta})
        changes = [
            Change(package=alpha, baseline=_tag("a", "1.0.0.dev0")),
            Change(package=beta, baseline=_tag("b", "1.0.0.dev0")),
        ]
        plan = _create_plan(ws, changes=changes, params=PlanParams(target="local"))
        group = plan.workflow.jobs["uvr-validate"].commands[0]
        assert isinstance(group, CommandGroup)
        pin_cmds = [c for c in group.commands if isinstance(c, PinDepsCommand)]
        assert len(pin_cmds) > 0

    def test_no_version_fix_when_versions_match(self) -> None:
        """Clean version (1.0.0) needs no fix commands."""
        pkg = _package("a", version="1.0.0")
        ws = _workspace({"a": pkg})
        change = Change(package=pkg, baseline=_tag("a", "0.9.0"))
        plan = _create_plan(ws, changes=[change], params=PlanParams(target="local"))
        validate_cmds = plan.workflow.jobs["uvr-validate"].commands
        assert len(validate_cmds) == 0

    def test_no_version_fix_for_dev_release(self) -> None:
        """dev_release=True publishes dev versions as-is, no fix needed."""
        pkg = _package("a", version="1.0.0.dev0")
        ws = _workspace({"a": pkg})
        change = Change(package=pkg, baseline=_tag("a", "1.0.0.dev0"))
        plan = _create_plan(
            ws, changes=[change], params=PlanParams(dev_release=True, target="local")
        )
        validate_cmds = plan.workflow.jobs["uvr-validate"].commands
        assert len(validate_cmds) == 0

    def test_ci_target_gets_raw_commands_not_group(self) -> None:
        """CI target gets the same fix commands but not wrapped in a CommandGroup."""
        pkg = _package("a", version="1.0.0.dev0")
        ws = _workspace({"a": pkg})
        change = Change(package=pkg, baseline=_tag("a", "1.0.0.dev0"))
        plan = _create_plan(ws, changes=[change], params=PlanParams(target="ci"))
        validate_cmds = plan.workflow.jobs["uvr-validate"].commands
        assert len(validate_cmds) > 0
        # Not wrapped in a CommandGroup
        assert not isinstance(validate_cmds[0], CommandGroup)
        # Contains SetVersionCommand
        set_cmds = [c for c in validate_cmds if isinstance(c, SetVersionCommand)]
        assert len(set_cmds) == 1

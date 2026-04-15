"""Tests for plan_bump_job: generate bump job based on target and params."""

from __future__ import annotations

from uv_release.commands import CreateTagCommand, SetVersionCommand, ShellCommand
from uv_release.plan.bump import plan_bump_job
from uv_release.types import CommandGroup, Job, Package, PlanParams, Release, Version


def _version(raw: str) -> Version:
    return Version.parse(raw)


def _package(name: str) -> Package:
    return Package(name=name, path=f"packages/{name}", version=_version("1.0.0.dev0"))


def _release(name: str) -> Release:
    return Release(
        package=_package(name),
        release_version=_version("1.0.0"),
        next_version=_version("1.0.1.dev0"),
    )


def _ci_params(**overrides: object) -> PlanParams:
    return PlanParams(target="ci", **overrides)  # type: ignore[arg-type]


class TestBumpVersionCommands:
    """Each release should produce a version bump command."""

    def test_single_package_has_bump(self) -> None:
        releases = {"a": _release("a")}
        job = plan_bump_job(releases, params=_ci_params())
        assert isinstance(job, Job)
        assert job.name == "bump"
        set_cmds = [c for c in job.commands if isinstance(c, SetVersionCommand)]
        assert len(set_cmds) == 1
        assert set_cmds[0].version.raw == "1.0.1.dev0"

    def test_two_packages_have_two_bumps(self) -> None:
        releases = {"a": _release("a"), "b": _release("b")}
        job = plan_bump_job(releases, params=_ci_params())
        set_cmds = [c for c in job.commands if isinstance(c, SetVersionCommand)]
        assert len(set_cmds) == 2


class TestEmptyBump:
    """Empty releases should produce an empty bump job."""

    def test_no_releases_no_commands(self) -> None:
        job = plan_bump_job({}, params=_ci_params())
        assert job.commands == []


class TestCiTarget:
    """CI target: auto-commit, tag baselines, push."""

    def test_ci_has_commit(self) -> None:
        releases = {"a": _release("a")}
        job = plan_bump_job(releases, params=PlanParams(target="ci"))
        shell_cmds = [c for c in job.commands if isinstance(c, ShellCommand)]
        commit_cmds = [c for c in shell_cmds if "commit" in c.args]
        assert len(commit_cmds) == 1

    def test_ci_has_baseline_tags(self) -> None:
        releases = {"a": _release("a")}
        job = plan_bump_job(releases, params=PlanParams(target="ci"))
        tag_cmds = [c for c in job.commands if isinstance(c, CreateTagCommand)]
        assert len(tag_cmds) == 1
        assert "base" in tag_cmds[0].tag_name

    def test_ci_has_push_when_push_true(self) -> None:
        releases = {"a": _release("a")}
        job = plan_bump_job(releases, params=PlanParams(target="ci", push=True))
        shell_cmds = [c for c in job.commands if isinstance(c, ShellCommand)]
        push_cmds = [c for c in shell_cmds if "push" in c.args]
        assert len(push_cmds) == 1

    def test_ci_no_push_when_push_false(self) -> None:
        releases = {"a": _release("a")}
        job = plan_bump_job(releases, params=PlanParams(target="ci", push=False))
        shell_cmds = [c for c in job.commands if isinstance(c, ShellCommand)]
        push_cmds = [c for c in shell_cmds if "push" in c.args]
        assert len(push_cmds) == 0

    def test_ci_commands_have_no_confirmation(self) -> None:
        releases = {"a": _release("a")}
        job = plan_bump_job(releases, params=PlanParams(target="ci"))
        for cmd in job.commands:
            assert cmd.needs_user_confirmation is False


class TestLocalTarget:
    """Local target: sync lockfile, commit with needs_user_confirmation."""

    def test_local_wraps_all_in_command_group(self) -> None:
        """Local target wraps everything in a single CommandGroup."""
        releases = {"a": _release("a")}
        job = plan_bump_job(releases, params=PlanParams(target="local"))
        assert len(job.commands) == 1
        assert isinstance(job.commands[0], CommandGroup)
        assert job.commands[0].needs_user_confirmation is True

    def test_local_group_contains_same_commands_as_ci(self) -> None:
        """The inner commands of the local group match CI commands."""
        releases = {"a": _release("a")}
        ci_job = plan_bump_job(releases, params=_ci_params())
        local_job = plan_bump_job(releases, params=PlanParams(target="local"))
        group = local_job.commands[0]
        assert isinstance(group, CommandGroup)
        # Same number of inner commands as CI top-level commands
        assert len(group.commands) == len(ci_job.commands)


class TestPinFalse:
    """pin=False skips dependency pinning."""

    def test_pin_false_skips_pin_commands(self) -> None:
        from uv_release.commands import PinDepsCommand

        alpha = Package(
            name="a", path="packages/a", version=_version("1.0.0.dev0"), deps=[]
        )
        beta = Package(
            name="b", path="packages/b", version=_version("1.0.0.dev0"), deps=["a"]
        )
        releases = {
            "a": Release(
                package=alpha,
                release_version=_version("1.0.0"),
                next_version=_version("1.0.1.dev0"),
            ),
            "b": Release(
                package=beta,
                release_version=_version("1.0.0"),
                next_version=_version("1.0.1.dev0"),
            ),
        }
        job = plan_bump_job(releases, params=PlanParams(pin=False))
        pin_cmds = [c for c in job.commands if isinstance(c, PinDepsCommand)]
        assert len(pin_cmds) == 0

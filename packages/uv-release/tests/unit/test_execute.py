"""Tests for execute_plan and execute_job."""

from __future__ import annotations

from typing import Literal

import pytest

from uv_release.commands import ShellCommand
from uv_release.execute import execute_job, execute_plan
from uv_release.types import (
    Config,
    Hooks,
    Job,
    Plan,
    Publishing,
    Workflow,
    Workspace,
)


def _cmd(label: str, *, check: bool = True, fail: bool = False) -> ShellCommand:
    return ShellCommand(
        label=label,
        check=check,
        args=["false"] if fail else ["true"],
    )


def _make_workspace() -> Workspace:
    return Workspace(
        packages={},
        config=Config(uvr_version="0.1.0"),
        runners={},
        publishing=Publishing(),
    )


def _make_plan(
    jobs: dict[str, Job] | None = None, target: Literal["ci", "local"] = "local"
) -> Plan:
    return Plan(
        workspace=_make_workspace(),
        releases={},
        workflow=Workflow(jobs=jobs or {}),
        target=target,
    )


class TestExecuteJob:
    def test_executes_commands_in_order(self) -> None:
        """Commands in a job execute sequentially."""
        cmd1 = _cmd("first")
        cmd2 = _cmd("second")
        jobs = {
            "uvr-validate": Job(name="uvr-validate", needs=[], commands=[cmd1, cmd2]),
        }
        plan = _make_plan(jobs)
        execute_job(plan, "uvr-validate")  # both succeed, no error

    def test_stops_on_failed_check_command(self) -> None:
        """When check=True and returncode != 0, stop execution."""
        cmd1 = _cmd("fail", fail=True)
        jobs = {
            "uvr-validate": Job(
                name="uvr-validate",
                needs=[],
                commands=[cmd1],
            ),
        }
        plan = _make_plan(jobs)
        with pytest.raises(SystemExit):
            execute_job(plan, "uvr-validate")

    def test_continues_on_failed_nocheck_command(self) -> None:
        """When check=False and returncode != 0, continue."""
        cmd1 = _cmd("soft-fail", check=False, fail=True)
        cmd2 = _cmd("runs")
        jobs = {
            "uvr-validate": Job(name="uvr-validate", needs=[], commands=[cmd1, cmd2]),
        }
        plan = _make_plan(jobs)
        execute_job(plan, "uvr-validate")  # should not raise

    def test_empty_job_is_noop(self) -> None:
        """Job with no commands is a no-op."""
        jobs = {
            "uvr-validate": Job(name="uvr-validate", needs=[], commands=[]),
        }
        plan = _make_plan(jobs)
        execute_job(plan, "uvr-validate")  # should not raise


class TestExecutePlan:
    def test_respects_dag_order(self) -> None:
        """execute_plan runs jobs in dependency order (no error means correct DAG)."""
        jobs = {
            "uvr-validate": Job(
                name="uvr-validate",
                needs=[],
                commands=[_cmd("validate")],
            ),
            "uvr-build": Job(
                name="uvr-build",
                needs=["uvr-validate"],
                commands=[_cmd("build")],
            ),
            "uvr-release": Job(
                name="uvr-release",
                needs=["uvr-build"],
                commands=[_cmd("release")],
            ),
            "uvr-publish": Job(
                name="uvr-publish",
                needs=["uvr-release"],
                commands=[_cmd("publish")],
            ),
            "uvr-bump": Job(
                name="uvr-bump",
                needs=["uvr-publish"],
                commands=[_cmd("bump")],
            ),
        }
        plan = _make_plan(jobs)
        execute_plan(plan)


class TestHooksSentinel:
    """The _unset sentinel distinguishes 'not passed' from 'explicitly None'."""

    def test_explicit_none_skips_hooks(self) -> None:
        """Passing hooks=None disables hooks even if a job declares them."""
        jobs = {
            "uvr-build": Job(
                name="uvr-build",
                commands=[_cmd("build")],
                pre_hook="pre_build",
                post_hook="post_build",
            ),
        }
        plan = _make_plan(jobs)
        # hooks=None means no hooks, should not attempt to call any
        execute_job(plan, "uvr-build", hooks=None)

    def test_explicit_hooks_are_called(self) -> None:
        """Passing a Hooks instance calls the declared hooks."""
        called: list[str] = []

        class _TrackingHooks(Hooks):
            def pre_build(self, plan: Plan, runner: list[str] | None = None) -> None:
                called.append("pre_build")

            def post_build(self, plan: Plan, runner: list[str] | None = None) -> None:
                called.append("post_build")

        jobs = {
            "uvr-build": Job(
                name="uvr-build",
                commands=[_cmd("build")],
                pre_hook="pre_build",
                post_hook="post_build",
            ),
        }
        plan = _make_plan(jobs)
        execute_job(plan, "uvr-build", hooks=_TrackingHooks())
        assert called == ["pre_build", "post_build"]

    def test_no_hooks_on_job_skips_even_with_hooks_instance(self) -> None:
        """Jobs without pre_hook/post_hook don't call hooks even if provided."""
        called: list[str] = []

        class _TrackingHooks(Hooks):
            def pre_build(self, plan: Plan, runner: list[str] | None = None) -> None:
                called.append("pre_build")

        jobs = {
            "uvr-validate": Job(
                name="uvr-validate",
                commands=[_cmd("validate")],
            ),
        }
        plan = _make_plan(jobs)
        execute_job(plan, "uvr-validate", hooks=_TrackingHooks())
        assert called == []


class TestNeedsUserConfirmation:
    """Executor prompts the user when a command has needs_user_confirmation=True."""

    def test_confirmation_accepted_runs_command(self) -> None:
        """When user confirms, the command executes."""
        cmd = ShellCommand(
            label="set version", args=["true"], needs_user_confirmation=True
        )
        jobs = {"uvr-validate": Job(name="uvr-validate", commands=[cmd])}
        plan = _make_plan(jobs)
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("builtins.input", lambda _: "y")
            execute_job(plan, "uvr-validate", hooks=None)

    def test_confirmation_declined_stops_execution(self) -> None:
        """When user declines, execution stops."""
        cmd = ShellCommand(
            label="set version", args=["true"], needs_user_confirmation=True
        )
        jobs = {"uvr-validate": Job(name="uvr-validate", commands=[cmd])}
        plan = _make_plan(jobs)
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("builtins.input", lambda _: "n")
            with pytest.raises(SystemExit):
                execute_job(plan, "uvr-validate", hooks=None)

    def test_no_confirmation_flag_runs_without_prompt(self) -> None:
        """Commands without needs_user_confirmation run without prompting."""
        cmd = ShellCommand(
            label="regular", args=["true"], needs_user_confirmation=False
        )
        jobs = {"uvr-validate": Job(name="uvr-validate", commands=[cmd])}
        plan = _make_plan(jobs)
        execute_job(plan, "uvr-validate", hooks=None)

    def test_command_group_prompts_once_for_all_inner(self) -> None:
        """CommandGroup prompts once, then runs all inner commands."""
        from uv_release.types import CommandGroup

        group = CommandGroup(
            label="Set versions and commit",
            needs_user_confirmation=True,
            commands=[_cmd("step 1"), _cmd("step 2")],
        )
        jobs = {"uvr-validate": Job(name="uvr-validate", commands=[group])}
        plan = _make_plan(jobs)
        prompt_count = 0

        def _mock_input(prompt: str) -> str:
            nonlocal prompt_count
            prompt_count += 1
            return "y"

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("builtins.input", _mock_input)
            execute_job(plan, "uvr-validate", hooks=None)
        assert prompt_count == 1

    def test_keyboard_interrupt_during_confirmation(self) -> None:
        """KeyboardInterrupt during confirmation exits."""
        cmd = ShellCommand(label="confirm", args=["true"], needs_user_confirmation=True)
        jobs = {"uvr-validate": Job(name="uvr-validate", commands=[cmd])}
        plan = _make_plan(jobs)
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "builtins.input", lambda _: (_ for _ in ()).throw(KeyboardInterrupt)
            )
            with pytest.raises(SystemExit):
                execute_job(plan, "uvr-validate", hooks=None)


class TestExecuteJobEdgeCases:
    def test_missing_job_exits_with_error(self) -> None:
        """execute_job with a non-existent job name exits with an error."""
        plan = _make_plan({})
        with pytest.raises(SystemExit):
            execute_job(plan, "nonexistent", hooks=None)

    def test_missing_hook_method_raises(self) -> None:
        """Calling a hook method that doesn't exist raises AttributeError."""
        jobs = {
            "uvr-build": Job(
                name="uvr-build",
                commands=[],
                pre_hook="nonexistent_hook",
            ),
        }
        plan = _make_plan(jobs)
        with pytest.raises(AttributeError, match="nonexistent_hook"):
            execute_job(plan, "uvr-build", hooks=Hooks())

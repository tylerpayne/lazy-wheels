"""Tests for execute_plan, execute_job, and find_job."""

from __future__ import annotations

import pytest

from uv_release.commands import ShellCommand
from uv_release.execute import execute_job, execute_plan, find_job
from uv_release.types import (
    Command,
    Hooks,
    Job,
    Plan,
)


def _cmd(label: str, *, check: bool = True, fail: bool = False) -> ShellCommand:
    return ShellCommand(
        label=label,
        check=check,
        args=["false"] if fail else ["true"],
    )


def _job(
    name: str = "test", commands: list[Command] | None = None, **kwargs: object
) -> Job:
    return Job(name=name, commands=commands or [], **kwargs)  # type: ignore[arg-type]


def _plan(jobs: list[Job] | None = None) -> Plan:
    return Plan(jobs=jobs or [])


class TestExecuteJob:
    def test_executes_commands_in_order(self) -> None:
        """Commands in a job execute sequentially."""
        job = _job("test", [_cmd("first"), _cmd("second")])
        execute_job(job, hooks=None)

    def test_stops_on_failed_check_command(self) -> None:
        """When check=True and returncode != 0, stop execution."""
        job = _job("test", [_cmd("fail", fail=True)])
        with pytest.raises(SystemExit):
            execute_job(job, hooks=None)

    def test_continues_on_failed_nocheck_command(self) -> None:
        """When check=False and returncode != 0, continue."""
        job = _job("test", [_cmd("soft-fail", check=False, fail=True), _cmd("runs")])
        execute_job(job, hooks=None)

    def test_empty_job_is_noop(self) -> None:
        """Job with no commands is a no-op."""
        job = _job("test", [])
        execute_job(job, hooks=None)


class TestExecutePlan:
    def test_runs_all_jobs_in_order(self) -> None:
        """execute_plan runs jobs in list order."""
        plan = _plan(
            [
                _job("validate", [_cmd("validate")]),
                _job("build", [_cmd("build")]),
                _job("release", [_cmd("release")]),
            ]
        )
        execute_plan(plan, hooks=None)


class TestFindJob:
    def test_finds_existing_job(self) -> None:
        plan = _plan([_job("build"), _job("release")])
        found = find_job(plan, "build")
        assert found.name == "build"

    def test_missing_job_exits(self) -> None:
        plan = _plan([_job("build")])
        with pytest.raises(SystemExit):
            find_job(plan, "nonexistent")


class TestHooksSentinel:
    """The _unset sentinel distinguishes 'not passed' from 'explicitly None'."""

    def test_explicit_none_skips_hooks(self) -> None:
        """Passing hooks=None disables hooks even if a job declares them."""
        job = _job(
            "build", [_cmd("build")], pre_hook="pre_build", post_hook="post_build"
        )
        execute_job(job, hooks=None)

    def test_explicit_hooks_are_called(self) -> None:
        """Passing a Hooks instance calls the declared hooks."""
        called: list[str] = []

        class _TrackingHooks(Hooks):
            def pre_build(self) -> None:
                called.append("pre_build")

            def post_build(self) -> None:
                called.append("post_build")

        job = _job(
            "build", [_cmd("build")], pre_hook="pre_build", post_hook="post_build"
        )
        execute_job(job, hooks=_TrackingHooks())
        assert called == ["pre_build", "post_build"]

    def test_no_hooks_on_job_skips_even_with_hooks_instance(self) -> None:
        """Jobs without pre_hook/post_hook don't call hooks even if provided."""
        called: list[str] = []

        class _TrackingHooks(Hooks):
            def pre_build(self) -> None:
                called.append("pre_build")

        job = _job("validate", [_cmd("validate")])
        execute_job(job, hooks=_TrackingHooks())
        assert called == []


class TestNeedsUserConfirmation:
    """Executor prompts the user when a command has needs_user_confirmation=True."""

    def test_confirmation_accepted_runs_command(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cmd = ShellCommand(
            label="set version", args=["true"], needs_user_confirmation=True
        )
        job = _job("validate", [cmd])
        monkeypatch.setattr("builtins.input", lambda _: "y")
        execute_job(job, hooks=None)

    def test_confirmation_declined_stops_execution(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cmd = ShellCommand(
            label="set version", args=["true"], needs_user_confirmation=True
        )
        job = _job("validate", [cmd])
        monkeypatch.setattr("builtins.input", lambda _: "n")
        with pytest.raises(SystemExit):
            execute_job(job, hooks=None)

    def test_no_confirmation_flag_runs_without_prompt(self) -> None:
        cmd = ShellCommand(
            label="regular", args=["true"], needs_user_confirmation=False
        )
        job = _job("validate", [cmd])
        execute_job(job, hooks=None)

    def test_command_group_prompts_once_for_all_inner(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from uv_release.types import CommandGroup

        group = CommandGroup(
            label="Set versions and commit",
            needs_user_confirmation=True,
            commands=[_cmd("step 1"), _cmd("step 2")],
        )
        job = _job("validate", [group])
        prompt_count = 0

        def _mock_input(prompt: str) -> str:
            nonlocal prompt_count
            prompt_count += 1
            return "y"

        monkeypatch.setattr("builtins.input", _mock_input)
        execute_job(job, hooks=None)
        assert prompt_count == 1

    def test_keyboard_interrupt_during_confirmation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cmd = ShellCommand(label="confirm", args=["true"], needs_user_confirmation=True)
        job = _job("validate", [cmd])
        monkeypatch.setattr(
            "builtins.input", lambda _: (_ for _ in ()).throw(KeyboardInterrupt)
        )
        with pytest.raises(SystemExit):
            execute_job(job, hooks=None)


class TestMissingHookMethod:
    def test_missing_hook_method_raises(self) -> None:
        job = _job("build", [], pre_hook="nonexistent_hook")
        with pytest.raises(AttributeError, match="nonexistent_hook"):
            execute_job(job, hooks=Hooks())

"""Tests for create_workflow: assemble a Workflow with DAG edges and execution order."""

from __future__ import annotations

from uv_release.commands import ShellCommand
from uv_release.plan.workflow import create_workflow
from uv_release.types import Command, Job, Workflow


def _cmd(label: str) -> Command:
    return ShellCommand(label=label, args=["echo", label])


def _job(
    name: str,
    needs: list[str] | None = None,
    commands: list[Command] | None = None,
) -> Job:
    return Job(name=name, needs=needs or [], commands=commands or [])


class TestWorkflowJobCount:
    def test_five_jobs_present(self) -> None:
        wf = create_workflow(
            validate_job=_job("validate"),
            build_job=_job("build"),
            release_job=_job("release"),
            publish_job=_job("publish"),
            bump_job=_job("bump"),
        )
        assert isinstance(wf, Workflow)
        assert len(wf.jobs) == 5
        assert set(wf.jobs.keys()) == {
            "uvr-validate",
            "uvr-build",
            "uvr-release",
            "uvr-publish",
            "uvr-bump",
        }


class TestWorkflowDAG:
    def test_validate_has_no_needs(self) -> None:
        wf = create_workflow(
            validate_job=_job("validate"),
            build_job=_job("build"),
            release_job=_job("release"),
            publish_job=_job("publish"),
            bump_job=_job("bump"),
        )
        assert wf.jobs["uvr-validate"].needs == []

    def test_build_needs_validate(self) -> None:
        wf = create_workflow(
            validate_job=_job("validate"),
            build_job=_job("build"),
            release_job=_job("release"),
            publish_job=_job("publish"),
            bump_job=_job("bump"),
        )
        assert "uvr-validate" in wf.jobs["uvr-build"].needs

    def test_release_needs_build(self) -> None:
        wf = create_workflow(
            validate_job=_job("validate"),
            build_job=_job("build"),
            release_job=_job("release"),
            publish_job=_job("publish"),
            bump_job=_job("bump"),
        )
        assert "uvr-build" in wf.jobs["uvr-release"].needs

    def test_publish_needs_release(self) -> None:
        wf = create_workflow(
            validate_job=_job("validate"),
            build_job=_job("build"),
            release_job=_job("release"),
            publish_job=_job("publish"),
            bump_job=_job("bump"),
        )
        assert "uvr-release" in wf.jobs["uvr-publish"].needs

    def test_bump_needs_publish(self) -> None:
        wf = create_workflow(
            validate_job=_job("validate"),
            build_job=_job("build"),
            release_job=_job("release"),
            publish_job=_job("publish"),
            bump_job=_job("bump"),
        )
        assert "uvr-publish" in wf.jobs["uvr-bump"].needs


class TestWorkflowJobOrder:
    def test_job_order_is_topological(self) -> None:
        wf = create_workflow(
            validate_job=_job("validate"),
            build_job=_job("build"),
            release_job=_job("release"),
            publish_job=_job("publish"),
            bump_job=_job("bump"),
        )
        assert wf.job_order == [
            "uvr-validate",
            "uvr-build",
            "uvr-release",
            "uvr-publish",
            "uvr-bump",
        ]


class TestWorkflowPreservesCommands:
    def test_commands_preserved(self) -> None:
        cmds = {
            name: [_cmd(name)]
            for name in ("validate", "build", "release", "publish", "bump")
        }
        wf = create_workflow(
            validate_job=_job("validate", commands=cmds["validate"]),
            build_job=_job("build", commands=cmds["build"]),
            release_job=_job("release", commands=cmds["release"]),
            publish_job=_job("publish", commands=cmds["publish"]),
            bump_job=_job("bump", commands=cmds["bump"]),
        )
        for job_key, label in [
            ("uvr-validate", "validate"),
            ("uvr-build", "build"),
            ("uvr-release", "release"),
            ("uvr-publish", "publish"),
            ("uvr-bump", "bump"),
        ]:
            assert len(wf.jobs[job_key].commands) == 1
            assert wf.jobs[job_key].commands[0].label == label

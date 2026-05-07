"""uvr release: plan and execute a full release."""

from __future__ import annotations

from diny import inject, resolve

from .. import ui
from ..commands import (
    BuildCommand,
    CreateReleaseCommand,
    DispatchWorkflowCommand,
    DownloadWheelsCommand,
    PublishToIndexCommand,
)
from ..dependencies.params.release_target import ReleaseTarget
from ..dependencies.release.plan import Plan
from ..dependencies.release.release_bump_versions import ReleaseBumpVersions
from ..dependencies.release.release_notes import ReleaseNotes
from ..dependencies.release.release_versions import ReleaseVersions
from ..dependencies.shared.baseline_tags import BaselineTags
from ..dependencies.shared.hooks import Hooks
from ..dependencies.shared.workflow_state import WorkflowState
from ..dependencies.shared.workspace_packages import WorkspacePackages
from ..execute import execute_job, execute_plan
from ..types.job import Job
from ._cli import Params


@inject
def cmd_release(
    plan: Plan,
    params: Params,
    release_notes: ReleaseNotes,
    release_versions: ReleaseVersions,
    bump_versions: ReleaseBumpVersions,
    baseline_tags: BaselineTags,
    hooks: Hooks,
    workspace: WorkspacePackages,
    workflow_state: WorkflowState,
) -> None:
    # --plan: execute a pre-serialized plan from CI.
    if params.plan_json:
        deserialized = Plan.model_validate_json(params.plan_json)
        execute_plan(deserialized, hooks)
        return

    plan = hooks.post_plan(workspace.root, "release", plan)

    # --json: print the plan as JSON and exit. Byte-exact, no Rich.
    if params.json_output:
        print(plan.model_dump_json(indent=2))
        return

    if not any(j.commands for j in plan.jobs):
        ui.console.print("Nothing changed since last release.")
        return

    # Packages table.
    ui.console.print()
    ui.section("Packages")
    rows: list[list[str]] = []
    for name in sorted(release_versions.items):
        pkg = workspace.items[name]
        rel_ver = release_versions.items[name]
        next_ver = bump_versions.items.get(name)
        baseline = baseline_tags.items.get(name)
        rows.append(
            [
                f"[uvr.accent]{name}[/]",
                pkg.version.raw,
                f"[b]{rel_ver.raw}[/]",
                next_ver.raw if next_ver else "",
                baseline.raw if baseline else "[uvr.dim](initial)[/]",
            ]
        )
    ui.print_table(["package", "current", "release", "next", "diff from"], rows)

    ui.console.print()
    ui.section("Pipeline")
    _print_jobs(plan, workflow_state)

    if release_notes.items:
        ui.console.print()
        ui.section("Release notes")
        for name, notes in sorted(release_notes.items.items()):
            ui.console.print(f"  [uvr.accent]{name}[/]:")
            for line in notes.splitlines()[:5]:
                ui.console.print(f"    {line}")

    if params.dry_run:
        return

    if not params.yes:
        ui.console.print()
        try:
            if not ui.confirm("Proceed?"):
                return
        except (EOFError, KeyboardInterrupt):
            print()
            return

    # --where ci: dispatch to GitHub Actions.
    target = resolve(ReleaseTarget)
    if target.value == "ci":
        plan_json = plan.model_dump_json()
        dispatch_job = Job(
            name="dispatch",
            commands=[
                DispatchWorkflowCommand(
                    label="Dispatch to GitHub Actions", plan_json=plan_json
                )
            ],
        )  # type: ignore[arg-type]
        execute_job(dispatch_job, hooks)
        return

    execute_plan(plan, hooks)


def _print_jobs(plan: Plan, workflow_state: WorkflowState) -> None:
    """Print jobs in workflow YAML order, merging plan data with workflow jobs."""
    plan_jobs = {j.name: j for j in plan.jobs}

    if workflow_state.job_names:
        printed: set[str] = set()
        for name in workflow_state.job_names:
            _print_job_status(name, plan_jobs.get(name), plan)
            printed.add(name)
        # Any plan jobs missing from the workflow (shouldn't happen, but safe).
        for name, job in plan_jobs.items():
            if name not in printed:
                _print_job_status(name, job, plan)
    else:
        for job in plan.jobs:
            _print_job_status(job.name, job, plan)


def _print_job_status(name: str, job: Job | None, plan: Plan) -> None:
    if name in plan.skip:
        ui.console.print(f"  {name}: [uvr.dim](skip)[/]")
        return
    ui.console.print(f"  [uvr.value]{name}[/]")
    if job and job.commands:
        _print_job_detail(job, plan)


def _print_job_detail(job: Job, plan: Plan) -> None:
    if job.name == "build":
        all_builds = [c for c in job.commands if isinstance(c, BuildCommand)]
        downloaded_deps = [
            c for c in job.commands if isinstance(c, DownloadWheelsCommand)
        ]
        for runner in plan.build_matrix:
            label = ", ".join(runner)
            runner_builds = [b for b in all_builds if b.runs_on(runner)]
            targets = [b for b in runner_builds if b.is_target_on(runner)]
            build_deps = [b for b in runner_builds if not b.is_target_on(runner)]
            ui.console.print(f"    {label}")
            if targets:
                ui.console.print("      [uvr.dim]targets:[/]")
                for t in targets:
                    name = t.label.removeprefix("Build ")
                    ui.console.print(f"        [uvr.accent]{name}[/]")
            if build_deps or downloaded_deps:
                ui.console.print("      [uvr.dim]deps:[/]")
                for b in build_deps:
                    name = b.label.removeprefix("Build ")
                    ui.console.print(f"        {name} [uvr.dim](build)[/]")
                for d in downloaded_deps:
                    ui.console.print(f"        {d.tag_name}")
    elif job.name == "release":
        releases = [c for c in job.commands if isinstance(c, CreateReleaseCommand)]
        for rel in releases:
            ui.console.print(f"    [uvr.accent]{rel.title}[/]")
    elif job.name == "publish":
        publishes = [c for c in job.commands if isinstance(c, PublishToIndexCommand)]
        for pub in publishes:
            ui.console.print(f"    [uvr.accent]{pub.package_name}[/]")

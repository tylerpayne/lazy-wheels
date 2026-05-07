"""Execute jobs and plans."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from .types.job import Job
from .dependencies.release.plan import Plan
from .ui import error as ui_error, section

if TYPE_CHECKING:
    from .dependencies.shared.hooks import Hooks


def execute_plan(plan: Plan, hooks: Hooks | None = None) -> None:
    """Execute all jobs in the plan, skipping any in plan.skip."""
    for job in plan.jobs:
        if job.name in plan.skip:
            continue
        execute_job(job, hooks)


def execute_job(job: Job, hooks: Hooks | None = None) -> None:
    """Execute every command in a single job sequentially."""
    if not job.commands:
        return

    # Per-job lifecycle hooks (pre_build, post_build, etc.)
    pre_hook = getattr(hooks, f"pre_{job.name}", None) if hooks else None
    post_hook = getattr(hooks, f"post_{job.name}", None) if hooks else None

    if pre_hook:
        pre_hook()

    print()
    section(job.name)
    for cmd in job.commands:
        if hooks:
            hooks.pre_command(job.name, cmd)
        returncode = cmd.execute()
        if hooks:
            hooks.post_command(job.name, cmd, returncode)
        if cmd.check and returncode != 0:
            ui_error(f"Command failed with exit code {returncode}")
            sys.exit(returncode)

    if post_hook:
        post_hook()

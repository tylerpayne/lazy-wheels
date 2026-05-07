"""uvr jobs: execute a single job from a serialized plan (used by CI)."""

from __future__ import annotations

import os
import sys

from diny import inject

from .. import ui
from ..dependencies.release.plan import Plan
from ..dependencies.shared.hooks import Hooks
from ..execute import execute_job
from ._cli import ParsedArgs


@inject
def cmd_jobs(args: ParsedArgs, hooks: Hooks) -> None:
    job_name = args.values.get("job_name", "")
    if not job_name:
        ui.error("Usage: uvr jobs <job_name>")
        sys.exit(1)

    plan_json = os.environ.get("UVR_PLAN", "")
    if not plan_json:
        ui.error("UVR_PLAN environment variable not set.")
        sys.exit(1)

    plan = Plan.model_validate_json(plan_json)

    job = None
    for j in plan.jobs:
        if j.name == job_name:
            job = j
            break

    if job is None:
        available = [j.name for j in plan.jobs]
        ui.error(
            f"Job {job_name!r} not found.",
            detail={"available": ", ".join(available)},
        )
        sys.exit(1)

    if job.name in plan.skip:
        ui.console.print(f"Job [uvr.value]{job_name}[/] is skipped.")
        return

    execute_job(job, hooks)

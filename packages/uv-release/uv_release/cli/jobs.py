"""The hidden ``uvr jobs <JOB>`` command. Used by CI workflows."""

from __future__ import annotations

import argparse
import os
import sys

from ..execute import execute_job
from ..parse.hooks import parse_hooks
from ..types import Plan


def cmd_jobs(args: argparse.Namespace) -> None:
    """Load plan from UVR_PLAN env var and execute a single job."""
    job_name = args.job_name

    plan_json = os.environ.get("UVR_PLAN", "")
    if not plan_json:
        print("ERROR: UVR_PLAN environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    plan = Plan.model_validate_json(plan_json)
    hooks = parse_hooks()

    execute_job(plan, job_name, hooks=hooks)

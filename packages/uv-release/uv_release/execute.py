"""Execute a Plan's jobs."""

from __future__ import annotations

import sys

from .states.hooks import parse_hooks
from .types import Hooks, Job, Plan, Unset, UNSET


def execute_plan(plan: Plan, *, hooks: Hooks | None | Unset = UNSET) -> None:
    """Execute all jobs in order."""
    if isinstance(hooks, Unset):
        hooks = parse_hooks()
    for job in plan.jobs:
        execute_job(job, hooks=hooks)


def execute_job(
    job: Job,
    *,
    hooks: Hooks | None | Unset = UNSET,
) -> None:
    """Execute a single job's commands with pre/post hooks."""
    if isinstance(hooks, Unset):
        hooks = parse_hooks()

    # Pre-hook
    if hooks is not None and job.pre_hook:
        _call_hook(hooks, job.pre_hook)

    # Commands
    for cmd in job.commands:
        if cmd.needs_user_confirmation:
            if cmd.label:
                print(f"  {cmd.label}")
            try:
                answer = input("  Execute? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                sys.exit(1)
            if answer != "y":
                sys.exit(1)

        if cmd.label and not cmd.needs_user_confirmation:
            print(f"  {cmd.label}")
        returncode = cmd.execute()
        if cmd.check and returncode != 0:
            print(
                f"ERROR: {cmd.label or job.name} failed (exit {returncode})",
                file=sys.stderr,
            )
            sys.exit(1)

    # Post-hook
    if hooks is not None and job.post_hook:
        _call_hook(hooks, job.post_hook)


def find_job(plan: Plan, name: str) -> Job:
    """Find a job by name in the plan. Exits with error if not found."""
    for job in plan.jobs:
        if job.name == name:
            return job
    available = ", ".join(j.name for j in plan.jobs)
    print(
        f"ERROR: Job '{name}' not found in plan. Available jobs: {available}",
        file=sys.stderr,
    )
    sys.exit(1)


def _call_hook(hooks: Hooks, method_name: str) -> None:
    if not hasattr(hooks, method_name):
        msg = f"Hooks class {type(hooks).__name__} is missing method '{method_name}'"
        raise AttributeError(msg)
    getattr(hooks, method_name)()

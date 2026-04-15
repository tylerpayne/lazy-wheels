"""Execute a Plan's workflow."""

from __future__ import annotations

import sys
from enum import Enum

from .parse.hooks import parse_hooks
from .types import Hooks, Plan


class _Unset(Enum):
    UNSET = "UNSET"


_unset = _Unset.UNSET


def execute_plan(plan: Plan, *, hooks: Hooks | None | _Unset = _unset) -> None:
    """Execute all jobs in the pre-computed order."""
    if hooks is _unset:
        hooks = parse_hooks()
    for job_name in plan.workflow.job_order:
        execute_job(plan, job_name, hooks=hooks)


def execute_job(
    plan: Plan,
    job_name: str,
    *,
    hooks: Hooks | None | _Unset = _unset,
) -> None:
    """Execute a single job's commands with pre/post hooks."""
    if hooks is _unset:
        hooks = parse_hooks()
    job = plan.workflow.jobs.get(job_name)
    if job is None:
        return

    # Pre-hook
    if hooks is not None and job.pre_hook:
        _call_hook(hooks, job.pre_hook, plan)

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
                f"ERROR: {cmd.label or job_name} failed (exit {returncode})",
                file=sys.stderr,
            )
            sys.exit(1)

    # Post-hook
    if hooks is not None and job.post_hook:
        _call_hook(hooks, job.post_hook, plan)


def _call_hook(hooks: Hooks, method_name: str, plan: Plan) -> None:
    if not hasattr(hooks, method_name):
        msg = f"Hooks class {type(hooks).__name__} is missing method '{method_name}'"
        raise AttributeError(msg)
    getattr(hooks, method_name)(plan)

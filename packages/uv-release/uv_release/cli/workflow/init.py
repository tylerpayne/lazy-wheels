"""The ``uvr workflow init`` and ``uvr workflow init --upgrade`` commands."""

from __future__ import annotations

import argparse

from .._args import CommandArgs, compute_plan_or_exit
from ...intents.upgrade_workflow import UpgradeWorkflowIntent
from ...execute import execute_plan


class WorkflowInitArgs(CommandArgs):
    """Typed arguments for ``uvr workflow init``."""

    workflow_dir: str = ".github/workflows"
    force: bool = False
    upgrade: bool = False
    base_only: bool = False
    editor: str | None = None


def cmd_init_dispatch(args: argparse.Namespace) -> None:
    """Route to init or upgrade based on --upgrade flag."""
    if getattr(args, "upgrade", False):
        cmd_upgrade(args)
    else:
        cmd_init(args)


def cmd_init(args: argparse.Namespace) -> None:
    """Scaffold the GitHub Actions workflow into your repo."""
    parsed = WorkflowInitArgs.from_namespace(args)

    intent = UpgradeWorkflowIntent(
        workflow_dir=parsed.workflow_dir,
        force=parsed.force,
        upgrade=False,
        base_only=parsed.base_only,
        editor=parsed.editor,
    )

    plan = compute_plan_or_exit(intent)

    execute_plan(plan, hooks=None)

    version = plan.metadata.uvr_state.uvr_version if plan.metadata.uvr_state else ""
    if parsed.base_only:
        print(f"OK: Wrote merge base (uvr v{version})")
    else:
        rel_dest = f"{parsed.workflow_dir}/release.yml"
        print(f"OK: Wrote workflow to {rel_dest} (uvr v{version})")
        print()
        print("Next steps:")
        print("  1. Review and commit the workflow file")
        print("  2. Run `uvr workflow validate` to check your changes")
        print("  3. Trigger a release with `uvr release`")


def cmd_upgrade(args: argparse.Namespace) -> None:
    """Upgrade an existing release.yml via three-way merge."""
    parsed = WorkflowInitArgs.from_namespace(args)

    intent = UpgradeWorkflowIntent(
        workflow_dir=parsed.workflow_dir,
        force=False,
        upgrade=True,
        base_only=False,
        editor=parsed.editor,
    )

    plan = compute_plan_or_exit(intent)

    execute_plan(plan, hooks=None)

    version = plan.metadata.uvr_state.uvr_version if plan.metadata.uvr_state else ""
    print(f"OK: Upgrade complete (uvr v{version})")

"""The ``uvr status`` command."""

from __future__ import annotations

import argparse

from ._args import CommandArgs
from .display import print_status_table
from ..plan.planner import create_plan
from ..types import PlanParams


class StatusArgs(CommandArgs):
    """Typed arguments for ``uvr status``."""

    rebuild_all: bool = False
    rebuild: list[str] | None = None


def cmd_status(args: argparse.Namespace) -> None:
    """Show workspace package status. Read-only, never modifies disk."""
    parsed = StatusArgs.from_namespace(args)

    params = PlanParams(
        rebuild_all=parsed.rebuild_all,
        rebuild=frozenset(parsed.rebuild or []),
        dev_release=True,
        skip=frozenset({"build", "release", "publish", "bump"}),
        require_clean_worktree=False,
    )
    plan = create_plan(params)

    if not plan.releases and not plan.workspace.packages:
        print("No packages found.")
        return

    print()
    print("Packages")
    print("--------")
    print_status_table(plan, show_release_version=False)

    if not plan.releases:
        print()
        print("Nothing changed since last release. Use --rebuild-all to force.")

    print()

"""The ``uvr build`` command."""

from __future__ import annotations

import argparse
import sys

from ._args import CommandArgs
from ..intents.build import BuildIntent
from ..planner import compute_plan
from ..execute import execute_plan


class BuildArgs(CommandArgs):
    """Typed arguments for ``uvr build``."""

    rebuild_all: bool = False
    packages: list[str] | None = None


def cmd_build(args: argparse.Namespace) -> None:
    """Build changed workspace packages locally."""
    parsed = BuildArgs.from_namespace(args)

    intent = BuildIntent(
        rebuild_all=parsed.rebuild_all,
        restrict_packages=frozenset(parsed.packages or []),
    )
    try:
        plan = compute_plan(intent)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    if not plan.jobs or not plan.jobs[0].commands:
        print("Nothing to build. No packages have changed since last release.")
        print("Use --rebuild-all to build all packages.")
        return

    print("Building packages:\n")
    execute_plan(plan, hooks=None)
    print("\nDone.")

"""The ``uvr build`` command."""

from __future__ import annotations

import argparse

from diny import provide

from ._args import CommandArgs, compute_plan_or_exit
from ..intents.build import BuildIntent
from ..execute import execute_plan
from ..types import PlanParams


class BuildArgs(CommandArgs):
    """Typed arguments for ``uvr build``."""

    all_packages: bool = False
    packages: list[str] | None = None


def cmd_build(args: argparse.Namespace) -> None:
    """Build changed workspace packages locally."""
    parsed = BuildArgs.from_namespace(args)

    params = PlanParams(
        all_packages=parsed.all_packages,
        packages=frozenset(parsed.packages or []),
    )
    intent = BuildIntent()
    with provide(params):
        plan = compute_plan_or_exit(intent)

    if not plan.jobs or not plan.jobs[0].commands:
        print("Nothing to build. No packages have changed since last release.")
        print("Use --all-packages to build all packages.")
        return

    print("Building packages:\n")
    execute_plan(plan, hooks=None)
    print("\nDone.")

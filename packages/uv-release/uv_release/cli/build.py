"""The ``uvr build`` command."""

from __future__ import annotations

import argparse

from ._args import CommandArgs
from ..execute import execute_plan
from ..plan.planner import create_plan
from ..types import PlanParams


class BuildArgs(CommandArgs):
    """Typed arguments for ``uvr build``."""

    rebuild_all: bool = False
    packages: list[str] | None = None


def cmd_build(args: argparse.Namespace) -> None:
    """Build changed workspace packages locally."""
    parsed = BuildArgs.from_namespace(args)

    params = PlanParams(
        rebuild_all=parsed.rebuild_all,
        restrict_packages=frozenset(parsed.packages or []),
        dev_release=True,
        skip=frozenset({"release", "publish", "bump"}),
    )
    plan = create_plan(params)

    if not plan.releases:
        print("Nothing to build. No packages have changed since last release.")
        print("Use --rebuild-all to build all packages.")
        return

    nw = max(len(n) for n in plan.releases)
    print(f"Building {len(plan.releases)} package(s):\n")
    for name, release in sorted(plan.releases.items()):
        print(f"  {name.ljust(nw)}  {release.release_version.raw}")
    print()

    execute_plan(plan, hooks=None)

    print(f"\nBuilt {len(plan.releases)} package(s) into dist/")

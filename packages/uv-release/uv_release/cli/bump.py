"""The ``uvr bump`` command."""

from __future__ import annotations

import argparse

from ._args import CommandArgs
from .display import print_bump_summary
from ..execute import execute_plan
from ..plan.planner import create_plan
from ..types import BumpType, PlanParams


class BumpArgs(CommandArgs):
    """Typed arguments for ``uvr bump``."""

    bump_all: bool = False
    packages: list[str] | None = None
    force: bool = False
    no_pin: bool = False  # CLI uses negative flag, inverted for PlanParams.pin
    bump_type: str = ""


def cmd_bump(args: argparse.Namespace) -> None:
    """Bump package versions in the workspace."""
    parsed = BumpArgs.from_namespace(args)

    if not parsed.bump_type:
        print("ERROR: Specify a bump type: --minor, --major, --patch, etc.")
        return

    bump_type = BumpType(parsed.bump_type)

    # Map CLI flags to PlanParams
    rebuild_packages = frozenset(parsed.packages or [])
    params = PlanParams(
        rebuild_all=parsed.bump_all or not rebuild_packages,
        rebuild=rebuild_packages,
        restrict_packages=rebuild_packages,
        dev_release=True,
        skip=frozenset({"build", "release", "publish"}),
        bump_type=bump_type,
        pin=not parsed.no_pin,
        tag=False,
        push=False,
    )
    plan = create_plan(params)

    if not plan.releases:
        print("No packages to bump.")
        return

    # Show what will happen
    results = [
        (name, release.package.version.raw, release.next_version.raw)
        for name, release in sorted(plan.releases.items())
    ]
    print()
    print_bump_summary(results)
    print()

    execute_plan(plan, hooks=None)

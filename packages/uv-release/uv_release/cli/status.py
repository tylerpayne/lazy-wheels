"""The ``uvr status`` command."""

from __future__ import annotations

import argparse
import sys

from ._args import CommandArgs
from ..intents.status import StatusIntent
from ..planner import compute_plan
from ..types import PlanParams


class StatusArgs(CommandArgs):
    """Typed arguments for ``uvr status``."""

    all_packages: bool = False
    packages: list[str] | None = None


def cmd_status(args: argparse.Namespace) -> None:
    """Show workspace package status. Read-only, never modifies disk."""
    parsed = StatusArgs.from_namespace(args)

    params = PlanParams(
        all_packages=parsed.all_packages,
        packages=frozenset(parsed.packages or []),
    )
    intent = StatusIntent()
    try:
        plan = compute_plan(intent, params=params)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    changed_map = {c.package.name: c for c in plan.changes}

    workspace = plan.metadata.workspace
    assert workspace is not None

    if not workspace.packages:
        print("No packages found.")
        return

    print()
    print("Packages")
    print("--------")

    nw = max(len(n) for n in workspace.packages)
    for name, pkg in sorted(workspace.packages.items()):
        if name in changed_map:
            reason = changed_map[name].reason or "changed"
            print(f"  {reason.ljust(16)}  {name.ljust(nw)}  {pkg.version.raw}")
        else:
            print(f"  {'unchanged'.ljust(16)}  {name.ljust(nw)}  {pkg.version.raw}")

    if not changed_map:
        print()
        print("Nothing changed since last release. Use --all-packages to force.")

    print()

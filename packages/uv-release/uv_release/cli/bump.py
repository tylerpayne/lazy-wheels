"""The ``uvr bump`` command."""

from __future__ import annotations

import argparse
import sys

from ._args import CommandArgs
from ._display import print_bump_summary
from ..intents.bump import BumpIntent
from ..intents.shared.versioning import compute_bumped_version
from ..planner import compute_plan
from ..execute import execute_plan
from ..types import BumpType


class BumpArgs(CommandArgs):
    """Typed arguments for ``uvr bump``."""

    bump_all: bool = False
    packages: list[str] | None = None
    force: bool = False
    no_pin: bool = False  # CLI uses negative flag, inverted for BumpIntent.pin
    bump_type: str = ""


def cmd_bump(args: argparse.Namespace) -> None:
    """Bump package versions in the workspace."""
    parsed = BumpArgs.from_namespace(args)

    if not parsed.bump_type:
        print(
            "ERROR: Specify a bump type: --minor, --major, --patch, etc.",
            file=sys.stderr,
        )
        sys.exit(1)

    bump_type = BumpType(parsed.bump_type)

    intent = BumpIntent(
        bump_type=bump_type,
        packages=frozenset(parsed.packages or []),
        pin=not parsed.no_pin,
        commit=True,
    )
    try:
        plan = compute_plan(intent)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    if not plan.jobs or not plan.jobs[0].commands:
        print("No packages to bump.")
        return

    # Display what will happen using workspace from plan metadata
    workspace = plan.metadata.workspace
    assert workspace is not None
    results = []
    targets = intent.packages or frozenset(workspace.packages.keys())
    for name in sorted(targets):
        if name not in workspace.packages:
            continue
        pkg = workspace.packages[name]
        bumped = compute_bumped_version(pkg.version, bump_type)
        results.append((name, pkg.version.raw, bumped.raw))

    print()
    print_bump_summary(results)
    print()

    execute_plan(plan, hooks=None)
